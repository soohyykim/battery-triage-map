"""
battery_data.py — 3개 앱(app_mobile / app_junkyard / app_company) 공용 데이터 레이어.

백엔드 엔드포인트:
  POST /triage                   -> 배터리 예비 판정 (+ /match 로 처리업체 매칭)
  POST /match                    -> 처리기업 매칭
  GET  /history                  -> 판정 이력 목록 (vin, matched_company_name 포함)
  GET  /history/{id}             -> 판정 1건 상세 (matched_companies 포함)
  POST /history/{id}/approve     -> 매입 확정 처리(내부적으로 approved_by 기록)
  DELETE /history/{id}, POST /history/delete -> 삭제(단건/일괄)

상태 모델 (5단계):
  등록 → 판정 → 매물 등록 → 매입 확정 → 처리 완료
  - "등록"은 백엔드에 대응 개념이 없다. 엑셀 대량 업로드처럼 아직 판정을
    돌리지 않은 배터리를, 로컬 공유 JSON 파일(.battery_pending_registrations.json)에
    임시로 들고 있는 목업 계층(pending registrations)이다.
  - "판정"부터는 실제 DB(triage_history)에 저장된 레코드다.
  - "매물 등록"/"매입 확정"/"처리 완료"는 백엔드가 구분하지 못해(approved_by
    유무만 구분 가능) 로컬 공유 JSON 파일(.battery_status_overrides.json)
    오버라이드로 화면에서만 관리한다. 세션이 아니라 파일이라서, 같은
    컴퓨터에서 실행 중인 app_mobile / app_junkyard / app_company 3개 앱이
    전부 같은 상태를 즉시 공유해서 볼 수 있다 (로컬 데모 전용 — Streamlit
    Cloud에 3개 앱을 별도 배포하면 파일이 공유되지 않으니 그때는 백엔드
    DB 컬럼으로 옮겨야 한다).
  - "처리 완료"는 Red(지정폐기물) 등급 배터리의 최종 처리 완료 표시 전용이며,
    Green~Gray(재사용/재활용) 배터리는 "매입 확정" 이후 실물 흐름을 이
    시스템이 추적하지 않는다(요구사항에 따른 의도된 설계).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# 백엔드 API 주소
# ---------------------------------------------------------------------------
API_BASE_URL = os.environ.get("API_BASE_URL", "https://battery-triage-map-api.onrender.com")

# ---------------------------------------------------------------------------
# 상태 오버라이드 공유 저장소 (로컬 데모 전용)
# ---------------------------------------------------------------------------
# 매물 등록/매입 확정/처리 완료는 백엔드 DB 컬럼이 없어 프론트에서만
# 관리하는데, st.session_state는 브라우저 세션(탭)별로 분리돼 있어서
# 앱(app_mobile)/웹(app_junkyard)/웹(app_company)이 서로 다른 프로세스로
# 뜨면 상태를 공유하지 못한다. 로컬 시연에서는 3개 앱이 같은 컴퓨터의
# 같은 저장소 폴더를 쓰므로, 세션 대신 로컬 JSON 파일을 "간이 공유 DB"로
# 사용해 3개 앱이 즉시 서로의 상태 변경을 볼 수 있게 한다.
#
# ⚠ 이 방식은 로컬 데모 전용이다. Streamlit Cloud에 3개 앱을 각각 별도
# 배포하면 컨테이너가 분리돼 파일도 공유되지 않는다 — 그 단계에서는
# 백엔드 DB에 실제 컬럼(listing_status 등)을 추가해야 한다.
# ---------------------------------------------------------------------------
_OVERRIDES_FILE = Path(__file__).resolve().parent / ".battery_status_overrides.json"
_PENDING_FILE = Path(__file__).resolve().parent / ".battery_pending_registrations.json"


def _read_json_file(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_file(path, data):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        st.error(f"공유 상태 파일 저장에 실패했습니다: {e}")

# ---------------------------------------------------------------------------
# 상태 정의: 등록 → 판정 → 매물 등록 → 협의 중
#                          └(Red만) 처리 완료 — 처리업체 개입 없이 폐차장이 직접 종결
#
# 지난 버전엔 Red(지정폐기물)를 처리업체가 '수락'하는 처리 의뢰 단계가
# 있었으나, 지정폐기물 처리를 플랫폼이 중개하는 모양새가 법적으로
# 애매하다는 지적(폐기물 처리 중개업으로 비칠 소지)에 따라 제거했다.
# 이제 Red는 순수하게 폐차장 내부 기록용으로만 '처리 완료' 처리한다.
# ---------------------------------------------------------------------------
STATUS_REGISTERED = "등록"          # 판정 전 (엑셀 업로드 등, 세션에만 존재)
STATUS_TRIAGED = "판정"             # /triage 완료, DB에 실존
STATUS_LISTED = "매물 등록"          # 처리업체에 노출 시작 (Red 등급 불가)
STATUS_NEGOTIATING = "협의 중"       # 처리업체가 '협의 요청' 클릭 (approve 호출) — 확정 계약 아님
STATUS_COMPLETED = "처리 완료"       # Red(지정폐기물) 전용, 폐차장이 직접 종결(플랫폼 밖에서 처리)

ALL_STATUSES = [
    "전체",
    STATUS_REGISTERED,
    STATUS_TRIAGED,
    STATUS_LISTED,
    STATUS_NEGOTIATING,
    STATUS_COMPLETED,
]

STATUS_COLOR = {
    STATUS_REGISTERED: "#9aa5b1",
    STATUS_TRIAGED: "#576574",
    STATUS_LISTED: "#f3821d",
    STATUS_NEGOTIATING: "#00b5b5",
    STATUS_COMPLETED: "#2e9e5b",
}

GRADE_EMOJI = {"Green": "✅", "Yellow": "⚠️", "Orange": "⚡", "Gray": "❌", "Red": "⛔", None: "—"}

GRADE_COLOR = {
    "Green": "#2e9e5b",
    "Yellow": "#f0c419",
    "Orange": "#e07a1f",
    "Gray": "#576574",
    "Red": "#cc3333",
    None: "#9aa5b1",
}

DUMMY_USER = {
    "name": "홍길동",
    "channel_name": "강남폐차센터",
    "channel_type": "폐차장",
}

# 발생채널(폐차장) 좌표. 백엔드 DB에는 폐차장 구분 컬럼이 없어서, 어떤
# 배터리가 어느 폐차장에서 왔는지는 로컬 공유 파일(채널 배정)로 관리한다.
CHANNEL_COORDS = {
    "강남폐차센터": (37.4979, 127.0276),
    "수원폐차센터": (37.2636, 127.0286),
    "인천폐차센터": (37.4563, 126.7052),
}
CHANNEL_NAMES = list(CHANNEL_COORDS.keys())
_CHANNEL_FILE = Path(__file__).resolve().parent / ".battery_channel_assignments.json"


# =============================================================================
# 발생채널(폐차장) 배정 — 로컬 공유 파일
# =============================================================================
def _channel_assignments():
    return _read_json_file(_CHANNEL_FILE)


def set_battery_channel(battery_id, channel_name):
    data = _channel_assignments()
    data[str(battery_id)] = channel_name
    _write_json_file(_CHANNEL_FILE, data)


def get_battery_channel(battery_id, default=None):
    data = _channel_assignments()
    return data.get(str(battery_id), default or DUMMY_USER["channel_name"])


# =============================================================================
# 상태 오버라이드 (매물 등록 / 매입 확정 / 처리 의뢰 / 처리 완료 — 로컬 공유 파일)
# =============================================================================
def _status_overrides():
    return _read_json_file(_OVERRIDES_FILE)


def _set_status_override(battery_id, status):
    data = _status_overrides()
    data[str(battery_id)] = status
    _write_json_file(_OVERRIDES_FILE, data)


def _derive_status(item: dict) -> str:
    overrides = _status_overrides()
    key = str(item["id"])
    if key in overrides:
        return overrides[key]
    return STATUS_TRIAGED  # 백엔드(/history)에서 온 건 이미 판정이 끝난 상태


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
        "channel_name": get_battery_channel(item["id"]),
        "matched_company": item.get("matched_company_name"),
        "created_at": item.get("created_at") or "",
        "approved_by": item.get("approved_by"),
        "origin_latitude": item.get("origin_latitude"),
        "origin_longitude": item.get("origin_longitude"),
        "is_pending": False,
    }


# =============================================================================
# 판정 완료 배터리 조회 (백엔드 /history)
# =============================================================================
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


# =============================================================================
# [목업] "등록" 상태 — 엑셀 대량 업로드 등, 판정 전 배터리를 세션에만 보관.
# 실제 백엔드에는 "판정 없이 배터리만 저장"하는 엔드포인트가 없어서, 판정
# 전 단계는 세션 상태로만 구현하고, '판정' 버튼을 눌러야 비로소 실제
# POST /triage(+/match)를 호출해 DB에 반영한다.
# =============================================================================
def _pending_store():
    return _read_json_file(_PENDING_FILE)


def _save_pending_store(data):
    _write_json_file(_PENDING_FILE, data)


def add_pending_registrations(records, channel_name=None):
    """엑셀 업로드 등으로 얻은 배터리 원본 정보를 '등록' 상태로 공유 파일에 추가.

    records: [{vin, manufacturer, model_name, vehicle_year, mileage_km,
               capacity_kwh, chemistry}, ...]
    channel_name: 이 배터리들이 발생한 폐차장 이름 (미지정 시 기본 채널)
    반환값: 새로 추가된 local_id 리스트
    """
    channel_name = channel_name or DUMMY_USER["channel_name"]
    store = _pending_store()
    added_ids = []
    now = datetime.now(timezone.utc).isoformat()
    for rec in records:
        local_id = f"local-{uuid.uuid4().hex[:8]}"
        store[local_id] = {
            "id": local_id,
            "vin": (rec.get("vin") or local_id),
            "model_name": rec.get("model_name"),
            "battery_manufacturer": rec.get("manufacturer"),
            "capacity_kwh": rec.get("capacity_kwh"),
            "chemistry": rec.get("chemistry") or "UNKNOWN",
            "vehicle_year": rec.get("vehicle_year"),
            "mileage_km": rec.get("mileage_km"),
            "grade": None,
            "soh_proxy_score": None,
            "reuse_score": None,
            "recycle_score": None,
            "recommended_path": None,
            "data_confidence": None,
            "status": STATUS_REGISTERED,
            "channel_name": channel_name,
            "matched_company": None,
            "created_at": now,
            "approved_by": None,
            "is_pending": True,
        }
        set_battery_channel(local_id, channel_name)
        added_ids.append(local_id)
    _save_pending_store(store)
    return added_ids


def get_pending_registrations():
    return list(_pending_store().values())


def remove_pending_registration(local_id):
    store = _pending_store()
    if store.pop(local_id, None) is not None:
        _save_pending_store(store)


def list_all_batteries():
    """'등록'(로컬) + '판정 이상'(백엔드) 배터리를 합쳐 최신순으로 반환.
    배터리 관리 페이지의 메인 목록은 항상 이 함수를 쓴다.
    """
    pending = get_pending_registrations()
    triaged = fetch_batteries()
    return sorted(pending + triaged, key=lambda b: b["created_at"], reverse=True)


def triage_pending_registration(local_id):
    """'등록' 상태 배터리를 실제 POST /triage(+/match)로 넘겨 판정 확정.

    성공하면 로컬 등록 목록에서 제거하고 실제 triage_id를 반환한다.
    실패하면 None을 반환하고(에러는 st.error로 표시) 로컬 레코드는 유지한다.
    """
    store = _pending_store()
    rec = store.get(local_id)
    if not rec:
        return None

    payload = {
        "vin": rec["vin"],
        "vehicle_year": rec.get("vehicle_year"),
        "mileage_km": rec.get("mileage_km"),
        "capacity_kwh": rec.get("capacity_kwh"),
        "chemistry": rec.get("chemistry") or "UNKNOWN",
        "manufacturer": rec.get("battery_manufacturer"),
        "model_name": rec.get("model_name"),
        "battery_count": 1,
        "condition_flags": {
            "flooded": False, "leakage": False, "overheated": False,
            "swollen": False, "impact": False,
        },
    }

    try:
        tr = requests.post(f"{API_BASE_URL}/triage", json=payload, timeout=30)
        tr.raise_for_status()
        result = tr.json()
        triage_id = result.get("triage_id")
    except requests.RequestException as e:
        st.error(f"판정 처리에 실패했습니다: {e}")
        return None

    # 매칭까지 시도(실패해도 판정 자체는 이미 성공했으므로 무시하고 진행)
    channel_name = get_battery_channel(local_id)
    try:
        lat, lon = CHANNEL_COORDS.get(channel_name, CHANNEL_COORDS[DUMMY_USER["channel_name"]])
        requests.post(
            f"{API_BASE_URL}/match",
            json={
                "triage_result": result,
                "origin_latitude": lat,
                "origin_longitude": lon,
                "max_results": 3,
                "triage_id": triage_id,
            },
            timeout=30,
        )
    except requests.RequestException:
        pass

    if triage_id is not None:
        set_battery_channel(triage_id, channel_name)
    remove_pending_registration(local_id)
    return triage_id


def triage_pending_registrations_bulk(local_ids):
    """여러 건을 순차적으로 판정 확정. (성공, 실패) local_id 리스트를 반환."""
    succeeded, failed = [], []
    for local_id in local_ids:
        triage_id = triage_pending_registration(local_id)
        if triage_id is not None:
            succeeded.append(local_id)
        else:
            failed.append(local_id)
    return succeeded, failed


# =============================================================================
# 매물 등록 / 매입 확정 / 처리 완료 (상태 전이)
# =============================================================================
def mark_listed(battery_ids):
    """선택한 배터리들을 '매물 등록' 상태로 전환.

    Red(지정폐기물) 등급은 매물 등록 대상에서 제외한다.
    반환값: (등록된 id 리스트, Red라서 제외된 id 리스트)
    """
    all_by_id = {b["id"]: b for b in list_all_batteries()}

    listed, rejected = [], []
    for bid in battery_ids:
        battery = all_by_id.get(bid)
        if battery and battery.get("grade") == "Red":
            rejected.append(bid)
            continue
        _set_status_override(bid, STATUS_LISTED)
        listed.append(bid)
    return listed, rejected


def mark_negotiating(battery_id, requester_name="처리업체 담당자"):
    """처리업체의 '협의 요청' 액션 — 협의 중 상태로 전환 (백엔드 approve 호출로 기록만 남김).

    이건 확정 계약이 아니라 관심 표명/연락 단계다. 실제 매입 계약과 정산은
    플랫폼 밖에서 폐차장·처리업체 당사자 간에 별도로 진행된다.
    """
    try:
        res = requests.post(
            f"{API_BASE_URL}/history/{battery_id}/approve",
            json={"approved_by": requester_name},
            timeout=10,
        )
        res.raise_for_status()
    except requests.RequestException as e:
        st.error(f"협의 요청 처리에 실패했습니다: {e}")
        return False

    _set_status_override(battery_id, STATUS_NEGOTIATING)
    return True


def mark_disposed(battery_id):
    """Red(지정폐기물) 배터리를 폐차장이 직접 '처리 완료'로 종결 (공유 파일 상태만 변경).

    처리업체를 거치지 않는다 — 지정폐기물 처리는 플랫폼 밖(허가된 처리
    경로)에서 이뤄지고, 이 버튼은 폐차장 내부 기록용일 뿐이다.
    """
    _set_status_override(battery_id, STATUS_COMPLETED)
    return True


# =============================================================================
# 로컬 상태 초기화 (설정 페이지 — 시연/관리자 도구)
# =============================================================================
def reset_local_state():
    """
    로컬 공유 파일(상태 오버라이드/등록 대기/채널 배정) 3종을 전부 비운다.

    백엔드 DB(triage_history/match_history)는 건드리지 않는다 — 이건 어디까지나
    프론트 3개 앱이 공유하는 로컬 상태(매물 등록/매입 확정/처리 완료 표시,
    엑셀 대량 등록 대기열, 발생 폐차장 배정)만 초기화하는 것이다. 되돌릴 수 없다.
    """
    _write_json_file(_OVERRIDES_FILE, {})
    _write_json_file(_PENDING_FILE, {})
    _write_json_file(_CHANNEL_FILE, {})
    return True


# =============================================================================
# 삭제
# =============================================================================
def delete_battery(battery_id):
    """배터리 판정 이력 1건 삭제 (등록 상태 로컬 레코드도 지원). 성공하면 True."""
    if isinstance(battery_id, str) and battery_id.startswith("local-"):
        remove_pending_registration(battery_id)
        return True
    try:
        res = requests.delete(f"{API_BASE_URL}/history/{battery_id}", timeout=10)
        res.raise_for_status()
        return True
    except requests.RequestException as e:
        st.error(f"삭제에 실패했습니다: {e}")
        return False


def delete_batteries_bulk(battery_ids):
    """배터리 판정 이력 여러 건 일괄 삭제. 실제로 삭제된 id 리스트를 반환."""
    local_ids = [bid for bid in battery_ids if isinstance(bid, str) and bid.startswith("local-")]
    remote_ids = [bid for bid in battery_ids if bid not in local_ids]

    deleted = list(local_ids)
    for local_id in local_ids:
        remove_pending_registration(local_id)

    if remote_ids:
        try:
            res = requests.post(
                f"{API_BASE_URL}/history/delete",
                json={"triage_ids": remote_ids},
                timeout=15,
            )
            res.raise_for_status()
            deleted += res.json().get("deleted_ids", [])
        except requests.RequestException as e:
            st.error(f"일괄 삭제에 실패했습니다: {e}")

    return deleted


# =============================================================================
# 집계 / 표시용 유틸
# =============================================================================
def get_channel_list():
    return ["전체"] + CHANNEL_NAMES


def get_status_counts(channel_name=None):
    items = list_all_batteries()
    counts = {}
    for b in items:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    return counts


def get_grade_counts():
    items = fetch_batteries()  # 등급은 판정 이후에만 존재
    counts = {"Green": 0, "Yellow": 0, "Orange": 0, "Gray": 0, "Red": 0}
    for b in items:
        g = b.get("grade")
        if g in counts:
            counts[g] += 1
    return counts


def haversine_km(lat1, lon1, lat2, lon2):
    """두 좌표 사이 거리(km)를 구면 삼각법(haversine)으로 계산."""
    from math import radians, sin, cos, atan2, sqrt
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return round(r * 2 * atan2(sqrt(a), sqrt(1 - a)), 1)


def get_most_matched_company_name():
    """전체 판정 이력의 matched_companies를 집계해 가장 많이 추천된
    처리업체명을 반환한다 (app_company.py의 기본 로그인 계정 선택용).
    순위 가중치: 1순위 3점 / 2순위 2점 / 3순위 1점. 데이터가 없으면 None.
    """
    scores = {}
    for b in fetch_batteries():
        detail = fetch_battery_detail(b["id"])
        if not detail:
            continue
        for m in detail.get("matched_companies", []):
            name = m.get("company_name")
            if not name:
                continue
            weight = {1: 3, 2: 2, 3: 1}.get(m.get("rank"), 1)
            scores[name] = scores.get(name, 0) + weight
    if not scores:
        return None
    return max(scores, key=scores.get)


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
            "입고일": (b["created_at"] or "")[:10] or "—",
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
