"""
services/db.py
SQLite 영속 계층 (백엔드/AI 담당).

역할:
  - /triage 결과를 triage_history 에 저장 (save_triage)
  - /match 결과를 match_history 에 저장 (save_match)
  - 배터리 관리 페이지용 이력 조회 (list_history / get_history)
  - 담당자 승인 기록 (approve_triage)

DB 파일은 data/battery.db (git 제외). 스키마가 없으면 schema.sql 로 자동 생성한다.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "battery.db")))
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"


# ---------------------------------------------------------------------------
# 연결 / 스키마 보장
# ---------------------------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    """row_factory 가 적용된 커넥션 반환. 스키마가 없으면 만든다."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """triage_history 테이블이 없으면 schema.sql 전체를 실행한다."""
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='triage_history'"
    ).fetchone()
    if not exists and SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------
def save_triage(
    result: dict[str, Any],
    origin_latitude: Optional[float] = None,
    origin_longitude: Optional[float] = None,
) -> int:
    """evaluate_battery() 결과 1건을 triage_history 에 저장하고 id 를 반환한다."""
    s = result.get("input_summary", {})
    reason_codes = ",".join(result.get("reason_codes", []) or [])

    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO triage_history (
                manufacturer, model_name, vehicle_year, mileage_km, capacity_kwh,
                chemistry, battery_count,
                soh_proxy_score, reuse_score, recycle_score, data_confidence,
                grade, recommended_path, required_diagnostic_capability,
                collection_route, reason_codes,
                origin_latitude, origin_longitude
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                s.get("manufacturer"), s.get("model_name"), s.get("vehicle_year"),
                s.get("mileage_km"), s.get("capacity_kwh"), s.get("chemistry"),
                s.get("battery_count", 1),
                result.get("soh_proxy_score"), result.get("reuse_score"),
                result.get("recycle_score"), result.get("data_confidence"),
                result.get("grade"), result.get("recommended_path"),
                result.get("required_diagnostic_capability"),
                result.get("collection_route"), reason_codes,
                origin_latitude, origin_longitude,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def save_match(triage_id: int, match_result: dict[str, Any]) -> int:
    """match_companies() 결과(matched_companies)를 match_history 에 저장. 저장 행 수 반환."""
    companies = match_result.get("matched_companies", []) or []
    if not companies:
        return 0

    conn = get_conn()
    try:
        rows = [
            (
                triage_id, c.get("rank"), c.get("company_id"), c.get("company_name"),
                c.get("distance_km"), c.get("total_score"),
                c.get("process_type"), c.get("diagnostic_capability"),
            )
            for c in companies
        ]
        conn.executemany(
            """
            INSERT INTO match_history (
                triage_id, rank, company_id, company_name,
                distance_km, total_score, process_type, diagnostic_capability
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 조회 (배터리 관리 페이지)
# ---------------------------------------------------------------------------
def list_history(limit: int = 100) -> list[dict[str, Any]]:
    """최근 판정 이력 목록을 최신순으로 반환한다."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM triage_history ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_history(triage_id: int) -> Optional[dict[str, Any]]:
    """판정 1건 + 매칭 결과를 함께 반환한다. 없으면 None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM triage_history WHERE id=?", (triage_id,)
        ).fetchone()
        if row is None:
            return None
        matches = conn.execute(
            "SELECT * FROM match_history WHERE triage_id=? ORDER BY rank", (triage_id,)
        ).fetchall()
        result = dict(row)
        result["matched_companies"] = [dict(m) for m in matches]
        return result
    finally:
        conn.close()


def approve_triage(triage_id: int, approver: str) -> bool:
    """담당자 승인 기록. 대상이 있으면 True."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE triage_history SET approved_by=?, approved_at=? WHERE id=?",
            (approver, datetime.now().isoformat(timespec="seconds"), triage_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
