"""
배터리 관리 페이지 — 데이터 접근 레이어 (실제 API 연동 버전)

백엔드 엔드포인트:
  GET  /history                  -> 판정 이력 목록 (vin, matched_company_name 포함 예정)
  GET  /history/{id}             -> 판정 1건 상세 (matched_companies 포함)
  POST /history/{id}/approve     -> 승인 처리

주의: 백엔드 DB(HistoryItem)에는 channel_name(발생채널), 운영 status(요청/
수거신청/완료/반려/지정폐기물) 개념이 없다. status는 approved_by 유무로
"승인 전 / 승인됨"만 구분 가능하고, 그 이상의 세부 단계는 Streamlit
session_state에서 화면상으로만 관리한다(새로고침하면 초기화됨).
"""

import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# 백엔드 API 주소
# ---------------------------------------------------------------------------
API_BASE_URL = os.environ.get("API_BASE_URL", "https://battery-triage-map-api.onrender.com")

# ---------------------------------------------------------------------------
# 상태 정의 (백엔드AI 요청 메시지와 동일한 5단계 + 예외 2개)
# 실제로 백엔드가 구분 가능한 건 "승인 전 / 승인됨" 뿐이고, 나머지는
# 프론트(session_state)에서만 관리하는 시연용 상태값이다.
# ---------------------------------------------------------------------------
STATUS_PENDING_TRIAGE = "판정 전"
STATUS_PENDING_APPROVAL = "승인 전"
STATUS_REQUESTED = "요청"
STATUS_PICKUP_SCHEDULED = "수거 신청"
STATUS_COMPLETED = "완료"
STATUS_REJECTED = "반려"
STATUS_DESIGNATED_WASTE = "지정폐기물"

ALL_STATUSES = [
    "전체",
    STATUS_PENDING_TRIAGE,
    STATUS_PENDING_APPROVAL,
    STATUS_REQUESTED,
    STATUS_PICKUP_SCHEDULED,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    STATUS_DESIGNATED_WASTE,
]

STATUS_COLOR = {
    STATUS_PENDING_TRIAGE: "#9aa5b1",
    STATUS_PENDING_APPROVAL: "#f3821d",
    STATUS_REQUESTED: "#00b5b5",
    STATUS_PICKUP_SCHEDULED: "#142f4b",
    STATUS_COMPLETED: "#2e9e5b",
    STATUS_REJECTED: "#e62d28",
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
    if not item.get("grade"):
        return STATUS_PENDING_TRIAGE
    if not item.get("approved_by"):
        return STATUS_PENDING_APPROVAL
    return STATUS_REQUESTED


def _normalize_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "vin": item.get("vin") or f"TRIAGE-{item['id']}",
        "model_name": item.get("model_name"),
        "battery_manufacturer": item.get("manufacturer"),
        "capacity_kwh": item.get("capacity_kwh"),
        "chemistry": item.get("chemistry"),
        "grade": item.get("grade"),
        "soh_proxy_score": item.get("soh_proxy_score"),
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
    if new_status == STATUS_REQUESTED:
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
            "VIN": b["vin"],
            "모델명": b["model_name"],
            "제조사": b["battery_manufacturer"],
            "용량(kWh)": b["capacity_kwh"],
            "등급": b["grade"] or "미판정",
            "상태": b["status"],
            "추천업체": b["matched_company"] or "—",
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