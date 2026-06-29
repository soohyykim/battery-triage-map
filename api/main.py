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
)
from services import triage as triage_svc
from services import matching as matching_svc

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
    return triage_svc.evaluate_battery(**req.model_dump())


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
    return matching_svc.match_companies(
        triage_result=req.triage_result,
        companies_df=companies,
        origin_latitude=req.origin_latitude,
        origin_longitude=req.origin_longitude,
        max_results=req.max_results,
    )


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
