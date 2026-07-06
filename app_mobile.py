"""
app_mobile.py — 앱(모바일): 배터리 등록 + 판정 결과

BATLINK 앱/웹 3분리 중 "앱" 파트. 현장(폐차장)에서 VIN 스캔 후
배터리 정보를 입력하고 판정하는 화면만 담당한다. 판정 결과를 저장하면
실제 백엔드 DB(triage_history)에 저장되어, 웹(폐차장)의 "배터리 관리"
페이지에 "판정" 상태로 즉시 조회된다 (battery_data.py를 통해 동일 DB 공유).

이 파일은 처리업체 매칭/구매/대시보드 등을 다루지 않는다 — 그건 웹(폐차장)과
웹(처리업체) 쪽 담당이다.
"""

import cv2
import numpy as np
import requests
import streamlit as st

import ui_common
from battery_data import API_BASE_URL, DUMMY_USER, CHANNEL_COORDS

# ---------------------------------------------------------------------------
# 페이지 설정 + 전역 CSS (앱이라 좁은 폭으로 고정)
# ---------------------------------------------------------------------------

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


def render_register():
    ui_common.inject_global_css(container_max_width="480px")

    # ---------------------------------------------------------------------------
    # 세션 상태 초기화
    # ---------------------------------------------------------------------------
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

    # ---------------------------------------------------------------------------
    # 참고: 예전에는 여기서 st.sidebar에 "새 배터리 등록" 버튼을 따로 넣었으나,
    # app.py로 통합 네비게이션이 되면서 이 페이지에서만 사이드바가 달라 보이는
    # 문제가 생겨 제거했다. 초기화는 아래 "input" 스텝이 이미 기본값이고,
    # approval 스텝의 "저장" 버튼이 동일한 초기화를 수행한다.
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # 배터리 등록 → 판정 결과 (2단계 플로우)
    # ---------------------------------------------------------------------------
    if st.session_state.step == "input":
        st.markdown(
            f"""
            <div class="list-header">
                <div class="list-header-left">
                    <p class="list-header-title">배터리 등록</p>
                    <p class="list-header-sub">사용후 배터리 접수 및 자동 판정</p>
                </div>
                <div class="list-header-user">
                    <span class="list-header-user-name">{DUMMY_USER['name']} 님</span>
                    <span class="list-header-user-channel">{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 01. 식별 정보
        card01 = st.container(border=False, key="card_id")
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
                <b>QR코드 스캔</b> (또는 수동 입력)<br/>
                VIN이 담긴 QR코드를 촬영하면 자동으로 입력됩니다.
                </div>
                """,
                unsafe_allow_html=True,
            )

            input_method = st.radio(
                "입력 방식 선택",
                ["카메라로 스캔", "수동 입력"],
                horizontal=True,
                label_visibility="collapsed",
            )

            if input_method == "카메라로 스캔":
                st.info("VIN QR코드를 카메라에 비춰주세요. (약 3초 소요)")

                camera_image = st.camera_input("카메라에서 촬영 (VIN QR코드)")

                if camera_image is not None:
                    st.markdown("**촬영된 이미지:**")
                    st.image(camera_image, use_column_width=True)

                    decoded = decode_barcode(camera_image)

                    if decoded:
                        st.success("QR코드 인식 성공!")

                        vin_from_scan = decoded[0]["data"]
                        st.markdown(f"**인식된 데이터 ({decoded[0]['type']}):**")
                        st.code(vin_from_scan)

                        st.session_state.scanned_vin = vin_from_scan
                        vin = vin_from_scan
                    else:
                        st.warning("QR코드를 인식하지 못했습니다. 더 명확한 이미지를 다시 촬영해주세요.")
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
                        ">리콜 이력 조회 (국가기술표준원) →</a>
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
        card02 = st.container(border=False, key="card_vehicle")
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
                st.markdown('<p class="field-label">연식 <span class="req-star">*</span></p>', unsafe_allow_html=True)
                model_year = st.selectbox(
                    "연식", year_options, label_visibility="collapsed", key="year"
                )
            with col6:
                st.markdown(
                    '<p class="field-label">주행거리 <span class="req-star">*</span><span class="field-hint">km</span></p>',
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
                    '<p class="field-label">수량 <span class="req-star">*</span><span class="field-hint">개</span></p>',
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
                    '<p class="field-label">화학계 <span class="req-star">*</span></p>',
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

        card03 = st.container(border=False, key="card_condition")
        with card03:
            placeholder_header = st.empty()

            selected_conditions = st.pills(
                "외관 상태",
                options=condition_options,
                format_func=lambda x: x,
                selection_mode="multi",
                label_visibility="collapsed",
                key="hazard_pills",
            )

            hazard_count = len(selected_conditions)
            is_alert = hazard_count > 0

            num_class = "section-num-alert" if is_alert else ""
            badge_class = "status-badge-alert" if is_alert else "status-badge-ok"
            badge_text = f"위험요소 {hazard_count}" if is_alert else "이상 없음"

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
                div[class*="st-key-card_condition"] {{
                    {border_css}
                }}
            </style>
            """,
            unsafe_allow_html=True,
        )

        # ------------------------------------------------------------------
        # 배터리 판정 버튼 (등록 버튼은 제거 — 판정 버튼 하나로 등록+판정+매칭 수행)
        # ------------------------------------------------------------------
        if st.button("배터리 판정", use_container_width=True, type="primary", key="judge_battery_btn"):
            errors = []
            if not vin:
                errors.append("차대번호(VIN)는 필수 입력 항목입니다.")
            if capacity_kwh <= 0:
                errors.append("배터리 용량은 0보다 큰 값을 입력해야 합니다.")
            if model_year == "선택":
                errors.append("연식을 선택해주세요.")
            if mileage_km is None or mileage_km < 0:
                errors.append("주행거리를 입력해주세요.")
            if not quantity or quantity < 1:
                errors.append("수량을 입력해주세요.")
            if chemistry == "선택":
                errors.append("화학계를 선택해주세요. (모르는 경우 '모름' 선택 가능)")

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

                # 발생채널별 좌표는 battery_data.py의 공용 CHANNEL_COORDS를 그대로 쓴다
                # (예전엔 여기 로컬로 중복 정의돼 있었음).
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
                    st.warning("지정폐기물 판정 - 특별 처리 업체로 매칭합니다.")

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
            <div class="list-header">
                <div class="list-header-left">
                    <p class="list-header-title">판정 결과</p>
                    <p class="list-header-sub">배터리 판정 결과 및 처리업체 매칭 확인</p>
                </div>
                <div style="display:flex; align-items:center; gap:10px;">
                    <div class="list-header-user">
                        <span class="list-header-user-name">{DUMMY_USER['name']} 님</span>
                        <span class="list-header-user-channel">{DUMMY_USER['channel_name']} · {DUMMY_USER['channel_type']}</span>
                    </div>
                    <div class="triage-channel-badge">최종 확인 단계</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        intake_record = st.session_state.intake_record
        triage_result = st.session_state.triage_result
        matching_result = st.session_state.matching_result

        # 예전엔 "배터리 정보"/"Triage 판정" 카드를 st.columns(2)로 나란히
        # 배치했는데, 한 행에 한 카드씩 세로로 쌓아달라는 요청에 따라 컬럼
        # 분할 없이 순서대로(01 → 02 → 03) 렌더링하도록 변경했다.
        card_info = st.container(border=False, key="card_approval_info")
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

        card_triage = st.container(border=False, key="card_approval_triage")
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

            grade_emoji = {"Green": "", "Yellow": "", "Orange": "", "Gray": "", "Red": ""}
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

        card_matching = st.container(border=False, key="card_approval_matching")
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

            # 처리유형 코드값을 한글 라벨로 변환 (긴 영문 문자열이 좁은 박스에서
            # 줄바꿈되며 다른 카드를 침범하는 문제 방지 목적도 겸함)
            _PROCESS_LABEL = {"reuse": "재사용", "recycle": "재활용", "designated_waste": "지정폐기물 처리"}

            # 좌우로 카드를 나열하던 st.columns() 그리드는 업체 수가 늘거나
            # process_type처럼 긴 문자열(예: designated_waste)이 들어오면 좁은
            # 칸 안에서 줄바꿈되며 옆 카드를 침범하는 문제가 있었다. 이를
            # 세로로 한 줄씩 쌓는 리스트 형태로 바꿔 폭에 상관없이 안전하게
            # 표시되도록 한다.
            for company in matched_companies:
                process_label = _PROCESS_LABEL.get(company['process_type'], company['process_type'])
                st.markdown(
                    f"""
                    <div style="background-color: var(--c-card); border: 1.5px solid var(--c-border); border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px;">
                            <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
                                <span style="flex-shrink: 0; font-size: 12px; font-weight: 700; color: var(--c-primary-foreground); background-color: var(--c-primary); border-radius: 999px; padding: 2px 9px;">{company['rank']}위</span>
                                <span style="font-size: 14px; font-weight: 700; color: var(--c-foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{company['company_name']}</span>
                            </div>
                            <div style="flex-shrink: 0; font-size: 12px; color: var(--c-muted-foreground); text-align: right;">
                                {company['distance_km']}km · <b style="color: var(--c-foreground);">{company['total_score']:.1f}점</b>
                            </div>
                        </div>
                        <div style="margin-top: 6px; font-size: 11px; color: var(--c-muted-foreground);">
                            지역: {company['region']} &nbsp;|&nbsp; 진단역량: {company['diagnostic_capability'].upper()} &nbsp;|&nbsp; 처리유형: {process_label} &nbsp;|&nbsp; 상태: 운영중
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
                origin_lat, origin_lon = CHANNEL_COORDS.get(channel_name, (37.5665, 126.9780))

                all_lats = [origin_lat] + [c['latitude'] for c in matched_companies if c.get('latitude')]
                all_lons = [origin_lon] + [c['longitude'] for c in matched_companies if c.get('longitude')]
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)

                m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="CartoDB positron")

                # 발생 위치 마커 (파란색)
                folium.Marker(
                    location=[origin_lat, origin_lon],
                    popup=folium.Popup(f"<b> 발생위치</b><br>{channel_name}", max_width=200),
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

                st.markdown("**처리업체 위치 지도**")
                st_folium(m, width="100%", height=340, returned_objects=[])

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 1], gap="small")

        with col1:
            if st.button("← 이전", use_container_width=True):
                st.session_state.step = "input"
                st.rerun()

        with col2:
            if st.button("저장", use_container_width=True, type="primary"):
                # 판정 시점에 이미 DB에 저장돼 배터리 관리 페이지에 등록된 상태이므로,
                # 여기서는 입력 화면으로 복귀하며 현재 접수 건 세션만 정리한다.
                st.session_state.step = "input"
                st.session_state.intake_record = None
                st.session_state.triage_result = None
                st.session_state.matching_result = None
                st.rerun()
