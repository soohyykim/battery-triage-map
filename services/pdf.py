"""
services/pdf.py - PDF ?먮룞 諛쒓툒 2醫?(W3 ?꾩꽦 ?덉젙)
1) 諛고꽣由??먯젙 寃곌낵??/ 2) 泥섎━ 留ㅼ묶 ?뺤씤???쇱씠釉뚮윭由? fpdf2 | ?쒓? ?고듃: assets/NanumGothic.ttf
"""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")))
FONT_PATH = BASE_DIR / "assets" / "NanumGothic.ttf"
DISCLAIMER = "蹂?臾몄꽌???됱젙 李멸퀬?⑹씠硫??щ컮濡??쒖뒪???꾩옄?멸퀎?쒕? ?泥댄븯吏 ?딆뒿?덈떎."

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
    raise NotImplementedError("諛고꽣由??먯젙 寃곌낵??PDF??W3?먯꽌 援ы쁽")

def build_match_confirm(data: dict) -> str:
    raise NotImplementedError("泥섎━ 留ㅼ묶 ?뺤씤??PDF??W3?먯꽌 援ы쁽")
