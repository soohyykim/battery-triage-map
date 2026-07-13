"""
app.py — BATLINK 통합 진입점.

기존에는 app_mobile.py(앱) / app_junkyard.py(웹·폐차장) / app_company.py
(웹·처리업체) 3개를 별도 포트로 따로 띄웠으나, 이제 하나의 URL 안에서
Streamlit의 st.navigation으로 화면을 전환하는 방식으로 통합했다.

사이드바는 역할별로 그룹(앱 / 웹·폐차장 / 웹·처리업체)이 나뉘어 표시된다
(st.navigation이 dict의 각 key를 섹션 제목으로, 섹션 사이에는 구분선을
자동으로 그려준다).

실행:
    streamlit run app.py

기존처럼 app_mobile.py / app_junkyard.py / app_company.py를 개별
실행하는 건 더 이상 지원하지 않는다 — 각 파일은 이제 최상위 실행 코드
없이 render_*() 함수만 내보내는 모듈이다.
"""

import os

# ---------------------------------------------------------------------------
# numpy가 쓰는 OpenBLAS가 컨테이너/공유 클라우드 환경(Streamlit Cloud 등)에서
# CPU 코어 수를 잘못 감지해, 임포트 시점에 스레드 풀을 초기화하다가 간헐적으로
# Segmentation fault를 일으키는 게 잘 알려진 문제다(numpy/OpenBLAS 공식
# 트러블슈팅 문서에도 나오는 케이스). numpy가 실제로 import되기 전에
# 스레드 수를 1로 강제해서 이 레이스 컨디션을 막는다.
#
# 반드시 이 파일에서 numpy를 (직접이든, streamlit/pandas/opencv 등을 통해
# 간접적이든) import하기 전에 실행돼야 하므로, 다른 import보다 앞에 둔다.
# ---------------------------------------------------------------------------
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import streamlit as st

import ui_common
from app_mobile import render_register
from app_junkyard import render_battery_list, render_dashboard, render_settings
from app_company import render_market

st.set_page_config(page_title="BATLINK", layout="wide")
ui_common.inject_global_css(container_max_width="1200px")

# ---------------------------------------------------------------------------
# 사이드바 순서 강제 조정 + 네비게이션 스타일
#
# st.navigation은 코드에 어디서 호출하든 사이드바 "맨 위"에 자기 자신을
# 렌더링해버린다(이 프로젝트 로고를 먼저 그려도 결과적으로 nav가 위로
# 올라온다). 코드 순서로는 못 이기므로, flexbox의 order 속성으로 강제
# 재배치한다 — 사이드바 컨테이너를 flex column으로 두고, nav 위젯에는
# 큰 order 값을, 나머지(로고 등)는 기본값(0)을 둬서 nav가 항상 아래로
# 가게 만든다.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        /* 사이드바 콘텐츠 영역을 flex column으로 강제 (order가 먹히려면 필요) */
        section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            display: flex !important;
            flex-direction: column !important;
        }
        /* 네비게이션 위젯 자체를 맨 뒤로 보내 로고보다 아래에 오게 한다 */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            order: 999 !important;
        }

        /* 네비게이션 글자색: 흰색 (슬로건 제외) */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a *,
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] span,
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] p,
        section[data-testid="stSidebar"] a[data-testid*="NavLink"],
        section[data-testid="stSidebar"] a[data-testid*="NavLink"] *,
        section[data-testid="stSidebar"] [data-testid*="NavSectionHeader"],
        section[data-testid="stSidebar"] [data-testid*="NavSectionHeader"] * {
            color: #ffffff !important;
        }

        /* 페이지 이름(배터리 등록/배터리 관리/대시보드/설정/마켓) 글자 확대.
           그룹 제목(앱/웹·폐차장/웹·처리업체)은 stSidebarNav의 섹션 헤더라
           별도 셀렉터로 손대지 않는 한 이 규칙의 영향을 덜 받는다. */
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span,
        section[data-testid="stSidebar"] a[data-testid*="NavLink"] span {
            font-size: 16px !important;
            font-weight: 600 !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 사이드바 로고 — 페이지와 무관하게 항상 최상단에 고정 표시
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        ui_common.dedent_html("""
        <div class="sidebar-logo">
            <div class="sidebar-logo-text">BATLINK</div>
            <div class="sidebar-logo-desc">배트링크</div>
            <div class="sidebar-logo-slogan">Every Battery Finds Its Next Life.</div>
        </div>
        """),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 통합 네비게이션 — 역할별로 그룹핑 (그룹 사이는 st.navigation이 자동으로
# 구분선을 넣어준다). 아이콘은 요청에 따라 제거했다.
# ---------------------------------------------------------------------------
pages = {
    "앱": [
        st.Page(render_register, title="배터리 등록", url_path="register"),
    ],
    "웹 · 폐차장": [
        st.Page(render_battery_list, title="배터리 관리", url_path="battery-list"),
        st.Page(render_dashboard, title="대시보드", url_path="dashboard"),
        st.Page(render_settings, title="설정", url_path="settings"),
    ],
    "웹 · 처리업체": [
        st.Page(render_market, title="마켓", url_path="market"),
    ],
}

nav = st.navigation(pages, position="sidebar")
nav.run()
