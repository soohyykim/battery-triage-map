from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

class BatteryInput(BaseModel):
    battery_id: str = Field(..., description="諛고꽣由??앸퀎??)
    chemistry: Optional[str] = Field(None, description="?뷀븰怨?(NCM/LFP/NCA ??")
    soh: Optional[float] = Field(None, ge=0, le=100, description="State of Health (%)")
    voltage: Optional[float] = Field(None, description="?꾩븬 (V)")
    temperature: Optional[float] = Field(None, description="?쒕㈃ ?⑤룄 (??")
    swelling: Optional[bool] = Field(None, description="?멸? 遺????щ?")
    leakage: Optional[bool] = Field(None, description="?꾪빐???꾩텧 ?щ?")
    cycle_count: Optional[int] = Field(None, ge=0, description="異⑸갑???ъ씠????)
    region: Optional[str] = Field(None, description="諛곗텧 吏??(??援?援?")
    lat: Optional[float] = Field(None, description="諛곗텧 ?꾩튂 ?꾨룄")
    lon: Optional[float] = Field(None, description="諛곗텧 ?꾩튂 寃쎈룄")

class TriageRequest(BatteryInput): pass
class TriageResponse(BaseModel):
    battery_id: str
    risk_level: str = Field(..., description="?꾪뿕??(?뺤긽/二쇱쓽/?꾪뿕/湲닿툒)")
    triggered_rules: List[str] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)

class ScoreRequest(BatteryInput): pass
class ScoreResponse(BaseModel):
    battery_id: str
    chemistry: str
    grade: str
    risk_score: float
    recommended_route: str

class MatchRequest(BaseModel):
    battery_id: str
    chemistry: str
    grade: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    region: Optional[str] = None
    top_k: int = Field(3, ge=1, le=10)

class MatchedCompany(BaseModel):
    rank: int
    company_id: int
    name: str
    region: str
    handling_types: str
    distance_km: Optional[float] = None
    score: float

class MatchResponse(BaseModel):
    battery_id: str
    candidates: List[MatchedCompany] = Field(default_factory=list)

class ReportRequest(BaseModel):
    battery_id: str
    chemistry: str
    grade: str
    risk_level: Optional[str] = None
    question: Optional[str] = None

class ReportResponse(BaseModel):
    battery_id: str
    report: str
    sources: List[str] = Field(default_factory=list)
