"""
tests/test_triage.py
?곗뿏 寃利?耳?댁뒪瑜??뚭? ?뚯뒪?몃줈 怨좎젙?쒕떎.

?ㅽ뻾:  pytest          (?꾨줈?앺듃 猷⑦듃?먯꽌)
湲곗?:  triage.ipynb / matching.ipynb ?ㅼ젣 異쒕젰媛?
二쇱쓽:  Handoff 臾몄꽌 ?뚯뒪?? 湲곕?媛믪? 'Orange' 濡??곹? ?덉쑝??
       ?ㅼ젣 肄붾뱶쨌?명듃遺?異쒕젰? 'Yellow' 媛 留욌떎 (reuse_score 70.3 -> 60~75 援ш컙).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from services.triage import evaluate_battery
from services.matching import match_companies

BASE_DIR = Path(__file__).resolve().parent.parent
COMPANIES_CSV = BASE_DIR / "data" / "companies_mock.csv"


# (?대쫫, ?낅젰, 湲곕? ?깃툒) ??current_year 怨좎젙???곕룄???붾뱾由ъ? ?딄쾶 ?쒕떎.
TRIAGE_CASES = [
    ("醫뗭? NCM", dict(vehicle_year=2024, mileage_km=15000, capacity_kwh=77.4,
                      chemistry="NCM", manufacturer="?꾨??먮룞李?, model_name="IONIQ5",
                      current_year=2026), "Green"),
    ("以묎컙 NCM", dict(vehicle_year=2020, mileage_km=85000, capacity_kwh=64.0,
                      chemistry="NCM", manufacturer="?꾨??먮룞李?, model_name="IONIQ5",
                      current_year=2026), "Yellow"),
    ("?명썑 NCM", dict(vehicle_year=2017, mileage_km=180000, capacity_kwh=58.0,
                      chemistry="NCM", manufacturer="湲곗븘", model_name="NIRO EV",
                      current_year=2026), "Orange"),
    ("?뺣낫遺議?, dict(vehicle_year=None, mileage_km=None, capacity_kwh=None,
                      chemistry="UNKNOWN", current_year=2026), "Gray"),
    ("LFP", dict(vehicle_year=2022, mileage_km=40000, capacity_kwh=58.0,
                 chemistry="LFP", manufacturer="湲곗븘", model_name="EV3",
                 current_year=2026), "Green"),
]


@pytest.mark.parametrize("name,payload,expected_grade", TRIAGE_CASES)
def test_triage_grade(name, payload, expected_grade):
    result = evaluate_battery(**payload)
    assert result["grade"] == expected_grade, f"{name}: {result['grade']} != {expected_grade}"
    assert result["result_type"] == "preliminary_estimate"


def test_match_orange_ncm():
    """Orange / NCM / ?ы솢???꾨낫 -> recycle + basic ?낆껜 1~3?쒖쐞."""
    companies = pd.read_csv(COMPANIES_CSV, encoding="utf-8-sig")
    triage_result = evaluate_battery(
        vehicle_year=2018, mileage_km=160000, capacity_kwh=64.0,
        chemistry="NCM", manufacturer="?꾨??먮룞李?, model_name="IONIQ5",
        battery_count=2, current_year=2026,
    )
    assert triage_result["grade"] == "Orange"

    res = match_companies(triage_result, companies, 37.456, 126.705, max_results=3)
    assert res["status"] == "matched"
    assert len(res["matched_companies"]) == 3
    # 1?쒖쐞??異⑹껌?먯썝?쒗솚 (?명듃遺?寃利앷컪)
    assert res["matched_companies"][0]["company_name"] == "異⑹껌?먯썝?쒗솚"
    # ?꾨? recycle 泥섎━?좏삎?댁뼱???쒕떎
    assert all(c["process_type"] == "recycle" for c in res["matched_companies"])
