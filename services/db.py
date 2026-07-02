"""
services/db.py
DB 영속 계층 (백엔드/AI 담당) — SQLAlchemy 기반, SQLite/PostgreSQL 양쪽 호환.

엔진 선택:
  - 환경변수 DATABASE_URL 이 있으면 그걸로 접속 (배포: Render PostgreSQL)
  - 없으면 로컬 SQLite(data/battery.db) 사용 (로컬 개발/테스트)
  => 코드 변경 없이 DATABASE_URL 만으로 DB 가 바뀐다.

역할:
  - /triage 결과를 triage_history 에 저장 (save_triage)
  - /match 결과를 match_history 에 저장 (save_match)
  - 배터리 관리 페이지용 이력 조회 (list_history / get_history)
    * list_history 는 match_history 1순위(rank=1) 업체명을 LEFT JOIN 해서
      matched_company_name 으로 같이 내려준다 (관리 페이지 목록에서 추천업체
      표시를 위해 항목마다 상세 조회를 추가로 안 해도 되게 하기 위함).
  - 담당자 승인 기록 (approve_triage)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    Column, DateTime, Float, Integer, MetaData, String, Table,
    create_engine, delete, func, insert, select, update,
)
from sqlalchemy.engine import Engine, Row

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = f"sqlite:///{BASE_DIR / 'data' / 'battery.db'}"


def _resolve_db_url() -> str:
    """DATABASE_URL(배포) 우선, 없으면 로컬 SQLite. postgres:// 는 postgresql:// 로 정규화."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return DEFAULT_SQLITE
    # Render/Heroku 가 주는 구형 postgres:// 스킴을 SQLAlchemy 표준으로 교정
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


# ---------------------------------------------------------------------------
# 테이블 정의 (DDL은 SQLAlchemy가 DB 종류에 맞게 생성 — SQLite/Postgres 모두 OK)
# ---------------------------------------------------------------------------
metadata = MetaData()

triage_history = Table(
    "triage_history", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("vin", String),
    Column("manufacturer", String),
    Column("model_name", String),
    Column("vehicle_year", Integer),
    Column("mileage_km", Float),
    Column("capacity_kwh", Float),
    Column("chemistry", String),
    Column("battery_count", Integer, default=1),
    Column("soh_proxy_score", Float),
    Column("reuse_score", Float),
    Column("recycle_score", Float),
    Column("data_confidence", Float),
    Column("grade", String),
    Column("recommended_path", String),
    Column("required_diagnostic_capability", String),
    Column("collection_route", String),
    Column("reason_codes", String),
    Column("origin_latitude", Float),
    Column("origin_longitude", Float),
    Column("approved_by", String),
    Column("approved_at", DateTime),
    Column("created_at", DateTime, server_default=func.now()),
)

companies = Table(
    "companies", metadata,
    Column("company_id", String, primary_key=True),
    Column("company_name", String, nullable=False),
    Column("address", String),
    Column("region", String),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("license_type", String),
    Column("process_type", String),
    Column("accepted_chemistry", String),
    Column("accepted_grade", String),
    Column("monthly_capacity_count", Integer),
    Column("diagnostic_capability", String),
    Column("is_active", Integer, default=1),
)

match_history = Table(
    "match_history", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("triage_id", Integer),
    Column("rank", Integer),
    Column("company_id", String),
    Column("company_name", String),
    Column("distance_km", Float),
    Column("total_score", Float),
    Column("process_type", String),
    Column("diagnostic_capability", String),
    Column("status", String, default="제안"),
    Column("created_at", DateTime, server_default=func.now()),
)


# ---------------------------------------------------------------------------
# 엔진 (1회 생성 후 캐시) + 스키마 보장
# ---------------------------------------------------------------------------
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """엔진을 한 번만 만들어 캐시하고, 테이블이 없으면 생성한다.

    환경변수 RESET_DB=true 가 설정되어 있으면, 기존 테이블을 전부 삭제하고
    새 스키마로 재생성한다. (스키마 변경 시 1회성으로만 켜고, 재배포 확인 후
    반드시 Render 환경변수에서 다시 제거할 것 — 매 배포마다 데이터가
    초기화되는 걸 막기 위함)
    """
    global _engine
    if _engine is None:
        url = _resolve_db_url()
        connect_args = {}
        if url.startswith("sqlite"):
            # FastAPI 멀티스레드에서 SQLite 공유 허용
            connect_args = {"check_same_thread": False}
            Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

        if os.getenv("RESET_DB", "").strip().lower() == "true":
            print("[db] RESET_DB=true 감지 — 기존 테이블 삭제 후 재생성")
            metadata.drop_all(_engine)

        metadata.create_all(_engine)  # 없으면 생성 (있으면 그대로)
    return _engine


def _row_to_dict(row: Row) -> dict[str, Any]:
    """Row -> dict. datetime 은 ISO 문자열로 변환(응답 스키마가 str 이라서)."""
    d = dict(row._mapping)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat(timespec="seconds")
    return d


# ---------------------------------------------------------------------------
# 저장
# ---------------------------------------------------------------------------
def save_triage(
    result: dict[str, Any],
    vin: Optional[str] = None,
    origin_latitude: Optional[float] = None,
    origin_longitude: Optional[float] = None,
) -> int:
    """evaluate_battery() (또는 rule.py 분기) 결과 1건을 triage_history 에 저장하고 id 를 반환한다."""
    s = result.get("input_summary", {})
    values = {
        "vin": vin,
        "manufacturer": s.get("manufacturer"),
        "model_name": s.get("model_name"),
        "vehicle_year": s.get("vehicle_year"),
        "mileage_km": s.get("mileage_km"),
        "capacity_kwh": s.get("capacity_kwh"),
        "chemistry": s.get("chemistry"),
        "battery_count": s.get("battery_count", 1),
        "soh_proxy_score": result.get("soh_proxy_score"),
        "reuse_score": result.get("reuse_score"),
        "recycle_score": result.get("recycle_score"),
        "data_confidence": result.get("data_confidence"),
        "grade": result.get("grade"),
        "recommended_path": result.get("recommended_path"),
        "required_diagnostic_capability": result.get("required_diagnostic_capability"),
        "collection_route": result.get("collection_route"),
        "reason_codes": ",".join(result.get("reason_codes", []) or []),
        "origin_latitude": origin_latitude,
        "origin_longitude": origin_longitude,
    }
    with get_engine().begin() as conn:
        res = conn.execute(insert(triage_history).values(**values))
        return int(res.inserted_primary_key[0])


def save_match(triage_id: int, match_result: dict[str, Any]) -> int:
    """match_companies() 결과(matched_companies)를 match_history 에 저장. 저장 행 수 반환."""
    rows = [
        {
            "triage_id": triage_id,
            "rank": c.get("rank"),
            "company_id": c.get("company_id"),
            "company_name": c.get("company_name"),
            "distance_km": c.get("distance_km"),
            "total_score": c.get("total_score"),
            "process_type": c.get("process_type"),
            "diagnostic_capability": c.get("diagnostic_capability"),
        }
        for c in (match_result.get("matched_companies", []) or [])
    ]
    if not rows:
        return 0
    with get_engine().begin() as conn:
        conn.execute(insert(match_history), rows)
    return len(rows)


# ---------------------------------------------------------------------------
# 조회 (배터리 관리 페이지)
# ---------------------------------------------------------------------------
def list_history(limit: int = 100) -> list[dict[str, Any]]:
    """
    최근 판정 이력 목록을 최신순으로 반환한다.

    match_history 에서 triage_id 별 rank=1(1순위 추천업체) 행만 골라
    LEFT JOIN 해서 matched_company_name 을 같이 내려준다. 매칭 이력이
    없는 건(아직 /match 호출 안 됨)은 matched_company_name 이 None.
    """
    rank1 = (
        select(match_history.c.triage_id, match_history.c.company_name)
        .where(match_history.c.rank == 1)
        .subquery()
    )

    stmt = (
        select(triage_history, rank1.c.company_name.label("matched_company_name"))
        .select_from(
            triage_history.outerjoin(rank1, triage_history.c.id == rank1.c.triage_id)
        )
        .order_by(triage_history.c.created_at.desc(), triage_history.c.id.desc())
        .limit(limit)
    )
    with get_engine().connect() as conn:
        return [_row_to_dict(r) for r in conn.execute(stmt)]


def get_history(triage_id: int) -> Optional[dict[str, Any]]:
    """판정 1건 + 매칭 결과를 함께 반환한다. 없으면 None."""
    with get_engine().connect() as conn:
        row = conn.execute(
            select(triage_history).where(triage_history.c.id == triage_id)
        ).first()
        if row is None:
            return None
        matches = conn.execute(
            select(match_history)
            .where(match_history.c.triage_id == triage_id)
            .order_by(match_history.c.rank)
        )
        result = _row_to_dict(row)
        matched_list = [_row_to_dict(m) for m in matches]
        result["matched_companies"] = matched_list
        result["matched_company_name"] = matched_list[0]["company_name"] if matched_list else None
        return result


def approve_triage(triage_id: int, approver: str) -> bool:
    """담당자 승인 기록. 대상이 있으면 True."""
    stmt = (
        update(triage_history)
        .where(triage_history.c.id == triage_id)
        .values(approved_by=approver, approved_at=datetime.now())
    )
    with get_engine().begin() as conn:
        return conn.execute(stmt).rowcount > 0


# ---------------------------------------------------------------------------
# 삭제 (배터리 관리 페이지 — 선택 삭제)
# ---------------------------------------------------------------------------
def delete_triage(triage_id: int) -> bool:
    """
    판정 이력 1건 삭제. 연결된 match_history 행도 함께 지운다(외래키 제약은
    없지만 고아 행이 남지 않도록). 대상이 있어서 실제로 지웠으면 True.
    """
    with get_engine().begin() as conn:
        conn.execute(delete(match_history).where(match_history.c.triage_id == triage_id))
        result = conn.execute(delete(triage_history).where(triage_history.c.id == triage_id))
        return result.rowcount > 0


def delete_triage_bulk(triage_ids: list[int]) -> list[int]:
    """
    판정 이력 여러 건 일괄 삭제. 실제로 존재해서 삭제된 id 목록을 반환한다
    (존재하지 않는 id는 조용히 건너뜀). 마찬가지로 연결된 match_history도 함께 지운다.
    """
    if not triage_ids:
        return []
    with get_engine().begin() as conn:
        existing = [
            row[0]
            for row in conn.execute(
                select(triage_history.c.id).where(triage_history.c.id.in_(triage_ids))
            )
        ]
        if not existing:
            return []
        conn.execute(delete(match_history).where(match_history.c.triage_id.in_(existing)))
        conn.execute(delete(triage_history).where(triage_history.c.id.in_(existing)))
        return existing
