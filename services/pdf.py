"""
services/pdf.py - PDF 자동 발급 2종 (W3 완성 예정)
1) 배터리 판정 결과서 / 2) 처리 매칭 확인서
라이브러리: fpdf2 | 한글 폰트: assets/NanumGothic.ttf
"""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")))
FONT_PATH = BASE_DIR / "assets" / "NanumGothic.ttf"
DISCLAIMER = "본 문서는 행정 참고용이며 올바로 시스템 전자인계서를 대체하지 않습니다."

def _new_pdf():
    from fpdf import FPDF
    pdf = FPDF()
    if FONT_PATH.exists():
        pdf.add_font("Nanum", "", str(FONT_PATH))
        pdf.set_font("Nanum", size=12)
    else:
        pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    return pdf

def build_triage_report(data: dict) -> str:
    raise NotImplementedError("배터리 판정 결과서 PDF는 W3에서 구현")

def build_match_confirm(data: dict) -> str:
    raise NotImplementedError("처리 매칭 확인서 PDF는 W3에서 구현")
