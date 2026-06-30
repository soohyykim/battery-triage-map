"""data/init_db.py - SQLite DB 초기화. 실행: python data/init_db.py

스키마(schema.sql)를 적용하고, companies 테이블을 companies_mock.csv 로 시드한다.
companies_mock.csv 는 매칭(services/matching.py)이 쓰는 처리업체 DB와 동일 파일이라
DB와 매칭 데이터가 한 소스로 일치한다. 나중에 실데이터 CSV로 교체하면 그대로 반영된다.
"""
from __future__ import annotations
import csv, os, sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "battery.db")))
SCHEMA_PATH = BASE_DIR / "schema.sql"
COMPANIES_CSV = BASE_DIR / "companies_mock.csv"

# companies 테이블 = companies_mock.csv 헤더와 동일
COMPANY_COLS = [
    "company_id", "company_name", "address", "region", "latitude", "longitude",
    "license_type", "process_type", "accepted_chemistry", "accepted_grade",
    "monthly_capacity_count", "diagnostic_capability", "is_active",
]


def init_schema(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    print(f"[init_db] 스키마 적용 완료 -> {DB_PATH}")


def _to_int_bool(value) -> int:
    """is_active 같은 True/False/1/0 문자열을 0/1 정수로 정규화한다."""
    return 1 if str(value).strip().lower() in {"1", "true", "y", "yes"} else 0


def seed_companies(conn):
    if not COMPANIES_CSV.exists() or COMPANIES_CSV.stat().st_size == 0:
        print("[init_db] companies_mock.csv 없음 -> 시드 건너뜀"); return
    # utf-8-sig: 엑셀이 붙이는 BOM 제거
    with COMPANIES_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[init_db] companies_mock.csv 비어있음 -> 시드 건너뜀"); return

    conn.execute("DELETE FROM companies")  # 재실행 시 중복 방지
    records = []
    for r in rows:
        rec = [r.get(c) for c in COMPANY_COLS]
        rec[-1] = _to_int_bool(r.get("is_active", "1"))  # is_active 정규화
        records.append(tuple(rec))
    conn.executemany(
        f"INSERT INTO companies ({','.join(COMPANY_COLS)}) "
        f"VALUES ({','.join('?' * len(COMPANY_COLS))})",
        records,
    )
    conn.commit()
    print(f"[init_db] companies 시드 {len(records)}건 적재 완료")


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        init_schema(conn); seed_companies(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        print("[init_db] 생성된 테이블:", [t[0] for t in tables])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
