"""data/init_db.py - SQLite DB 초기화. 실행: python data/init_db.py"""
from __future__ import annotations
import csv, os, sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "battery.db")))
SCHEMA_PATH = BASE_DIR / "schema.sql"
COMPANIES_CSV = BASE_DIR / "sample_companies.csv"

def init_schema(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    print(f"[init_db] 스키마 적용 완료 -> {DB_PATH}")

def seed_companies(conn):
    if not COMPANIES_CSV.exists() or COMPANIES_CSV.stat().st_size == 0:
        print("[init_db] sample_companies.csv 없음 -> 시드 건너뜀"); return
    with COMPANIES_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    cols = ["name","permit_no","region","address","lat","lon",
            "handling_types","chemistry_supported","capacity_ton","phone"]
    conn.executemany(
        f"INSERT INTO companies ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
        [tuple(r.get(c) for c in cols) for r in rows])
    conn.commit()
    print(f"[init_db] companies 시드 {len(rows)}건 적재 완료")

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        init_schema(conn); seed_companies(conn)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print("[init_db] 생성된 테이블:", [t[0] for t in tables])
    finally:
        conn.close()

if __name__ == "__main__":
    main()
