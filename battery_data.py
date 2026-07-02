"""
배터리 관리 페이지 — 데이터 접근 레이어 (실제 API 연동 버전)

백엔드 엔드포인트:
  GET  /history                  -> 판정 이력 목록 (vin, matched_company_name 포함 예정)
  GET  /history/{id}             -> 판정 1건 상세 (matched_companies 포함)
  POST /history/{id}/approve     -> 처리 요청 수락 처리(내부적으로 approved_by 기록)

주의: 백엔드 DB(HistoryItem)에는 channel_name(발생채널), 운영 status(판정/
처리 요청/처리 수락/수거 예정/수거 완료/지정폐기물) 개념이 없다. 백엔드가
구분 가능한 건 approved_by 유무("처리 미수락 / 수락됨")뿐이고, 그 이상의
세부 단계(판정/처리 요청/수거 예정/수거 완료)는 Streamlit session_state에서
화면상으로만 관리한다(새로고침하면 초기화됨).
"""

import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# 백엔드 API 주소
# ---------------------------------------------------------------------------
API_BASE_URL = os.environ.get("API_BASE_URL", "https://battery-triage-map-api.onrender.com")

# ---------------------------------------------------------------------------
# 상태 정의: 판정 → 처리 요청 → 처리 수락 → 수거 예정 → 수거 완료
# 백엔드가 실제로 구분 가능한 건 "판정됨 / 승인(approved_by)됨" 뿐이고,
# 나머지 세부 단계는 프론트(session_state)에서만 관리하는 시연용 상태값이다.
# ---------------------------------------------------------------------------
STATUS_TRIAGED = "판정"
STATUS_REQUESTED = "처리 요청"
STATUS_ACCEPTED = "처리 수락"
STATUS_PICKUP_SCHEDULED = "수거 예정"
STATUS_COMPLETED = "수거 완료"
STATUS_DESIGNATED_WASTE = "지정폐기물"  # Red 등급 판정 시 내부 처리용 (목록엔 등급으로 표시)

ALL_STATUSES = [
    "전체",
    STATUS_TRIAGED,
    STATUS_REQUESTED,
    STATUS_ACCEPTED,
    STATUS_PICKUP_SCHEDULED,
    STATUS_COMPLETED,
]

STATUS_COLOR = {
    STATUS_TRIAGED: "#9aa5b1",
    STATUS_REQUESTED: "#f3821d",
    STATUS_ACCEPTED: "#00b5b5",
    STATUS_PICKUP_SCHEDULED: "#142f4b",
    STATUS_COMPLETED: "#2e9e5b",
    STATUS_DESIGNATED_WASTE: "#7a1f1f",
}

GRADE_EMOJI = {"Green": "✅", "Yellow": "⚠️", "Orange": "⚡", "Gray": "❌", None: "—"}

GRADE_COLOR = {
    "Green": "#2e9e5b",
    "Yellow": "#f3821d",
    "Orange": "#e07a1f",
    "Gray": "#576574",
    None: "#9aa5b1",
}

DUMMY_USER = {
    "name": "홍길동",
    "channel_name": "강남폐차센터",
    "channel_type": "폐차장",
}


def _status_overrides():
    if "battery_status_overrides" not in st.session_state:
        st.session_state.battery_status_overrides = {}
    return st.session_state.battery_status_overrides


def _derive_status(item: dict) -> str:
    overrides = _status_overrides()
    if item["id"] in overrides:
        return overrides[item["id"]]
    return STATUS_TRIAGED


def _normalize_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "vin": item.get("vin") or f"TRIAGE-{item['id']}",
        "model_name": item.get("model_name"),
        "battery_manufacturer": item.get("manufacturer"),
        "capacity_kwh": item.get("capacity_kwh"),
        "chemistry": item.get("chemistry"),
        "vehicle_year": item.get("vehicle_year"),
        "mileage_km": item.get("mileage_km"),
        "grade": item.get("grade"),
        "soh_proxy_score": item.get("soh_proxy_score"),
        "reuse_score": item.get("reuse_score"),
        "recycle_score": item.get("recycle_score"),
        "recommended_path": item.get("recommended_path"),
        "data_confidence": item.get("data_confidence"),
        "status": _derive_status(item),
        "channel_name": DUMMY_USER["channel_name"],
        "matched_company": item.get("matched_company_name"),
        "created_at": item.get("created_at") or "",
        "approved_by": item.get("approved_by"),
    }


def fetch_batteries(channel_name=None, status=None):
    try:
        res = requests.get(f"{API_BASE_URL}/history", params={"limit": 200}, timeout=10)
        res.raise_for_status()
        items = [_normalize_item(i) for i in res.json()]
    except requests.RequestException as e:
        st.error(f"배터리 목록을 불러오지 못했습니다: {e}")
        return []

    if status and status != "전체":
        items = [b for b in items if b["status"] == status]

    return sorted(items, key=lambda b: b["created_at"], reverse=True)


def fetch_battery_detail(battery_id):
    try:
        res = requests.get(f"{API_BASE_URL}/history/{battery_id}", timeout=10)
        if res.status_code == 404:
            return None
        res.raise_for_status()
        raw = res.json()
        item = _normalize_item(raw)
        item["matched_companies"] = raw.get("matched_companies", [])
        return item
    except requests.RequestException as e:
        st.error(f"배터리 상세 정보를 불러오지 못했습니다: {e}")
        return None


def update_battery_status(battery_id, new_status, note=""):
    if new_status == STATUS_ACCEPTED:
        try:
            res = requests.post(
                f"{API_BASE_URL}/history/{battery_id}/approve",
                json={"approved_by": DUMMY_USER["name"]},
                timeout=10,
            )
            res.raise_for_status()
        except requests.RequestException as e:
            st.error(f"승인 처리에 실패했습니다: {e}")
            return False

    overrides = _status_overrides()
    overrides[battery_id] = new_status
    return True


def request_processing(battery_id):
    """배터리 관리 페이지에서 '처리 요청' 버튼 클릭 시 호출.

    실제 처리업체 수락/거절 흐름은 아직 미구현이라, 요청과 동시에
    '처리 수락' 상태로 즉시 전이시키는 시연용 로직이다.
    """
    return update_battery_status(battery_id, STATUS_ACCEPTED)


def delete_battery(battery_id):
    """배터리 판정 이력 1건 삭제. 성공하면 True."""
    try:
        res = requests.delete(f"{API_BASE_URL}/history/{battery_id}", timeout=10)
        res.raise_for_status()
        return True
    except requests.RequestException as e:
        st.error(f"삭제에 실패했습니다: {e}")
        return False


def delete_batteries_bulk(battery_ids):
    """배터리 판정 이력 여러 건 일괄 삭제. 실제로 삭제된 id 리스트를 반환."""
    try:
        res = requests.post(
            f"{API_BASE_URL}/history/delete",
            json={"triage_ids": list(battery_ids)},
            timeout=15,
        )
        res.raise_for_status()
        return res.json().get("deleted_ids", [])
    except requests.RequestException as e:
        st.error(f"일괄 삭제에 실패했습니다: {e}")
        return []


def get_channel_list():
    return ["전체", DUMMY_USER["channel_name"]]


def get_status_counts(channel_name=None):
    items = fetch_batteries(channel_name=channel_name)
    counts = {}
    for b in items:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    return counts


def batteries_to_table_rows(batteries):
    rows = []
    for b in batteries:
        rows.append({
            "VIN": b["vin"] or "—",
            "모델명": b["model_name"] or "—",
            "제조사": b["battery_manufacturer"] or "—",
            "용량(kWh)": b["capacity_kwh"] if b["capacity_kwh"] is not None else "—",
            "등급": b["grade"] or "미판정",
            "상태": b["status"],
            "추천업체": b["matched_company"] or "—",
            "입고일": (b["created_at"] or "")[:10] or "—",  # 판정(Triage)이 완료된 날짜 = 배터리 입고일
            "발생채널": b["channel_name"] or "—",
            "_id": b["id"],
        })
    return rows


def style_battery_table(df):
    def _grade_style(val):
        color = GRADE_COLOR.get(val if val != "미판정" else None, "#9aa5b1")
        return f"background-color: {color}; color: white; font-weight: 700; text-align: center; border-radius: 6px;"

    def _status_style(val):
        color = STATUS_COLOR.get(val, "#9aa5b1")
        return f"background-color: {color}; color: white; font-weight: 700; text-align: center; border-radius: 6px;"

    styler = df.style
    apply_fn = styler.map if hasattr(styler, "map") else styler.applymap

    styler = apply_fn(_grade_style, subset=["등급"])
    styler = apply_fn(_status_style, subset=["상태"])
    return styler
