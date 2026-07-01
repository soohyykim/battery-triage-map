"""data/init_db.py - DB 초기화. 실행: python data/init_db.py

SQLAlchemy 로 테이블을 생성하고 companies 테이블을 companies_mock.csv 로 시드한다.
DATABASE_URL 이 있으면 그 DB(배포: Render PostgreSQL), 없으면 로컬 SQLite 에 적용된다.
companies_mock.csv 는 매칭(services/matching.py)이 쓰는 처리업체 DB와 동일 파일이라
DB와 매칭 데이터가 한 소스로 일치한다. 실데이터 CSV로 교체하면 그대로 반영된다.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

# services 패키지 임포트를 위해 프로젝트 루트를 경로에 추가
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import insert, delete  # noqa: E402
from services import db as db_svc      # noqa: E402

COMPANIES_CSV = BASE_DIR / "data" / "companies_mock.csv"
COMPANY_COLS = [
    "company_id", "company_name", "address", "region", "latitude", "longitude",
    "license_type", "process_type", "accepted_chemistry", "accepted_grade",
    "monthly_capacity_count", "diagnostic_capability", "is_active",
]


def _to_int_bool(value) -> int:
    """is_active 같은 True/False/1/0 문자열을 0/1 정수로 정규화한다."""
    return 1 if str(value).strip().lower() in {"1", "true", "y", "yes"} else 0


def seed_companies(engine) -> int:
    if not COMPANIES_CSV.exists() or COMPANIES_CSV.stat().st_size == 0:
        print("[init_db] companies_mock.csv 없음 -> 시드 건너뜀")
        return 0
    with COMPANIES_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[init_db] companies_mock.csv 비어있음 -> 시드 건너뜀")
        return 0

    records = []
    for r in rows:
        rec = {c: r.get(c) for c in COMPANY_COLS}
        rec["is_active"] = _to_int_bool(r.get("is_active", "1"))
        records.append(rec)

    with engine.begin() as conn:
        conn.execute(delete(db_svc.companies))         # 재실행 시 중복 방지
        conn.execute(insert(db_svc.companies), records)
    return len(records)


def main():
    # 주의: Render 빌드 단계에서는 내부 DB 호스트(dpg-...)가 아직 안 붙어서
    #       접속이 실패할 수 있다. 그건 정상이며(테이블은 런타임 첫 요청 때 자동 생성),
    #       빌드를 막지 않도록 예외를 삼킨다.
    try:
        engine = db_svc.get_engine()      # 테이블 자동 생성 포함
        print(f"[init_db] 스키마 적용 완료 -> {engine.url}")
        n = seed_companies(engine)
        if n:
            print(f"[init_db] companies 시드 {n}건 적재 완료")
        print("[init_db] 생성된 테이블:", list(db_svc.metadata.tables.keys()))
    except Exception as e:
        print(f"[init_db] DB 연결 불가 -> 건너뜀(런타임에 자동 생성됨): {e}")


if __name__ == "__main__":
    main()
