"""
services/matching.py
처리업체 매칭 모듈  [데이터 엔지니어 로직 이식]

triage.py(evaluate_battery)의 예비 평가 결과를 받아,
1차 필터링 → 2차 점수화(AHP/TOPSIS) → 처리업체 1~3순위를 추천한다.

출처: matching.ipynb (Colab 검증 완료) — 로직 수정 없이 이식.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd


DIAGNOSTIC_RANK = {
    "none": 0,
    "basic": 1,
    "kolas": 2,
}


def _split_values(value) -> list[str]:
    """'NCM,LFP' 같은 문자열을 리스트로 변환한다."""
    if pd.isna(value):
        return []

    return [v.strip() for v in str(value).split(",")]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """위도/경도를 이용해 두 지점 사이의 거리를 km 단위로 계산한다."""
    radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_km * c


def _is_diagnostic_sufficient(company_capability, required_capability) -> bool:
    """업체 진단역량이 필요한 수준 이상인지 확인한다."""
    company_rank = DIAGNOSTIC_RANK.get(company_capability, -1)
    required_rank = DIAGNOSTIC_RANK.get(required_capability, 0)

    return company_rank >= required_rank


def _expected_process_type(recommended_path) -> Optional[str]:
    """triage.py의 예비 처리방향에 따라 우선적으로 필요한 처리유형을 정한다."""

    if recommended_path == "reuse_candidate":
        return "reuse"

    if recommended_path == "reuse_or_recycle_after_diagnosis":
        return "reuse"

    if recommended_path == "recycle_candidate":
        return "recycle"

    if recommended_path == "diagnosis_required":
        return "reuse"

    if recommended_path == "designated_waste":
        return "designated_waste"

    return None


def _filter_companies(
    companies_df,
    grade,
    chemistry,
    recommended_path,
    required_diagnostic_capability,
    battery_count,
):
    """매칭 1단계: 조건을 만족하지 못하는 업체를 제거한다."""

    expected_process_type = _expected_process_type(recommended_path)

    filtered_rows = []

    for _, row in companies_df.iterrows():
        # 1. 운영 중인지 확인
        if not bool(row["is_active"]):
            continue

        # 2. 화학계 처리 가능 여부 확인 (UNKNOWN이면 화학계 필터 미적용)
        accepted_chemistry = _split_values(row["accepted_chemistry"])
        if chemistry != "UNKNOWN":
            if chemistry not in accepted_chemistry and "UNKNOWN" not in accepted_chemistry:
                continue

        # 3. 등급 처리 가능 여부 확인
        accepted_grade = _split_values(row["accepted_grade"])
        if grade not in accepted_grade:
            continue

        # 4. 진단역량 확인
        if not _is_diagnostic_sufficient(
            row["diagnostic_capability"],
            required_diagnostic_capability,
        ):
            continue

        # 5. 처리유형 확인
        if expected_process_type is not None and row["process_type"] != expected_process_type:
            continue

        # 6. 처리 가능 수량 확인
        if row["monthly_capacity_count"] < battery_count:
            continue

        filtered_rows.append(row)

    if not filtered_rows:
        return pd.DataFrame(columns=companies_df.columns)

    return pd.DataFrame(filtered_rows).reset_index(drop=True)


def _calculate_company_features(
    candidates_df,
    origin_latitude,
    origin_longitude,
    battery_count,
    chemistry,
    recommended_path,
):
    """매칭 2단계: 후보 업체별 평가 점수를 계산한다."""

    df = candidates_df.copy()

    # 거리 계산
    df["distance_km"] = df.apply(
        lambda row: _haversine_km(
            origin_latitude,
            origin_longitude,
            row["latitude"],
            row["longitude"],
        ),
        axis=1,
    )

    # 거리 점수: 가까울수록 높게
    max_distance = df["distance_km"].max()
    min_distance = df["distance_km"].min()

    if max_distance == min_distance:
        df["distance_score"] = 100.0
    else:
        df["distance_score"] = (
            (max_distance - df["distance_km"])
            / (max_distance - min_distance)
            * 100
        )

    # 진단역량 점수
    df["diagnostic_score"] = df["diagnostic_capability"].map({
        "none": 40.0,
        "basic": 75.0,
        "kolas": 100.0,
    })

    # 처리용량 점수: 배터리 수량 대비 여유가 클수록 높게
    df["capacity_margin"] = df["monthly_capacity_count"] - battery_count

    max_margin = df["capacity_margin"].max()
    min_margin = df["capacity_margin"].min()

    if max_margin == min_margin:
        df["capacity_score"] = 100.0
    else:
        df["capacity_score"] = (
            (df["capacity_margin"] - min_margin)
            / (max_margin - min_margin)
            * 100
        )

    # 허가 적합성 점수
    expected_process_type = _expected_process_type(recommended_path)
    df["license_score"] = df["process_type"].apply(
        lambda x: 100.0 if x == expected_process_type else 60.0
    )

    # 화학계 적합성 점수
    df["chemistry_score"] = df["accepted_chemistry"].apply(
        lambda value: 100.0 if chemistry in _split_values(value) else 70.0
    )

    return df


def _apply_topsis(scored_df, weights=None):
    """
    AHP/TOPSIS 방식 중 TOPSIS 점수화 부분.
    AHP: 기준별 가중치를 정한다.
    TOPSIS: 이상적인 업체에 가장 가까운 업체를 높은 점수로 정렬한다.
    """

    if weights is None:
        weights = {
            "distance_score": 0.35,
            "diagnostic_score": 0.25,
            "capacity_score": 0.20,
            "license_score": 0.10,
            "chemistry_score": 0.10,
        }

    criteria = list(weights.keys())

    matrix = scored_df[criteria].astype(float).to_numpy()

    # 벡터 정규화
    norm = np.sqrt((matrix ** 2).sum(axis=0))
    norm[norm == 0] = 1

    normalized = matrix / norm

    weight_vector = np.array([weights[c] for c in criteria])
    weighted = normalized * weight_vector

    ideal_best = weighted.max(axis=0)
    ideal_worst = weighted.min(axis=0)

    distance_to_best = np.sqrt(((weighted - ideal_best) ** 2).sum(axis=1))
    distance_to_worst = np.sqrt(((weighted - ideal_worst) ** 2).sum(axis=1))

    denominator = distance_to_best + distance_to_worst

    # 후보가 1개뿐이거나 모든 점수가 같으면 100점 처리
    closeness = np.where(
        denominator == 0,
        1.0,
        distance_to_worst / denominator,
    )

    scored_df = scored_df.copy()
    scored_df["total_score"] = np.round(closeness * 100, 1)

    return scored_df.sort_values("total_score", ascending=False).reset_index(drop=True)


def match_companies(
    triage_result,
    companies_df,
    origin_latitude,
    origin_longitude,
    max_results=3,
) -> dict[str, Any]:
    """triage.py 결과를 바탕으로 처리업체 1~3순위를 추천한다."""

    grade = triage_result["grade"]
    recommended_path = triage_result["recommended_path"]
    chemistry = triage_result["input_summary"]["chemistry"]
    battery_count = triage_result["input_summary"].get("battery_count", 1)
    capacity_kwh = triage_result["input_summary"].get("capacity_kwh", None)
    required_diagnostic_capability = triage_result["required_diagnostic_capability"]

    # 1. 조건 필터링
    candidates_df = _filter_companies(
        companies_df=companies_df,
        grade=grade,
        chemistry=chemistry,
        recommended_path=recommended_path,
        required_diagnostic_capability=required_diagnostic_capability,
        battery_count=battery_count,
    )

    if candidates_df.empty:
        return {
            "status": "no_match",
            "input_summary": {
                "grade": grade,
                "recommended_path": recommended_path,
                "chemistry": chemistry,
                "battery_count": battery_count,
                "capacity_kwh": capacity_kwh,
                "required_diagnostic_capability": required_diagnostic_capability,
            },
            "matched_companies": [],
        }

    # 2. 후보별 점수 계산
    scored_df = _calculate_company_features(
        candidates_df=candidates_df,
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        battery_count=battery_count,
        chemistry=chemistry,
        recommended_path=recommended_path,
    )

    # 3. TOPSIS 점수 적용
    ranked_df = _apply_topsis(scored_df)

    top_df = ranked_df.head(max_results).copy()
    top_df["rank"] = range(1, len(top_df) + 1)

    matched_companies = []

    for _, row in top_df.iterrows():
        matched_companies.append({
            "rank": int(row["rank"]),
            "company_id": row["company_id"],
            "company_name": row["company_name"],
            "address": row["address"],
            "region": row["region"],
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "distance_km": round(float(row["distance_km"]), 1),
            "total_score": float(row["total_score"]),
            "license_type": row["license_type"],
            "process_type": row["process_type"],
            "diagnostic_capability": row["diagnostic_capability"],
            "monthly_capacity_count": int(row["monthly_capacity_count"]),
            "score_detail": {
                "distance_score": round(float(row["distance_score"]), 1),
                "diagnostic_score": round(float(row["diagnostic_score"]), 1),
                "capacity_score": round(float(row["capacity_score"]), 1),
                "license_score": round(float(row["license_score"]), 1),
                "chemistry_score": round(float(row["chemistry_score"]), 1),
            }
        })

    return {
        "status": "matched",
        "input_summary": {
            "grade": grade,
            "recommended_path": recommended_path,
            "chemistry": chemistry,
            "battery_count": battery_count,
            "capacity_kwh": capacity_kwh,
            "required_diagnostic_capability": required_diagnostic_capability,
            "origin_latitude": origin_latitude,
            "origin_longitude": origin_longitude,
        },
        "matched_companies": matched_companies,
    }
