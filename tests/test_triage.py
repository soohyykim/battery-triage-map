"""
tests/test_triage.py
데엔 검증 케이스를 회귀 테스트로 고정한다.

실행:  pytest          (프로젝트 루트에서)
기준:  triage.ipynb / matching.ipynb 실제 출력값
주의:  Handoff 문서 테스트2 기대값은 'Orange' 로 적혀 있으나,
       실제 코드·노트북 출력은 'Yellow' 가 맞다 (reuse_score 70.3 -> 60~75 구간).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.triage import evaluate_battery
from services.matching import match_companies

BASE_DIR = Path(__file__).resolve().parent.parent
COMPANIES_CSV = BASE_DIR / "data" / "companies_mock.csv"


# (이름, 입력, 기대 등급) — current_year 고정해 연도에 흔들리지 않게 한다.
TRIAGE_CASES = [
    ("좋은 NCM", dict(vehicle_year=2024, mileage_km=15000, capacity_kwh=77.4,
                      chemistry="NCM", manufacturer="현대자동차", model_name="IONIQ5",
                      current_year=2026), "Green"),
    ("중간 NCM", dict(vehicle_year=2020, mileage_km=85000, capacity_kwh=64.0,
                      chemistry="NCM", manufacturer="현대자동차", model_name="IONIQ5",
                      current_year=2026), "Yellow"),
    ("노후 NCM", dict(vehicle_year=2017, mileage_km=180000, capacity_kwh=58.0,
                      chemistry="NCM", manufacturer="기아", model_name="NIRO EV",
                      current_year=2026), "Orange"),
    ("정보부족", dict(vehicle_year=None, mileage_km=None, capacity_kwh=None,
                      chemistry="UNKNOWN", current_year=2026), "Gray"),
    ("LFP", dict(vehicle_year=2022, mileage_km=40000, capacity_kwh=58.0,
                 chemistry="LFP", manufacturer="기아", model_name="EV3",
                 current_year=2026), "Green"),
]


@pytest.mark.parametrize("name,payload,expected_grade", TRIAGE_CASES)
def test_triage_grade(name, payload, expected_grade):
    result = evaluate_battery(**payload)
    assert result["grade"] == expected_grade, f"{name}: {result['grade']} != {expected_grade}"
    assert result["result_type"] == "preliminary_estimate"


def test_match_orange_ncm():
    """Orange / NCM / 재활용 후보 -> recycle + basic 업체 1~3순위."""
    companies = pd.read_csv(COMPANIES_CSV, encoding="utf-8-sig")
    triage_result = evaluate_battery(
        vehicle_year=2018, mileage_km=160000, capacity_kwh=64.0,
        chemistry="NCM", manufacturer="현대자동차", model_name="IONIQ5",
        battery_count=2, current_year=2026,
    )
    assert triage_result["grade"] == "Orange"

    res = match_companies(triage_result, companies, 37.456, 126.705, max_results=3)
    assert res["status"] == "matched"
    assert len(res["matched_companies"]) == 3
    # 1순위는 충청자원순환 (노트북 검증값)
    assert res["matched_companies"][0]["company_name"] == "충청자원순환"
    # 전부 recycle 처리유형이어야 한다
    assert all(c["process_type"] == "recycle" for c in res["matched_companies"])
