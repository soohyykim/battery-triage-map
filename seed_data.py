"""
seed_data.py
Battery Triage Map 시연용 시드 데이터 삽입 스크립트.

battery_cases_demo_lfp_v2_triage_check.csv에서 등급별 케이스를 골라
실제 백엔드 API(/triage → /match)를 순서대로 호출해서 DB에 10건을 쌓는다.

실행:
    python seed_data.py

주의:
    - 한 번만 실행할 것 (여러 번 실행하면 중복 데이터가 쌓임)
    - 백엔드 서버가 살아있어야 함
    - 로컬 환경에서 실행
"""

import time
from pathlib import Path

import pandas as pd
import requests

API_BASE_URL = "https://battery-triage-map-api.onrender.com"

# 발생채널별 시연용 좌표
CHANNEL_COORDS = {
    "강남폐차센터": (37.4979, 127.0276),
    "수원폐차센터": (37.2636, 127.0286),
    "인천폐차센터": (37.4563, 126.7052),
}
CHANNELS = list(CHANNEL_COORDS.keys())

# ---------------------------------------------------------------------------
# 시드 케이스 정의 (등급별 수동 선정, capacity nan 케이스 제외)
# ---------------------------------------------------------------------------
SEED_CASES = [
    # Green x3
    {
        "vin": "SEED001GREEN00001",
        "manufacturer": "현대자동차(주)",
        "model_name": "포터Ⅱ 일렉트릭",
        "vehicle_year": 2023,
        "mileage_km": 10.0,
        "capacity_kwh": 58.8,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "강남폐차센터",
    },
    {
        "vin": "SEED002GREEN00002",
        "manufacturer": "현대자동차(주)",
        "model_name": "아이오닉5 (IONIQ5)",
        "vehicle_year": 2022,
        "mileage_km": 72735.0,
        "capacity_kwh": 72.6,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "수원폐차센터",
    },
    {
        "vin": "SEED003GREEN00003",
        "manufacturer": "현대자동차(주)",
        "model_name": "포터Ⅱ 일렉트릭",
        "vehicle_year": 2021,
        "mileage_km": 26553.0,
        "capacity_kwh": 58.8,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "인천폐차센터",
    },
    # Yellow x3
    {
        "vin": "SEED004YELLOW0001",
        "manufacturer": "현대자동차(주)",
        "model_name": "코나 일렉트릭 (KONA ELECTRIC)",
        "vehicle_year": 2020,
        "mileage_km": 60678.0,
        "capacity_kwh": 64.0,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "강남폐차센터",
    },
    {
        "vin": "SEED005YELLOW0002",
        "manufacturer": "현대자동차(주)",
        "model_name": "코나 일렉트릭 (KONA ELECTRIC)",
        "vehicle_year": 2019,
        "mileage_km": 95239.0,
        "capacity_kwh": 64.0,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "수원폐차센터",
    },
    {
        "vin": "SEED006YELLOW0003",
        "manufacturer": "기아 주식회사",
        "model_name": "EV6",
        "vehicle_year": 2021,
        "mileage_km": 88000.0,
        "capacity_kwh": 77.4,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "인천폐차센터",
    },
    # Orange x3
    {
        "vin": "SEED007ORANGE0001",
        "manufacturer": "현대자동차(주)",
        "model_name": "아이오닉 일렉트릭(IONIQ ELECTRIC)",
        "vehicle_year": 2017,
        "mileage_km": 126454.0,
        "capacity_kwh": 28.0,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "강남폐차센터",
    },
    {
        "vin": "SEED008ORANGE0002",
        "manufacturer": "한국지엠주식회사",
        "model_name": "CHEVROLET BOLT EV",
        "vehicle_year": 2018,
        "mileage_km": 143597.0,
        "capacity_kwh": 66.0,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "수원폐차센터",
    },
    {
        "vin": "SEED009ORANGE0003",
        "manufacturer": "현대자동차(주)",
        "model_name": "아이오닉 일렉트릭(IONIQ ELECTRIC)",
        "vehicle_year": 2017,
        "mileage_km": 177993.0,
        "capacity_kwh": 28.0,
        "chemistry": "NCM",
        "condition_flags": {"flooded": False, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "인천폐차센터",
    },
    # Red x1 (침수 플래그 켜서 지정폐기물 판정 유도)
    {
        "vin": "SEED010RED0000001",
        "manufacturer": "기아 주식회사",
        "model_name": "니로 EV",
        "vehicle_year": 2020,
        "mileage_km": 45000.0,
        "capacity_kwh": 64.8,
        "chemistry": "NCM",
        "condition_flags": {"flooded": True, "leakage": False, "overheated": False, "swollen": False, "impact": False},
        "channel": "강남폐차센터",
    },
]


def seed():
    print(f"API: {API_BASE_URL}")
    print(f"총 {len(SEED_CASES)}건 삽입 시작\n")

    success, fail = 0, 0

    for i, case in enumerate(SEED_CASES, 1):
        channel = case["channel"]
        lat, lon = CHANNEL_COORDS[channel]

        triage_payload = {
            "vin": case["vin"],
            "vehicle_year": case["vehicle_year"],
            "mileage_km": case["mileage_km"],
            "capacity_kwh": case["capacity_kwh"],
            "chemistry": case["chemistry"],
            "manufacturer": case["manufacturer"],
            "model_name": case["model_name"],
            "battery_count": 1,
            "condition_flags": case["condition_flags"],
        }

        try:
            # 1) /triage 호출
            tr = requests.post(f"{API_BASE_URL}/triage", json=triage_payload, timeout=30)
            tr.raise_for_status()
            triage_result = tr.json()
            triage_id = triage_result.get("triage_id")
            grade = triage_result.get("grade")
            print(f"[{i:02d}] {case['vin']} → 등급: {grade} (triage_id: {triage_id})")

            # Red 포함 모든 등급에 대해 /match 호출 시도
            mr = requests.post(
                f"{API_BASE_URL}/match",
                json={
                    "triage_result": triage_result,
                    "origin_latitude": lat,
                    "origin_longitude": lon,
                    "max_results": 3,
                    "triage_id": triage_id,
                },
                timeout=30,
            )
            mr.raise_for_status()
            match_result = mr.json()
            companies = match_result.get("matched_companies", [])
            rank1 = companies[0]["company_name"] if companies else "매칭 없음"
            print(f"      매칭 완료 → 1순위: {rank1}")

            success += 1

        except Exception as e:
            print(f"[{i:02d}] {case['vin']} 실패: {e}")
            fail += 1

        # Render 무료 플랜 Rate Limit 방지
        time.sleep(1.5)

    print(f"\n완료: 성공 {success}건 / 실패 {fail}건")


if __name__ == "__main__":
    seed()
