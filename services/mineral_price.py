# services/mineral_price.py

"""
Battery Triage Map - mineral_price.py

역할:
- KOMIR(한국광해광업공단) 리튬/니켈/코발트 가격예측 OpenAPI를 호출한다.
- API 호출이 실패하거나 환경변수가 없으면 기본 점수로 안전하게 대체한다.
- triage.py / triage_v2.py에는 원본 가격이 아니라 0~100 정규화 점수만 넘긴다.

사용 방식:
1) 환경변수에 API endpoint와 service key를 설정한다.
   - KOMIR_LITHIUM_API_URL
   - KOMIR_NICKEL_API_URL
   - KOMIR_COBALT_API_URL
   - DATA_GO_KR_SERVICE_KEY

2) app.py 또는 score API에서 아래처럼 사용한다.

   from services.mineral_price import get_mineral_price_inputs
   from services.triage import evaluate_battery

   mineral_inputs = get_mineral_price_inputs()

   result = evaluate_battery(
       vehicle_year=2018,
       mileage_km=160000,
       capacity_kwh=77.4,
       chemistry="NCM",
       mineral_price_scores=mineral_inputs["mineral_price_scores"],
       mineral_price_source=mineral_inputs["mineral_price_source"],
   )

주의:
- 이 파일은 API 실패 시에도 절대 시연이 멈추지 않도록 설계되어 있다.
- 공공데이터포털 자동변환 API의 실제 URL은 활용신청 후 화면에서 복사해 환경변수에 넣는 것을 권장한다.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


# triage_v2.py와 동일한 기본값이다.
# 값은 원본 가격이 아니라 0~100 정규화된 MVP용 광물 회수 가치 점수다.
DEFAULT_MINERAL_PRICE_SCORES: dict[str, float] = {
    "LITHIUM": 65.0,
    "NICKEL": 70.0,
    "COBALT": 60.0,
}

MINERAL_ENV_URLS: dict[str, str] = {
    "LITHIUM": "KOMIR_LITHIUM_API_URL",
    "NICKEL": "KOMIR_NICKEL_API_URL",
    "COBALT": "KOMIR_COBALT_API_URL",
}

SERVICE_KEY_ENV = "DATA_GO_KR_SERVICE_KEY"

# 공공데이터 자동변환 API의 컬럼명이 한글/영문/공백 포함 형태로 달라져도 최대한 읽도록 후보를 넓게 둔다.
PRICE_FIELD_CANDIDATES = [
    "예측가격",
    "예측 가격",
    "가격",
    "price",
    "forecast_price",
    "predicted_price",
    "PREDICTED_PRICE",
]

PERIOD_FIELD_CANDIDATES = [
    "전망기간",
    "전망 기간",
    "기간",
    "연도",
    "year",
    "period",
    "forecast_period",
    "PREDICTED_PERIOD",
]


@dataclass
class MineralFetchResult:
    mineral: str
    score: float
    source: str
    reason: str
    selected_price: Optional[float] = None
    baseline_price: Optional[float] = None
    selected_period: Optional[str] = None
    row_count: int = 0


def _clip(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """점수를 0~100 범위로 제한한다."""
    return max(min_value, min(value, max_value))


def _append_query_params(url: str, params: dict[str, Any]) -> str:
    """기존 URL에 안전하게 쿼리 파라미터를 추가한다."""
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))

    for key, value in params.items():
        if value is not None and key not in query:
            query[key] = str(value)

    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def _request_json(url: str, service_key: Optional[str], timeout: float) -> dict[str, Any]:
    """
    공공데이터 API를 JSON으로 호출한다.

    endpoint에 이미 serviceKey가 붙어 있으면 그대로 두고,
    없으면 DATA_GO_KR_SERVICE_KEY를 추가한다.
    """
    params = {
        "serviceKey": service_key,
        "page": 1,
        "perPage": 1000,
        "returnType": "JSON",
        "_type": "json",
    }
    request_url = _append_query_params(url, params)

    request = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BatteryTriageMap/0.1",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("API 응답이 JSON 형식이 아닙니다.") from exc

    if not isinstance(payload, dict):
        raise ValueError("API 응답 최상위 구조가 dict가 아닙니다.")

    return payload


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """data.go.kr 자동변환 API에서 데이터 행 목록을 추출한다."""
    candidates = [
        payload.get("data"),
        payload.get("items"),
        payload.get("body", {}).get("items") if isinstance(payload.get("body"), dict) else None,
        payload.get("response", {}).get("body", {}).get("items")
        if isinstance(payload.get("response"), dict)
        else None,
    ]

    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
        if isinstance(candidate, dict):
            item = candidate.get("item")
            if isinstance(item, list):
                return [row for row in item if isinstance(row, dict)]
            if isinstance(item, dict):
                return [item]

    # 일부 자동변환 API는 records처럼 다른 키를 쓰는 경우가 있어 마지막으로 list 값을 탐색한다.
    for value in payload.values():
        if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
            return value

    return []


def _parse_number(value: Any) -> Optional[float]:
    """문자열에 쉼표, 단위, 공백이 섞여 있어도 숫자를 추출한다."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    # 예: "12,345.6 USD/t" -> "12345.6"
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _get_first_available(row: dict[str, Any], keys: list[str]) -> Any:
    """후보 키 중 존재하는 첫 값을 반환한다. 대소문자와 공백 차이도 일부 허용한다."""
    normalized_row = {str(k).strip().lower().replace(" ", ""): v for k, v in row.items()}

    for key in keys:
        if key in row:
            return row[key]

        normalized_key = key.strip().lower().replace(" ", "")
        if normalized_key in normalized_row:
            return normalized_row[normalized_key]

    return None


def _period_sort_key(period: Any) -> tuple[int, str]:
    """전망기간에서 연도/숫자를 추출해 최신 기간 선택에 사용한다."""
    text = "" if period is None else str(period)
    numbers = re.findall(r"\d{4}|\d+", text)
    if not numbers:
        return (-1, text)
    return (max(int(n) for n in numbers), text)


def _score_from_prices(selected_price: float, baseline_price: float) -> float:
    """
    원본 가격을 0~100 점수로 변환한다.

    기준가격 대비 비율이 1.0이면 50점, 1.3이면 65점, 2.0이면 100점이다.
    기준가격은 해당 광물 API 응답 가격들의 중앙값을 쓴다.
    """
    if baseline_price <= 0:
        return 50.0

    price_ratio = selected_price / baseline_price
    score = 50.0 + (price_ratio - 1.0) * 50.0
    return round(_clip(score), 1)


def _calculate_score_from_rows(mineral: str, rows: list[dict[str, Any]]) -> MineralFetchResult:
    """API 응답 행 목록에서 선택 가격, 기준 가격, 0~100 점수를 계산한다."""
    parsed_rows: list[tuple[str, float]] = []

    for row in rows:
        price = _parse_number(_get_first_available(row, PRICE_FIELD_CANDIDATES))
        if price is None or price <= 0:
            continue

        period = _get_first_available(row, PERIOD_FIELD_CANDIDATES)
        parsed_rows.append(("" if period is None else str(period), price))

    if not parsed_rows:
        return MineralFetchResult(
            mineral=mineral,
            score=DEFAULT_MINERAL_PRICE_SCORES[mineral],
            source="fallback_default",
            reason="NO_VALID_PRICE_ROWS",
            row_count=len(rows),
        )

    # 최신 전망기간을 선택한다. 기간 해석이 어려워도 문자열 기반 보조 정렬을 수행한다.
    selected_period, selected_price = sorted(parsed_rows, key=lambda item: _period_sort_key(item[0]))[-1]
    baseline_price = statistics.median(price for _, price in parsed_rows)
    score = _score_from_prices(selected_price=selected_price, baseline_price=baseline_price)

    return MineralFetchResult(
        mineral=mineral,
        score=score,
        source="api",
        reason="API_USED",
        selected_price=selected_price,
        baseline_price=baseline_price,
        selected_period=selected_period,
        row_count=len(rows),
    )


def fetch_mineral_score(
    mineral: str,
    api_url: str,
    service_key: Optional[str] = None,
    timeout: float = 3.0,
) -> MineralFetchResult:
    """단일 광물의 API를 호출하고 0~100 점수를 반환한다."""
    mineral = mineral.upper()
    if mineral not in DEFAULT_MINERAL_PRICE_SCORES:
        raise ValueError(f"지원하지 않는 광물입니다: {mineral}")

    try:
        payload = _request_json(api_url, service_key=service_key, timeout=timeout)
        rows = _extract_rows(payload)
        if not rows:
            return MineralFetchResult(
                mineral=mineral,
                score=DEFAULT_MINERAL_PRICE_SCORES[mineral],
                source="fallback_default",
                reason="API_RETURNED_NO_ROWS",
                row_count=0,
            )
        return _calculate_score_from_rows(mineral=mineral, rows=rows)
    except Exception as exc:  # API 실패가 시연 전체 실패로 이어지지 않게 안전하게 fallback한다.
        return MineralFetchResult(
            mineral=mineral,
            score=DEFAULT_MINERAL_PRICE_SCORES[mineral],
            source="fallback_default",
            reason=f"API_ERROR:{type(exc).__name__}",
        )


def get_mineral_price_inputs(
    use_api: bool = True,
    service_key: Optional[str] = None,
    api_urls: Optional[dict[str, str]] = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """
    triage.evaluate_battery()에 바로 넣을 수 있는 광물 가격 입력값을 만든다.

    반환 예시:
    {
        "mineral_price_scores": {"LITHIUM": 65.0, "NICKEL": 70.0, "COBALT": 60.0},
        "mineral_price_source": "api" 또는 "fallback_default" 또는 "api_partial_fallback",
        "mineral_price_details": {...},
    }
    """
    if not use_api:
        return {
            "mineral_price_scores": DEFAULT_MINERAL_PRICE_SCORES.copy(),
            "mineral_price_source": "fallback_default",
            "mineral_price_details": {
                mineral: {
                    "source": "fallback_default",
                    "reason": "API_DISABLED",
                    "score": score,
                }
                for mineral, score in DEFAULT_MINERAL_PRICE_SCORES.items()
            },
        }

    service_key = service_key or os.getenv(SERVICE_KEY_ENV)
    api_urls = api_urls or {
        mineral: os.getenv(env_name, "") for mineral, env_name in MINERAL_ENV_URLS.items()
    }

    results: list[MineralFetchResult] = []

    for mineral in ["LITHIUM", "NICKEL", "COBALT"]:
        api_url = api_urls.get(mineral, "")
        if not api_url:
            results.append(
                MineralFetchResult(
                    mineral=mineral,
                    score=DEFAULT_MINERAL_PRICE_SCORES[mineral],
                    source="fallback_default",
                    reason="API_URL_NOT_CONFIGURED",
                )
            )
            continue

        results.append(
            fetch_mineral_score(
                mineral=mineral,
                api_url=api_url,
                service_key=service_key,
                timeout=timeout,
            )
        )

    scores = {result.mineral: result.score for result in results}
    api_count = sum(1 for result in results if result.source == "api")

    if api_count == 3:
        source = "api"
    elif api_count == 0:
        source = "fallback_default"
    else:
        source = "api_partial_fallback"

    details = {
        result.mineral: {
            "score": result.score,
            "source": result.source,
            "reason": result.reason,
            "selected_price": result.selected_price,
            "baseline_price": result.baseline_price,
            "selected_period": result.selected_period,
            "row_count": result.row_count,
        }
        for result in results
    }

    return {
        "mineral_price_scores": scores,
        "mineral_price_source": source,
        "mineral_price_details": details,
    }


if __name__ == "__main__":
    # 환경변수가 없으면 fallback_default가 출력된다.
    print(json.dumps(get_mineral_price_inputs(), ensure_ascii=False, indent=2))
