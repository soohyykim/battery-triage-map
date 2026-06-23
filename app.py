"""
Battery Triage Map - 사용후 배터리 접수 (입력 UI)

Lovable 소스코드(src/routes/index.tsx, src/styles.css)를 기준으로
색상 변수(OKLCH→HEX 변환)와 03 섹션의 동적 위험 표시 로직까지 재현.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="사용후 배터리 접수 | EV Battery Intake",
    page_icon="🔋",
    layout="centered",
)

# ---------------------------------------------------------------------------
# CSS — Lovable styles.css의 OKLCH 색상 변수를 HEX로 변환하여 그대로 적용
#   primary    (네이비)   : oklch(0.30 0.06 250) -> #142f4b
#   accent     (민트)     : oklch(0.70 0.13 195) -> #00b5b5
#   warning    (주황)     : oklch(0.72 0.17 55)  -> #f3821d
#   background (연한 회청) : oklch(0.98 0.005 240) -> #f6f9fb
#   border                : oklch(0.90 0.012 250) -> #d8dfe6
#   muted-foreground      : oklch(0.50 0.03 250)  -> #576574
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

        /* ---------- 헤더 ---------- */
        .triage-header {
            background-color: var(--c-primary);
            border-radius: 14px;
            padding: 14px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.06);
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
            width: 36px;
            height: 36px;
            min-width: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }
        .triage-header-text-sub {
            color: rgba(246,249,251,0.70);
            font-size: 11px;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .triage-header-text-main {
            color: var(--c-primary-foreground);
            font-size: 14px;
            font-weight: 700;
            margin: 0;
        }
        .triage-channel-badge {
            background-color: rgba(0,181,181,0.15);
            border: 1px solid rgba(0,181,181,0.30);
            color: var(--c-accent);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.03em;
            padding: 5px 12px;
            border-radius: 999px;
            white-space: nowrap;
        }

        /* ---------- 섹션 카드 공통 (st.container border wrapper) ---------- */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 12px !important;
            margin-bottom: 16px;
            background-color: var(--c-card);
            border: 1px solid var(--c-border) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] > div:first-child {
            border-radius: 12px !important;
        }

        /* ---------- 섹션 타이틀 ---------- */
        .section-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
        }
        .section-title-left {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-num {
            background-color: var(--c-primary);
            color: var(--c-primary-foreground);
            font-weight: 700;
            font-size: 11px;
            width: 28px;
            height: 28px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .section-num-normal {
            background-color: rgba(0,181,181,0.20);
            color: var(--c-accent-foreground);
            border: 1px solid rgba(0,181,181,0.40);
        }
        .section-num-alert {
            background-color: var(--c-warning);
            color: var(--c-warning-foreground);
        }
        .section-title-text {
            font-size: 15px;
            font-weight: 700;
            color: var(--c-foreground);
            margin: 0;
        }
        .section-desc {
            color: var(--c-muted-foreground);
            font-size: 12px;
            margin: 2px 0 0 0;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 700;
            padding: 5px 11px;
            border-radius: 999px;
        }
        .status-badge-ok {
            background-color: var(--c-secondary);
            color: var(--c-secondary-foreground);
        }
        .status-badge-alert {
            background-color: var(--c-warning);
            color: var(--c-warning-foreground);
        }

        /* 필수 표시 / 힌트 */
        .req-star { color: var(--c-destructive); font-weight: 700; }
        .field-hint {
            color: var(--c-muted-foreground);
            font-weight: 400;
            text-transform: none;
            margin-left: 4px;
            font-size: 11px;
        }

        /* 라벨 — Lovable의 text-xs uppercase tracking-wide 재현 */
        .field-label {
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--c-muted-foreground);
            margin-bottom: 4px;
        }

        /* input/select 테두리 색 보정 */
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-color: var(--c-input) !important;
            border-radius: 8px !important;
        }

        /* CTA 버튼 */
        div.stButton > button {
            background-color: var(--c-primary);
            color: var(--c-primary-foreground);
            font-size: 15px;
            font-weight: 700;
            padding: 13px 0;
            border-radius: 12px;
            border: none;
            width: 100%;
            box-shadow: 0 4px 10px rgba(20,47,75,0.20);
        }
        div.stButton > button:hover {
            filter: brightness(1.12);
            color: var(--c-primary-foreground);
        }

        /* pills(외관 상태) 카드형 보정 — 평소(민트 hover) / 선택시(주황 active) */
        div[data-testid="stPills"] {
            gap: 8px;
        }
        div[data-testid="stPills"] label {
            border: 1.5px solid var(--c-border) !important;
            border-radius: 10px !important;
            padding: 14px 6px !important;
            background-color: var(--c-card) !important;
            transition: all 0.15s ease;
        }
        div[data-testid="stPills"] label:hover {
            border-color: var(--c-accent) !important;
        }
        div[data-testid="stPills"] label[aria-checked="true"] {
            border-color: var(--c-warning) !important;
            background-color: var(--c-warning) !important;
            color: var(--c-warning-foreground) !important;
        }
        div[data-testid="stPills"] label[aria-checked="true"] p {
            color: var(--c-warning-foreground) !important;
            font-weight: 700;
        }

        .footer-note {
            text-align: center;
            font-size: 11px;
            color: var(--c-muted-foreground);
            margin-top: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 발생채널 — 로그인 계정에 자동 연동 (현재는 placeholder, auth.py 연결 예정)
# ---------------------------------------------------------------------------
if "channel_name" not in st.session_state:
    st.session_state.channel_name = "강남폐차센터"
if "channel_type" not in st.session_state:
    st.session_state.channel_type = "폐차장"

# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="triage-header">
        <div class="triage-header-left">
            <div class="triage-logo-box">🔋</div>
            <div>
                <p class="triage-header-text-sub">🏢 {st.session_state.channel_name}</p>
                <p class="triage-header-text-main">사용후 배터리 접수</p>
            </div>
        </div>
        <div class="triage-channel-badge">발생채널 · {st.session_state.channel_type}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 01·02. 식별 정보 / 차량 기본 정보
#   - 03(외관상태)이 실시간으로 색이 바뀌어야 해서 st.form을 쓰지 않음.
#     (st.form 안 위젯은 제출 전까지 화면을 다시 그리지 않아 즉시 반응이 불가능)
# ---------------------------------------------------------------------------

# --- 01. 식별 정보 ---
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
        '<p class="field-label">차대번호 (VIN) <span class="req-star">*</span></p>',
        unsafe_allow_html=True,
    )
    vin = st.text_input(
        "VIN", placeholder="KMHXX00XXXX000000", label_visibility="collapsed", max_chars=17
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<p class="field-label">차량모델명</p>', unsafe_allow_html=True)
        model_name = st.text_input(
            "차량모델명", placeholder="예: 아이오닉 5", label_visibility="collapsed"
        )
    with col2:
        st.markdown('<p class="field-label">배터리 제조사명</p>', unsafe_allow_html=True)
        manufacturer = st.text_input(
            "배터리 제조사명", placeholder="예: LG에너지솔루션", label_visibility="collapsed"
        )

    col3, col4 = st.columns(2)
    with col3:
        st.markdown('<p class="field-label">배터리 일련번호</p>', unsafe_allow_html=True)
        serial_number = st.text_input(
            "배터리 일련번호", placeholder="SN-000000", label_visibility="collapsed"
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
            label_visibility="collapsed",
        )

# --- 02. 차량 기본 정보 ---
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

    col5, col6, col7, col8 = st.columns(4)
    current_year = 2026
    year_options = ["선택"] + [str(y) for y in range(current_year, current_year - 16, -1)]

    with col5:
        st.markdown('<p class="field-label">연식</p>', unsafe_allow_html=True)
        model_year = st.selectbox("연식", year_options, label_visibility="collapsed")
    with col6:
        st.markdown(
            '<p class="field-label">주행거리<span class="field-hint">km</span></p>',
            unsafe_allow_html=True,
        )
        mileage_km = st.number_input(
            "주행거리", min_value=0, step=1000, label_visibility="collapsed"
        )
    with col7:
        st.markdown(
            '<p class="field-label">수량<span class="field-hint">개</span></p>',
            unsafe_allow_html=True,
        )
        quantity = st.number_input(
            "수량", min_value=1, step=1, value=1, label_visibility="collapsed"
        )
    with col8:
        st.markdown('<p class="field-label">화학계</p>', unsafe_allow_html=True)
        chemistry = st.selectbox(
            "화학계", ["선택", "NCM", "LFP", "모름"], label_visibility="collapsed"
        )

# ---------------------------------------------------------------------------
# 03. 외관 상태 점검
#   Lovable 원본 로직 재현: 하나라도 선택되면 카드 전체가 주황(warning) 톤으로
#   전환되고, 배지가 "이상 없음" -> "위험요소 N"으로 바뀜.
# ---------------------------------------------------------------------------
condition_options = ["침수", "누액", "과열", "팽창", "충격"]
condition_icons = {"침수": "🌊", "누액": "💧", "과열": "🔥", "팽창": "↔️", "충격": "⚡"}

card03 = st.container(border=True)
with card03:
    # pills를 먼저 렌더링해 선택 상태를 즉시 읽고, 그 결과에 따라 헤더를 그린다.
    placeholder_header = st.empty()

    selected_conditions = st.pills(
        "외관 상태",
        options=condition_options,
        format_func=lambda x: f"{condition_icons[x]}  {x}",
        selection_mode="multi",
        label_visibility="collapsed",
        key="hazard_pills",
    )

    hazard_count = len(selected_conditions)
    is_alert = hazard_count > 0

    num_class = "section-num-alert" if is_alert else "section-num-normal"
    badge_class = "status-badge-alert" if is_alert else "status-badge-ok"
    badge_text = f"⚠️ 위험요소 {hazard_count}" if is_alert else "🛡️ 이상 없음"

    placeholder_header.markdown(
        f"""
        <div class="section-title-row">
            <div class="section-title-left">
                <div class="section-num {num_class}">03</div>
                <div>
                    <p class="section-title-text">외관 상태 점검</p>
                </div>
            </div>
            <div class="status-badge {badge_class}">{badge_text}</div>
        </div>
        <p class="section-desc">해당 항목을 모두 선택하세요. 안전 판정의 핵심 정보입니다.</p>
        """,
        unsafe_allow_html=True,
    )

# 03 카드 테두리를 위험 여부에 따라 동적으로 전환
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

submitted = st.button("배터리 판정 시작  →", use_container_width=True)

# ---------------------------------------------------------------------------
# 제출 처리 — 현재는 rule.py 미연결, 입력값 구조화 + 임시 표시만 수행
# ---------------------------------------------------------------------------
if submitted:
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

        st.success("접수 정보가 등록되었습니다. (Rule Engine 연결 전 — 임시 확인 화면)")
        st.json(intake_record)

        # TODO: services/rule.py 완성 후 아래로 교체
        # from services.rule import classify_battery
        # result = classify_battery(intake_record)
        # st.write(result)
