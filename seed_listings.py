"""
seed_listings.py — BATLINK 시연용 매물 사전 등록 스크립트.

battery_cases_demo.csv에서 20건을 골라 실제 백엔드 POST /triage(+/match)를
호출해 DB에 판정 이력을 쌓는다. 여러 폐차장(강남/수원/인천폐차센터)에
라운드로빈으로 배정해, 웹(처리업체)에서 다양한 발생 폐차장의 매물이 보이게
한다. Red(지정폐기물)가 아닌 건은 '매물 등록' 상태로 전환한다(로컬 공유
JSON 파일에 기록되므로 통합 앱(app.py)의 배터리 관리/마켓 양쪽에서 바로
보인다). Red인 건은 '판정' 상태로 남겨두며, 처리업체를 거치지 않고
폐차장이 직접 '처리 완료'로 종결해야 한다.

시연 시나리오:
1. 이 스크립트를 먼저 한 번 실행해 웹(처리업체) 화면에 매물이 이미 깔려있는
   상태로 시작한다.
2. 시연 중 웹(폐차장)에서 새 배터리를 판정 -> 매물 등록하면, 웹(처리업체)의
   "전체 매물 검색"(최신 등록순) 맨 위에 새로 뜨는 걸 보여주면 된다.

실행:
    python seed_listings.py

주의:
    - 한 번만 실행할 것 (여러 번 실행하면 중복 데이터가 쌓인다)
    - 백엔드 서버(API_BASE_URL)가 살아있어야 한다
    - battery_data.py와 같은 폴더에서 실행해야 공유 상태 파일 경로가 맞는다
"""

import sys
import time
from pathlib import Path

import pandas as pd
import requests

from battery_data import (
    API_BASE_URL, CHANNEL_COORDS, CHANNEL_NAMES,
    mark_listed, set_battery_channel,
)

SCRIPT_DIR = Path(__file__).resolve().parent

# battery_cases_demo.csv가 있을 법한 위치들을 순서대로 탐색한다.
# (프로젝트 구조에 따라 루트에 바로 있을 수도, data/ 나 data/processed/
# 밑에 있을 수도 있어서 여러 후보를 확인한다.)
CANDIDATE_PATHS = [
    SCRIPT_DIR / "battery_cases_demo.csv",
    SCRIPT_DIR / "data" / "battery_cases_demo.csv",
    SCRIPT_DIR / "data" / "processed" / "battery_cases_demo.csv",
]
N_SEED = 20


def _synthetic_vin(battery_id, index: int) -> str:
    """battery_cases_demo.csv의 battery_id(예: BAT_000025, 10자)는 내부 케이스
    식별자일 뿐 실제 VIN이 아니다. 실제 VIN은 항상 17자리인데 이 값을 그대로
    써버리면 화면에 10자리 VIN이 노출돼 눈에 띄게 어색해 보인다. battery_id의
    숫자부분 + 순번을 조합해 자릿수(17자)만이라도 실제 VIN 형태에 맞춘
    합성 VIN을 만든다 (체크섬 등 ISO 3779 규격까지 충족하진 않는 데모용 값).
    """
    digits = "".join(ch for ch in str(battery_id) if ch.isdigit()).zfill(6)[-6:]
    return f"KMHDM41A{digits}{index:03d}"  # 8 + 6 + 3 = 17자


def resolve_csv_path():
    """CLI 인자로 경로를 직접 줬으면 그걸 쓰고, 아니면 후보 경로들을 순서대로 탐색."""
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists():
            return p
        raise FileNotFoundError(f"지정한 경로에 파일이 없습니다: {p}")

    for p in CANDIDATE_PATHS:
        if p.exists():
            return p

    tried = "\n  - ".join(str(p) for p in CANDIDATE_PATHS)
    raise FileNotFoundError(
        f"battery_cases_demo.csv를 찾지 못했습니다. 다음 경로들을 확인했습니다:\n  - {tried}\n\n"
        f"다른 위치에 있다면 경로를 직접 지정해서 실행하세요:\n"
        f"  python seed_listings.py \"C:\\경로\\battery_cases_demo.csv\""
    )


def load_seed_rows(csv_path, n=N_SEED):
    df = pd.read_csv(csv_path)
    df_known = df[df["chemistry"] != "UNKNOWN"]
    sample = df_known.sample(n=min(n, len(df_known)), random_state=42)
    return sample


def seed():
    print(f"API: {API_BASE_URL}")
    try:
        csv_path = resolve_csv_path()
    except FileNotFoundError as e:
        print(f"\n오류: {e}")
        return
    print(f"CSV: {csv_path}")

    rows = load_seed_rows(csv_path)
    print(f"총 {len(rows)}건 시드 시작 — {len(CHANNEL_NAMES)}개 폐차장에 분산 배정\n")

    triaged_ids = []      # Red가 아닌 것 (매물 등록 대상)
    disposal_ids = []     # Red인 것 (판정 상태로 남겨두고 폐차장이 직접 처리 완료 처리)
    success, fail = 0, 0

    for i, row in enumerate(rows.itertuples(index=False), 1):
        # 여러 폐차장(채널)에 라운드로빈으로 배정해서, 웹(처리업체)에서
        # 다양한 발생 폐차장의 매물이 보이도록 한다.
        channel_name = CHANNEL_NAMES[(i - 1) % len(CHANNEL_NAMES)]
        origin_lat, origin_lon = CHANNEL_COORDS[channel_name]

        payload = {
            "vin": _synthetic_vin(getattr(row, "battery_id", f"SEED-{i:03d}"), i),
            "vehicle_year": int(row.vehicle_year) if pd.notna(row.vehicle_year) else None,
            "mileage_km": float(row.mileage_km) if pd.notna(row.mileage_km) else None,
            "capacity_kwh": float(row.capacity_kwh) if pd.notna(row.capacity_kwh) else None,
            "chemistry": row.chemistry if pd.notna(row.chemistry) else "UNKNOWN",
            "manufacturer": row.manufacturer if pd.notna(row.manufacturer) else None,
            "model_name": row.model_name if pd.notna(row.model_name) else None,
            "battery_count": 1,
            "condition_flags": {
                "flooded": bool(getattr(row, "flooded", False)),
                "leakage": bool(getattr(row, "leakage", False)),
                "overheated": bool(getattr(row, "overheated", False)),
                "swollen": bool(getattr(row, "swelling", False)),
                "impact": bool(getattr(row, "impact", False)),
            },
        }

        try:
            tr = requests.post(f"{API_BASE_URL}/triage", json=payload, timeout=30)
            tr.raise_for_status()
            triage_result = tr.json()
            triage_id = triage_result.get("triage_id")
            grade = triage_result.get("grade")
            print(f"[{i:02d}] {payload['vin']} -> 등급: {grade} · 발생: {channel_name} (triage_id: {triage_id})")

            mr = requests.post(
                f"{API_BASE_URL}/match",
                json={
                    "triage_result": triage_result,
                    "origin_latitude": origin_lat,
                    "origin_longitude": origin_lon,
                    "max_results": 3,
                    "triage_id": triage_id,
                },
                timeout=30,
            )
            mr.raise_for_status()

            if triage_id is not None:
                set_battery_channel(triage_id, channel_name)
                if grade == "Red":
                    disposal_ids.append(triage_id)
                else:
                    triaged_ids.append(triage_id)

            success += 1
        except requests.RequestException as e:
            print(f"[{i:02d}] 실패: {e}")
            fail += 1

        time.sleep(0.5)

    print(f"\n판정 완료: 성공 {success}건 / 실패 {fail}건")

    if triaged_ids:
        listed, rejected = mark_listed(triaged_ids)
        print(f"매물 등록 처리: {len(listed)}건 (Red라서 제외된 건: {len(rejected)}건)")
    else:
        print("매물 등록으로 전환할 대상이 없습니다.")

    if disposal_ids:
        print(f"Red(지정폐기물) {len(disposal_ids)}건은 '판정' 상태로 남겨뒀습니다 — "
              f"웹(폐차장) 배터리 관리에서 '처리 완료 (지정폐기물)'을 눌러 직접 종결해주세요.")

    print("\n완료! app.py를 실행해 확인하세요.")


if __name__ == "__main__":
    seed()
