"""
api/schemas.py
FastAPI 요청/응답 Pydantic 스키마 (엔드포인트 입출력 계약서).

데엔 모듈(services/triage.py · matching.py)의 실제 입출력에 맞춰 정의한다.
  · /triage : evaluate_battery() 입력/반환 (+ rule.py 지정폐기물 1차 선별)
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
class ConditionFlags(BaseModel):
    """rule.py check_designated_waste() 가 보는 외관 위험 5항목."""
    flooded: bool = False
    leakage: bool = False
    overheated: bool = False
    swollen: bool = False
    impact: bool = False


class BatteryInput(BaseModel):
    vin: Optional[str] = Field(None, description="차대번호 (관리 페이지 식별자로 사용)")
    vehicle_year: Optional[int] = Field(None, description="차량 연식")
    mileage_km: Optional[float] = Field(None, description="주행거리 (km)")
    capacity_kwh: Optional[float] = Field(None, description="배터리 용량 (kWh)")
    chemistry: str = Field("UNKNOWN", description="화학계 NCM / LFP / UNKNOWN")
    manufacturer: Optional[str] = Field(None, description="제조사")
    model_name: Optional[str] = Field(None, description="차량 모델명")
    battery_count: int = Field(1, ge=1, description="동일 조건 배터리 수량")
    current_year: Optional[int] = Field(None, description="기준 연도 (테스트용)")
    condition_flags: ConditionFlags = Field(
        default_factory=ConditionFlags,
        description="rule.py 1차 선별용 외관 위험 플래그 (침수/누액/과열/팽창/충격)",
    )

    model_config = {
        "protected_namespaces": (),  # model_name 이 예약어(model_)와 겹쳐 뜨는 경고 제거
        "json_schema_extra": {
            "example": {
                "vin": "KMHXX00XXX000001",
                "vehicle_year": 2018, "mileage_km": 160000, "capacity_kwh": 64.0,
                "chemistry": "NCM", "manufacturer": "현대자동차", "model_name": "IONIQ5",
                "battery_count": 2,
                "condition_flags": {
                    "flooded": False, "leakage": False, "overheated": False,
                    "swollen": False, "impact": False,
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# POST /triage  -> evaluate_battery() 반환 구조 (+ rule.py 분기 시 동일 형태로 맞춤)
# ---------------------------------------------------------------------------
class TriageResponse(BaseModel):
    status: str
    result_type: str = Field(..., description="preliminary_estimate (법적 최종판정 아님)")
    input_summary: Dict[str, Any]
    soh_proxy_score: Optional[float] = None
    capacity_score: Optional[float] = Field(
        None, description="배터리 용량 기반 점수 (evaluate_battery() 산출값)"
    )
    mineral_value_score: Optional[float] = Field(
        None, description="화학계별 광물 회수 가치 점수 (KOMIR 가격 반영)"
    )
    reuse_score: Optional[float] = None
    recycle_score: Optional[float] = None
    grade: str = Field(..., description="Green / Yellow / Orange / Gray / Red")
    recommended_path: str
    required_diagnostic_capability: str = Field(..., description="none / basic / kolas")
    collection_route: str
    data_confidence: Optional[float] = Field(None, description="입력 완성도 0~1")
    mineral_price_source: Optional[str] = Field(
        None, description="api / fallback_default / api_partial_fallback / external 등 (KOMIR 가격 출처)"
    )
    mineral_price_scores_used: Optional[Dict[str, float]] = Field(
        None, description="실제 반영된 LITHIUM/NICKEL/COBALT 0~100 정규화 점수"
    )
    reason_codes: List[str] = Field(default_factory=list)
    triage_id: Optional[int] = Field(
        None, description="DB에 저장된 판정 이력 id (/match·관리페이지에서 사용)"
    )


# ---------------------------------------------------------------------------
# POST /score  -> 잔존가치 점수 요약 (triage 결과의 점수 부분만)
# ---------------------------------------------------------------------------
class ScoreResponse(BaseModel):
    grade: str
    soh_proxy_score: Optional[float] = None
    reuse_score: Optional[float] = None
    recycle_score: Optional[float] = None
    data_confidence: Optional[float] = None


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
    triage_id: Optional[int] = Field(
        None, description="연결할 판정 이력 id (/triage 응답의 triage_id). 주면 매칭 이력 저장"
    )


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


# ---------------------------------------------------------------------------
# GET /history  -> 배터리 관리 페이지 (판정 이력)
# ---------------------------------------------------------------------------
class HistoryItem(BaseModel):
    """판정 이력 목록 1행. DB triage_history 컬럼과 대응 (extra 허용으로 유연)."""
    id: int
    vin: Optional[str] = None
    created_at: Optional[str] = None
    manufacturer: Optional[str] = None
    model_name: Optional[str] = None
    vehicle_year: Optional[int] = None
    mileage_km: Optional[float] = None
    capacity_kwh: Optional[float] = None
    chemistry: Optional[str] = None
    battery_count: Optional[int] = None
    soh_proxy_score: Optional[float] = None
    capacity_score: Optional[float] = None
    mineral_value_score: Optional[float] = None
    reuse_score: Optional[float] = None
    recycle_score: Optional[float] = None
    data_confidence: Optional[float] = None
    grade: Optional[str] = None
    recommended_path: Optional[str] = None
    required_diagnostic_capability: Optional[str] = None
    collection_route: Optional[str] = None
    mineral_price_source: Optional[str] = None
    mineral_price_scores_used: Optional[str] = Field(
        None, description="JSON 문자열로 저장된 LITHIUM/NICKEL/COBALT 점수"
    )
    reason_codes: Optional[str] = None
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    matched_company_name: Optional[str] = Field(
        None, description="match_history 1순위(rank=1) 업체명 LEFT JOIN 결과"
    )

    model_config = {"extra": "allow", "protected_namespaces": ()}


class HistoryDetail(HistoryItem):
    """판정 1건 + 연결된 매칭 결과."""
    matched_companies: List[Dict[str, Any]] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    approved_by: str = Field(..., description="승인 담당자 이름/ID")


class HistoryDeleteRequest(BaseModel):
    """POST /history/delete 요청 바디 — 일괄 삭제할 triage_history id 목록."""
    triage_ids: List[int] = Field(..., description="삭제할 triage_history id 목록")


# ---------------------------------------------------------------------------
# POST /pdf/*  -> PDF 발급 (판정 결과서 · 매칭 확인서)
# ---------------------------------------------------------------------------
class PdfTriageRequest(BaseModel):
    triage_result: Dict[str, Any] = Field(..., description="evaluate_battery() 반환값 (/triage 응답)")


class PdfMatchRequest(BaseModel):
    triage_result: Dict[str, Any] = Field(..., description="evaluate_battery() 반환값")
    matched_companies: Optional[List[Dict[str, Any]]] = Field(
        None, description="match_companies() 결과의 matched_companies (/match 응답)"
    )
