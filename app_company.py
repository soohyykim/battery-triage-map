"""
app_company.py — 웹(처리업체): 추천 매물 확인 + 협의 요청

BATLINK 앱/웹 3분리 중 "웹(처리업체)" 파트. 당근마켓의 상품 카드 그리드
레이아웃을 참고해 매물을 카드로 나열한다.

- 추천 매물: 판정 시 이미 계산된 1~3순위 매칭 결과(matched_companies)에
  현재 로그인한(선택한) 업체가 포함된 "매물 등록" 상태 배터리를 카드로 보여준다.
- 전체 매물 검색: 추천 여부와 무관하게 "매물 등록" 상태 전체를 필터로 탐색.
- 초기 화면은 최신 등록순(입고일 desc) 정렬 — 폐차장에서 새로 매물 등록하면
  맨 위에서 바로 확인 가능하다.
- 카드 클릭(상세보기) 시 모달에서 "협의 요청하기" 클릭 → "협의 중" 상태로 전환.
  이는 확정 계약이 아니라 관심 표명 단계이며, 실제 매입 계약과 정산은
  플랫폼 밖에서 폐차장·처리업체 당사자 간에 별도로 진행된다.

지정폐기물(Red)은 처리업체 매칭 대상에서 제외한다 — 지정폐기물 처리를
플랫폼이 중개하면 법적으로 애매하다는 지적에 따라, Red는 폐차장이 직접
'처리 완료' 처리하는 것으로 단순화했다 (app_junkyard.py 참고).

실제 로그인 시스템이 없어, 상단바에서 companies_mock.csv 중 하나를
"내 업체"로 선택하는 방식으로 처리업체 로그인을 목업한다. 기본 선택값은
강남폐차센터(현재 유일한 발생채널) 기준으로 가장 많이 매칭된 업체로
자동 지정된다.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import ui_common
from battery_data import (
    STATUS_LISTED,
    list_all_batteries,
    fetch_battery_detail,
    mark_negotiating,
    get_most_matched_company_name,
    haversine_km,
)

GRADE_EMOJI_MAP = {"Green": "🟢", "Yellow": "🟡", "Orange": "🟠", "Gray": "⚪", "Red": "🔴", "미판정": "⬜"}


# ---------------------------------------------------------------------------
# 상대 시간 표시 (당근마켓 스타일: "3분 전", "2일 전")
# ---------------------------------------------------------------------------
def _relative_time(iso_str):
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = delta.total_seconds()
        if seconds < 60:
            return "방금 전"
        if seconds < 3600:
            return f"{int(seconds // 60)}분 전"
        if seconds < 86400:
            return f"{int(seconds // 3600)}시간 전"
        return f"{int(seconds // 86400)}일 전"
    except (ValueError, TypeError):
        return iso_str[:10]


# ---------------------------------------------------------------------------
# 배터리 상세보기 + 구매하기 모달
# ---------------------------------------------------------------------------
@st.dialog("배터리 상세 정보", width="large")
def show_purchase_dialog(battery_id, match_info=None, selected_company=None):
    detail = fetch_battery_detail(battery_id)
    if not detail:
        st.error("배터리 정보를 찾을 수 없습니다.")
        return

    st.markdown(f"**{detail.get('vin') or '—'}**")
    st.caption(f"{detail.get('battery_manufacturer') or '제조사 미입력'} · {detail.get('model_name') or '모델명 미입력'}")

    d1, d2, d3 = st.columns(3)
    with d1:
        grade = detail.get("grade")
        st.metric("등급", f"{GRADE_EMOJI_MAP.get(grade, '⬜')} {grade or '미판정'}")
    with d2:
        st.metric("SOH Proxy", f"{detail['soh_proxy_score']}%" if detail.get("soh_proxy_score") is not None else "—")
    with d3:
        st.metric("용량", f"{detail.get('capacity_kwh')} kWh" if detail.get("capacity_kwh") is not None else "—")

    st.markdown(
        f"- 화학계: {detail.get('chemistry') or '—'} &nbsp;·&nbsp; "
        f"연식: {detail.get('vehicle_year') or '미입력'}년 &nbsp;·&nbsp; "
        f"주행거리: {(detail.get('mileage_km') or 0):,.0f} km"
    )
    path_label = ui_common.PATH_LABEL.get(detail.get("recommended_path"), detail.get("recommended_path") or "—")
    st.markdown(f"- 처리 방향: **{path_label}** &nbsp;·&nbsp; 접수처(폐차장): {detail.get('channel_name') or '—'}")
    st.caption(f"등록: {_relative_time(detail.get('created_at'))}")

    if match_info:
        st.markdown("---")
        st.markdown("**나에 대한 매칭 정보**")
        m1, m2 = st.columns(2)
        m1.metric("거리", f"{match_info.get('distance_km')} km")
        m2.metric("매칭 점수", f"{match_info.get('total_score'):.1f}" if match_info.get("total_score") is not None else "—")

    st.markdown("---")

    if detail.get("status") != STATUS_LISTED:
        st.info(f"현재 상태: {detail.get('status')} — 이미 다른 처리업체와 협의 중이거나 노출 전입니다.")
        if st.button("닫기", use_container_width=True):
            st.rerun()
        return

    st.caption("⚠ '협의 요청'은 확정 계약이 아닙니다. 실제 매입 계약과 정산은 이 요청 이후 폐차장·처리업체 당사자 간에 별도로 진행됩니다.")
    if st.button("협의 요청하기", use_container_width=True, type="primary", key="negotiate_btn"):
        ok = mark_negotiating(battery_id, requester_name=selected_company)
        if ok:
            st.success("협의 요청을 보냈습니다! 폐차장과 별도로 연락해 조건을 협의해주세요.")
            st.rerun()


# ---------------------------------------------------------------------------
# BATLINK 상품 카드 (로버블 목업 스타일 — 흰 배경 통일, 아이콘 고정)
# ---------------------------------------------------------------------------
GRADE_BADGE_BG = {
    "Green": "rgba(46,158,91,0.12)", "Yellow": "rgba(240,196,25,0.18)",
    "Orange": "rgba(224,122,31,0.12)", "Gray": "rgba(87,101,116,0.12)",
    "Red": "rgba(204,51,51,0.12)", None: "rgba(154,165,177,0.12)",
}
GRADE_DOT_COLOR = {
    "Green": "#2e9e5b", "Yellow": "#c99a00", "Orange": "#e07a1f",
    "Gray": "#576574", "Red": "#cc3333", None: "#9aa5b1",
}


def _battery_card(battery, match_info=None, key_prefix="", is_recommended=False, distance_km=None, selected_company=None):
    grade = battery.get("grade") or "미판정"
    chemistry = battery.get("chemistry") or "UNKNOWN"
    capacity = battery.get("capacity_kwh")
    soh = battery.get("soh_proxy_score")
    capacity_text = f"{capacity:.1f}kWh" if isinstance(capacity, (int, float)) else "용량 미입력"
    soh_text = f"SOH {soh:.0f}%" if isinstance(soh, (int, float)) else "SOH 미판정"

    match_pct = f"{match_info['total_score']:.0f}% 매칭" if match_info and match_info.get("total_score") is not None else None
    dist_text = f"{distance_km}km" if distance_km is not None else "—"

    match_badge_html = (
        f'<span style="background:#00b5b5; color:#fff; font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px;">{match_pct}</span>'
        if match_pct else ""
    )
    icon_html = "🔋"
    icon_bg = "var(--c-secondary)"
    button_label = "상세보기 / 협의 요청"

    st.markdown(
        ui_common.dedent_html(f"""
        <div style="background-color: var(--c-card); border: 1px solid var(--c-border); border-radius: 14px; overflow:hidden; margin-bottom: 8px; min-height: 258px; box-sizing: border-box;">
            <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 12px 0 12px; min-height:26px;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="background:{GRADE_BADGE_BG.get(grade)}; color:{GRADE_DOT_COLOR.get(grade)}; font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px;">&#9679; {grade}</span>
                    <span style="background:var(--c-secondary); color:var(--c-muted-foreground); font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px;">{chemistry}</span>
                </div>
                {match_badge_html}
            </div>
            <div style="height:120px; background:{icon_bg}; margin:10px 12px; border-radius:10px; display:flex; align-items:center; justify-content:center;">
                <span style="font-size:44px;">{icon_html}</span>
            </div>
            <div style="padding:0 12px 14px 12px;">
                <div style="font-size:14px; font-weight:700; color:var(--c-foreground); margin-bottom:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                    {battery.get('model_name') or '모델명 미입력'} · {capacity_text} · {soh_text}
                </div>
                <div style="font-size:12px; color:var(--c-muted-foreground); margin-bottom:3px;">
                    {capacity_text} · {chemistry}
                </div>
                <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--c-muted-foreground); margin-bottom:3px;">
                    <span>&#128205; {battery.get('channel_name') or '폐차장 미상'}</span>
                    <span>{dist_text}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--c-muted-foreground);">
                    <span>&#128267; {soh_text}</span>
                    <span>{_relative_time(battery.get('created_at'))}</span>
                </div>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )
    if st.button(button_label, use_container_width=True, key=f"{key_prefix}_{battery['id']}"):
        show_purchase_dialog(battery["id"], match_info=match_info, selected_company=selected_company)


def _render_card_grid(items_with_match, key_prefix, selected_company, cols_per_row=4):
    for i in range(0, len(items_with_match), cols_per_row):
        row_items = items_with_match[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (battery, match_info, is_rec, dist) in zip(cols, row_items):
            with col:
                _battery_card(battery, match_info=match_info, key_prefix=key_prefix, is_recommended=is_rec, distance_km=dist, selected_company=selected_company)


def render_market():
    ui_common.inject_global_css(container_max_width="1200px")

    # ---------------------------------------------------------------------------
    # 업체 데이터 로드
    # ---------------------------------------------------------------------------
    _company_csv = Path(__file__).parent / "data" / "companies_mock.csv"
    _df_co = pd.read_csv(_company_csv) if _company_csv.exists() else pd.DataFrame()

    if _df_co.empty:
        st.error("처리업체 데이터를 불러오지 못했습니다.")
        st.stop()

    company_names = _df_co["company_name"].dropna().unique().tolist()

    # 기본 선택: 강남폐차센터(현재 유일한 발생채널) 기준으로 가장 많이
    # 매칭된 업체. 계산 실패/데이터 없음이면 목록 첫 번째로 폴백.
    if "my_company_default_computed" not in st.session_state:
        with st.spinner("최다 매칭 업체 계산 중..."):
            top_company = get_most_matched_company_name()
        st.session_state.my_company_default_computed = True
        st.session_state.my_company_default = top_company if top_company in company_names else company_names[0]

    # ---------------------------------------------------------------------------
    # 상단바 — 사이드바 없이 플랫폼명 + 검색창 + 업체 선택을 한 줄에 배치
    # (당근마켓 상단 내비게이션 참고)
    # ---------------------------------------------------------------------------
    top_logo_col, top_search_col, top_login_col = st.columns([2, 4, 2])

    with top_logo_col:
        st.markdown(
            ui_common.dedent_html(
                """
                <div style="display:flex; align-items:center; height:100%;">
                    <div>
                        <div style="font-size:1.9rem; font-weight:800; color:var(--c-foreground); line-height:1.1;">BATLINK</div>
                        <div style="font-size:11px; color:var(--c-muted-foreground);">배트링크 · 처리업체</div>
                        <div style="font-size:11px; color:#00838a; font-style:italic; font-weight:600; margin-top:2px;">Every Battery Finds Its Next Life.</div>
                    </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    with top_search_col:
        search_query = st.text_input(
            "검색",
            placeholder="검색어를 입력해주세요 (모델명, VIN)",
            label_visibility="collapsed",
            key="top_search_query",
        )

    with top_login_col:
        default_index = company_names.index(st.session_state.my_company_default)
        selected_company = st.selectbox(
            "내 업체",
            company_names,
            index=default_index,
            label_visibility="collapsed",
            key="my_company",
        )

    my_company_row = _df_co[_df_co["company_name"] == selected_company].iloc[0]
    my_lat, my_lon = my_company_row.get("latitude"), my_company_row.get("longitude")
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)





    # ---------------------------------------------------------------------------
    # 필터 (네이티브 사이드바 대신 메인 콘텐츠 영역에 고정 배치)
    # st.sidebar에 두면 사용자가 사이드바를 접었을 때 필터가 통째로 사라진다.
    # 로버블 목업처럼 항상 보이는 좌측 패널로 만들기 위해 컬럼으로 구현한다.
    # ---------------------------------------------------------------------------
    filter_col, main_col = st.columns([1, 3], gap="medium")

    with filter_col:
        st.markdown(
            """
            <style>
                div[class*="st-key-filter_reset_btn"] button {
                    background: transparent !important;
                    border: none !important;
                    box-shadow: none !important;
                    padding: 0 !important;
                    min-height: auto !important;
                    height: auto !important;
                    font-size: 16px !important;
                    font-weight: 700 !important;
                    color: var(--c-muted-foreground) !important;
                    text-decoration: underline;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
        fh1, fh2 = st.columns([3, 1])
        with fh1:
            st.markdown("**필터**")
        with fh2:
            if st.button("초기화", key="filter_reset_btn"):
                for k in ("f_region", "f_distance", "f_cap_min", "f_cap_max",
                          "f_chem_ncm", "f_chem_lfp",
                          "f_grade_Green", "f_grade_Yellow", "f_grade_Orange",
                          "f_grade_Gray"):
                    st.session_state.pop(k, None)
                st.rerun()

        with st.form("company_filter_form"):
            region_options = ["전체"] + sorted(_df_co["region"].dropna().unique().tolist())
            f_region = st.selectbox("위치", region_options, key="f_region")
            st.form_submit_button("현 위치로 설정", use_container_width=True, disabled=True)

            st.markdown("**등급**")
            grade_checks = {}
            for g, desc in [("Green", "재사용"), ("Yellow", "재사용·재활용 검토"), ("Orange", "재활용"),
                            ("Gray", "정보누락")]:
                grade_checks[g] = st.checkbox(f"{g} ({desc})", value=(g in ("Green", "Yellow")), key=f"f_grade_{g}")

            st.markdown("**거리 (km)**")
            f_distance = st.slider("거리", 1, 50, 50, label_visibility="collapsed", key="f_distance")

            st.markdown("**용량 (kWh)**")
            cap_col1, cap_col2 = st.columns(2)
            with cap_col1:
                f_cap_min = st.number_input("최소", min_value=0.0, value=0.0, step=1.0, key="f_cap_min")
            with cap_col2:
                f_cap_max = st.number_input("최대", min_value=0.0, value=200.0, step=1.0, key="f_cap_max")

            st.markdown("**화학계**")
            chem_col1, chem_col2 = st.columns(2)
            with chem_col1:
                f_chem_ncm = st.checkbox("NCM", value=True, key="f_chem_ncm")
            with chem_col2:
                f_chem_lfp = st.checkbox("LFP", value=True, key="f_chem_lfp")

            st.form_submit_button("조건 적용", use_container_width=True, type="primary")

    with main_col:
        # ---------------------------------------------------------------------------
        # 매물(=매물 등록 상태) 전체 로드 (최신순 — list_all_batteries가 이미 정렬함)
        # 이 업체가 추천 대상인 건 별도 구분, 거리는 haversine으로 실제 계산
        # ---------------------------------------------------------------------------
        listed_batteries = [b for b in list_all_batteries() if b["status"] == STATUS_LISTED]

        for b in listed_batteries:
            b["_distance_km"] = haversine_km(my_lat, my_lon, b.get("origin_latitude"), b.get("origin_longitude"))

        recommended = []
        recommended_ids = set()
        with st.spinner("추천 매물을 불러오는 중..."):
            for b in listed_batteries:
                detail = fetch_battery_detail(b["id"])
                if not detail:
                    continue
                for m in detail.get("matched_companies", []):
                    if m.get("company_name") == selected_company:
                        dist = m.get("distance_km", b.get("_distance_km"))
                        recommended.append((b, m, True, dist))
                        recommended_ids.add(b["id"])
                        break

        # ---------------------------------------------------------------------------
        # 1) 추천 매물 (카드 그리드)
        # ---------------------------------------------------------------------------
        st.markdown("#### 추천 매물")
        if not recommended:
            st.info("현재 추천된 매물이 없습니다. 아래 전체 매물 검색에서 직접 찾아보세요.")
        else:
            _render_card_grid(recommended[:3], key_prefix="rec", selected_company=selected_company)

        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

        # ---------------------------------------------------------------------------
        # 2) 전체 매물 검색 (사이드바 필터 적용 + 정렬 + 카드 그리드)
        # ---------------------------------------------------------------------------
        selected_grades = [g for g in ["Green", "Yellow", "Orange", "Gray"] if st.session_state.get(f"f_grade_{g}")]
        selected_chemistries = []
        if st.session_state.get("f_chem_ncm"):
            selected_chemistries.append("NCM")
        if st.session_state.get("f_chem_lfp"):
            selected_chemistries.append("LFP")

        filtered_all = listed_batteries
        if search_query:
            q = search_query.lower()
            filtered_all = [
                b for b in filtered_all
                if q in (b.get("model_name") or "").lower() or q in (b.get("vin") or "").lower()
            ]
        if selected_grades:
            filtered_all = [b for b in filtered_all if b.get("grade") in selected_grades]
        if selected_chemistries:
            filtered_all = [b for b in filtered_all if b.get("chemistry") in selected_chemistries]
        filtered_all = [b for b in filtered_all if st.session_state.get("f_cap_min", 0) <= (b.get("capacity_kwh") or 0) <= st.session_state.get("f_cap_max", 10_000)]
        max_dist = st.session_state.get("f_distance", 50)
        filtered_all = [b for b in filtered_all if b.get("_distance_km") is None or b.get("_distance_km") <= max_dist]
        # 참고: "위치" 필터는 로버블 목업의 UI만 재현했다. 현재 배터리 발생지가
        # 강남폐차센터 단일 채널이라 지역별로 나눠 필터링할 실제 데이터가 없어서,
        # 선택은 가능하지만 목록에는 영향을 주지 않는다(거리 슬라이더가 실질적인
        # 위치 기반 필터 역할을 한다).

        top_row1, top_row2 = st.columns([4, 1])
        with top_row1:
            st.markdown("#### 전체 매물")
            st.caption(f"필터 조건에 맞는 {len(filtered_all)}건")
        with top_row2:
            sort_option = st.selectbox("정렬", ["최신순", "등급순", "거리순"], label_visibility="collapsed", key="sort_option")

        if sort_option == "등급순":
            grade_order = {"Green": 0, "Yellow": 1, "Orange": 2, "Gray": 3, "Red": 4, None: 5}
            filtered_all = sorted(filtered_all, key=lambda b: grade_order.get(b.get("grade"), 5))
        elif sort_option == "거리순":
            filtered_all = sorted(filtered_all, key=lambda b: (b.get("_distance_km") is None, b.get("_distance_km") or 0))
        # "최신순"은 list_all_batteries()가 이미 created_at desc로 정렬해뒀으므로 그대로 둔다.

        if not filtered_all:
            st.info("조건에 맞는 매물이 없습니다.")
        else:
            items = [(b, None, b["id"] in recommended_ids, b.get("_distance_km")) for b in filtered_all]
            _render_card_grid(items, key_prefix="all", selected_company=selected_company)
