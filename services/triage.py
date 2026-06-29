"""
services/triage.py
배터리 예비 평가(가치 판정) 모듈  [데이터 엔지니어 로직 이식]

Rule Engine(rule.py)을 통과한 '정상 평가 대상' 배터리에 대해,
폐차장 등 현장에서 확보 가능한 기본 입력값(연식·주행거리·용량·화학계)으로
잔존가치와 처리방향을 예비 추정한다.

※ 실측 SOH 나 법적 최종 판정이 아니라 입력값 기반 'preliminary_estimate' 이다.
출처: triage.ipynb (Colab 검증 완료) — 로직 수정 없이 이식.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


VALID_CHEMISTRIES = {"NCM", "LFP", "UNKNOWN"}


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
    current_year: int,
) -> tuple[float, list[str]]:
    """
    SOH Proxy 점수를 계산한다.

    계산식:
    SOH Proxy = 100 - 연식 감점 - 주행거리 감점
    """

    reason_codes = []

    # 1. 연식 감점
    if _is_valid_vehicle_year(vehicle_year, current_year):
        age_years = current_year - int(vehicle_year)
        age_penalty = min(age_years * 3.0, 25.0)

        if age_years <= 3:
            reason_codes.append("AGE_LOW")
        elif age_years <= 7:
            reason_codes.append("AGE_MODERATE")
        else:
            reason_codes.append("AGE_HIGH")
    else:
        age_penalty = 25.0
        reason_codes.append("VEHICLE_YEAR_MISSING_OR_INVALID")

    # 2. 주행거리 감점
    if _is_valid_mileage(mileage_km):
        mileage = float(mileage_km)
        mileage_penalty = min((mileage / 10_000) * 1.8, 25.0)

        if mileage < 50_000:
            reason_codes.append("MILEAGE_LOW")
        elif mileage < 120_000:
            reason_codes.append("MILEAGE_MODERATE")
        else:
            reason_codes.append("MILEAGE_HIGH")
    else:
        mileage_penalty = 25.0
        reason_codes.append("MILEAGE_MISSING_OR_INVALID")

    soh_proxy_score = 100.0 - age_penalty - mileage_penalty
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


def _calculate_chemistry_scores(chemistry: str) -> tuple[float, float, list[str]]:
    """
    화학계별 재사용/재활용 보정 점수를 계산한다.

    화학계는 고정 처리경로가 아니라 점수 보정과 수거 루트에만 사용한다.
    """

    if chemistry == "NCM":
        return 75.0, 90.0, ["CHEMISTRY_NCM"]

    if chemistry == "LFP":
        return 80.0, 60.0, ["CHEMISTRY_LFP"]

    return 60.0, 50.0, ["CHEMISTRY_UNKNOWN"]


def _assign_grade(
    reuse_score: float,
    recycle_score: float,
    data_confidence: float,
) -> tuple[str, str]:
    """
    재사용 점수, 재활용 점수, 입력 신뢰도를 기준으로 등급을 결정한다.
    """

    if data_confidence < 0.60:
        return "Gray", "diagnosis_required"

    if reuse_score >= 75:
        return "Green", "reuse_candidate"

    if reuse_score >= 60:
        return "Yellow", "reuse_or_recycle_after_diagnosis"

    if recycle_score >= 55:
        return "Orange", "recycle_candidate"

    return "Gray", "diagnosis_required"


def _required_diagnostic_capability(grade: str) -> str:
    """
    등급별 필요한 처리업체 진단역량을 반환한다.

    Green/Yellow/Gray는 정밀 진단이 필요하다고 보고 kolas를 요구한다.
    Orange는 재활용 후보이므로 basic 이상을 요구한다.
    """

    if grade == "Orange":
        return "basic"

    return "kolas"


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
) -> dict[str, Any]:
    """
    배터리 1개 또는 동일 조건 배터리 묶음에 대한 예비 평가를 수행한다.

    이 함수는 실측 진단이 아니라 입력값 기반 예비 추정이다.
    """

    if current_year is None:
        current_year = datetime.now().year

    chemistry_normalized = _normalize_chemistry(chemistry)

    reason_codes = []

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
        current_year=current_year,
    )
    reason_codes.extend(soh_reasons)

    # 3. 용량 점수 계산
    capacity_score, capacity_reasons = _calculate_capacity_score(capacity_kwh)
    reason_codes.extend(capacity_reasons)

    # 4. 화학계별 보정 점수 계산
    chemistry_reuse_score, chemistry_recycle_score, chemistry_reasons = (
        _calculate_chemistry_scores(chemistry_normalized)
    )
    reason_codes.extend(chemistry_reasons)

    # 5. 재사용 점수 계산
    reuse_score = (
        soh_proxy_score * 0.75
        + capacity_score * 0.15
        + chemistry_reuse_score * 0.10
    )

    # 6. 재활용 점수 계산
    degradation_score = 100.0 - soh_proxy_score

    recycle_score = (
        capacity_score * 0.45
        + chemistry_recycle_score * 0.35
        + degradation_score * 0.20
    )

    reuse_score = round(_clip(reuse_score), 1)
    recycle_score = round(_clip(recycle_score), 1)

    # 7. 등급과 예비 처리 방향 결정
    grade, recommended_path = _assign_grade(
        reuse_score=reuse_score,
        recycle_score=recycle_score,
        data_confidence=data_confidence,
    )

    # 8. 판단 코드 추가
    if data_confidence < 0.60:
        reason_codes.append("DATA_CONFIDENCE_LOW")

    if grade == "Green":
        reason_codes.append("REUSE_SCORE_HIGH")
    elif grade == "Yellow":
        reason_codes.append("REUSE_SCORE_MODERATE")
    elif grade == "Orange":
        reason_codes.append("REUSE_SCORE_LOW_RECYCLE_SCORE_VALID")
    else:
        reason_codes.append("DIAGNOSIS_REQUIRED")

    # 9. 최종 결과 반환
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
            "battery_count": battery_count,
        },

        "soh_proxy_score": soh_proxy_score,
        "reuse_score": reuse_score,
        "recycle_score": recycle_score,

        "grade": grade,
        "recommended_path": recommended_path,
        "required_diagnostic_capability": _required_diagnostic_capability(grade),
        "collection_route": _collection_route(chemistry_normalized),

        "data_confidence": data_confidence,
        "reason_codes": reason_codes,
    }


if __name__ == "__main__":
    # 데엔 검증 테스트 5종 — 노트북 출력과 동일해야 한다 (회귀 기준)
    cases = [
        ("좋은 NCM", dict(vehicle_year=2024, mileage_km=15000, capacity_kwh=77.4, chemistry="NCM", manufacturer="현대자동차", model_name="IONIQ5", current_year=2026)),
        ("중간 NCM", dict(vehicle_year=2020, mileage_km=85000, capacity_kwh=64.0, chemistry="NCM", manufacturer="현대자동차", model_name="IONIQ5", current_year=2026)),
        ("노후 NCM", dict(vehicle_year=2017, mileage_km=180000, capacity_kwh=58.0, chemistry="NCM", manufacturer="기아", model_name="NIRO EV", current_year=2026)),
        ("정보부족", dict(vehicle_year=None, mileage_km=None, capacity_kwh=None, chemistry="UNKNOWN", current_year=2026)),
        ("LFP", dict(vehicle_year=2022, mileage_km=40000, capacity_kwh=58.0, chemistry="LFP", manufacturer="기아", model_name="EV3", current_year=2026)),
    ]
    for name, kw in cases:
        r = evaluate_battery(**kw)
        print(f"{name:8s} → {r['grade']:6s} | reuse={r['reuse_score']} recycle={r['recycle_score']} | {r['recommended_path']}")
