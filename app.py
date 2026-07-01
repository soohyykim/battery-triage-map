"""
Battery Triage Map - 모바일 비율 + 사이드바 개선 + 관리페이지 표 형태 버전

변경 사항:
- layout="centered" + max-width 480px → 모바일 비율 고정
- 헤더 sticky 고정 (스크롤해도 상단에 유지)
- 카드 바깥 큰 박스 제거, 번호별 카드만 노출
- 사이드바 글씨 안 보이는 버그 수정
- 사이드바 메뉴 항목 박스 분리 + 로그인 더미 정보 표시
- 배터리 관리 페이지: 발생채널 필터 제거(로그인 시 자동),
  요약 카드 중첩 구조(큰 박스 안 작은 박스 7개, 상태명 위/숫자 아래),
  배터리 리스트를 카드 → 표(dataframe) 형태로 변경
"""

import streamlit as st
import json
from datetime import datetime
import cv2
import numpy as np
from PIL import Image
import pandas as pd
import requests

from battery_data import (
    fetch_batteries,
    fetch_battery_detail,
    update_battery_status,
    get_channel_list,
    get_status_counts,
    batteries_to_table_rows,
    style_battery_table,
    ALL_STATUSES,
    STATUS_COLOR,
    GRADE_EMOJI,
    DUMMY_USER,
    API_BASE_URL,
)

# ---------------------------------------------------------------------------
# 페이지 설정 (전체 화면 확장)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="사용후 배터리 접수 | EV Battery Intake",
    page_icon="🔋",
    layout="wide",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

        :root {
            --c-background: #f6f9fb;
            --c-foreground: #0b1c2c;
            --c-card: #ffffff;
            --c-primary: #142f4b;
            --c-primary-foreground: #f6f9fb;
            --c-secondary: #e9f0f5;
            --c-secondary-foreground: #142a41;
            --c-muted: #e9f0f5;
            --c-muted-foreground: #576574;
            --c-accent: #00b5b5;
            --c-accent-foreground: #071727;
            --c-destructive: #e62d28;
            --c-warning: #f3821d;
            --c-warning-foreground: #071727;
            --c-border: #d8dfe6;
            --c-input: #dfe5ec;
        }

        html, body, [class*="css"] {
            font-family: "Pretendard", "Inter", system-ui, sans-serif;
        }

        .stApp {
            background-color: var(--c-background);
        }

        /* 전체 화면 폭 사용 (모바일 제한 해제) */
        .block-container {
            max-width: 1200px !important;
            padding-top: 1rem !important;
            padding-left: 0px !important;
            padding-right: 0px !important;
        }

        /* ---------- 헤더 (fixed 고정) ----------
           이전에 JS(getBoundingClientRect)로 동적 정렬을 시도했으나,
           Streamlit은 st.markdown(unsafe_allow_html=True) 안의 <script>를
           보안 정책상 실행하지 않아 전혀 작동하지 않았음.
           따라서 순수 CSS 고정값으로 전환: Streamlit 사이드바 기본 폭(21rem)과
           .block-container의 max-width(1100px) + 좌우 padding(24px)을 그대로
           계산해 헤더 위치/폭을 고정값으로 지정. */
        /* ---------- 헤더 (sticky 고정) ----------
           이전에 두 가지 방식을 시도했으나 모두 실패:
           1) JS(getBoundingClientRect) 동적 정렬 → Streamlit이
              st.markdown(unsafe_allow_html=True) 안의 <script>를 보안 정책상
              실행하지 않아 작동하지 않음.
           2) position: fixed + calc(21rem + ...) 고정값 계산 → 사이드바 실제
              렌더링 폭이 21rem과 정확히 일치하지 않거나(폰트/스크롤바 등 영향),
              fixed 요소는 100vw 기준이라 block-container의 실제 렌더링 폭과
              근본적으로 별개의 좌표계라 페이지마다 미세하게 어긋남.
           최종 해결: 헤더를 fixed로 따로 띄우지 않고, block-container 안의
           일반 흐름 요소로 두되 position: sticky로 상단 고정. 이렇게 하면
           헤더가 카드들과 똑같은 부모(block-container) 안에서 동일한 폭을
           그대로 상속받으므로 구조적으로 어긋날 수가 없음. */
        .triage-header {
            background-color: var(--c-primary);
            border-radius: 14px;
            padding: 14px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.10);
            position: sticky;
            top: 1rem;
            width: 100%;
            box-sizing: border-box;
            z-index: 999;
            margin-bottom: 16px;
        }
        .triage-header-left {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }
        .triage-logo-box {
            background-color: rgba(0,181,181,0.20);
            border: 1px solid rgba(0,181,181,0.40);
            border-radius: 10px;
            width: 34px;
            height: 34px;
            min-width: 34px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        }
        .triage-header-text-sub {
            color: rgba(246,249,251,0.70);
            font-size: 10px;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .triage-header-text-main {
            color: var(--c-primary-foreground);
            font-size: 13px;
            font-weight: 700;
            margin: 0;
        }
        .triage-channel-badge {
            background-color: rgba(0,181,181,0.15);
            border: 1px solid rgba(0,181,181,0.30);
            color: var(--c-accent);
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.02em;
            padding: 4px 9px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .triage-header-user {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
        }
        .triage-header-user-name {
            color: rgba(255,255,255,0.95);
            font-size: 12px;
            font-weight: 600;
        }
        .triage-header-user-channel {
            color: rgba(255,255,255,0.55);
            font-size: 10px;
        }

        /* ---------- 카드(번호 섹션)만 남기고 바깥 큰 박스 제거 ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 12px !important;
            margin-bottom: 14px;
            background-color: var(--c-card);
            border: 1.5px solid var(--c-border) !important;
            padding: 16px !important;
            box-shadow: none !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }
        /* Streamlit이 카드를 감싸는 상위 element-container에 거터(margin/padding)를
           추가로 붙이는 경우가 있어, 헤더와 폭이 미세하게 어긋나 보임 → 0으로 강제 */
        div[data-testid="stVerticalBlockBorderWrapper"] > div {
            width: 100% !important;
        }
        .block-container > div[data-testid="stVerticalBlock"] {
            width: 100% !important;
            gap: 0 !important;
        }

        /* ---------- 섹션 타이틀 ---------- */
        .section-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
            gap: 10px;
        }
        .section-title-left {
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
            flex: 1;
        }
        .section-num {
            background-color: var(--c-primary);
            color: var(--c-primary-foreground);
            font-weight: 700;
            font-size: 11px;
            width: 26px;
            height: 26px;
            min-width: 26px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .section-num-alert {
            background-color: var(--c-warning);
            color: var(--c-warning-foreground);
        }
        .section-title-text {
            font-size: 14px;
            font-weight: 700;
            color: var(--c-foreground);
            margin: 0;
            word-break: keep-all;
        }
        .section-desc {
            color: var(--c-muted-foreground);
            font-size: 11px;
            margin: 2px 0 0 0;
            line-height: 1.4;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 10px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .status-badge-ok {
            background-color: var(--c-secondary);
            color: var(--c-secondary-foreground);
        }
        .status-badge-alert {
            background-color: var(--c-warning);
            color: var(--c-warning-foreground);
        }

        /* 메트릭 카드 */
        .info-card {
            background-color: var(--c-secondary);
            border: 1px solid var(--c-border);
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 10px;
            line-height: 1.6;
        }
        .info-card-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 10px;
        }
        .info-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .info-label {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            color: var(--c-muted-foreground);
        }
        .info-value {
            font-size: 13px;
            font-weight: 600;
            color: var(--c-foreground);
            word-break: break-word;
        }

        /* 필수 표시 */
        .req-star { color: var(--c-destructive); font-weight: 700; }
        .field-label {
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            color: var(--c-muted-foreground);
            margin-bottom: 4px;
        }

        /* CTA 버튼 */
        div.stButton > button {
            background-color: var(--c-primary);
            color: var(--c-primary-foreground);
            font-size: 14px;
            font-weight: 700;
            padding: 12px 0;
            border-radius: 12px;
            border: none;
            width: 100%;
            box-shadow: 0 4px 10px rgba(20,47,75,0.20);
        }
        div.stButton > button:hover {
            filter: brightness(1.12);
            color: var(--c-primary-foreground);
        }

        /* pills */
        div[data-testid="stPills"] {
            gap: 6px;
        }
        div[data-testid="stPills"] label {
            border: 1.5px solid var(--c-border) !important;
            border-radius: 10px !important;
            padding: 12px 4px !important;
            background-color: var(--c-card) !important;
            transition: all 0.15s ease;
        }
        div[data-testid="stPills"] label[aria-checked="true"] {
            border-color: var(--c-warning) !important;
            background-color: var(--c-warning) !important;
            color: var(--c-warning-foreground) !important;
        }

        .footer-note {
            text-align: center;
            font-size: 10px;
            color: var(--c-muted-foreground);
            margin-top: 18px;
        }

        .qr-scan-section {
            background-color: var(--c-secondary);
            border: 2px dashed var(--c-accent);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 14px;
            text-align: center;
            font-size: 13px;
        }

        /* ===================================================================
           사이드바 — .streamlit/config.toml의 [theme.sidebar]가 기본 배경/글자색을
           네이티브로 처리함 (Streamlit 공식 기능, 버전에 안전). 아래 CSS는 로고/
           로그인박스 등 커스텀 요소와 버튼 호버 효과 등 디테일만 보강.
           =================================================================== */
        /* ===================================================================
           사이드바 — 안쪽 모든 wrapper의 배경을 투명하게 만들어
           "흰 박스 안에 흰 글씨" 같은 색 충돌이 원천적으로 불가능하게 함
           (Claude 사이드바처럼 박스 구분 없이 배경이 쭉 이어지는 방식)
           =================================================================== */
        section[data-testid="stSidebar"] {
            background-color: #142f4b !important;
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        section[data-testid="stSidebar"] > div {
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            border: none !important;
            box-shadow: none !important;
            outline: none !important;
        }
        section[data-testid="stSidebar"] * {
            background-color: transparent !important;
            border-color: transparent !important;
        }
        /* 위 전체 투명화 규칙(specificity 0-1-1)보다 우선순위를 확보하기 위해
           "section[data-testid=stSidebar] .클래스명" 형태로 동일하게 구체적인
           선택자를 사용해, 의도적으로 색을 넣어야 하는 요소들만 다시 복원 */
        section[data-testid="stSidebar"] .sidebar-logo-box {
            background-color: rgba(0,181,181,0.20) !important;
            border-color: rgba(0,181,181,0.40) !important;
        }
        section[data-testid="stSidebar"] .sidebar-login-box {
            background-color: rgba(255,255,255,0.08) !important;
            border-color: rgba(255,255,255,0.15) !important;
        }
        section[data-testid="stSidebar"] .sidebar-login-avatar {
            background-color: var(--c-accent) !important;
        }
        section[data-testid="stSidebar"] .sidebar-logo {
            border-bottom-color: rgba(255,255,255,0.15) !important;
        }
        section[data-testid="stSidebar"] .block-container {
            max-width: none;
            padding: 16px 12px;
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 32px);
        }

        /* 외관 상태 점검 pills 크기 조정 */
        div[data-testid="stPills"] button {
            padding: 4px 12px !important;
            font-size: 12px !important;
            min-height: 30px !important;
        }

        .sidebar-group-label {
            font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
            color: rgba(255,255,255,0.35); text-transform: uppercase;
            padding: 10px 4px 5px 4px;
        }
        .sidebar-divider {
            border-top: 1px solid rgba(255,255,255,0.10);
            margin: 10px 0 4px 0;
        }
        .sidebar-info-row {
            font-size: 12px; color: rgba(255,255,255,0.65);
            padding: 2px 4px; line-height: 1.9;
        }
        .sidebar-menu-disabled {
            padding: 8px 12px; border-radius: 8px;
            opacity: 0.35; font-size: 13px; font-weight: 600; color: #fff;
            cursor: not-allowed;
        }
        .sidebar-logo {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 4px 4px 16px 4px;
            border-bottom: 1px solid rgba(255,255,255,0.15) !important;
            margin-bottom: 14px;
        }
        .sidebar-logo-box {
            background-color: rgba(0,181,181,0.20) !important;
            border: 1px solid rgba(0,181,181,0.40) !important;
            border-radius: 10px;
            width: 34px;
            height: 34px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        }
        .sidebar-logo-text {
            font-size: 13px;
            font-weight: 700;
            color: #ffffff !important;
        }

        .sidebar-login-box {
            background-color: rgba(255,255,255,0.08) !important;
            border: 1px solid rgba(255,255,255,0.15) !important;
            border-radius: 10px;
            padding: 10px 12px;
            margin-top: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .sidebar-login-avatar {
            width: 28px;
            height: 28px;
            min-width: 28px;
            border-radius: 50%;
            background-color: var(--c-accent) !important;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
            color: #071727 !important;
        }
        .sidebar-login-name {
            font-size: 12px;
            font-weight: 700;
            color: #ffffff !important;
            margin: 0;
        }
        .sidebar-login-sub {
            font-size: 10px;
            color: rgba(255,255,255,0.6) !important;
            margin: 0;
        }

        /* 사이드바 메뉴 버튼 — 텍스트 색상 통일, active는 배경으로만 구분 */
        section[data-testid="stSidebar"] div.stButton button,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button {
            background-color: transparent !important;
            color: rgba(255,255,255,0.85) !important;
            text-align: left !important;
            justify-content: flex-start !important;
            box-shadow: none !important;
            font-weight: 500 !important;
            font-size: 13px !important;
            border: none !important;
            outline: none !important;
            border-radius: 6px !important;
            padding: 8px 12px !important;
            margin-bottom: 2px;
            transition: background-color 0.15s ease;
        }
        section[data-testid="stSidebar"] div.stButton button p,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button p {
            color: rgba(255,255,255,0.85) !important;
            font-weight: 500 !important;
        }
        section[data-testid="stSidebar"] div.stButton button:hover,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
            background-color: rgba(255,255,255,0.08) !important;
        }
        section[data-testid="stSidebar"] div.stButton button:focus,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:focus,
        section[data-testid="stSidebar"] div.stButton button:active,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:active,
        section[data-testid="stSidebar"] div.stButton button:focus-visible,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:focus-visible {
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            background-color: rgba(255,255,255,0.08) !important;
            color: rgba(255,255,255,0.85) !important;
        }
        section[data-testid="stSidebar"] div.stButton,
        section[data-testid="stSidebar"] div[data-testid="stButton"],
        section[data-testid="stSidebar"] div[data-testid="element-container"] {
            border: none !important;
            box-shadow: none !important;
        }

        .sidebar-bottom-spacer {
            flex-grow: 1;
        }

        /* ===================================================================
           배터리 관리 페이지
           =================================================================== */
        .summary-outer {
            background-color: var(--c-card);
            border: 1.5px solid var(--c-border);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 14px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
        }
        @media (max-width: 900px) {
            .summary-grid {
                grid-template-columns: repeat(3, 1fr);
            }
        }
        @media (max-width: 480px) {
            .summary-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        .summary-inner-box {
            background-color: var(--c-secondary);
            border: 1px solid var(--c-border);
            border-radius: 10px;
            padding: 14px 8px;
            text-align: center;
        }
        .summary-inner-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--c-muted-foreground);
            margin-bottom: 6px;
        }
        .summary-inner-count {
            font-size: 22px;
            font-weight: 700;
            color: var(--c-foreground);
        }

        .table-status-pill {
            display: inline-block;
            font-size: 10px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 999px;
            color: white;
            white-space: nowrap;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "intake"  # "intake" | "battery_list"
if "step" not in st.session_state:
    st.session_state.step = "input"
if "intake_record" not in st.session_state:
    st.session_state.intake_record = None
if "triage_result" not in st.session_state:
    st.session_state.triage_result = None
if "matching_result" not in st.session_state:
    st.session_state.matching_result = None
if "channel_name" not in st.session_state:
    st.session_state.channel_name = DUMMY_USER["channel_name"]
if "channel_type" not in st.session_state:
    st.session_state.channel_type = DUMMY_USER["channel_type"]
if "scanned_vin" not in st.session_state:
    st.session_state.scanned_vin = None
if "selected_battery_id" not in st.session_state:
    st.session_state.selected_battery_id = None
if "show_detail_panel" not in st.session_state:
    st.session_state.show_detail_panel = False

# ---------------------------------------------------------------------------
# 사이드바 — 로고 / 메뉴 그룹 / 로그인 정보
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-logo">
            <div class="sidebar-logo-box">🔋</div>
            <div class="sidebar-logo-text">Battery Triage Map</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    is_intake = st.session_state.page == "intake"
    is_list   = st.session_state.page == "battery_list"

    # ── 접수 관리 그룹 ──────────────────────────────
    st.markdown(
        '<div class="sidebar-group-label">접수 관리</div>',
        unsafe_allow_html=True,
    )

    if st.button("배터리 등록", use_container_width=True, key="nav_intake"):
        st.session_state.page = "intake"
        st.session_state.step = "input"
        st.rerun()

    if st.button("배터리 관리", use_container_width=True, key="nav_list"):
        st.session_state.page = "battery_list"
        st.rerun()

    # ── 채널 정보 + 설정 (흐리게) ───────────────────
    st.markdown(
        f"""
        <div class="sidebar-divider"></div>
        <div class="sidebar-group-label">채널 정보</div>
        <div class="sidebar-info-row">{DUMMY_USER['channel_name']}</div>
        <div class="sidebar-info-row">{DUMMY_USER['channel_type']}</div>
        <div class="sidebar-divider"></div>
        <div class="sidebar-group-label">설정</div>
        <div class="sidebar-menu-disabled">발생채널 설정</div>
        <div class="sidebar-menu-disabled">통계 / 리포트</div>
        """,
        unsafe_allow_html=True,
    )
    user_initial = DUMMY_USER["name"][0]


# ---------------------------------------------------------------------------
# QR/바코드 디코딩 함수
# ---------------------------------------------------------------------------
def decode_barcode(image):
    """이미지에서 QR코드 디코딩 (OpenCV 내장 디코더 사용 — 별도 DLL 불필요)"""
    try:
        img_array = np.array(image)

        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        else:
            img_cv = img_array

        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(img_cv)

        if data:
            return [{"type": "QRCODE", "data": data}]
        return None
    except Exception as e:
        st.error(f"디코딩 오류: {str(e)}")
        return None


# ---------------------------------------------------------------------------
# 배터리 상세보기 모달 (st.dialog — 화면 중앙에 바로 뜨므로 스크롤 이동 불필요)
# ---------------------------------------------------------------------------
@st.dialog("배터리 상세 정보")
def show_battery_detail_dialog(battery_id):
    detail = fetch_battery_detail(battery_id)
    if not detail:
        st.error("배터리 정보를 찾을 수 없습니다.")
        return

    st.markdown(f"**🔍 {detail['vin']}**")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.metric("등급", f"{GRADE_EMOJI.get(detail['grade'], '—')} {detail['grade'] or '미판정'}")
    with d2:
        st.metric("SOH Proxy", f"{detail['soh_proxy_score']}%" if detail['soh_proxy_score'] else "—")
    with d3:
        st.metric("현재 상태", detail["status"])

    st.markdown("**상태 변경 (테스트용 — 더미 데이터에만 적용됨)**")
    new_status = st.selectbox(
        "변경할 상태",
        ALL_STATUSES[1:],
        index=ALL_STATUSES[1:].index(detail["status"]) if detail["status"] in ALL_STATUSES[1:] else 0,
        key="new_status_select",
    )

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("✅ 상태 변경 적용", use_container_width=True, type="primary"):
            update_battery_status(detail["id"], new_status)
            st.success(f"상태가 '{new_status}'(으)로 변경되었습니다.")
            st.session_state.show_detail_panel = False
            st.rerun()
    with col_s2:
        if st.button("닫기", use_container_width=True):
            st.session_state.show_detail_panel = False
            st.rerun()


# ===========================================================================
# 페이지 분기: 배터리 접수 (intake) vs 배터리 관리 (battery_list)
# ===========================================================================

if st.session_state.page == "battery_list":
    # =======================================================================
    # 배터리 관리 페이지
    # =======================================================================
    st.markdown(
        f"""
        <div class="triage-header">
            <div class="triage-header-left">
                <div class="triage-logo-box">📋</div>
                <div>
                    <p class="triage-header-text-sub">보유 배터리 현황</p>
                    <p class="triage-header-text-main">배터리 관리</p>
                </div>
            </div>
            <div class="triage-header-user">
                <span class="triage-header-user-name">{DUMMY_USER['name']} 님</span>
                <span class="triage-header-user-channel">{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- 데이터 로드 ---
    channel_filter = DUMMY_USER["channel_name"]
    counts = get_status_counts(channel_name=channel_filter)
    batteries = fetch_batteries(channel_name=channel_filter)

    import json as _json
    import streamlit.components.v1 as components

    ROWS_JS         = _json.dumps(batteries_to_table_rows(batteries) if batteries else [])
    COUNTS_JS       = _json.dumps({s: counts.get(s, 0) for s in ALL_STATUSES[1:]})
    STATUS_OPTIONS_JS = _json.dumps(ALL_STATUSES)
    GRADE_OPTIONS_JS  = _json.dumps(["전체", "Green", "Yellow", "Orange", "Gray", "Red", "미판정"])
    STATUS_COLOR_JS = _json.dumps({
        "판정 전": "#9aa5b1", "승인 전": "#f3821d", "승인 완료": "#00b5b5",
        "수거 예정": "#142f4b", "완료": "#2e9e5b", "지정폐기물": "#7a1f1f",
    })
    GRADE_COLOR_JS = _json.dumps({
        "Green": "#2e9e5b", "Yellow": "#f3821d", "Orange": "#e07a1f",
        "Gray": "#576574", "Red": "#cc3333", "미판정": "#9aa5b1",
    })

    react_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Malgun Gothic','Segoe UI',sans-serif; font-size: 13px; background: #f0f2f6; color: #1a2e44; }}

/* ── 필터 바 ── */
.filter-bar {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  padding: 12px 14px; display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px; flex-wrap: wrap;
}}
.filter-bar label {{ font-size: 11px; color: #6b7280; font-weight: 600; white-space: nowrap; }}
.filter-bar input, .filter-bar select {{
  height: 32px; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 0 8px; font-size: 12px; color: #374151; background: #f9fafb;
  outline: none;
}}
.filter-bar input:focus, .filter-bar select:focus {{
  border-color: #00838a; background: #fff;
}}
.filter-bar input {{ width: 200px; }}
.filter-bar select {{ width: 110px; }}
.filter-sep {{ width: 1px; height: 24px; background: #e5e7eb; margin: 0 4px; }}
.btn {{ height: 32px; padding: 0 14px; border-radius: 6px; border: none;
  font-size: 12px; font-weight: 700; cursor: pointer; white-space: nowrap; }}
.btn-primary {{ background: #1a2e44; color: #fff; }}
.btn-primary:hover {{ background: #142438; }}
.btn-outline {{ background: #fff; color: #374151; border: 1px solid #d1d5db; }}
.btn-outline:hover {{ background: #f3f4f6; }}
.btn-teal {{ background: #00838a; color: #fff; }}
.btn-teal:hover:not(:disabled) {{ background: #006b71; }}
.btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}

/* ── 상태 요약 카드 ── */
.summary-row {{
  display: flex; gap: 8px; margin-bottom: 10px;
}}
.summary-card {{
  flex: 1; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 10px 8px; text-align: center;
}}
.summary-card .s-label {{ font-size: 11px; color: #6b7280; font-weight: 600; margin-bottom: 4px; }}
.summary-card .s-count {{ font-size: 20px; font-weight: 800; color: #1a2e44; }}

/* ── 테이블 컨테이너 ── */
.table-wrap {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  overflow: hidden;
}}
.table-toolbar {{
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid #f1f5f9;
}}
.table-toolbar .info {{ font-size: 12px; color: #6b7280; margin-right: auto; }}
.status-select {{
  height: 30px; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 0 8px; font-size: 12px; background: #f9fafb; outline: none;
}}
table {{ width: 100%; border-collapse: collapse; }}
thead tr {{ background: #f8fafc; }}
th {{
  padding: 9px 10px; text-align: left; font-size: 11px;
  font-weight: 700; color: #6b7280; border-bottom: 2px solid #e5e7eb;
  white-space: nowrap;
}}
th:first-child {{ width: 36px; text-align: center; }}
tbody tr {{ border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: background 0.1s; }}
tbody tr:hover {{ background: #f8fafc; }}
tbody tr.selected {{ background: #e8f6f7; }}
td {{ padding: 9px 10px; font-size: 12px; color: #374151; }}
td:first-child {{ text-align: center; }}
.badge {{
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 700; color: #fff; white-space: nowrap;
}}
input[type=checkbox] {{ width: 14px; height: 14px; cursor: pointer; accent-color: #00838a; }}
.feedback {{
  margin: 8px 14px; padding: 8px 12px; border-radius: 6px;
  font-size: 12px; font-weight: 600;
}}
.fb-ok {{ background: #d1fae5; color: #065f46; }}
.empty {{ padding: 32px; text-align: center; color: #9ca3af; font-size: 13px; }}
</style>
</head>
<body>
<div id="root"></div>
<script>
const {{ useState, useMemo }} = React;

const STATUS_COLOR   = {STATUS_COLOR_JS};
const GRADE_COLOR    = {GRADE_COLOR_JS};
const STATUS_OPTIONS = {STATUS_OPTIONS_JS};
const GRADE_OPTIONS  = {GRADE_OPTIONS_JS};
const ALL_ROWS       = {ROWS_JS};
const COUNTS         = {COUNTS_JS};
const BULK_STATUSES  = ["승인 전","승인 완료","수거 예정","완료"];

function Badge({{ value, map }}) {{
  return React.createElement("span",{{
    className:"badge", style:{{ backgroundColor: map[value]||"#9aa5b1" }}
  }}, value);
}}

function App() {{
  const [vinQ, setVinQ]           = useState("");
  const [gradeQ, setGradeQ]       = useState("전체");
  const [statusQ, setStatusQ]     = useState("전체");
  const [rows, setRows]           = useState(ALL_ROWS);
  const [counts, setCounts]       = useState(COUNTS);
  const [checked, setChecked]     = useState(new Set());
  const [bulkStatus, setBulk]     = useState("승인 완료");
  const [feedback, setFeedback]   = useState(null);

  const filtered = useMemo(() => {{
    return rows.filter(r => {{
      const vinOk    = !vinQ || (r.VIN||"").toLowerCase().includes(vinQ.toLowerCase()) || (r["모델명"]||"").toLowerCase().includes(vinQ.toLowerCase());
      const gradeOk  = gradeQ === "전체" || r["등급"] === gradeQ;
      const statusOk = statusQ === "전체" || r["상태"] === statusQ;
      return vinOk && gradeOk && statusOk;
    }});
  }}, [rows, vinQ, gradeQ, statusQ]);

  const allChecked  = filtered.length > 0 && checked.size === filtered.length;
  const someChecked = checked.size > 0;

  const toggleAll = () => {{
    if (allChecked) setChecked(new Set());
    else setChecked(new Set(filtered.map(r => r._id)));
  }};

  const toggleRow = id => {{
    setChecked(prev => {{
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    }});
  }};

  const applyBulk = () => {{
    if (!someChecked) return;
    const ids = [...checked];
    setRows(prev => prev.map(r => checked.has(r._id) ? {{...r, 상태: bulkStatus}} : r));
    // 상태 카운트 업데이트
    setCounts(prev => {{
      const n = {{...prev}};
      ids.forEach(id => {{
        const row = rows.find(r => r._id === id);
        if (row) {{
          n[row["상태"]] = Math.max(0, (n[row["상태"]]||0) - 1);
          n[bulkStatus]  = (n[bulkStatus]||0) + 1;
        }}
      }});
      return n;
    }});
    setChecked(new Set());
    setFeedback(`${{ids.length}}건 → '${{bulkStatus}}'(으)로 변경 완료`);
    setTimeout(() => setFeedback(null), 3000);
  }};

  const resetFilter = () => {{ setVinQ(""); setGradeQ("전체"); setStatusQ("전체"); }};

  return React.createElement("div", null,

    // ── 필터 바
    React.createElement("div", {{className:"filter-bar"}},
      React.createElement("label", null, "VIN / 모델명"),
      React.createElement("input", {{
        type:"text", placeholder:"검색어 입력",
        value: vinQ, onChange: e => setVinQ(e.target.value),
      }}),
      React.createElement("div", {{className:"filter-sep"}}),
      React.createElement("label", null, "등급"),
      React.createElement("select", {{value: gradeQ, onChange: e => setGradeQ(e.target.value)}},
        GRADE_OPTIONS.map(g => React.createElement("option",{{key:g,value:g}},g))
      ),
      React.createElement("label", null, "상태"),
      React.createElement("select", {{value: statusQ, onChange: e => setStatusQ(e.target.value)}},
        STATUS_OPTIONS.map(s => React.createElement("option",{{key:s,value:s}},s))
      ),
      React.createElement("div", {{className:"filter-sep"}}),
      React.createElement("button", {{className:"btn btn-primary", onClick:()=>{{}}}}, "조회"),
      React.createElement("button", {{className:"btn btn-outline", onClick:resetFilter}}, "초기화"),
    ),

    // ── 상태 요약 카드
    React.createElement("div", {{className:"summary-row"}},
      Object.entries(counts).map(([label, cnt]) =>
        React.createElement("div", {{key:label, className:"summary-card"}},
          React.createElement("div", {{className:"s-label"}}, label),
          React.createElement("div", {{className:"s-count"}}, cnt),
        )
      )
    ),

    // ── 테이블
    React.createElement("div", {{className:"table-wrap"}},

      // 툴바
      React.createElement("div", {{className:"table-toolbar"}},
        React.createElement("span", {{className:"info"}},
          someChecked ? `${{checked.size}}건 선택` : `전체 ${{filtered.length}}건`
        ),
        React.createElement("select", {{
          className:"status-select", value: bulkStatus,
          onChange: e => setBulk(e.target.value), disabled: !someChecked,
        }}, BULK_STATUSES.map(s => React.createElement("option",{{key:s,value:s}},s))),
        React.createElement("button", {{
          className:"btn btn-teal", disabled:!someChecked, onClick:applyBulk,
        }}, `✅ 일괄 변경 (${{checked.size}}건)`),
        React.createElement("button", {{
          className:"btn btn-outline",
          disabled: checked.size !== 1,
          onClick: () => {{
            const id = [...checked][0];
            try {{ window.parent.postMessage({{type:"battery_detail",id}}, "*"); }} catch(e) {{}}
          }},
        }}, "🔍 상세보기"),
      ),

      feedback && React.createElement("div", {{className:"feedback fb-ok"}}, feedback),

      // 테이블 본체
      filtered.length === 0
        ? React.createElement("div", {{className:"empty"}}, "조건에 맞는 배터리가 없습니다.")
        : React.createElement("table", null,
          React.createElement("thead", null,
            React.createElement("tr", null,
              React.createElement("th", null,
                React.createElement("input", {{type:"checkbox", checked:allChecked, onChange:toggleAll}})
              ),
              ["VIN","모델명","제조사","용량(kWh)","등급","상태","추천업체"].map(h =>
                React.createElement("th",{{key:h}},h)
              )
            )
          ),
          React.createElement("tbody", null,
            filtered.map(row =>
              React.createElement("tr", {{
                key: row._id,
                className: checked.has(row._id) ? "selected" : "",
                onClick: () => toggleRow(row._id),
              }},
                React.createElement("td", {{onClick:e=>e.stopPropagation()}},
                  React.createElement("input",{{type:"checkbox",checked:checked.has(row._id),onChange:()=>toggleRow(row._id)}})
                ),
                React.createElement("td", null, row["VIN"]),
                React.createElement("td", null, row["모델명"]),
                React.createElement("td", null, row["제조사"]),
                React.createElement("td", null, row["용량(kWh)"] != null ? Number(row["용량(kWh)"]).toFixed(1) : "—"),
                React.createElement("td", null, React.createElement(Badge,{{value:row["등급"],map:GRADE_COLOR}})),
                React.createElement("td", null, React.createElement(Badge,{{value:row["상태"],map:STATUS_COLOR}})),
                React.createElement("td", null, row["추천업체"]),
              )
            )
          )
        )
    )
  );
}}

ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(App));
</script>
</body>
</html>"""

    n_rows = len(batteries) if batteries else 0
    react_height = min(max(400, 320 + n_rows * 38), 800)
    components.html(react_html, height=react_height, scrolling=False)

    # 상세보기는 기존 Streamlit dialog 활용
    if st.session_state.get("selected_battery_id") and st.session_state.get("show_detail_panel"):
        show_battery_detail_dialog(st.session_state.selected_battery_id)


elif st.session_state.page == "intake":
    # =======================================================================
    # STEP 1: 입력 UI
    # =======================================================================
    if st.session_state.step == "input":
        st.markdown(
            f"""
            <div class="triage-header">
                <div class="triage-header-left">
                    <div class="triage-logo-box">🔋</div>
                    <div>
                        <p class="triage-header-text-sub">{st.session_state.channel_name}</p>
                        <p class="triage-header-text-main">배터리 등록</p>
                    </div>
                </div>
                <div class="triage-header-user">
                    <span class="triage-header-user-name">{DUMMY_USER['name']} 님</span>
                    <span class="triage-header-user-channel">{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 01. 식별 정보
        card01 = st.container(border=True)
        with card01:
            st.markdown(
                """
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num">01</div>
                        <p class="section-title-text">식별 정보</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                """
                <div class="qr-scan-section">
                📱 <b>QR코드 스캔</b> (또는 수동 입력)<br/>
                VIN이 담긴 QR코드를 촬영하면 자동으로 입력됩니다.
                </div>
                """,
                unsafe_allow_html=True,
            )

            input_method = st.radio(
                "입력 방식 선택",
                ["📷 카메라로 스캔", "⌨️ 수동 입력"],
                horizontal=True,
                label_visibility="collapsed",
            )

            if input_method == "📷 카메라로 스캔":
                st.info("📷 VIN QR코드를 카메라에 비춰주세요. (약 3초 소요)")

                camera_image = st.camera_input("카메라에서 촬영 (VIN QR코드)")

                if camera_image is not None:
                    st.markdown("**📸 촬영된 이미지:**")
                    st.image(camera_image, use_column_width=True)

                    decoded = decode_barcode(camera_image)

                    if decoded:
                        st.success("✅ QR코드 인식 성공!")

                        vin_from_scan = decoded[0]["data"]
                        st.markdown(f"**인식된 데이터 ({decoded[0]['type']}):**")
                        st.code(vin_from_scan)

                        st.session_state.scanned_vin = vin_from_scan
                        vin = vin_from_scan
                    else:
                        st.warning("⚠️ QR코드를 인식하지 못했습니다. 더 명확한 이미지를 다시 촬영해주세요.")
                        vin = ""
                else:
                    vin = ""

            else:
                st.markdown(
                    '<p class="field-label">차대번호 (VIN) <span class="req-star">*</span></p>',
                    unsafe_allow_html=True,
                )
                vin = st.text_input(
                    "VIN",
                    value=st.session_state.scanned_vin or "",
                    placeholder="KMHXX00XXXX000000",
                    label_visibility="collapsed",
                    max_chars=17,
                    key="vin",
                )

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(
                    '<p class="field-label">차량모델명</p>',
                    unsafe_allow_html=True,
                )
                model_name = st.text_input(
                    "차량모델명",
                    placeholder="예: 아이오닉 5",
                    label_visibility="collapsed",
                    key="model",
                )
                # 리콜 이력 조회 버튼 (산업통상자원부 국가기술표준원 제품안전정보센터 연결)
                if model_name:
                    recall_url = f"https://www.safetykorea.kr/recall/recallBoard?searchText={model_name}"
                    st.markdown(
                        f"""
                        <a href="{recall_url}" target="_blank" style="
                            display: inline-flex; align-items: center; gap: 5px;
                            font-size: 11px; color: #f3821d; font-weight: 600;
                            text-decoration: none; margin-top: 4px;
                        ">⚠️ 리콜 이력 조회 (국가기술표준원) →</a>
                        """,
                        unsafe_allow_html=True,
                    )
            with col2:
                st.markdown(
                    '<p class="field-label">배터리 제조사명</p>',
                    unsafe_allow_html=True,
                )
                manufacturer = st.text_input(
                    "배터리 제조사명",
                    placeholder="예: LG에너지솔루션",
                    label_visibility="collapsed",
                    key="mfr",
                )

            col3, col4 = st.columns(2)
            with col3:
                st.markdown(
                    '<p class="field-label">배터리 일련번호</p>',
                    unsafe_allow_html=True,
                )
                serial_number = st.text_input(
                    "배터리 일련번호",
                    placeholder="SN-000000",
                    label_visibility="collapsed",
                    key="sn",
                )
            with col4:
                st.markdown(
                    '<p class="field-label">배터리 용량 <span class="req-star">*</span><span class="field-hint">kWh</span></p>',
                    unsafe_allow_html=True,
                )
                capacity_kwh = st.number_input(
                    "배터리 용량",
                    min_value=0.0,
                    step=0.1,
                    format="%.1f",
                    value=77.4,
                    label_visibility="collapsed",
                    key="cap",
                )

        # 02. 차량 기본 정보
        card02 = st.container(border=True)
        with card02:
            st.markdown(
                """
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num">02</div>
                        <p class="section-title-text">차량 기본 정보</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col5, col6 = st.columns(2)
            current_year = 2026
            year_options = ["선택"] + [str(y) for y in range(current_year, current_year - 16, -1)]

            with col5:
                st.markdown('<p class="field-label">연식</p>', unsafe_allow_html=True)
                model_year = st.selectbox(
                    "연식", year_options, label_visibility="collapsed", key="year"
                )
            with col6:
                st.markdown(
                    '<p class="field-label">주행거리<span class="field-hint">km</span></p>',
                    unsafe_allow_html=True,
                )
                mileage_km = st.number_input(
                    "주행거리",
                    min_value=0,
                    step=1000,
                    value=45000,
                    label_visibility="collapsed",
                    key="mile",
                )

            col7, col8 = st.columns(2)
            with col7:
                st.markdown(
                    '<p class="field-label">수량<span class="field-hint">개</span></p>',
                    unsafe_allow_html=True,
                )
                quantity = st.number_input(
                    "수량",
                    min_value=1,
                    step=1,
                    value=1,
                    label_visibility="collapsed",
                    key="qty",
                )
            with col8:
                st.markdown(
                    '<p class="field-label">화학계</p>',
                    unsafe_allow_html=True,
                )
                chemistry = st.selectbox(
                    "화학계",
                    ["선택", "NCM", "LFP", "모름"],
                    label_visibility="collapsed",
                    key="chem",
                )

        # 03. 외관 상태
        condition_options = ["침수", "누액", "과열", "팽창", "충격"]
        condition_icons = {"침수": "🌊", "누액": "💧", "과열": "🔥", "팽창": "↔️", "충격": "⚡"}

        card03 = st.container(border=True)
        with card03:
            placeholder_header = st.empty()

            selected_conditions = st.pills(
                "외관 상태",
                options=condition_options,
                format_func=lambda x: f"{condition_icons[x]} {x}",
                selection_mode="multi",
                label_visibility="collapsed",
                key="hazard_pills",
            )

            hazard_count = len(selected_conditions)
            is_alert = hazard_count > 0

            num_class = "section-num-alert" if is_alert else ""
            badge_class = "status-badge-alert" if is_alert else "status-badge-ok"
            badge_text = f"⚠️ 위험요소 {hazard_count}" if is_alert else "🛡️ 이상 없음"

            placeholder_header.markdown(
                f"""
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num {num_class}">03</div>
                        <p class="section-title-text">외관 상태 점검</p>
                    </div>
                    <div class="status-badge {badge_class}">{badge_text}</div>
                </div>
                <p class="section-desc">해당 항목을 모두 선택하세요. 안전 판정의 핵심 정보입니다.</p>
                """,
                unsafe_allow_html=True,
            )

        if is_alert:
            border_css = "border: 1.5px solid #f3821d !important; background-color: rgba(243,130,29,0.08) !important;"
        else:
            border_css = "border: 1.5px solid rgba(0,181,181,0.40) !important;"

        st.markdown(
            f"""
            <style>
                div[data-testid="stVerticalBlockBorderWrapper"]:has(div[data-testid="stPills"]) {{
                    {border_css}
                }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        if st.button("배터리 판정 시작  →", use_container_width=True, type="primary"):
            errors = []
            if not vin:
                errors.append("차대번호(VIN)는 필수 입력 항목입니다.")
            if capacity_kwh <= 0:
                errors.append("배터리 용량은 0보다 큰 값을 입력해야 합니다.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                intake_record = {
                    "identification": {
                        "vin": vin,
                        "model_name": model_name or None,
                        "battery_manufacturer": manufacturer or None,
                        "serial_number": serial_number or None,
                        "capacity_kwh": capacity_kwh,
                    },
                    "vehicle_info": {
                        "model_year": None if model_year == "선택" else int(model_year),
                        "mileage_km": mileage_km,
                        "quantity": quantity,
                        "chemistry": None if chemistry == "선택" else chemistry,
                    },
                    "condition_flags": {
                        "flooded": "침수" in selected_conditions,
                        "leakage": "누액" in selected_conditions,
                        "overheated": "과열" in selected_conditions,
                        "swollen": "팽창" in selected_conditions,
                        "impact": "충격" in selected_conditions,
                    },
                    "channel": {
                        "name": st.session_state.channel_name,
                        "type": st.session_state.channel_type,
                    },
                }

                st.session_state.intake_record = intake_record

                # 발생채널별 임시 좌표 (실제 채널 주소 DB가 없어 시연용으로 고정값 사용)
                CHANNEL_COORDS = {
                    "강남폐차센터": (37.4979, 127.0276),
                    "수원폐차센터": (37.2636, 127.0286),
                    "인천폐차센터": (37.4563, 126.7052),
                }
                origin_lat, origin_lon = CHANNEL_COORDS.get(
                    st.session_state.channel_name, (37.5665, 126.9780)  # 기본값: 서울시청
                )

                triage_payload = {
                    "vin": vin,
                    "vehicle_year": intake_record["vehicle_info"]["model_year"],
                    "mileage_km": mileage_km,
                    "capacity_kwh": capacity_kwh,
                    "chemistry": intake_record["vehicle_info"]["chemistry"] or "UNKNOWN",
                    "manufacturer": manufacturer or None,
                    "model_name": model_name or None,
                    "battery_count": quantity or 1,
                    "condition_flags": intake_record["condition_flags"],
                }

                try:
                    triage_res = requests.post(
                        f"{API_BASE_URL}/triage", json=triage_payload, timeout=15
                    )
                    triage_res.raise_for_status()
                    triage_result = triage_res.json()
                except requests.RequestException as e:
                    st.error(f"배터리 판정 요청에 실패했습니다: {e}")
                    st.stop()

                grade = triage_result.get("grade")

                if grade == "Red":
                    st.warning("⚠️ 지정폐기물 판정 - 특별 처리 업체로 매칭합니다.")

                triage_id = triage_result.get("triage_id")

                try:
                    match_res = requests.post(
                        f"{API_BASE_URL}/match",
                        json={
                            "triage_result": triage_result,
                            "origin_latitude": origin_lat,
                            "origin_longitude": origin_lon,
                            "max_results": 3,
                            "triage_id": triage_id,
                        },
                        timeout=15,
                    )
                    match_res.raise_for_status()
                    matching_result = match_res.json()
                except requests.RequestException as e:
                    st.error(f"처리업체 매칭 요청에 실패했습니다: {e}")
                    matching_result = {"status": "no_match", "matched_companies": [], "grade": grade}

                st.session_state.triage_result = triage_result
                st.session_state.matching_result = matching_result
                st.session_state.step = "approval"
                st.rerun()

        st.markdown(
            """
            <div class="footer-note">
            접수 시점·작성자·발생채널이 자동으로 기록됩니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # =======================================================================
    # STEP 2: 담당자 승인
    # =======================================================================
    elif st.session_state.step == "approval":
        st.markdown(
            f"""
            <div class="triage-header">
                <div class="triage-header-left">
                    <div class="triage-logo-box">✅</div>
                    <div>
                        <p class="triage-header-text-sub">판정 결과 확인</p>
                        <p class="triage-header-text-main">담당자 승인</p>
                    </div>
                </div>
                <div class="triage-channel-badge">최종 확인 단계</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        intake_record = st.session_state.intake_record
        triage_result = st.session_state.triage_result
        matching_result = st.session_state.matching_result

        card_info = st.container(border=True)
        with card_info:
            st.markdown(
                """
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num">01</div>
                        <p class="section-title-text">배터리 정보</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-card-row">
                        <div class="info-item">
                            <span class="info-label">VIN</span>
                            <span class="info-value">{intake_record['identification']['vin']}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">연식</span>
                            <span class="info-value">{intake_record['vehicle_info']['model_year'] or '미입력'}년</span>
                        </div>
                    </div>
                    <div class="info-card-row">
                        <div class="info-item">
                            <span class="info-label">모델명</span>
                            <span class="info-value">{intake_record['identification']['model_name'] or '미입력'}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">주행거리</span>
                            <span class="info-value">{intake_record['vehicle_info']['mileage_km']:,} km</span>
                        </div>
                    </div>
                    <div class="info-card-row">
                        <div class="info-item">
                            <span class="info-label">제조사</span>
                            <span class="info-value">{intake_record['identification']['battery_manufacturer'] or '미입력'}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">용량</span>
                            <span class="info-value">{intake_record['identification']['capacity_kwh']} kWh</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        card_triage = st.container(border=True)
        with card_triage:
            st.markdown(
                """
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num">02</div>
                        <p class="section-title-text">Triage 판정</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            grade_emoji = {"Green": "✅", "Yellow": "⚠️", "Orange": "⚡", "Gray": "❌", "Red": "🚫"}
            path_label = {
                "reuse_candidate": "재사용 후보",
                "reuse_or_recycle_after_diagnosis": "추가진단 후 판단",
                "recycle_candidate": "재활용 후보",
                "diagnosis_required": "정밀진단 필요",
                "designated_waste": "지정폐기물 처리",
            }.get(triage_result['recommended_path'], triage_result['recommended_path'])
            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-card-row">
                        <div class="info-item">
                            <span class="info-label">SOH Proxy</span>
                            <span class="info-value">{f"{triage_result['soh_proxy_score']}%" if triage_result.get('soh_proxy_score') is not None else "—"}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">등급</span>
                            <span class="info-value">{grade_emoji.get(triage_result['grade'], '')} {triage_result['grade']}</span>
                        </div>
                    </div>
                    <div class="info-card-row">
                        <div class="info-item">
                            <span class="info-label">처리 방향</span>
                            <span class="info-value">{path_label}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">화학계</span>
                            <span class="info-value">{intake_record['vehicle_info']['chemistry'] or 'UNKNOWN'}</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        card_matching = st.container(border=True)
        with card_matching:
            st.markdown(
                """
                <div class="section-title-row">
                    <div class="section-title-left">
                        <div class="section-num">03</div>
                        <p class="section-title-text">처리업체 추천 (1~3순위)</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            matched_companies = matching_result.get('matched_companies') or []
            if not matched_companies:
                st.markdown(
                    """
                    <div style="background-color: var(--c-card); border: 1.5px solid var(--c-border); border-radius: 12px; padding: 16px; text-align: center; color: var(--c-muted-foreground); font-size: 13px;">
                        추천 처리업체가 없습니다. (지정폐기물 또는 매칭 실패)
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            for company in matched_companies:
                st.markdown(
                    f"""
                    <div style="background-color: var(--c-card); border: 1.5px solid var(--c-border); border-radius: 12px; padding: 14px; margin-bottom: 10px;">
                        <div style="font-size: 12px; font-weight: 700; color: var(--c-primary); margin-bottom: 6px;">{company['rank']}순위</div>
                        <div style="font-size: 14px; font-weight: 700; color: var(--c-foreground); margin-bottom: 4px;">{company['company_name']}</div>
                        <div style="font-size: 11px; color: var(--c-muted-foreground); margin-bottom: 10px;">지역: {company['region']} | 거리: {company['distance_km']}km</div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                            <div style="background-color: var(--c-secondary); padding: 7px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 9px; font-weight: 600; color: var(--c-muted-foreground);">점수</div>
                                <div style="font-size: 12px; font-weight: 700; color: var(--c-foreground);">{company['total_score']:.1f}</div>
                            </div>
                            <div style="background-color: var(--c-secondary); padding: 7px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 9px; font-weight: 600; color: var(--c-muted-foreground);">진단역량</div>
                                <div style="font-size: 12px; font-weight: 700; color: var(--c-foreground);">{company['diagnostic_capability'].upper()}</div>
                            </div>
                            <div style="background-color: var(--c-secondary); padding: 7px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 9px; font-weight: 600; color: var(--c-muted-foreground);">처리유형</div>
                                <div style="font-size: 12px; font-weight: 700; color: var(--c-foreground);">{company['process_type']}</div>
                            </div>
                            <div style="background-color: var(--c-secondary); padding: 7px; border-radius: 8px; text-align: center;">
                                <div style="font-size: 9px; font-weight: 600; color: var(--c-muted-foreground);">상태</div>
                                <div style="font-size: 12px; font-weight: 700; color: var(--c-foreground);">운영중</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # 지도 표시 (매칭된 업체가 있고 좌표가 있을 때)
            if matched_companies and any(c.get('latitude') and c.get('longitude') for c in matched_companies):
                import folium
                from streamlit_folium import st_folium

                channel_name = st.session_state.get("channel_name", "강남폐차센터")
                CHANNEL_COORDS = {
                    "강남폐차센터": (37.4979, 127.0276),
                    "수원폐차센터": (37.2636, 127.0286),
                    "인천폐차센터": (37.4563, 126.7052),
                }
                origin_lat, origin_lon = CHANNEL_COORDS.get(channel_name, (37.5665, 126.9780))

                all_lats = [origin_lat] + [c['latitude'] for c in matched_companies if c.get('latitude')]
                all_lons = [origin_lon] + [c['longitude'] for c in matched_companies if c.get('longitude')]
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)

                m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="CartoDB positron")

                # 발생 위치 마커 (파란색)
                folium.Marker(
                    location=[origin_lat, origin_lon],
                    popup=folium.Popup(f"<b>📍 발생위치</b><br>{channel_name}", max_width=200),
                    tooltip=channel_name,
                    icon=folium.Icon(color="blue", icon="home", prefix="fa"),
                ).add_to(m)

                # 순위별 업체 마커 색상
                rank_colors = {1: "red", 2: "orange", 3: "green"}

                for company in matched_companies:
                    if not company.get('latitude') or not company.get('longitude'):
                        continue
                    rank = company['rank']
                    color = rank_colors.get(rank, "gray")
                    folium.Marker(
                        location=[company['latitude'], company['longitude']],
                        popup=folium.Popup(
                            f"<b>{rank}순위: {company['company_name']}</b><br>"
                            f"거리: {company['distance_km']}km<br>"
                            f"점수: {company['total_score']:.1f}<br>"
                            f"처리유형: {company['process_type']}",
                            max_width=220,
                        ),
                        tooltip=f"{rank}순위 {company['company_name']}",
                        icon=folium.Icon(color=color, icon="industry", prefix="fa"),
                    ).add_to(m)

                    # 발생위치 → 업체 선 연결
                    folium.PolyLine(
                        locations=[[origin_lat, origin_lon], [company['latitude'], company['longitude']]],
                        color=color,
                        weight=2,
                        opacity=0.5,
                        dash_array="5",
                    ).add_to(m)

                st.markdown("**📍 처리업체 위치 지도**")
                st_folium(m, width="100%", height=340, returned_objects=[])

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1.2], gap="small")

        with col1:
            if st.button("← 이전", use_container_width=True):
                st.session_state.step = "input"
                st.rerun()

        with col2:
            if st.button("💾 저장", use_container_width=True):
                # 현재 접수 건을 "승인 전" 상태로 저장하고 입력 화면으로 복귀
                # (나중에 배터리 관리 페이지에서 승인 처리 가능)
                st.session_state.step = "input"
                st.session_state.intake_record = None
                st.session_state.triage_result = None
                st.session_state.matching_result = None
                st.rerun()

        with col3:
            if st.button("✅ 승인 (최종 확정)", use_container_width=True, type="primary"):
                st.session_state.step = "completed"
                st.rerun()

    # =======================================================================
    # STEP 3: 처리 완료
    # =======================================================================
    elif st.session_state.step == "completed":
        intake_record = st.session_state.intake_record
        triage_result = st.session_state.triage_result
        matching_result = st.session_state.matching_result

        matched_companies = matching_result.get('matched_companies') or []
        rank1_company_name = matched_companies[0]['company_name'] if matched_companies else "—"

        completion_info = {
            "timestamp": datetime.now().isoformat(),
            "vin": intake_record['identification']['vin'],
            "grade": triage_result['grade'],
            "matched_company_rank1": rank1_company_name,
            "status": "approved",
        }

        st.markdown(
            """
            <div style="text-align: center; padding: 32px 16px;">
                <div style="font-size: 64px; margin-bottom: 16px;">✨</div>
                <p style="font-size: 20px; font-weight: 700; color: var(--c-foreground); margin-bottom: 6px;">처리 완료</p>
                <p style="font-size: 13px; color: var(--c-muted-foreground); margin-bottom: 24px; line-height: 1.6;">배터리 판정 및 처리업체 매칭이<br/>완료되었습니다!</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div style="background-color: var(--c-secondary); border: 1px solid var(--c-border); border-radius: 12px; padding: 16px; margin-bottom: 24px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 12px;">
                    <div>
                        <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; color: var(--c-muted-foreground); margin-bottom: 4px;">처리 시간</div>
                        <div style="font-size: 13px; font-weight: 700; color: var(--c-foreground);">{completion_info['timestamp'][:19]}</div>
                    </div>
                    <div>
                        <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; color: var(--c-muted-foreground); margin-bottom: 4px;">VIN</div>
                        <div style="font-size: 13px; font-weight: 700; color: var(--c-foreground); word-break: break-word;">{completion_info['vin']}</div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                    <div>
                        <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; color: var(--c-muted-foreground); margin-bottom: 4px;">등급</div>
                        <div style="font-size: 13px; font-weight: 700; color: var(--c-foreground);">{completion_info['grade']}</div>
                    </div>
                    <div>
                        <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; color: var(--c-muted-foreground); margin-bottom: 4px;">추천 처리업체 (1순위)</div>
                        <div style="font-size: 13px; font-weight: 700; color: var(--c-foreground); word-break: break-word;">{completion_info['matched_company_rank1']}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.info("📄 결과서 다운로드는 추후 추가 예정입니다")

        # PDF 판정 결과서 다운로드
        st.markdown("#### 📄 판정 결과서 다운로드")
        if st.button("📥 PDF 결과서 생성", use_container_width=True):
            try:
                pdf_res = requests.post(
                    f"{API_BASE_URL}/pdf/triage",
                    json={"triage_result": triage_result},
                    timeout=30,
                )
                if pdf_res.status_code == 200:
                    st.download_button(
                        label="⬇️ PDF 저장",
                        data=pdf_res.content,
                        file_name=f"triage_{completion_info['vin']}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                else:
                    st.error(f"PDF 생성 실패: {pdf_res.status_code}")
            except requests.RequestException as e:
                st.error(f"PDF 요청 오류: {e}")

        # RAG 정책 리포트
        st.markdown("#### 📋 정책 리포트 (AI)")
        st.caption("판정 결과에 맞는 관련 법령·처리 가이드를 AI가 자동 생성합니다. 첫 호출은 약 1~2분 소요될 수 있습니다.")
        if st.button("🤖 정책 리포트 생성", use_container_width=True):
            with st.spinner("AI가 관련 법령 및 정책을 분석 중입니다... (첫 호출 시 최대 2분 소요)"):
                try:
                    report_res = requests.post(
                        f"{API_BASE_URL}/report",
                        json={
                            "triage_result": triage_result,
                            "matched_companies": [
                                {"company_name": c["company_name"], "process_type": c["process_type"]}
                                for c in matched_companies[:3]
                            ],
                        },
                        timeout=180,
                    )
                    if report_res.status_code == 200:
                        report_data = report_res.json()
                        st.markdown("---")
                        st.markdown(report_data.get("report", "리포트를 생성하지 못했습니다."))
                        sources = report_data.get("sources", [])
                        if sources:
                            st.caption("**참조 출처**: " + " / ".join(sources))
                    elif report_res.status_code == 501:
                        st.warning("RAG 리포트 기능은 현재 준비 중입니다. (백엔드 구현 예정)")
                    else:
                        st.error(f"리포트 생성 실패: {report_res.status_code}")
                except requests.RequestException as e:
                    st.error(f"리포트 요청 오류: {e}")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 새 배터리 입력", use_container_width=True):
            st.session_state.step = "input"
            st.session_state.intake_record = None
            st.session_state.triage_result = None
            st.session_state.matching_result = None
            st.session_state.scanned_vin = None
            st.rerun()

        st.markdown(
            """
            <div class="footer-note">
            🔋 Battery Triage Map © 2026 | 산업통상자원부 공공데이터 활용 아이디어 공모전
            </div>
            """,
            unsafe_allow_html=True,
        )