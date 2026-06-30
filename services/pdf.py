"""
services/pdf.py - PDF 자동 발급 2종 (백엔드/AI 담당)
  1) build_triage_report(triage_result)        -> 배터리 예비 판정 결과서
  2) build_match_confirm({triage_result,...})  -> 처리기업 매칭 확인서

라이브러리: fpdf2 | 한글 폰트: assets/NanumGothic.ttf
반환: 생성된 PDF 파일 경로(str). outputs/ 에 저장된다.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")))
FONT_PATH = BASE_DIR / "assets" / "NanumGothic.ttf"
DISCLAIMER = (
    "본 문서는 입력값 기반 예비 추정 결과이며, 법적 지위(순환자원/폐기물)와 최종 처리경로는 "
    "처리업체 실측 진단 이후 확정됩니다. 행정 참고용이며 올바로 시스템 전자인계서를 대체하지 않습니다."
)

FONT = "Nanum"  # 한글 폰트 alias (없으면 Helvetica 로 대체)

# 등급별 색상 (R,G,B)
_GRADE_COLOR = {
    "Green": (34, 139, 34),
    "Yellow": (200, 160, 0),
    "Orange": (216, 110, 20),
    "Gray": (110, 110, 110),
}
# 처리방향 한글 표기
_PATH_KO = {
    "reuse_candidate": "재사용 후보",
    "reuse_or_recycle_after_diagnosis": "진단 후 재사용/재활용",
    "recycle_candidate": "재활용 후보",
    "diagnosis_required": "정밀 진단 필요",
    "designated_waste": "지정폐기물 처리",
}


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _new_pdf() -> FPDF:
    """한글 폰트가 등록된 새 PDF(A4) 한 장을 만든다."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    if FONT_PATH.exists():
        pdf.add_font(FONT, "", str(FONT_PATH))
        base_font = FONT
    else:
        base_font = "Helvetica"  # 폰트 없으면 영문 대체(한글 깨짐)
    pdf.add_page()
    pdf.set_font(base_font, size=11)
    pdf._base_font = base_font  # 이후 헬퍼들이 참조
    return pdf


def _font(pdf: FPDF) -> str:
    return getattr(pdf, "_base_font", "Helvetica")


def _title(pdf: FPDF, text: str) -> None:
    pdf.set_font(_font(pdf), size=18)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 12, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font(_font(pdf), size=9)
    pdf.set_text_color(120, 120, 120)
    issued = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(0, 6, f"발급일시 {issued}  |  Battery Triage Map",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(4)
    pdf.set_text_color(0, 0, 0)


def _section(pdf: FPDF, text: str) -> None:
    pdf.ln(2)
    pdf.set_font(_font(pdf), size=13)
    pdf.set_fill_color(235, 240, 248)
    pdf.cell(0, 9, f"  {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.ln(1)
    pdf.set_font(_font(pdf), size=11)


def _row(pdf: FPDF, label: str, value: Any, value_color: tuple | None = None) -> None:
    """라벨(왼쪽 50) + 값(오른쪽) 한 줄."""
    pdf.set_font(_font(pdf), size=10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(50, 7, f"  {label}", border=0)
    pdf.set_text_color(*(value_color or (0, 0, 0)))
    pdf.set_font(_font(pdf), size=11)
    pdf.cell(0, 7, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)


def _disclaimer(pdf: FPDF) -> None:
    pdf.ln(4)
    pdf.set_font(_font(pdf), size=8)
    pdf.set_text_color(130, 130, 130)
    pdf.multi_cell(0, 5, f"[주의사항] {DISCLAIMER}")
    pdf.set_text_color(0, 0, 0)


def _save(pdf: FPDF, prefix: str) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{prefix}_{stamp}.pdf"
    pdf.output(str(path))
    return str(path)


def _fmt(value: Any, suffix: str = "") -> str:
    """None 안전 표기."""
    if value is None or value == "":
        return "-"
    return f"{value}{suffix}"


# ---------------------------------------------------------------------------
# 1) 배터리 예비 판정 결과서
# ---------------------------------------------------------------------------
def build_triage_report(data: dict) -> str:
    """triage_result(dict)를 받아 판정 결과서 PDF를 만들고 파일 경로를 반환한다."""
    s = data.get("input_summary", {}) or {}
    grade = data.get("grade", "-")
    grade_color = _GRADE_COLOR.get(grade)
    path_ko = _PATH_KO.get(data.get("recommended_path", ""), data.get("recommended_path", "-"))

    pdf = _new_pdf()
    _title(pdf, "배터리 예비 판정 결과서")

    _section(pdf, "입력 정보")
    _row(pdf, "제조사 / 모델", f"{_fmt(s.get('manufacturer'))} / {_fmt(s.get('model_name'))}")
    _row(pdf, "차량 연식", _fmt(s.get("vehicle_year"), "년"))
    _row(pdf, "주행거리", _fmt(s.get("mileage_km"), " km"))
    _row(pdf, "배터리 용량", _fmt(s.get("capacity_kwh"), " kWh"))
    _row(pdf, "화학계", _fmt(s.get("chemistry")))
    _row(pdf, "수량", _fmt(s.get("battery_count"), " 개"))

    _section(pdf, "판정 결과")
    _row(pdf, "등급", grade, value_color=grade_color)
    _row(pdf, "예비 처리방향", path_ko)
    _row(pdf, "SOH Proxy 점수", _fmt(data.get("soh_proxy_score"), " 점"))
    _row(pdf, "재사용 점수", _fmt(data.get("reuse_score"), " 점"))
    _row(pdf, "재활용 점수", _fmt(data.get("recycle_score"), " 점"))
    _row(pdf, "필요 진단역량", _fmt(data.get("required_diagnostic_capability")))
    _row(pdf, "수거 루트", _fmt(data.get("collection_route")))
    _row(pdf, "입력 신뢰도", _fmt(data.get("data_confidence")))

    reasons = data.get("reason_codes") or []
    if reasons:
        _section(pdf, "판단 근거 코드")
        pdf.set_font(_font(pdf), size=9)
        pdf.set_text_color(70, 70, 70)
        pdf.multi_cell(0, 5, ", ".join(reasons))
        pdf.set_text_color(0, 0, 0)

    _disclaimer(pdf)
    return _save(pdf, "triage_report")


# ---------------------------------------------------------------------------
# 2) 처리기업 매칭 확인서
# ---------------------------------------------------------------------------
def build_match_confirm(data: dict) -> str:
    """
    매칭 결과를 받아 확인서 PDF를 만들고 파일 경로를 반환한다.
    data 예: {"triage_result": {...}, "matched_companies": [...]}
             또는 /match 응답({"input_summary":..., "matched_companies":...}) 그대로.
    """
    triage = data.get("triage_result", data) or {}
    s = triage.get("input_summary", data.get("input_summary", {})) or {}
    companies = data.get("matched_companies", []) or []

    pdf = _new_pdf()
    _title(pdf, "처리기업 매칭 확인서")

    _section(pdf, "대상 배터리")
    _row(pdf, "등급", _fmt(triage.get("grade")),
         value_color=_GRADE_COLOR.get(triage.get("grade")))
    _row(pdf, "화학계", _fmt(s.get("chemistry")))
    _row(pdf, "수량", _fmt(s.get("battery_count"), " 개"))

    _section(pdf, f"추천 처리기업 (총 {len(companies)}곳)")
    if not companies:
        pdf.set_text_color(150, 60, 60)
        pdf.cell(0, 8, "  조건을 만족하는 처리기업이 없습니다.",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
    else:
        headers = [("순위", 14), ("업체명", 58), ("거리(km)", 24),
                   ("점수", 20), ("처리유형", 30), ("진단역량", 28)]
        pdf.set_font(_font(pdf), size=9)
        pdf.set_fill_color(225, 230, 238)
        for text, w in headers:
            pdf.cell(w, 8, text, border=1, align="C", fill=True)
        pdf.ln()
        for c in companies:
            pdf.set_font(_font(pdf), size=9)
            pdf.cell(14, 8, str(c.get("rank", "-")), border=1, align="C")
            pdf.cell(58, 8, _fmt(c.get("company_name")), border=1)
            pdf.cell(24, 8, _fmt(c.get("distance_km")), border=1, align="R")
            pdf.cell(20, 8, _fmt(c.get("total_score")), border=1, align="R")
            pdf.cell(30, 8, _fmt(c.get("process_type")), border=1, align="C")
            pdf.cell(28, 8, _fmt(c.get("diagnostic_capability")), border=1, align="C")
            pdf.ln()

    _disclaimer(pdf)
    return _save(pdf, "match_confirm")
