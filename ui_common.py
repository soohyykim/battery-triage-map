"""
ui_common.py — 3개 앱(app_mobile / app_junkyard / app_company) 공용 UI 레이어.

원래 하나의 app.py에 있던 전역 CSS(디자인 토큰, 카드 시스템, 리스트 헤더 등)를
그대로 가져와 공유 모듈로 뺐다. 각 앱은 실행 최상단에서
inject_global_css()를 한 번 호출해 동일한 톤앤매너를 유지한다.

- 앱(모바일, app_mobile.py): container_max_width="480px"
- 웹(폐차장/처리업체): container_max_width="1200px" (기본값)
"""

import streamlit as st

_CSS_TEMPLATE = """

    <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

        /* Streamlit 기본 상단 메뉴(햄버거)·헤더 툴바·"Made with Streamlit" 푸터
           숨김. 이 요소들은 앱 자체 DOM 안에 있어서 CSS로 제어 가능하다
           (Streamlit Cloud 소유자 화면에 뜨는 Share/Deploy 바는 호스팅
           플랫폼이 앱 iframe 바깥에 얹는 것이라 여기서 숨길 수 없다 —
           일반 방문자에게는 애초에 안 보인다). */
        #MainMenu {
            visibility: hidden;
        }
        footer {
            visibility: hidden;
        }
        header[data-testid="stHeader"] {
            visibility: hidden;
            height: 0;
        }
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            visibility: hidden;
            display: none;
        }

        /* 전역 box-sizing 리셋 — padding/border가 지정한 width에 "더해지는" 게
           아니라 "포함"되도록 강제. 이게 없으면 padding·border가 있는 요소들
           (QR 스캔 박스, 뱃지 등)이 카드 padding을 감안 못하고 카드 밖으로
           삐져나온다. */
        *, *::before, *::after {
            box-sizing: border-box;
        }

        /* Streamlit 1.40.0에서 확인된 실제 버그: 위젯 wrapper(.stMarkdown,
           stRadio, stToggle 등 data-testid를 가진 여러 요소들)에 렌더링
           시점의 고정 px 값을 인라인 style="width: ...px"로 박아넣는데, 이
           값이 카드 padding을 감안하지 않은 더 넓은 조상 기준으로 계산돼서
           카드보다 넓게 나온다(QR 스캔 박스·"이상 없음" 뱃지·라디오 버튼·
           토글 스위치 등이 카드 밖으로 튀어나오는 진짜 원인). stElementContainer
           는 항상 올바른 폭으로 계산되므로, 그 바로 아래 자식 전체를 강제로
           100%로 되돌린다. 스타일시트의 !important는 인라인 style보다 우선한다. */
        div[class*="st-key-card_"] [data-testid="stElementContainer"] > div {
            width: 100% !important;
            max-width: 100% !important;
        }
        /* folium 지도(st_folium), components.html 커스텀 컴포넌트는 iframe으로
           렌더링되는데, Streamlit이 iframe 크기를 리사이즈 스크립트로 JS에서
           직접 다시 계산해서 박아넣는다. 이것도 카드 padding을 감안 못하고
           카드보다 넓게 잡혀서 오른쪽으로 튀어나오므로 동일하게 강제 보정. */
        div[class*="st-key-card_"] iframe {
            width: 100% !important;
            max-width: 100% !important;
        }

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
            max-width: __CONTAINER_MAX_WIDTH__ !important;
            padding-top: 1rem !important;
            padding-left: 0px !important;
            padding-right: 0px !important;
        }

        __PHONE_FRAME_CSS__

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
            padding: 0 18px;
            height: 62px;
            box-sizing: border-box;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 6px rgba(0,0,0,0.10);
            position: sticky;
            top: 1rem;
            width: 100%;
            z-index: 999;
            margin-bottom: 16px;
        }
        .triage-header-left {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }
        /* 배터리 관리 페이지용 화이트 헤더 (신규 목록 디자인 기준) */
        .list-header {
            background-color: var(--c-card);
            border: 1.5px solid var(--c-border);
            border-radius: 14px;
            padding: 0 18px;
            height: 62px;
            box-sizing: border-box;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 1rem;
            width: 100%;
            z-index: 999;
            margin-bottom: 16px;
        }
        .list-header-left {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .list-header-title {
            font-size: 18px;
            font-weight: 800;
            color: var(--c-foreground);
            margin: 0;
            line-height: 1.3;
        }
        .list-header-sub {
            font-size: 12px;
            color: var(--c-muted-foreground);
            margin: 2px 0 0 0;
            line-height: 1.3;
        }
        .list-header-user {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
        }
        .list-header-user-name {
            color: var(--c-foreground);
            font-size: 12px;
            font-weight: 600;
        }
        .list-header-user-channel {
            color: var(--c-muted-foreground);
            font-size: 10px;
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
        .triage-header-text-main {
            color: var(--c-primary-foreground);
            font-size: 16px;
            font-weight: 700;
            margin: 0;
            line-height: 1.3;
        }
        .triage-header-text-sub {
            color: rgba(246,249,251,0.60);
            font-size: 11px;
            margin: 2px 0 0 0;
            line-height: 1.3;
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

        /* ---------- 카드(번호 섹션) 스타일 ----------
           예전에는 모든 stVerticalBlockBorderWrapper에 무조건 카드 스타일을
           입혔는데, 그러면 st.columns()나 페이지 루트처럼 의도치 않은
           컨테이너까지 전부 박스가 씌워지는 문제가 있었다. 이제는 카드로
           쓰고 싶은 컨테이너에만 key="card_..." 를 부여하고, 그 key로 생긴
           .st-key-card_* 클래스가 있는 wrapper에만 카드 스타일을 입힌다. */
        div[class*="st-key-card_"] {
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
        div[class*="st-key-card_"] > div {
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
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
        }
        .section-title-left {
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
            flex: 1 1 auto;
            overflow: hidden;
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
            flex-shrink: 0;
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
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
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
            flex-shrink: 0;
            box-sizing: border-box;
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

        /* pills — 외관 상태 점검 (침수/누액/과열/팽창/충격) 5개 버튼.
           실제 렌더링 DOM을 Playwright로 직접 확인해서 알아낸 진짜 구조:
           .st-key-hazard_pills 안의 div[data-baseweb="button-group"][role="group"]
           가 버튼들을 감싸는 진짜 컨테이너다. 그리고 버튼을 선택하면 Streamlit이
           data-testid를 "stBaseButton-pills"에서 "stBaseButton-pillsActive"로
           통째로 바꿔버린다(aria-checked는 안 씀) — 그래서 선택 전용 testid를
           빼먹으면 선택 순간 스타일이 통째로 날아가 버튼이 찌그러진다.
           [data-testid^="stBaseButton-pills"]로 두 testid를 한 번에 잡는다. */
        .st-key-hazard_pills {
            width: 100% !important;
            max-width: 100% !important;
        }
        .st-key-hazard_pills div[data-baseweb="button-group"] {
            display: grid !important;
            grid-template-columns: repeat(5, 1fr) !important;
            width: 100% !important;
            max-width: 100% !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
        }
        .st-key-hazard_pills button[data-testid^="stBaseButton-pills"] {
            width: 100% !important;
            aspect-ratio: 2 / 1 !important;
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
            border: 1.5px solid var(--c-border) !important;
            border-radius: 14px !important;
            padding: 6px !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            background-color: var(--c-card) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            box-sizing: border-box !important;
            transition: all 0.15s ease;
        }
        .st-key-hazard_pills button[data-testid="stBaseButton-pillsActive"] {
            border-color: var(--c-warning) !important;
            background-color: var(--c-warning) !important;
            color: var(--c-warning-foreground) !important;
        }

        /* 배터리 판정 버튼 — 카드형 배경/테두리가 전역 규칙(아래
           stVerticalBlockBorderWrapper)에 의해 자동으로 씌워지는 것을 제거.
           버튼에 준 key를 통해 해당 버튼을 포함하는 래퍼를 찾아 무력화 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.st-key-judge_battery_btn) {
            border: none !important;
            background: transparent !important;
            padding: 0 !important;
            box-shadow: none !important;
            margin-bottom: 0 !important;
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
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
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

        .sidebar-logo-desc {
            font-size: 10px;
            color: #ffffff;
            margin-top: 2px;
            font-weight: 400;
        }
        .sidebar-logo-slogan {
            font-size: 13px;
            color: rgba(0,181,181,0.75);
            margin-top: 6px;
            font-style: italic;
            font-weight: 500;
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
        section[data-testid="stSidebar"] > div:first-child {
            padding-top: 0rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 0rem !important;
        }
        .sidebar-logo {
            display: flex;
            align-items: flex-start;
            flex-direction: column;
            justify-content: center;
            gap: 4px;
            /* 메인 헤더(.triage-header)와 동일한 높이(62px)로 고정하고 세로 중앙
               정렬해서, 사이드바 블록의 padding-top(main과 동일한 1rem)이 같으면
               텍스트 높이가 자연스럽게 일치하도록 함 */
            height: 62px;
            padding: 4px;
            box-sizing: border-box;
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
            font-size: 30px;
            font-weight: 800;
            color: #ffffff !important;
            line-height: 1.2;
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
    
"""


_PHONE_FRAME_CSS = """
        /* 실제 모바일 기기처럼 보이도록 block-container를 폰 베젤로 감싼다.
           (app_mobile.py 배터리 등록 페이지 전용 — phone_frame=True일 때만 적용)
           틀(베젤+노치)은 고정하고 그 안의 콘텐츠만 스크롤되도록, block-container
           자체에 높이를 고정하고 overflow-y:auto를 줘서 내부 스크롤 컨테이너로
           만든다. border/box-shadow는 요소 자체의 테두리라 내부 스크롤과 무관하게
           항상 고정 위치에 그려지므로 베젤은 저절로 고정된다. 노치(::before)만
           position:sticky로 줘서 스크롤 중에도 상단에 붙어있게 한다. */
        html, body {
            overflow: hidden !important;
        }
        .stApp {
            background-color: #dfe3ea !important;
            height: 100vh;
            overflow: hidden;
        }
        .block-container {
            position: relative;
            margin: 32px auto !important;
            width: auto !important;
            max-width: 480px !important;
            height: min(calc(100vh - 64px), calc(100dvh - 64px), 932px);
            border: 12px solid #1a1d24;
            border-radius: 46px;
            box-shadow: 0 24px 48px rgba(0,0,0,0.28), 0 0 0 2px #3a3f4a;
            background-color: var(--c-background);
            padding-top: 8px !important;
            padding-left: 18px !important;
            padding-right: 18px !important;
            padding-bottom: 24px !important;
            overflow-y: auto;
            overflow-x: hidden;
            scrollbar-width: none; /* Firefox: 스크롤은 유지하되 막대는 안 보이게 */
            -ms-overflow-style: none; /* 구형 Edge/IE */
        }
        /* Chrome/Safari/Edge(Chromium) — 스크롤바를 0폭으로 숨겨서
           오른쪽 여백이 왼쪽보다 커 보이는 문제(스크롤바 트랙 폭만큼 좁아짐)를 없앤다. */
        .block-container::-webkit-scrollbar {
            width: 0px;
            height: 0px;
            display: none;
        }
        .block-container::before {
            content: "";
            display: block;
            position: sticky;
            top: 4px;
            left: 50%;
            transform: translateX(-50%);
            width: 100px;
            height: 20px;
            margin-bottom: 14px;
            background-color: #1a1d24;
            border-radius: 12px;
            z-index: 1000;
        }
"""


def inject_global_css(container_max_width: str = "1200px", phone_frame: bool = False):
    """전역 CSS 주입. 앱은 좁게(480px), 웹은 넓게(1200px) 쓰면 된다.

    phone_frame=True로 주면 block-container를 실제 스마트폰처럼 다크 베젤 +
    상단 노치가 있는 틀로 감싼다 (app_mobile.py 배터리 등록 화면 전용).
    """
    css = _CSS_TEMPLATE.replace("__CONTAINER_MAX_WIDTH__", container_max_width)
    css = css.replace("__PHONE_FRAME_CSS__", _PHONE_FRAME_CSS if phone_frame else "")
    st.markdown(css, unsafe_allow_html=True)


def render_list_header(title: str, sub: str, user_name: str, user_channel_line: str, badge_text: str | None = None) -> str:
    """배터리 관리/대시보드/처리업체 등 화이트 헤더 공통 마크업.

    badge_text를 주면 우측에 뱃지(예: "최종 확인 단계")가 사용자 정보 왼쪽에 붙는다.
    각 줄을 들여쓰기 없이(왼쪽 정렬) 만든 이유: st.markdown은 raw HTML을 넣기 전에
    먼저 마크다운으로 해석을 시도하는데, 4칸 이상 들여쓰인 줄은 코드블록으로
    오인될 수 있다. 그 가능성을 원천적으로 없애기 위해 들여쓰기를 전부 제거했다.
    """
    badge_html = f'<div class="triage-channel-badge">{badge_text}</div>' if badge_text else ""
    return (
        '<div class="list-header">'
        '<div class="list-header-left">'
        f'<p class="list-header-title">{title}</p>'
        f'<p class="list-header-sub">{sub}</p>'
        '</div>'
        '<div style="display:flex; align-items:center; gap:10px;">'
        '<div class="list-header-user">'
        f'<span class="list-header-user-name">{user_name} 님</span>'
        f'<span class="list-header-user-channel">{user_channel_line}</span>'
        '</div>'
        f'{badge_html}'
        '</div>'
        '</div>'
    )


def render_section_title(text: str, num: str | None = None, alert: bool = False) -> str:
    """카드 안 섹션 타이틀(예: "01 배터리 정보") 공통 마크업."""
    num_html = ""
    if num:
        num_cls = "section-num section-num-alert" if alert else "section-num"
        num_html = f'<div class="{num_cls}">{num}</div>'
    return f"""
    <div class="section-title-row">
        <div class="section-title-left">
            {num_html}
            <p class="section-title-text">{text}</p>
        </div>
    </div>
    """


GRADE_COLOR_HEX = {
    "Green": "#2e9e5b",
    "Yellow": "#f0c419",
    "Orange": "#e07a1f",
    "Gray": "#576574",
    "Red": "#cc3333",
    None: "#9aa5b1",
}

PATH_LABEL = {
    "reuse_candidate": "재사용 후보",
    "reuse_or_recycle_after_diagnosis": "추가진단 후 판단",
    "recycle_candidate": "재활용 후보",
    "diagnosis_required": "정밀진단 필요",
    "designated_waste": "지정폐기물 처리",
}


def dedent_html(html: str) -> str:
    """다중 라인 HTML 문자열의 각 줄 앞 공백을 전부 제거한다.

    st.markdown(..., unsafe_allow_html=True)은 HTML을 넣기 전에 먼저
    마크다운으로 해석을 시도하는데, 4칸 이상 들여쓰인 줄은 CommonMark의
    "들여쓰기 코드블록" 규칙에 걸려 HTML 태그가 그대로 이스케이프된 텍스트로
    노출된다(예: "<div>...</div>"가 화면에 글자 그대로 찍히는 버그).
    파이썬 코드 안에서 f-string으로 HTML을 만들면 자연스럽게 코드 들여쓰기를
    따라가게 되므로, st.markdown에 넘기기 직전에 항상 이 함수로 감싸서
    모든 줄을 왼쪽 정렬시킨다.
    """
    return "\n".join(line.strip() for line in html.strip("\n").splitlines())


def grade_badge_html(grade: str | None) -> str:
    """등급 뱃지 span HTML (카드 안 인라인용)."""
    g = grade or "미판정"
    color = GRADE_COLOR_HEX.get(grade, "#9aa5b1")
    return (
        f'<span style="background-color:{color}; color:#fff; font-size:11px; '
        f'font-weight:700; padding:2px 10px; border-radius:999px;">{g}</span>'
    )
