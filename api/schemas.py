"""
api/schemas.py
FastAPI 요청/응답 Pydantic 스키마 (엔드포인트 입출력 계약서).

데엔 모듈(services/triage.py · matching.py)의 실제 입출력에 맞춰 정의한다.
  · /triage : evaluate_battery() 입력/반환
  · /score  : evaluate_battery() 점수 요약
  · /match  : match_companies() 입력/반환
  · /report : 정책 RAG 리포트 (W2-3)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 공통: 배터리 입력 (/triage, /score) — evaluate_battery() 파라미터와 1:1 대응
# ---------------------------------------------------------------------------
class BatteryInput(BaseModel):
    vehicle_year: Optional[int] = Field(None, description="차량 연식")
    mileage_km: Optional[float] = Field(None, description="주행거리 (km)")
    capacity_kwh: Optional[float] = Field(None, description="배터리 용량 (kWh)")
    chemistry: str = Field("UNKNOWN", description="화학계 NCM / LFP / UNKNOWN")
    manufacturer: Optional[str] = Field(None, description="제조사")
    model_name: Optional[str] = Field(None, description="차량 모델명")
    battery_count: int = Field(1, ge=1, description="동일 조건 배터리 수량")
    current_year: Optional[int] = Field(None, description="기준 연도 (테스트용)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "vehicle_year": 2018, "mileage_km": 160000, "capacity_kwh": 64.0,
                "chemistry": "NCM", "manufacturer": "현대자동차", "model_name": "IONIQ5",
                "battery_count": 2,
            }
        }
    }


# ---------------------------------------------------------------------------
# POST /triage  -> evaluate_battery() 반환 구조 그대로
# ---------------------------------------------------------------------------
class TriageResponse(BaseModel):
    status: str
    result_type: str = Field(..., description="preliminary_estimate (법적 최종판정 아님)")
    input_summary: Dict[str, Any]
    soh_proxy_score: float
    reuse_score: float
    recycle_score: float
    grade: str = Field(..., description="Green / Yellow / Orange / Gray")
    recommended_path: str
    required_diagnostic_capability: str = Field(..., description="none / basic / kolas")
    collection_route: str
    data_confidence: float = Field(..., description="입력 완성도 0~1")
    reason_codes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /score  -> 잔존가치 점수 요약 (triage 결과의 점수 부분만)
# ---------------------------------------------------------------------------
class ScoreResponse(BaseModel):
    grade: str
    soh_proxy_score: float
    reuse_score: float
    recycle_score: float
    data_confidence: float


# ---------------------------------------------------------------------------
# POST /match  -> match_companies() 입력/반환
# ---------------------------------------------------------------------------
class MatchRequest(BaseModel):
    triage_result: Dict[str, Any] = Field(
        ..., description="evaluate_battery() 반환값 (/triage 응답 그대로 전달)"
    )
    origin_latitude: float = Field(..., description="배터리 발생 위치 위도")
    origin_longitude: float = Field(..., description="배터리 발생 위치 경도")
    max_results: int = Field(3, ge=1, le=10, description="추천 업체 수")


class MatchedCompany(BaseModel):
    rank: int
    company_id: Any
    company_name: str
    address: Optional[str] = None
    region: Optional[str] = None
    latitude: float
    longitude: float
    distance_km: float
    total_score: float
    license_type: Optional[str] = None
    process_type: Optional[str] = None
    diagnostic_capability: Optional[str] = None
    monthly_capacity_count: Optional[int] = None
    score_detail: Dict[str, float] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    status: str = Field(..., description="matched / no_match")
    input_summary: Dict[str, Any]
    matched_companies: List[MatchedCompany] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /report  -> 정책 RAG 리포트 (W2-3 에서 구현)
# ---------------------------------------------------------------------------
class ReportRequest(BaseModel):
    triage_result: Dict[str, Any] = Field(..., description="evaluate_battery() 반환값")
    matched_companies: Optional[List[Dict[str, Any]]] = Field(
        None, description="match_companies() 결과 (선택)"
    )
    question: Optional[str] = Field(None, description="자유 질의 (미지정 시 기본 리포트)")


class ReportResponse(BaseModel):
    report: str = Field(..., description="정책 RAG 기반 처리 가이드 리포트")
    sources: List[str] = Field(default_factory=list, description="참조 정책 문서 출처")
