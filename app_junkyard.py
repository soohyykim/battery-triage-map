"""
app_junkyard.py — 웹(폐차장): 배터리 관리 + 대시보드

BATLINK 앱/웹 3분리 중 "웹(폐차장)" 파트.
- 배터리 관리: 엑셀 대량 등록(목업) / 필터 조회 / CSV 다운로드 /
  체크박스 선택 기반 판정·상세보기·매물 등록·삭제
- 대시보드: 배터리 현황, 등급 분포, 최근 14일 등록 추이, 처리업체 현황,
  정산·예상 수익(목업), 정책·뉴스 브리핑(정적)

체크박스는 커스텀 HTML(iframe) 테이블 대신 Streamlit 네이티브
st.data_editor의 체크박스 컬럼을 사용한다 — 브릿지 없이 선택 상태를
바로 Python에서 읽을 수 있어 안정적이다. 다만 컬러 뱃지 대신 이모지+
텍스트로 등급/상태를 표시하는 절충안을 적용했다.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import ui_common
from battery_data import (
    API_BASE_URL,
    DUMMY_USER,
    STATUS_REGISTERED,
    STATUS_TRIAGED,
    STATUS_LISTED,
    STATUS_NEGOTIATING,
    STATUS_COMPLETED,
    ALL_STATUSES,
    CHANNEL_NAMES,
    list_all_batteries,
    fetch_battery_detail,
    add_pending_registrations,
    triage_pending_registrations_bulk,
    mark_listed,
    mark_disposed,
    delete_batteries_bulk,
    get_status_counts,
    get_grade_counts,
    reset_local_state,
)

GRADE_EMOJI_MAP = {"Green": "🟢", "Yellow": "🟡", "Orange": "🟠", "Gray": "⚪", "Red": "🔴", "미판정": "⬜"}


def _receipt_no(battery):
    """B-2026-0011 형식의 접수번호 표시용 문자열. '등록' 상태(로컬 대기)는
    아직 실제 triage_id가 없어 접두사를 P-로 구분한다."""
    bid = battery.get("id")
    year = (battery.get("created_at") or "")[:4] or "----"
    if isinstance(bid, str) and bid.startswith("local-"):
        return f"P-{bid.split('-')[-1][:6].upper()}"
    try:
        return f"B-{year}-{int(bid):04d}"
    except (TypeError, ValueError):
        return f"B-{year}-{bid}"

# ---------------------------------------------------------------------------
# 배터리 상세보기 모달 — PDF(배터리 판정서) / 정책 리포트(AI)
# ---------------------------------------------------------------------------
@st.dialog("배터리 상세 정보 · 판정 결과", width="large")
def show_detail_dialog(battery_id):
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
        st.metric("현재 상태", detail.get("status", "—"))

    cap = detail.get("capacity_kwh")
    st.markdown("**배터리 정보**")
    st.markdown(
        f"- 용량: {cap if cap is not None else '—'} kWh &nbsp;·&nbsp; 화학계: {detail.get('chemistry') or '—'}\n"
        f"- 연식: {detail.get('vehicle_year') or '미입력'}년 &nbsp;·&nbsp; 주행거리: {(detail.get('mileage_km') or 0):,.0f} km"
    )

    path_label = ui_common.PATH_LABEL.get(detail.get("recommended_path"), detail.get("recommended_path") or "—")
    st.markdown("**Triage 판정**")
    e1, e2 = st.columns(2)
    with e1:
        st.write(f"처리 방향: **{path_label}**")
        st.write(f"재사용 점수: {detail.get('reuse_score') if detail.get('reuse_score') is not None else '—'}")
    with e2:
        conf = detail.get("data_confidence")
        st.write(f"데이터 신뢰도: {f'{conf:.0%}' if isinstance(conf, (int, float)) else '—'}")
        st.write(f"재활용 점수: {detail.get('recycle_score') if detail.get('recycle_score') is not None else '—'}")

    matched_companies = detail.get("matched_companies") or []
    if matched_companies:
        st.markdown("**추천 처리업체**")
        for c in matched_companies[:3]:
            st.write(
                f"{c.get('rank')}순위 · **{c.get('company_name')}** "
                f"({c.get('region') or '—'} · {c.get('distance_km')}km · 점수 {c.get('total_score')})"
            )

    # /pdf/triage, /report 는 TriageResponse 형태의 dict를 기대하므로,
    # /history 상세 응답(HistoryDetail)에서 필요한 필드를 재구성한다.
    triage_result_for_api = {
        "status": "rule_checked",
        "result_type": "preliminary_estimate",
        "input_summary": {
            "manufacturer": detail.get("battery_manufacturer"),
            "model_name": detail.get("model_name"),
            "vehicle_year": detail.get("vehicle_year"),
            "mileage_km": detail.get("mileage_km"),
            "capacity_kwh": detail.get("capacity_kwh"),
            "chemistry": detail.get("chemistry"),
            "battery_count": 1,
        },
        "soh_proxy_score": detail.get("soh_proxy_score"),
        "reuse_score": detail.get("reuse_score"),
        "recycle_score": detail.get("recycle_score"),
        "grade": detail.get("grade"),
        "recommended_path": detail.get("recommended_path"),
        "required_diagnostic_capability": "basic",
        "collection_route": "—",
        "data_confidence": detail.get("data_confidence"),
        "reason_codes": [],
        "triage_id": detail.get("id"),
    }

    st.markdown("---")
    pdf_col, report_col = st.columns(2)

    with pdf_col:
        if st.button("PDF 다운로드 (배터리 판정서)", use_container_width=True, key="dl_pdf_btn"):
            try:
                with st.spinner("판정서를 생성하는 중..."):
                    resp = requests.post(
                        f"{API_BASE_URL}/pdf/triage",
                        json={"triage_result": triage_result_for_api},
                        timeout=30,
                    )
                    resp.raise_for_status()
                st.download_button(
                    "다운로드 준비 완료 — 클릭해서 저장",
                    data=resp.content,
                    file_name=f"battery_report_{detail['id']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_pdf_ready",
                )
            except requests.RequestException as e:
                st.error(f"PDF 생성에 실패했습니다: {e}")

    with report_col:
        if st.button("정책 리포트 생성 (AI)", use_container_width=True, type="primary", key="policy_report_btn"):
            try:
                with st.spinner("정책 RAG 리포트를 생성하는 중... (최대 1분 소요)"):
                    resp = requests.post(
                        f"{API_BASE_URL}/report",
                        json={
                            "triage_result": triage_result_for_api,
                            "matched_companies": matched_companies,
                        },
                        timeout=90,
                    )
                    resp.raise_for_status()
                    report_data = resp.json()
                st.markdown(report_data.get("report", "리포트 내용이 비어 있습니다."))
                if report_data.get("sources"):
                    st.caption("출처: " + ", ".join(report_data["sources"]))
            except requests.RequestException as e:
                st.error(f"정책 리포트 생성에 실패했습니다: {e}")

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    if st.button("닫기", use_container_width=True, key="detail_close_btn"):
        st.rerun()


# ---------------------------------------------------------------------------
# 배터리 관리 페이지
# ---------------------------------------------------------------------------
def render_battery_list():
    ui_common.inject_global_css(container_max_width="1200px")
    st.markdown(
        ui_common.render_list_header(
            "배터리 관리",
            "보유 배터리 현황 조회 및 상태 관리",
            DUMMY_USER["name"],
            f"{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}",
        ),
        unsafe_allow_html=True,
    )

    # 이 페이지 전용 버튼들(초기화 등)만 흰색/아웃라인 스타일로 통일.
    # 전역 CSS(div.stButton > button)를 바꾸면 앱 전체 버튼이 다 바뀌어버리므로,
    # key로 범위를 좁혀서 이 페이지 버튼에만 적용한다.
    st.markdown(
        """
        <style>
            div[class*="st-key-bl_reset_btn"] button,
            div[class*="st-key-bl_bulk_run"] button,
            div[class*="st-key-bl_detail_btn"] button {
                background-color: #ffffff !important;
                color: var(--c-foreground) !important;
                border: 1px solid var(--c-border) !important;
                box-shadow: none !important;
                font-weight: 700 !important;
            }
            div[class*="st-key-bl_reset_btn"] button:hover,
            div[class*="st-key-bl_bulk_run"] button:hover,
            div[class*="st-key-bl_detail_btn"] button:hover {
                background-color: var(--c-secondary) !important;
                filter: none !important;
            }
            /* 초기화·일괄작업 실행 버튼은 옆 셀렉트박스와 높이를 맞춘다 */
            div[class*="st-key-bl_reset_btn"] button,
            div[class*="st-key-bl_bulk_run"] button {
                height: 38px !important;
                padding: 0 14px !important;
                min-height: 38px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


    # ------------------------------------------------------------------
    # 엑셀 대량 등록 (목업 — 판정 없이 '등록' 상태로만 로컬 공유 파일에 추가)
    # ------------------------------------------------------------------
    with st.expander("📤 엑셀로 대량 등록", expanded=False):
        st.caption("필요 컬럼: VIN, 모델명, 제조사, 연식, 주행거리, 용량, 화학계 (컬럼명이 달라도 유사하게 인식 시도)")

        template_df = pd.DataFrame([{
            "VIN": "KMHXX00XXXX000000",
            "모델명": "아이오닉5",
            "제조사": "현대자동차(주)",
            "연식": 2021,
            "주행거리": 45000,
            "용량": 77.4,
            "화학계": "NCM",
        }])
        st.download_button(
            "📄 업로드 템플릿 다운로드 (.csv)",
            data=template_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="battery_upload_template.csv",
            mime="text/csv",
            key="bl_template_download_btn",
        )

        upload_channel = st.selectbox("발생 폐차장", CHANNEL_NAMES, key="upload_channel")
        uploaded_file = st.file_uploader("엑셀(.xlsx) 또는 CSV 파일 선택", type=["xlsx", "xls", "csv"])

        if uploaded_file is not None:
            try:
                if uploaded_file.name.lower().endswith(".csv"):
                    df_up = pd.read_csv(uploaded_file)
                else:
                    df_up = pd.read_excel(uploaded_file)
            except Exception as e:
                st.error(f"파일을 읽지 못했습니다: {e}")
                df_up = None

            if df_up is not None:
                st.dataframe(df_up.head(20), use_container_width=True, hide_index=True)

                def _col(row, *candidates):
                    for c in candidates:
                        if c in row and pd.notna(row[c]):
                            return row[c]
                    return None

                if st.button(f"{len(df_up)}건 '등록' 상태로 추가", type="primary"):
                    records = []
                    for _, row in df_up.iterrows():
                        records.append({
                            "vin": _col(row, "VIN", "vin", "차대번호"),
                            "model_name": _col(row, "모델명", "model_name", "차량모델명"),
                            "manufacturer": _col(row, "제조사", "manufacturer", "배터리제조사"),
                            "vehicle_year": _col(row, "연식", "vehicle_year"),
                            "mileage_km": _col(row, "주행거리", "주행거리(km)", "mileage_km"),
                            "capacity_kwh": _col(row, "용량", "용량(kWh)", "capacity_kwh"),
                            "chemistry": _col(row, "화학계", "chemistry"),
                        })
                    added = add_pending_registrations(records, channel_name=upload_channel)
                    st.success(f"{len(added)}건이 '{upload_channel}' 발생 '등록' 상태로 추가되었습니다. 아래 목록에서 확인 후 '판정'을 진행하세요.")
                    st.rerun()

    # ------------------------------------------------------------------
    # 필터 — VIN/모델명/제조사 (1행), 등급/상태 + 초기화/일괄작업 (2행)
    # ------------------------------------------------------------------
    all_batteries = list_all_batteries()

    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        st.markdown('<p class="field-label">차대번호(VIN)</p>', unsafe_allow_html=True)
        q_vin = st.text_input("VIN", placeholder="VIN 입력", label_visibility="collapsed", key="bl_q_vin")
    with r1c2:
        st.markdown('<p class="field-label">차량모델명</p>', unsafe_allow_html=True)
        q_model = st.text_input("모델명", placeholder="모델명 입력", label_visibility="collapsed", key="bl_q_model")
    with r1c3:
        st.markdown('<p class="field-label">배터리 제조사</p>', unsafe_allow_html=True)
        q_manufacturer = st.text_input("제조사", placeholder="제조사 입력", label_visibility="collapsed", key="bl_q_mfr")

    r2c1, r2c2, r2c3, r2c4 = st.columns([2, 2, 1, 2])
    with r2c1:
        st.markdown('<p class="field-label">등급</p>', unsafe_allow_html=True)
        q_grade = st.selectbox("등급", ["전체", "Green", "Yellow", "Orange", "Gray", "Red", "미판정"], label_visibility="collapsed", key="bl_q_grade")
    with r2c2:
        st.markdown('<p class="field-label">상태</p>', unsafe_allow_html=True)
        q_status = st.selectbox("상태", ALL_STATUSES, label_visibility="collapsed", key="bl_q_status")
    with r2c3:
        st.markdown('<p class="field-label">&nbsp;</p>', unsafe_allow_html=True)
        if st.button("초기화", use_container_width=True, key="bl_reset_btn"):
            for k in ("bl_q_vin", "bl_q_model", "bl_q_mfr", "bl_q_grade", "bl_q_status"):
                st.session_state.pop(k, None)
            st.rerun()
    with r2c4:
        st.markdown('<p class="field-label">&nbsp;</p>', unsafe_allow_html=True)
        # 일괄 작업(판정/매물등록/처리완료/상세보기/삭제) 토글은 아래 테이블에서
        # 선택된 건을 대상으로 동작해야 하므로, 실제 위젯은 테이블 렌더링 이후
        # (selected_ids 계산 후)에 채워 넣는다. st.empty()로 자리만 여기 잡아두면
        # 화면상으로는 '초기화' 오른쪽에 그대로 나타난다. (이 칸 자체가 이미
        # 1단계 중첩 컬럼이라, placeholder 안에서 또 st.columns를 쓰면 2단계
        # 중첩이 되어 Streamlit이 막는다 — 그래서 바깥 r2 행을 4칸으로
        # 미리 나눠, placeholder 안쪽에서 한 번만 더 나눌 수 있게 했다.)
        bulk_action_placeholder = st.empty()

    filtered = all_batteries
    if q_vin:
        filtered = [b for b in filtered if q_vin.lower() in (b.get("vin") or "").lower()]
    if q_model:
        filtered = [b for b in filtered if q_model.lower() in (b.get("model_name") or "").lower()]
    if q_manufacturer:
        filtered = [b for b in filtered if q_manufacturer.lower() in (b.get("battery_manufacturer") or "").lower()]
    if q_grade != "전체":
        filtered = [b for b in filtered if (b.get("grade") or "미판정") == q_grade]
    if q_status != "전체":
        filtered = [b for b in filtered if b.get("status") == q_status]

    st.markdown(
        f'<div style="display:flex; align-items:baseline; justify-content:space-between; margin-top:6px;">'
        f'<span style="font-size:14px; color:var(--c-foreground);">조회건수 <b>{len(filtered)}건</b></span>'
        f'<span style="font-size:12px; color:var(--c-muted-foreground);">최근 접수순</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("조건에 맞는 배터리가 없습니다.")
        return

    # ------------------------------------------------------------------
    # 전체 선택 체크박스 (기존 "전체 선택"/"전체 해제" 버튼 2개를 하나로 통합)
    # + 선택 건수 표시를 표 위쪽으로 이동 (값 자체는 data_editor 결과가
    #   나와야 계산되므로, 자리만 먼저 잡아두고 아래에서 채운다)
    # ------------------------------------------------------------------
    if "bl_select_all_version" not in st.session_state:
        st.session_state.bl_select_all_version = 0
    if "bl_select_all_value" not in st.session_state:
        st.session_state.bl_select_all_value = False

    sel_row_col1, sel_row_col2 = st.columns([2, 10])
    with sel_row_col1:
        select_all_checked = st.checkbox(
            "전체 선택",
            value=st.session_state.bl_select_all_value,
            key="bl_select_all_checkbox",
        )
    if select_all_checked != st.session_state.bl_select_all_value:
        st.session_state.bl_select_all_value = select_all_checked
        st.session_state.bl_select_all_version += 1
        st.rerun()
    with sel_row_col2:
        selected_count_placeholder = st.empty()

    # ------------------------------------------------------------------
    # 체크박스 리스트 (st.data_editor 네이티브 체크박스 컬럼)
    # ------------------------------------------------------------------
    display_rows = []
    for b in filtered:
        grade = b.get("grade") or "미판정"
        status = b.get("status")
        display_rows.append({
            "선택": st.session_state.bl_select_all_value,
            "접수번호": _receipt_no(b),
            "VIN": b.get("vin") or "—",
            "모델명": b.get("model_name") or "—",
            "제조사": b.get("battery_manufacturer") or "—",
            "용량(kWh)": b.get("capacity_kwh") if b.get("capacity_kwh") is not None else "—",
            "등급": grade,
            "상태": status,
            "추천업체": b.get("matched_company") or "—",
            "입고일": (b.get("created_at") or "")[:10] or "—",
            "_id": b.get("id"),
        })

    df = pd.DataFrame(display_rows)

    edited = st.data_editor(
        df,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False, width="small"),
        },
        disabled=["접수번호", "VIN", "모델명", "제조사", "용량(kWh)", "등급", "상태", "추천업체", "입고일"],
        hide_index=True,
        use_container_width=True,
        column_order=["선택", "접수번호", "VIN", "모델명", "제조사", "용량(kWh)", "등급", "상태", "추천업체", "입고일"],
        key=f"battery_editor_{st.session_state.bl_select_all_version}",
    )

    selected_ids = edited.loc[edited["선택"], "_id"].tolist()
    all_by_id = {b["id"]: b for b in filtered}

    selected_count_placeholder.markdown(
        f'<div style="font-size:12px; color:var(--c-muted-foreground); text-align:right; margin-top:6px;">'
        f'{f"{len(selected_ids)}건 선택" if selected_ids else "전체"}</div>',
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # 일괄 작업 토글 — 판정 / 매물 등록 / 처리 완료(지정폐기물) / 상세보기 / 삭제
    # 필터 영역의 '초기화' 오른쪽 자리(placeholder)에 실제로 렌더링된다.
    # ------------------------------------------------------------------
    with bulk_action_placeholder.container():
        bac1, bac2 = st.columns([2, 1])
        with bac1:
            bulk_action = st.selectbox(
                "일괄 작업",
                ["작업 선택", "판정", "매물 등록", "처리 완료 (지정폐기물)", "상세보기", "삭제"],
                label_visibility="collapsed",
                key="bl_bulk_action",
            )
        with bac2:
            run_clicked = st.button("실행", use_container_width=True, key="bl_bulk_run")

    if run_clicked:
        if bulk_action == "작업 선택":
            st.warning("실행할 작업을 선택해주세요.")

        elif bulk_action == "판정":
            targets = [bid for bid in selected_ids
                       if all_by_id.get(bid, {}).get("status") == STATUS_REGISTERED]
            if not targets:
                st.warning("'등록' 상태인 배터리를 선택해주세요.")
            else:
                with st.spinner(f"{len(targets)}건 판정 처리 중..."):
                    ok, fail = triage_pending_registrations_bulk(targets)
                if ok:
                    st.success(f"{len(ok)}건 판정 완료")
                if fail:
                    st.error(f"{len(fail)}건 판정 실패")
                st.rerun()

        elif bulk_action == "매물 등록":
            targets = [bid for bid in selected_ids
                       if all_by_id.get(bid, {}).get("status") == STATUS_TRIAGED]
            skipped_not_triaged = len(selected_ids) - len(targets)
            if not targets:
                st.warning("'판정' 상태인 배터리를 선택해주세요.")
            else:
                listed, rejected = mark_listed(targets)
                if listed:
                    st.success(f"{len(listed)}건 매물 등록 완료")
                if rejected:
                    st.warning(f"Red(지정폐기물) 등급 {len(rejected)}건은 매물 등록에서 제외되었습니다.")
                if skipped_not_triaged:
                    st.info(f"'판정' 상태가 아닌 {skipped_not_triaged}건은 건너뛰었습니다.")
                st.rerun()

        elif bulk_action == "처리 완료 (지정폐기물)":
            targets = [bid for bid in selected_ids if all_by_id.get(bid, {}).get("grade") == "Red"]
            skipped = len(selected_ids) - len(targets)
            if not targets:
                st.warning("Red(지정폐기물) 등급 배터리를 선택해주세요.")
            else:
                for bid in targets:
                    mark_disposed(bid)
                st.success(f"{len(targets)}건 처리 완료로 전환했습니다.")
                if skipped:
                    st.info(f"Red가 아닌 {skipped}건은 건너뛰었습니다.")
                st.rerun()

        elif bulk_action == "상세보기":
            if len(selected_ids) != 1:
                st.warning("상세보기는 1건만 선택해주세요.")
            elif str(selected_ids[0]).startswith("local-"):
                st.warning("'등록' 상태 배터리는 판정 후에 상세보기가 가능합니다.")
            else:
                show_detail_dialog(selected_ids[0])

        elif bulk_action == "삭제":
            if not selected_ids:
                st.warning("삭제할 배터리를 선택해주세요.")
            else:
                deleted = delete_batteries_bulk(selected_ids)
                st.success(f"{len(deleted)}건 삭제되었습니다.")
                st.rerun()


# ---------------------------------------------------------------------------
# 대시보드 페이지
# ---------------------------------------------------------------------------
def render_dashboard():
    ui_common.inject_global_css(container_max_width="1200px")
    st.markdown(
        ui_common.render_list_header(
            "대시보드",
            "배터리 현황 · 처리업체 현황 · 정책 브리핑",
            DUMMY_USER["name"],
            f"{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}",
        ),
        unsafe_allow_html=True,
    )

    all_batteries = list_all_batteries()
    status_counts = get_status_counts()
    grade_counts = get_grade_counts()

    total_count = len(all_batteries)
    registered_count = status_counts.get(STATUS_REGISTERED, 0)
    # 판정 완료 = 등록을 제외한 전부 (지정폐기물의 처리 완료도 포함).
    # 판정 완료율 = 판정 완료 수 / (판정 완료 수 + 등록 수)
    judged_count = (status_counts.get(STATUS_TRIAGED, 0) + status_counts.get(STATUS_LISTED, 0)
                    + status_counts.get(STATUS_NEGOTIATING, 0) + status_counts.get(STATUS_COMPLETED, 0))
    judge_rate = round(judged_count / (judged_count + registered_count) * 100) if (judged_count + registered_count) else 0
    red_count = grade_counts.get("Red", 0)
    red_pct = round(red_count / judged_count * 100, 1) if judged_count else 0.0
    red_completed_count = len([b for b in all_batteries if b.get("grade") == "Red" and b.get("status") == STATUS_COMPLETED])
    red_completed_pct = round(red_completed_count / red_count * 100) if red_count else 0

    # 예상 수익 (목업 — 광물시세 실시간 연동 전, 고정 단가 적용)
    # "구매 확정된 것만"이 아니라 "현재 판정 완료된 전체 배터리 기준 예상
    # 잠재가치"로 basis를 통일한다. 상단 스탯카드와 아래 정산 카드가 서로
    # 다른 값을 보여주지 않도록, 이 계산 결과를 양쪽에서 그대로 재사용한다.
    judged_batteries = [b for b in all_batteries if b.get("grade")]
    reuse_batteries = [b for b in judged_batteries if b.get("grade") in ("Green", "Yellow")]
    recycle_batteries = [b for b in judged_batteries if b.get("grade") in ("Orange", "Gray")]
    waste_count = grade_counts.get("Red", 0)

    est_price_per_kwh = 5500  # 임의 단가 (원/kWh)
    waste_cost_per_unit = 700000  # 임의 지정폐기물 처리비용 (원/건)

    reuse_kwh = sum(b.get("capacity_kwh") or 0 for b in reuse_batteries)
    recycle_kwh = sum(b.get("capacity_kwh") or 0 for b in recycle_batteries)
    reuse_revenue = int(reuse_kwh * est_price_per_kwh)
    recycle_revenue = int(recycle_kwh * est_price_per_kwh * 0.7)  # 재활용은 회수가치 비중을 낮게 반영
    waste_cost = int(waste_count * waste_cost_per_unit)
    est_revenue = reuse_revenue + recycle_revenue - waste_cost
    est_revenue_m = est_revenue / 1_000_000

    # -------------------------------------------------------------
    # 1) 상단 스탯카드 4개
    # -------------------------------------------------------------
    def _stat_card(icon, title, value_html, sub_html, icon_bg):
        return f"""
        <div style="background-color: var(--c-card); border: 1.5px solid var(--c-border); border-radius: 14px; padding: 18px; height: 118px; box-sizing: border-box;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px;">
                <span style="font-size:13px; font-weight:600; color:var(--c-muted-foreground);">{title}</span>
                <span style="background:{icon_bg}; width:30px; height:30px; border-radius:9px; display:flex; align-items:center; justify-content:center; font-size:15px;">{icon}</span>
            </div>
            <div style="font-size:26px; font-weight:800; color:var(--c-foreground); line-height:1;">{value_html}</div>
            <div style="font-size:12px; color:var(--c-muted-foreground); margin-top:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{sub_html}</div>
        </div>
        """

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(ui_common.dedent_html(_stat_card("🔋", "총 배터리", f"{total_count}<span style='font-size:14px;'> 개</span>", "누적 접수", "rgba(20,47,75,0.08)")), unsafe_allow_html=True)
    with s2:
        st.markdown(ui_common.dedent_html(_stat_card("✨", "판정 완료율", f"{judge_rate}<span style='font-size:14px;'>%</span>", f"{judged_count} / {total_count}", "rgba(0,181,181,0.12)")), unsafe_allow_html=True)
    with s3:
        st.markdown(ui_common.dedent_html(_stat_card("⚠️", "지정폐기물 (RED)", f"{red_count}<span style='font-size:14px;'> 개</span>", f"전체의 {red_pct}% · 처리완료 {red_completed_count}건({red_completed_pct}%)", "rgba(230,45,40,0.10)")), unsafe_allow_html=True)
    with s4:
        st.markdown(ui_common.dedent_html(_stat_card("💰", "예상 수익", f"{est_revenue_m:.1f}<span style='font-size:14px;'>M 원</span>", "이번 달 · 시세 반영", "rgba(46,158,91,0.10)")), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 2) 폐차장 배터리 상태 4단계 퍼널
    # -------------------------------------------------------------
    step1 = total_count
    step2 = judged_count
    step3 = status_counts.get(STATUS_LISTED, 0) + status_counts.get(STATUS_NEGOTIATING, 0)
    step4 = status_counts.get(STATUS_NEGOTIATING, 0)
    conv_rate = round(step4 / step1 * 100) if step1 else 0
    max_step = max(step1, 1)

    def _funnel_step(label_badge, badge_color, right_text, count, sub, bar_color, bar_pct):
        return f"""
        <div style="flex:1; min-width:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="background:{badge_color}; color:#fff; font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap;">{label_badge}</span>
                <span style="font-size:11px; color:var(--c-muted-foreground); white-space:nowrap;">{right_text}</span>
            </div>
            <div style="font-size:24px; font-weight:800; color:var(--c-foreground);">{count}<span style="font-size:13px; font-weight:600;"> 건</span></div>
            <div style="font-size:11px; color:var(--c-muted-foreground); margin:4px 0 10px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{sub}</div>
            <div style="background:var(--c-secondary); border-radius:999px; height:6px; overflow:hidden;">
                <div style="background:{bar_color}; width:{bar_pct}%; height:100%; border-radius:999px;"></div>
            </div>
        </div>
        """

    funnel_html = f"""
    <div style="background-color: var(--c-card); border: 1.5px solid var(--c-border); border-radius: 14px; padding: 18px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <div>
                <span style="font-size:14px; font-weight:700; color:var(--c-foreground);">폐차장 배터리 상태</span>
                <span style="font-size:12px; color:var(--c-muted-foreground); margin-left:8px;">등록 → 판정 → 매물 등록 → 협의 중 &nbsp;|&nbsp; 지정폐기물(Red)은 판정 후 폐차장이 직접 처리 완료 처리</span>
            </div>
            <span style="background:var(--c-secondary); color:var(--c-foreground); font-size:11px; font-weight:700; padding:4px 12px; border-radius:999px;">전환율 {conv_rate}%</span>
        </div>
        <div style="display:flex; gap:18px; align-items:stretch;">
            {_funnel_step("STEP 1 · 등록", "#576574", "", step1, "차량 입고 후 배터리 등록", "#142f4b", 100 * step1 / max_step)}
            <div style="display:flex; align-items:center; color:var(--c-border); font-size:18px;">&rarr;</div>
            {_funnel_step("STEP 2 · 판정", "#00838a", "", step2, "SoH · 등급 판정 진행", "#00b5b5", 100 * step2 / max_step)}
            <div style="display:flex; align-items:center; color:var(--c-border); font-size:18px;">&rarr;</div>
            {_funnel_step("STEP 3 · 매물 등록", "#f3821d", "", step3, "재사용·재활용 매물 게시", "#f3821d", 100 * step3 / max_step)}
            <div style="display:flex; align-items:center; color:var(--c-border); font-size:18px;">&rarr;</div>
            {_funnel_step("STEP 4 · 협의 중", "#2e9e5b", "", step4, "처리업체와 협의 진행", "#2e9e5b", 100 * step4 / max_step)}
        </div>
    </div>
    """
    st.markdown(ui_common.dedent_html(funnel_html), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 3) 등급 분포 도넛차트 + 범례 / 최근 10일 등록 추이 (좌우 배치)
    # -------------------------------------------------------------
    GRADE_DESC = {
        "Green": "재사용", "Yellow": "재사용·재활용 검토", "Orange": "재활용",
        "Gray": "정보누락", "Red": "지정폐기물",
    }
    st.markdown(
        """
        <style>
            div[class*="st-key-card_grade_pie"],
            div[class*="st-key-card_trend"] {
                height: 330px !important;
                min-height: 330px !important;
                max-height: 330px !important;
                box-sizing: border-box !important;
                overflow: hidden !important;
            }
            div[class*="st-key-card_settlement"],
            div[class*="st-key-card_policy_news"] {
                height: 460px !important;
                min-height: 460px !important;
                max-height: 460px !important;
                box-sizing: border-box !important;
                overflow: hidden !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    col_pie, col_trend = st.columns([4, 6])

    with col_pie:
        with st.container(border=False, key="card_grade_pie"):
            st.markdown("**등급 분포**")
            total_graded = sum(grade_counts.values())
            if total_graded == 0:
                st.info("판정된 배터리가 없습니다.")
            else:
                import matplotlib.pyplot as plt

                labels_all = ["Green", "Yellow", "Orange", "Gray", "Red"]
                colors_all = ["#2e9e5b", "#f0c419", "#e07a1f", "#576574", "#cc3333"]
                labels, colors, values = [], [], []
                for lb, cl in zip(labels_all, colors_all):
                    if grade_counts.get(lb, 0) > 0:
                        labels.append(lb)
                        colors.append(cl)
                        values.append(grade_counts[lb])

                chart_col, legend_col = st.columns([1, 1], gap="large")
                with chart_col:
                    fig, ax = plt.subplots(figsize=(2.1, 2.1))

                    def _pct_count_label(pct, all_values):
                        count = int(round(pct / 100.0 * sum(all_values)))
                        return f"{pct:.0f}%({count})" if pct > 0 else ""

                    ax.pie(
                        values, colors=colors, startangle=90,
                        autopct=lambda p: _pct_count_label(p, values),
                        pctdistance=0.78,
                        textprops={"fontsize": 8, "fontweight": "bold", "color": "#142f4b"},
                        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
                    )
                    ax.axis("equal")
                    st.pyplot(fig, use_container_width=False)
                with legend_col:
                    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                    for lb, cl in zip(labels_all, colors_all):
                        st.markdown(
                            ui_common.dedent_html(f"""
                            <div style="display:flex; align-items:center; gap:6px; padding:5px 0;">
                                <span style="width:9px; height:9px; border-radius:50%; background:{cl}; flex-shrink:0;"></span>
                                <span style="font-size:13px; font-weight:800; color:var(--c-foreground); white-space:nowrap;">{lb}</span>
                                <span style="font-size:11px; color:var(--c-muted-foreground); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{GRADE_DESC[lb]}</span>
                            </div>
                            """),
                            unsafe_allow_html=True,
                        )

    with col_trend:
        with st.container(border=False, key="card_trend"):
            st.markdown("**최근 10일 등록 추이**")
            today = datetime.now().date()
            date_range = [today - timedelta(days=i) for i in range(9, -1, -1)]
            counts_by_date = {d.isoformat(): 0 for d in date_range}
            for b in all_batteries:
                d = (b.get("created_at") or "")[:10]
                if d in counts_by_date:
                    counts_by_date[d] += 1
            trend_df = pd.DataFrame({
                "날짜": [d[5:] for d in counts_by_date.keys()],
                "등록 건수": list(counts_by_date.values()),
            }).set_index("날짜")
            # 오른쪽에 얇은 여백 컬럼을 하나 더 둬서, 맨 오른쪽(최신 날짜) 막대가
            # 카드 테두리에 바로 붙지 않게 한다. use_container_width=True라
            # 막대그래프가 자기 컨테이너 폭을 꽉 채우는데, 컨테이너 자체를
            # 카드보다 살짝 좁게 나눠서 오른쪽 여백을 만드는 방식이다.
            chart_col, _chart_spacer = st.columns([0.94, 0.06])
            with chart_col:
                st.bar_chart(trend_df, use_container_width=True, height=190, color="#142f4b")

    # 4) 처리업체 현황 (지도 + 리스트)
    with st.container(border=False, key="card_company_status"):
        st.markdown("**처리업체 현황**")
        company_csv = Path(__file__).parent / "data" / "companies_mock.csv"
        df_co = pd.read_csv(company_csv) if company_csv.exists() else pd.DataFrame()

        if df_co.empty:
            st.warning("처리업체 데이터를 불러오지 못했습니다. data/companies_mock.csv를 확인해주세요.")
        else:
            PROCESS_LABEL = {"reuse": "재사용", "recycle": "재활용", "designated_waste": "지정폐기물"}
            PROCESS_MARKER_COLOR = {"reuse": "green", "recycle": "orange", "designated_waste": "red"}

            map_col, list_col = st.columns([3, 2])
            with map_col:
                import folium
                from streamlit_folium import st_folium

                m = folium.Map(
                    location=[df_co["latitude"].mean(), df_co["longitude"].mean()],
                    zoom_start=7,
                    tiles="CartoDB positron",
                )
                for _, row in df_co.iterrows():
                    if pd.isna(row.get("latitude")) or pd.isna(row.get("longitude")):
                        continue
                    color = PROCESS_MARKER_COLOR.get(row.get("process_type"), "gray")
                    folium.CircleMarker(
                        location=[row["latitude"], row["longitude"]],
                        radius=7,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.85,
                        tooltip=row.get("company_name"),
                        popup=folium.Popup(
                            f"<b>{row.get('company_name')}</b><br>"
                            f"{PROCESS_LABEL.get(row.get('process_type'), row.get('process_type'))} · {row.get('region')}",
                            max_width=220,
                        ),
                    ).add_to(m)
                st_folium(m, width="100%", height=320, returned_objects=[])

            with list_col:
                st.dataframe(
                    df_co[["company_name", "region", "process_type", "monthly_capacity_count"]]
                    .rename(columns={
                        "company_name": "업체명", "region": "지역",
                        "process_type": "유형", "monthly_capacity_count": "월 처리량",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )

    # 5) 정산 · 예상 수익 (목업) / 6) 정책 · 뉴스 브리핑 — 좌우 배치
    col_settlement, col_news = st.columns(2)

    with col_settlement:
        with st.container(border=False, key="card_settlement"):
            st.markdown("**정산 · 예상 수익**")

            st.markdown(
                ui_common.dedent_html(f"""
                <div style="background-color: var(--c-secondary); border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                    <div style="font-size:12px; color:var(--c-muted-foreground); margin-bottom:4px;">이번 달 예상 수익</div>
                    <div style="font-size:28px; font-weight:800; color:var(--c-foreground);">{est_revenue:,} 원</div>
                </div>
                <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--c-border);">
                    <span style="font-size:13px; color:var(--c-muted-foreground);">재사용 매칭 수익</span>
                    <span style="font-size:13px; font-weight:700; color:#2e9e5b;">{reuse_revenue:,} 원</span>
                </div>
                <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid var(--c-border);">
                    <span style="font-size:13px; color:var(--c-muted-foreground);">재활용 원료 판매</span>
                    <span style="font-size:13px; font-weight:700; color:var(--c-foreground);">{recycle_revenue:,} 원</span>
                </div>
                <div style="display:flex; justify-content:space-between; padding:8px 0;">
                    <span style="font-size:13px; color:var(--c-muted-foreground);">지정폐기물 처리비</span>
                    <span style="font-size:13px; font-weight:700; color:#cc3333;">-{waste_cost:,} 원</span>
                </div>
                """),
                unsafe_allow_html=True,
            )

            st.markdown("<div style='margin-top:12px; font-size:12px; color:var(--c-muted-foreground);'>광물 시세</div>", unsafe_allow_html=True)
            mineral_mock = [
                ("리튬(Li2CO3)", "14.2", "+2.1%", "#cc3333"),
                ("니켈(Ni)", "16.8", "-0.8%", "#142f4b"),
                ("코발트(Co)", "27.5", "+1.4%", "#cc3333"),
                ("망간(Mn)", "2.1", "+0.3%", "#cc3333"),
            ]
            mc1, mc2 = st.columns(2)
            for idx, (name, price, change, color) in enumerate(mineral_mock):
                target_col = mc1 if idx % 2 == 0 else mc2
                with target_col:
                    st.markdown(
                        ui_common.dedent_html(f"""
                        <div style="background-color: var(--c-secondary); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px;">
                            <div style="font-size:11px; color:var(--c-muted-foreground);">{name}</div>
                            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                                <span style="font-size:16px; font-weight:800; color:var(--c-foreground);">{price}</span>
                                <span style="font-size:11px; font-weight:700; color:{color};">{change}</span>
                            </div>
                        </div>
                        """),
                        unsafe_allow_html=True,
                    )

    with col_news:
        with st.container(border=False, key="card_policy_news"):
            st.markdown("**정책 · 뉴스 브리핑**")
            news_items = [
                {
                    "tag": "정책",
                    "title": "「사용후 배터리 관리 및 산업육성법」 공포 (2026.5.26)",
                    "summary": "회수·유통·재활용을 규율하는 단일법 제정, 2027.5.27 시행 예정. 유통·재제조·재사용·재활용 4개 사업자 유형 구분.",
                    "url": "https://www.lawtimes.co.kr/news/articleView.html?idxno=222505",
                },
                {
                    "tag": "정책",
                    "title": "자동차관리법 개정안 국회 통과 (2026.1.29)",
                    "summary": "전기차 사용후 배터리 성능평가·재제조·안전관리·이력관리 체계 최초 법제화.",
                    "url": "https://www.energydaily.co.kr/news/articleView.html?idxno=164229",
                },
                {
                    "tag": "정책",
                    "title": "배터리 재생원료 생산 인증 시범사업 착수 (기후에너지환경부, 2026.6.25)",
                    "summary": "새빗켐·성일하이텍 등 6개사 참여, 2027년 5월 인증제도 본시행 앞둔 사전 검증.",
                    "url": "https://www.fnnews.com/news/202606251744526923",
                },
                {
                    "tag": "뉴스",
                    "title": "엘앤에프, 씨아이에스케미칼에 전략적 투자 (2026.6.30)",
                    "summary": "LFP·NCM 리사이클링 협력 MOU 후속 조치, 2027년 LFP 리사이클링 CAPA 우선 배정.",
                    "url": "https://www.mt.co.kr/industry/2026/06/30/2026063014111741478",
                },
            ]
            TAG_COLOR = {"정책": "#00838a", "뉴스": "#576574", "시세": "#f3821d"}
            for n in news_items:
                st.markdown(
                    ui_common.dedent_html(f"""
                    <div style="padding:10px 0; border-bottom:1px solid var(--c-border);">
                        <span style="background:{TAG_COLOR.get(n['tag'], '#576574')}; color:#fff; font-size:10px; font-weight:700; padding:2px 8px; border-radius:999px;">{n['tag']}</span>
                        <div style="font-size:13px; font-weight:700; color:var(--c-foreground); margin:6px 0 4px 0;">
                            <a href="{n['url']}" target="_blank" style="color:var(--c-foreground); text-decoration:none;">{n['title']}</a>
                        </div>
                        <div style="font-size:11px; color:var(--c-muted-foreground);">{n['summary']}</div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# 설정 페이지
# ---------------------------------------------------------------------------
def render_settings():
    ui_common.inject_global_css(container_max_width="1200px")
    st.markdown(
        ui_common.render_list_header(
            "설정",
            "사업자 정보 · 처리 기본값 · 알림 관리",
            DUMMY_USER["name"],
            f"{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}",
        ),
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # 1) 사업자 정보 — 폐차장 1곳 = 계정 1개를 전제로 한 실사용 정보.
    # 주소는 표시용이지만, 실제 배포 시에는 이 값을 지오코딩해서
    # battery_data.py의 CHANNEL_COORDS 하드코딩을 대체해야 매칭 거리
    # 계산이 폐차장별로 정확해진다.
    # ------------------------------------------------------------------
    st.markdown("#### 사업자 정보")
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("폐차장명", value=DUMMY_USER["channel_name"], disabled=True)
        st.text_input("사업자등록번호", value="123-45-67890", disabled=True)
        st.text_input("담당자명", value=DUMMY_USER["name"], disabled=True)
    with c2:
        st.text_input("주소", value="서울특별시 강남구 (예시)", disabled=True)
        st.text_input("대표 연락처", value="02-0000-0000", disabled=True)
        st.text_input("담당자 직통번호", value="010-0000-0000", disabled=True)

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 배터리 처리 기본값")
    st.toggle(
        "판정 완료 시 자동으로 매물 등록",
        value=False,
        key="settings_auto_listing",
        help="켜두면 Green/Yellow/Orange 등급 판정 완료 건을 배터리 관리에서 수동 등록하지 않아도 매물 등록 상태로 전환합니다. (Red는 항상 제외)",
    )

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 알림 설정")
    st.toggle("새 판정 완료 알림", value=True, key="settings_notify_triage")
    st.toggle("처리업체 협의 요청 알림", value=True, key="settings_notify_negotiate")

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    with st.expander("🛠 시연/관리자 도구"):
        st.caption("아래 작업은 로컬 공유 파일(.battery_status_overrides.json 등)만 대상으로 하며, 되돌릴 수 없습니다.")
        if st.button("⚠ 로컬 상태 초기화 (시연 데이터 리셋)", key="settings_reset_local_state"):
            reset_local_state()
            st.success("로컬 상태를 초기화했습니다. (매물 등록/매입 확정/처리 완료 표시, 엑셀 대량 등록 대기열, 발생 폐차장 배정이 모두 초기화됨)")
            st.rerun()


