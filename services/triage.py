# services/triage.py

"""
Battery Triage Map - triage.py

역할:
- rule.py에서 지정폐기물로 분류되지 않은 배터리만 평가한다.
- 연식, 주행거리, 배터리 용량, 화학계를 기반으로 예비 점수를 계산한다.
- KOMIR 리튬/니켈/코발트 가격 점수를 재활용 회수 가치 산정에 반영한다.
- Green / Yellow / Orange / Gray 등급을 부여한다.
- 재사용/재활용은 법적 최종 판단이 아니라 예비 추천으로만 출력한다.

주의:
- 이 모듈은 SOH 실측 모델이 아니다.
- 처리업체의 실제 진단 전까지 법적 지위와 최종 처리경로는 확정하지 않는다.
- KOMIR API 호출은 이 파일에서 직접 수행하지 않는다.
  외부 모듈에서 API 호출 성공 시 mineral_price_scores로 넘기고,
  실패하거나 값이 없으면 이 파일의 기본값을 사용한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


VALID_CHEMISTRIES = {"NCM", "LFP", "UNKNOWN"}

# API 실패 또는 미연동 시 사용할 기본 광물 가격 점수.
# 원본 가격이 아니라 0~100으로 정규화된 MVP용 회수 가치 보정 점수다.
DEFAULT_MINERAL_PRICE_SCORES = {
    "LITHIUM": 65.0,
    "NICKEL": 70.0,
    "COBALT": 60.0,
}


def _clip(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    """점수가 지정 범위를 벗어나지 않도록 제한한다."""
    return max(min_value, min(value, max_value))


def _normalize_chemistry(chemistry: Optional[str]) -> str:
    """화학계 입력값을 NCM / LFP / UNKNOWN 중 하나로 정리한다."""
    if chemistry is None:
        return "UNKNOWN"

    normalized = chemistry.strip().upper()

    if normalized in VALID_CHEMISTRIES:
        return normalized

    return "UNKNOWN"


def _is_valid_vehicle_year(vehicle_year: Optional[int], current_year: int) -> bool:
    """차량 연식이 계산 가능한 값인지 확인한다."""
    if vehicle_year is None:
        return False

    try:
        year = int(vehicle_year)
    except (TypeError, ValueError):
        return False

    return 1990 <= year <= current_year


def _is_valid_mileage(mileage_km: Optional[float]) -> bool:
    """주행거리가 계산 가능한 값인지 확인한다."""
    if mileage_km is None:
        return False

    try:
        mileage = float(mileage_km)
    except (TypeError, ValueError):
        return False

    return mileage >= 0


def _is_valid_capacity(capacity_kwh: Optional[float]) -> bool:
    """배터리 용량이 계산 가능한 값인지 확인한다."""
    if capacity_kwh is None:
        return False

    try:
        capacity = float(capacity_kwh)
    except (TypeError, ValueError):
        return False

    return capacity > 0


def _calculate_data_confidence(
    vehicle_year: Optional[int],
    mileage_km: Optional[float],
    capacity_kwh: Optional[float],
    chemistry: str,
    manufacturer: Optional[str],
    model_name: Optional[str],
    current_year: int,
) -> float:
    """
    입력 데이터 신뢰도를 계산한다.

    여기서 신뢰도는 모델 정확도가 아니라,
    필요한 입력값이 얼마나 잘 채워졌는지를 나타내는 입력 완성도 점수다.
    """

    score = 0.0

    if _is_valid_vehicle_year(vehicle_year, current_year):
        score += 0.25

    if _is_valid_mileage(mileage_km):
        score += 0.25

    if _is_valid_capacity(capacity_kwh):
        score += 0.20

    if chemistry in {"NCM", "LFP"}:
        score += 0.20

    if manufacturer and model_name:
        score += 0.10

    return round(_clip(score, 0.0, 1.0), 2)


def _calculate_soh_proxy_score(
    vehicle_year: Optional[int],
    mileage_km: Optional[float],
    chemistry: str,
    current_year: int,
) -> tuple[float, list[str]]:
    """
    SOH Proxy 점수를 계산한다.

    계산식:
    SOH Proxy = 100
        - 캘린더 열화 감점(연식)
        - 사이클 열화 감점(주행거리)
        - 사용강도 감점(연평균 주행거리)
        + 화학계 안정성 보정(소폭)

    이 값은 실측 SOH가 아니라 폐차장 입력값 기반 예비 추정치다.
    """

    reason_codes = []
    age_years: Optional[int] = None
    mileage: Optional[float] = None

    # 1. 캘린더 열화 감점: 차량이 오래될수록 감점
    if _is_valid_vehicle_year(vehicle_year, current_year):
        age_years = max(current_year - int(vehicle_year), 0)
        age_penalty = min(age_years * 2.8, 28.0)

        if age_years <= 3:
            reason_codes.append("AGE_LOW")
        elif age_years <= 7:
            reason_codes.append("AGE_MODERATE")
        else:
            reason_codes.append("AGE_HIGH")
    else:
        age_penalty = 28.0
        reason_codes.append("VEHICLE_YEAR_MISSING_OR_INVALID")

    # 2. 사이클 열화 감점: 누적 주행거리가 많을수록 감점
    if _is_valid_mileage(mileage_km):
        mileage = float(mileage_km)
        mileage_penalty = min((mileage / 10_000) * 1.5, 27.0)

        if mileage < 50_000:
            reason_codes.append("MILEAGE_LOW")
        elif mileage < 120_000:
            reason_codes.append("MILEAGE_MODERATE")
        else:
            reason_codes.append("MILEAGE_HIGH")
    else:
        mileage_penalty = 27.0
        reason_codes.append("MILEAGE_MISSING_OR_INVALID")

    # 3. 사용강도 감점: 같은 주행거리라도 짧은 기간에 많이 운행했으면 감점
    if age_years is not None and mileage is not None:
        annual_mileage = mileage / max(age_years, 1)

        if annual_mileage >= 25_000:
            usage_intensity_penalty = 8.0
            reason_codes.append("USAGE_INTENSITY_HIGH")
        elif annual_mileage >= 18_000:
            usage_intensity_penalty = 5.0
            reason_codes.append("USAGE_INTENSITY_MODERATE_HIGH")
        elif annual_mileage >= 12_000:
            usage_intensity_penalty = 2.0
            reason_codes.append("USAGE_INTENSITY_MODERATE")
        else:
            usage_intensity_penalty = 0.0
            reason_codes.append("USAGE_INTENSITY_LOW")
    else:
        usage_intensity_penalty = 0.0
        reason_codes.append("USAGE_INTENSITY_UNKNOWN")

    # 4. 화학계 보정: 처리경로를 고정하지 않기 위해 아주 작게만 반영
    if chemistry == "LFP":
        chemistry_adjustment = 2.0
        reason_codes.append("SOH_CHEMISTRY_LFP_SMALL_BONUS")
    elif chemistry == "NCM":
        chemistry_adjustment = 0.0
        reason_codes.append("SOH_CHEMISTRY_NCM_NEUTRAL")
    else:
        chemistry_adjustment = -2.0
        reason_codes.append("SOH_CHEMISTRY_UNKNOWN_SMALL_PENALTY")

    soh_proxy_score = (
        100.0
        - age_penalty
        - mileage_penalty
        - usage_intensity_penalty
        + chemistry_adjustment
    )
    soh_proxy_score = _clip(soh_proxy_score)

    return round(soh_proxy_score, 1), reason_codes


def _calculate_capacity_score(capacity_kwh: Optional[float]) -> tuple[float, list[str]]:
    """
    배터리 용량 점수를 계산한다.

    용량은 배터리 상태라기보다 활용성과 잔존가치에 영향을 주는 값이다.
    """

    reason_codes = []

    if not _is_valid_capacity(capacity_kwh):
        reason_codes.append("CAPACITY_MISSING_OR_INVALID")
        return 50.0, reason_codes

    capacity = float(capacity_kwh)

    if capacity >= 80:
        reason_codes.append("CAPACITY_VERY_HIGH")
        return 100.0, reason_codes

    if capacity >= 60:
        reason_codes.append("CAPACITY_HIGH")
        return 85.0, reason_codes

    if capacity >= 40:
        reason_codes.append("CAPACITY_MODERATE")
        return 70.0, reason_codes

    reason_codes.append("CAPACITY_LOW")
    return 55.0, reason_codes


def _calculate_chemistry_reuse_score(chemistry: str) -> tuple[float, list[str]]:
    """
    화학계별 재사용 보정 점수를 계산한다.

    화학계는 고정 처리경로가 아니라 점수 보정과 수거 루트에만 사용한다.
    재활용 가치는 별도의 mineral_value_score에서 계산한다.
    """

    if chemistry == "NCM":
        return 75.0, ["CHEMISTRY_NCM"]

    if chemistry == "LFP":
        return 80.0, ["CHEMISTRY_LFP"]

    return 60.0, ["CHEMISTRY_UNKNOWN"]


def _normalize_mineral_price_scores(
    mineral_price_scores: Optional[dict[str, float]],
    mineral_price_source: Optional[str],
) -> tuple[dict[str, float], str, list[str]]:
    """
    외부에서 받은 광물 가격 점수를 정리한다.

    mineral_price_scores는 원본 가격이 아니라 0~100으로 정규화된 점수여야 한다.
    값이 없거나 일부 광물이 누락되면 DEFAULT_MINERAL_PRICE_SCORES를 사용한다.
    """

    reason_codes: list[str] = []

    if not mineral_price_scores:
        reason_codes.append("KOMIR_PRICE_FALLBACK_USED")
        return DEFAULT_MINERAL_PRICE_SCORES.copy(), "fallback_default", reason_codes

    normalized_scores = DEFAULT_MINERAL_PRICE_SCORES.copy()
    used_fallback = False

    for mineral in ["LITHIUM", "NICKEL", "COBALT"]:
        raw_value = mineral_price_scores.get(mineral)
        if raw_value is None:
            used_fallback = True
            continue

        try:
            normalized_scores[mineral] = round(_clip(float(raw_value)), 1)
        except (TypeError, ValueError):
            used_fallback = True

    if used_fallback:
        reason_codes.append("KOMIR_PRICE_PARTIAL_FALLBACK_USED")
        source = mineral_price_source or "external_partial_fallback"
    else:
        reason_codes.append("KOMIR_PRICE_EXTERNAL_USED")
        source = mineral_price_source or "external"

    return normalized_scores, source, reason_codes


def _calculate_mineral_value_score(
    chemistry: str,
    mineral_price_scores: dict[str, float],
) -> tuple[float, list[str]]:
    """
    화학계별 광물 회수 가치 점수를 계산한다.

    - NCM: 리튬, 니켈, 코발트 가격 점수를 모두 반영한다.
    - LFP: 니켈·코발트가 없으므로 리튬 중심으로 보수적으로 반영한다.
    - UNKNOWN: 화학계 확인 전이므로 중립 점수로 둔다.
    """

    lithium_score = mineral_price_scores["LITHIUM"]
    nickel_score = mineral_price_scores["NICKEL"]
    cobalt_score = mineral_price_scores["COBALT"]

    if chemistry == "NCM":
        score = lithium_score * 0.25 + nickel_score * 0.50 + cobalt_score * 0.25
        return round(_clip(score), 1), ["MINERAL_VALUE_NCM"]

    if chemistry == "LFP":
        conservative_base_score = 40.0
        score = lithium_score * 0.70 + conservative_base_score * 0.30
        return round(_clip(score), 1), ["MINERAL_VALUE_LFP"]

    return 50.0, ["MINERAL_VALUE_UNKNOWN_CHEMISTRY"]


def _assign_grade(
    reuse_score: float,
    recycle_score: float,
    soh_proxy_score: float,
    data_confidence: float,
) -> tuple[str, str]:
    """
    재사용 점수, 재활용 점수, SOH Proxy, 입력 신뢰도를 기준으로 등급을 결정한다.
    """

    if data_confidence < 0.60:
        return "Gray", "diagnosis_required"

    if reuse_score >= 75 and soh_proxy_score >= 75:
        return "Green", "reuse_candidate"

    if recycle_score >= 70 and reuse_score < 65:
        return "Orange", "recycle_candidate"

    if reuse_score >= 60:
        return "Yellow", "reuse_or_recycle_after_diagnosis"

    if recycle_score >= 55:
        return "Orange", "recycle_candidate"

    return "Gray", "diagnosis_required"


def _required_diagnostic_capability(grade: str) -> str:
    """
    등급별 필요한 처리업체 진단역량을 반환한다.

    Green: 재사용 가능성이 높은 후보 → basic 이상 업체
    Yellow: 재사용/재활용 판단 전 추가 확인 필요 → basic 이상 업체
    Orange: 재활용 후보 → basic 이상 업체
    Gray: 데이터 부족/판단 보류 → kolas 업체
    """

    if grade == "Gray":
        return "kolas"

    return "basic"


def _collection_route(chemistry: str) -> str:
    """화학계별 수거 루트를 반환한다."""
    if chemistry == "NCM":
        return "NCM 전용 수거 루트"

    if chemistry == "LFP":
        return "LFP 전용 수거 루트"

    return "화학계 확인 필요 루트"


def evaluate_battery(
    vehicle_year: Optional[int],
    mileage_km: Optional[float],
    capacity_kwh: Optional[float],
    chemistry: str = "UNKNOWN",
    manufacturer: Optional[str] = None,
    model_name: Optional[str] = None,
    battery_count: int = 1,
    current_year: Optional[int] = None,
    mineral_price_scores: Optional[dict[str, float]] = None,
    mineral_price_source: Optional[str] = None,
) -> dict[str, Any]:
    """
    배터리 1개 또는 동일 조건 배터리 묶음에 대한 예비 평가를 수행한다.

    이 함수는 실측 진단이 아니라 입력값 기반 예비 추정이다.
    mineral_price_scores는 외부 API 또는 전처리 파일에서 계산한 0~100 점수다.
    값이 없으면 DEFAULT_MINERAL_PRICE_SCORES를 사용한다.
    """

    if current_year is None:
        current_year = datetime.now().year

    chemistry_normalized = _normalize_chemistry(chemistry)

    reason_codes: list[str] = []

    # 1. 입력 데이터 신뢰도 계산
    data_confidence = _calculate_data_confidence(
        vehicle_year=vehicle_year,
        mileage_km=mileage_km,
        capacity_kwh=capacity_kwh,
        chemistry=chemistry_normalized,
        manufacturer=manufacturer,
        model_name=model_name,
        current_year=current_year,
    )

    # 2. SOH Proxy 계산
    soh_proxy_score, soh_reasons = _calculate_soh_proxy_score(
        vehicle_year=vehicle_year,
        mileage_km=mileage_km,
        chemistry=chemistry_normalized,
        current_year=current_year,
    )
    reason_codes.extend(soh_reasons)

    # 3. 용량 점수 계산
    capacity_score, capacity_reasons = _calculate_capacity_score(capacity_kwh)
    reason_codes.extend(capacity_reasons)

    # 4. 화학계별 재사용 보정 점수 계산
    chemistry_reuse_score, chemistry_reasons = _calculate_chemistry_reuse_score(
        chemistry_normalized
    )
    reason_codes.extend(chemistry_reasons)

    # 5. KOMIR 광물 가격 점수 정리 및 광물 회수 가치 점수 계산
    normalized_mineral_scores, mineral_price_source_used, mineral_source_reasons = (
        _normalize_mineral_price_scores(
            mineral_price_scores=mineral_price_scores,
            mineral_price_source=mineral_price_source,
        )
    )
    reason_codes.extend(mineral_source_reasons)

    mineral_value_score, mineral_value_reasons = _calculate_mineral_value_score(
        chemistry=chemistry_normalized,
        mineral_price_scores=normalized_mineral_scores,
    )
    reason_codes.extend(mineral_value_reasons)

    # 6. 재사용 점수 계산
    # data_confidence는 0~1 값이므로 100점 척도로 변환한 뒤 반영한다.
    reuse_score = (
        soh_proxy_score * 0.70
        + capacity_score * 0.15
        + chemistry_reuse_score * 0.10
        + (data_confidence * 100.0) * 0.05
    )

    # 7. 재활용 점수 계산
    # 기존 chemistry_recycle_score 고정값 대신 KOMIR 기반 mineral_value_score를 반영한다.
    degradation_score = 100.0 - soh_proxy_score

    recycle_score = (
        capacity_score * 0.35
        + mineral_value_score * 0.45
        + degradation_score * 0.20
    )

    reuse_score = round(_clip(reuse_score), 1)
    recycle_score = round(_clip(recycle_score), 1)

    # 8. 등급과 예비 처리 방향 결정
    grade, recommended_path = _assign_grade(
        reuse_score=reuse_score,
        recycle_score=recycle_score,
        soh_proxy_score=soh_proxy_score,
        data_confidence=data_confidence,
    )

    # 9. 판단 코드 추가
    if data_confidence < 0.60:
        reason_codes.append("DATA_CONFIDENCE_LOW")

    if grade == "Green":
        reason_codes.append("REUSE_SCORE_HIGH")
    elif grade == "Yellow":
        reason_codes.append("REUSE_SCORE_MODERATE_DIAGNOSIS_REQUIRED")
    elif grade == "Orange":
        reason_codes.append("RECYCLE_SCORE_VALID_MINERAL_VALUE_APPLIED")
    else:
        reason_codes.append("DIAGNOSIS_REQUIRED")

    # 10. 묶음 요약값 계산: 개별 점수는 유지하고, 묶음 규모만 참고값으로 제공한다.
    try:
        battery_count_valid = max(int(battery_count), 1)
    except (TypeError, ValueError):
        battery_count_valid = 1
        reason_codes.append("BATTERY_COUNT_INVALID_DEFAULTED_TO_1")

    if _is_valid_capacity(capacity_kwh):
        total_capacity_kwh = round(float(capacity_kwh) * battery_count_valid, 1)
    else:
        total_capacity_kwh = None

    # 11. 최종 결과 반환
    return {
        "status": "triaged",
        "result_type": "preliminary_estimate",

        "input_summary": {
            "manufacturer": manufacturer,
            "model_name": model_name,
            "vehicle_year": vehicle_year,
            "mileage_km": mileage_km,
            "capacity_kwh": capacity_kwh,
            "chemistry": chemistry_normalized,
            "battery_count": battery_count_valid,
            "total_capacity_kwh": total_capacity_kwh,
        },

        "soh_proxy_score": soh_proxy_score,
        "capacity_score": capacity_score,
        "mineral_value_score": mineral_value_score,
        "reuse_score": reuse_score,
        "recycle_score": recycle_score,

        "grade": grade,
        "recommended_path": recommended_path,
        "required_diagnostic_capability": _required_diagnostic_capability(grade),
        "collection_route": _collection_route(chemistry_normalized),

        "data_confidence": data_confidence,
        "mineral_price_source": mineral_price_source_used,
        "mineral_price_scores_used": normalized_mineral_scores,
        "reason_codes": reason_codes,
    }
