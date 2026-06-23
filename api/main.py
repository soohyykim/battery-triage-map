"""
api/main.py - Battery Triage Map FastAPI ?붾뱶?ъ씤??4媛?  POST /triage  -> Rule Engine     (services/rule.py)      [???
  POST /score   -> ?깃툒 ?먯젙       (services/triage.py)    [?곗씠???붿??덉뼱]
  POST /match   -> 泥섎━湲곗뾽 留ㅼ묶   (services/matching.py)  [?곗씠???붿??덉뼱]
  POST /report  -> RAG 由ы룷??     (services/rag.py)       [諛깆뿏??AI]
?ㅽ뻾: uvicorn api.main:app --reload
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
    description="?꾧린李??ъ슜??諛고꽣由??꾪뿕?꽷룻솕?숆퀎 ?먯젙 諛?泥섎━湲곗뾽 留ㅼ묶 ?섏궗寃곗젙 吏??API",
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
        raise HTTPException(status_code=501, detail="services/rule.py 誘멸뎄??(W1)")
    return TriageResponse(battery_id=req.battery_id,
        risk_level=result.get("risk_level","誘몄젙"),
        triggered_rules=result.get("triggered_rules",[]),
        detail=result)

@app.post("/score", response_model=ScoreResponse, tags=["score"])
def score(req: ScoreRequest):
    try:
        from services import triage as triage_svc
        result = triage_svc.score(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/triage.py 誘멸뎄??(W1)")
    return ScoreResponse(battery_id=req.battery_id,
        chemistry=result.get("chemistry", req.chemistry or "UNKNOWN"),
        grade=result.get("grade","誘몄젙"),
        risk_score=result.get("risk_score",0.0),
        recommended_route=result.get("recommended_route","誘몄젙"))

@app.post("/match", response_model=MatchResponse, tags=["match"])
def match(req: MatchRequest):
    try:
        from services import matching
        candidates = matching.match(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/matching.py 誘멸뎄??(W1)")
    return MatchResponse(battery_id=req.battery_id, candidates=candidates)

@app.post("/report", response_model=ReportResponse, tags=["report"])
def report(req: ReportRequest):
    try:
        from services import rag
        result = rag.generate_report(req.model_dump())
    except (ImportError, AttributeError, NotImplementedError):
        raise HTTPException(status_code=501, detail="services/rag.py 誘멸뎄??(W2 ?댄썑)")
    return ReportResponse(battery_id=req.battery_id,
        report=result.get("report",""),
        sources=result.get("sources",[]))
