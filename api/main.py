"""
api/main.py - Battery Triage Map FastAPI 엔드포인트 4개
  POST /triage  -> Rule Engine     (services/rule.py)      [팀장]
  POST /score   -> 등급 판정       (services/triage.py)    [데이터 엔지니어]
  POST /match   -> 처리기업 매칭   (services/matching.py)  [데이터 엔지니어]
  POST /report  -> RAG 리포트      (services/rag.py)       [백엔드/AI]
실행: uvicorn api.main:app --reload
"""
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from api.schemas import (
    TriageRequest, TriageResponse,
    ScoreRequest, ScoreResponse,
    MatchRequest, MatchResponse,
    ReportRequest, ReportResponse,
)

app = FastAPI(
    title="Battery Triage Map API",
    description="전기차 사용후 배터리 위험도·화학계 판정 및 처리기업 매칭 의사결정 지원 API",
    version="0.1.0",
)

@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "battery-triage-map", "version": "0.1.0"}

@app.post("/triage", response_model=TriageResponse, tags=["triage"])
def triage(req: TriageRequest):
    try:
        from services import rule
        result = rule.run(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/rule.py 미구현 (W1)")
    return TriageResponse(battery_id=req.battery_id,
        risk_level=result.get("risk_level","미정"),
        triggered_rules=result.get("triggered_rules",[]),
        detail=result)

@app.post("/score", response_model=ScoreResponse, tags=["score"])
def score(req: ScoreRequest):
    try:
        from services import triage as triage_svc
        result = triage_svc.score(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/triage.py 미구현 (W1)")
    return ScoreResponse(battery_id=req.battery_id,
        chemistry=result.get("chemistry", req.chemistry or "UNKNOWN"),
        grade=result.get("grade","미정"),
        risk_score=result.get("risk_score",0.0),
        recommended_route=result.get("recommended_route","미정"))

@app.post("/match", response_model=MatchResponse, tags=["match"])
def match(req: MatchRequest):
    try:
        from services import matching
        candidates = matching.match(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/matching.py 미구현 (W1)")
    return MatchResponse(battery_id=req.battery_id, candidates=candidates)

@app.post("/report", response_model=ReportResponse, tags=["report"])
def report(req: ReportRequest):
    try:
        from services import rag
        result = rag.generate_report(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/rag.py 미구현 (W2 이후)")
    return ReportResponse(battery_id=req.battery_id,
        report=result.get("report",""),
        sources=result.get("sources",[]))
