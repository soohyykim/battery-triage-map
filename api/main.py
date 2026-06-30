"""
api/main.py
Battery Triage Map - FastAPI 엔드포인트 4개.

  POST /triage  -> 배터리 예비 판정 (evaluate_battery)   services/triage.py   [데엔]
  POST /score   -> 잔존가치 점수 요약 (triage 점수부)      services/triage.py   [데엔]
  POST /match   -> 처리기업 매칭 (match_companies)        services/matching.py [데엔]
  POST /report  -> 정책 RAG 리포트                        services/rag.py      [백엔드/AI]

흐름: rule.py(지정폐기물 1차 선별, 팀장) → /triage → /match → /report
실행:  python -m uvicorn api.main:app --reload   ->  http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    BatteryInput,
    TriageResponse,
    ScoreResponse,
    MatchRequest,
    MatchResponse,
    ReportRequest,
    ReportResponse,
    HistoryItem,
    HistoryDetail,
    ApproveRequest,
)
from services import triage as triage_svc
from services import matching as matching_svc
from services import db as db_svc

BASE_DIR = Path(__file__).resolve().parent.parent
COMPANIES_CSV = BASE_DIR / "data" / "companies_mock.csv"

app = FastAPI(
    title="Battery Triage Map API",
    description="전기차 사용후 배터리 가치 판정 및 처리기업 매칭 의사결정 지원 API",
    version="0.2.0",
)

# 프론트엔드 분리 배포(React/Vercel 등) 대비 CORS 허용. MVP 단계라 전체 허용.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def load_companies() -> pd.DataFrame:
    """처리업체 DB(companies_mock.csv)를 한 번만 읽어 캐시한다."""
    if not COMPANIES_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(COMPANIES_CSV, encoding="utf-8-sig")


@app.get("/", tags=["health"])
def health():
    df = load_companies()
    return {
        "status": "ok",
        "service": "battery-triage-map",
        "version": "0.2.0",
        "companies_loaded": int(len(df)),
    }


# ---------------------------------------------------------------------------
# POST /triage  - 배터리 예비 판정 (evaluate_battery)
# ---------------------------------------------------------------------------
@app.post("/triage", response_model=TriageResponse, tags=["triage"])
def triage(req: BatteryInput):
    result = triage_svc.evaluate_battery(**req.model_dump())
    # 판정 결과를 이력 DB에 저장하고, 발급된 id를 응답에 실어 보낸다.
    # (프론트가 이 triage_id를 /match 요청에 그대로 넣으면 매칭 이력이 연결된다.)
    try:
        result["triage_id"] = db_svc.save_triage(result)
    except Exception as e:  # DB 문제로 판정 자체가 막히지 않도록 방어
        print(f"[main] triage 저장 실패(무시하고 결과 반환): {e}")
        result["triage_id"] = None
    return result


# ---------------------------------------------------------------------------
# POST /score  - 잔존가치 점수 요약
# ---------------------------------------------------------------------------
@app.post("/score", response_model=ScoreResponse, tags=["score"])
def score(req: BatteryInput):
    result = triage_svc.evaluate_battery(**req.model_dump())
    return {
        "grade": result["grade"],
        "soh_proxy_score": result["soh_proxy_score"],
        "reuse_score": result["reuse_score"],
        "recycle_score": result["recycle_score"],
        "data_confidence": result["data_confidence"],
    }


# ---------------------------------------------------------------------------
# POST /match  - 처리기업 매칭
# ---------------------------------------------------------------------------
@app.post("/match", response_model=MatchResponse, tags=["match"])
def match(req: MatchRequest):
    companies = load_companies()
    if companies.empty:
        raise HTTPException(
            status_code=503,
            detail="data/companies_mock.csv 가 없거나 비어있음 (처리업체 DB 필요)",
        )
    result = matching_svc.match_companies(
        triage_result=req.triage_result,
        companies_df=companies,
        origin_latitude=req.origin_latitude,
        origin_longitude=req.origin_longitude,
        max_results=req.max_results,
    )
    # triage_id 가 함께 오면 매칭 결과를 해당 판정에 연결해 저장한다.
    if req.triage_id is not None:
        try:
            db_svc.save_match(req.triage_id, result)
        except Exception as e:
            print(f"[main] match 저장 실패(무시): {e}")
    return result


# ---------------------------------------------------------------------------
# POST /report  - 정책 RAG 리포트 (W2-3 구현 예정)
# ---------------------------------------------------------------------------
@app.post("/report", response_model=ReportResponse, tags=["report"])
def report(req: ReportRequest):
    try:
        from services import rag
        result = rag.generate_report(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(
            status_code=501,
            detail="services/rag.py generate_report 미구현 (W2-3 RAG 단계)",
        )
    return ReportResponse(
        report=result.get("report", ""),
        sources=result.get("sources", []),
    )


# ---------------------------------------------------------------------------
# GET /history  - 배터리 관리 페이지용 판정 이력 목록
# ---------------------------------------------------------------------------
@app.get("/history", response_model=list[HistoryItem], tags=["history"])
def history(limit: int = 100):
    return db_svc.list_history(limit=limit)


# ---------------------------------------------------------------------------
# GET /history/{triage_id}  - 판정 1건 + 매칭 결과 상세
# ---------------------------------------------------------------------------
@app.get("/history/{triage_id}", response_model=HistoryDetail, tags=["history"])
def history_detail(triage_id: int):
    item = db_svc.get_history(triage_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"triage_id={triage_id} 이력 없음")
    return item


# ---------------------------------------------------------------------------
# POST /history/{triage_id}/approve  - 담당자 승인 (팀장 app.py)
# ---------------------------------------------------------------------------
@app.post("/history/{triage_id}/approve", tags=["history"])
def approve(triage_id: int, req: ApproveRequest):
    ok = db_svc.approve_triage(triage_id, req.approved_by)
    if not ok:
        raise HTTPException(status_code=404, detail=f"triage_id={triage_id} 이력 없음")
    return {"status": "approved", "triage_id": triage_id, "approved_by": req.approved_by}
