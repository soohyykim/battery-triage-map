from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

class BatteryInput(BaseModel):
    battery_id: str = Field(..., description="배터리 식별자")
    chemistry: Optional[str] = Field(None, description="화학계 (NCM/LFP/NCA 등)")
    soh: Optional[float] = Field(None, ge=0, le=100, description="State of Health (%)")
    voltage: Optional[float] = Field(None, description="전압 (V)")
    temperature: Optional[float] = Field(None, description="표면 온도 (℃)")
    swelling: Optional[bool] = Field(None, description="외관 부풀음 여부")
    leakage: Optional[bool] = Field(None, description="전해액 누출 여부")
    cycle_count: Optional[int] = Field(None, ge=0, description="충방전 사이클 수")
    region: Optional[str] = Field(None, description="배출 지역 (시/군/구)")
    lat: Optional[float] = Field(None, description="배출 위치 위도")
    lon: Optional[float] = Field(None, description="배출 위치 경도")

class TriageRequest(BatteryInput): pass
class TriageResponse(BaseModel):
    battery_id: str
    risk_level: str = Field(..., description="위험도 (정상/주의/위험/긴급)")
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
