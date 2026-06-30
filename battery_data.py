"""
배터리 관리 페이지 — 데이터 접근 레이어

지금은 더미 데이터를 반환하지만, 백엔드AI의 API가 준비되면
이 파일의 함수 내부만 requests 호출로 바꾸면 됩니다.
(화면 코드는 이 함수들의 인터페이스만 보고 작동하므로 수정 불필요)
"""

from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 상태 정의 (백엔드AI 요청 메시지와 동일한 5단계 + 예외 2개)
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
    STATUS_PENDING_TRIAGE: "#9aa5b1",       # 회색
    STATUS_PENDING_APPROVAL: "#f3821d",     # 주황 (warning)
    STATUS_REQUESTED: "#00b5b5",            # 민트 (accent)
    STATUS_PICKUP_SCHEDULED: "#142f4b",     # 네이비 (primary)
    STATUS_COMPLETED: "#2e9e5b",            # 초록
    STATUS_REJECTED: "#e62d28",             # 빨강 (destructive)
    STATUS_DESIGNATED_WASTE: "#7a1f1f",     # 진한 빨강
}

GRADE_EMOJI = {"Green": "✅", "Yellow": "⚠️", "Orange": "⚡", "Gray": "❌", None: "—"}

GRADE_COLOR = {
    "Green": "#2e9e5b",
    "Yellow": "#f3821d",
    "Orange": "#e07a1f",
    "Gray": "#576574",
    None: "#9aa5b1",
}

# 더미 로그인 정보 (실제 로그인 기능은 추후 구현)
DUMMY_USER = {
    "name": "홍길동",
    "channel_name": "강남폐차센터",
    "channel_type": "폐차장",
}


def _now_minus(days=0, hours=0):
    return (datetime.now() - timedelta(days=days, hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# 더미 데이터 (8개 — 상태값 다양하게 분포)
# ---------------------------------------------------------------------------
_DUMMY_BATTERIES = [
    {
        "id": 1,
        "vin": "KMHXX00XXX000001",
        "model_name": "아이오닉 5",
        "battery_manufacturer": "LG에너지솔루션",
        "capacity_kwh": 77.4,
        "chemistry": "NCM",
        "grade": "Yellow",
        "soh_proxy_score": 73.9,
        "status": STATUS_PENDING_APPROVAL,
        "channel_name": "강남폐차센터",
        "matched_company": "충청자원순환",
        "created_at": _now_minus(days=0, hours=2),
    },
    {
        "id": 2,
        "vin": "KMHXX00XXX000002",
        "model_name": "EV6",
        "battery_manufacturer": "SK온",
        "capacity_kwh": 58.0,
        "chemistry": "NCM",
        "grade": "Orange",
        "soh_proxy_score": 52.1,
        "status": STATUS_REQUESTED,
        "channel_name": "강남폐차센터",
        "matched_company": "인천배터리리사이클",
        "created_at": _now_minus(days=1, hours=4),
    },
    {
        "id": 3,
        "vin": "KMHXX00XXX000003",
        "model_name": "니로 EV",
        "battery_manufacturer": "SK온",
        "capacity_kwh": 64.8,
        "chemistry": "NCM",
        "grade": "Green",
        "soh_proxy_score": 81.2,
        "status": STATUS_PICKUP_SCHEDULED,
        "channel_name": "수원폐차센터",
        "matched_company": "경기재활용센터",
        "created_at": _now_minus(days=2, hours=1),
    },
    {
        "id": 4,
        "vin": "KMHXX00XXX000004",
        "model_name": "테슬라 모델3",
        "battery_manufacturer": "CATL",
        "capacity_kwh": 60.0,
        "chemistry": "LFP",
        "grade": None,
        "soh_proxy_score": None,
        "status": STATUS_PENDING_TRIAGE,
        "channel_name": "강남폐차센터",
        "matched_company": None,
        "created_at": _now_minus(days=0, hours=1),
    },
    {
        "id": 5,
        "vin": "KMHXX00XXX000005",
        "model_name": "쏘나타 하이브리드",
        "battery_manufacturer": "LG에너지솔루션",
        "capacity_kwh": 1.6,
        "chemistry": "NCM",
        "grade": "Gray",
        "soh_proxy_score": 31.4,
        "status": STATUS_COMPLETED,
        "channel_name": "인천폐차센터",
        "matched_company": "경기재활용센터",
        "created_at": _now_minus(days=5, hours=0),
    },
    {
        "id": 6,
        "vin": "KMHXX00XXX000006",
        "model_name": "코나 일렉트릭",
        "battery_manufacturer": "LG에너지솔루션",
        "capacity_kwh": 64.0,
        "chemistry": "NCM",
        "grade": None,
        "soh_proxy_score": None,
        "status": STATUS_DESIGNATED_WASTE,
        "channel_name": "수원폐차센터",
        "matched_company": None,
        "created_at": _now_minus(days=1, hours=10),
    },
    {
        "id": 7,
        "vin": "KMHXX00XXX000007",
        "model_name": "비야디 아토3",
        "battery_manufacturer": "BYD",
        "capacity_kwh": 60.5,
        "chemistry": "LFP",
        "grade": "Yellow",
        "soh_proxy_score": 68.5,
        "status": STATUS_REJECTED,
        "channel_name": "강남폐차센터",
        "matched_company": "충청자원순환",
        "created_at": _now_minus(days=3, hours=2),
    },
    {
        "id": 8,
        "vin": "KMHXX00XXX000008",
        "model_name": "아이오닉 6",
        "battery_manufacturer": "SK온",
        "capacity_kwh": 77.4,
        "chemistry": "NCM",
        "grade": "Green",
        "soh_proxy_score": 88.0,
        "status": STATUS_PENDING_APPROVAL,
        "channel_name": "인천폐차센터",
        "matched_company": "인천배터리리사이클",
        "created_at": _now_minus(days=0, hours=5),
    },
]


# ---------------------------------------------------------------------------
# 데이터 접근 함수 (나중에 API 연동 시 이 함수 내부만 교체)
# ---------------------------------------------------------------------------

def fetch_batteries(channel_name=None, status=None):
    """
    배터리 목록 조회

    [나중에 API 연동 시]
    import requests
    params = {}
    if channel_name and channel_name != "전체": params["channel_name"] = channel_name
    if status and status != "전체": params["status"] = status
    res = requests.get(f"{API_BASE_URL}/batteries", params=params)
    return res.json()
    """
    results = _DUMMY_BATTERIES

    if channel_name and channel_name != "전체":
        results = [b for b in results if b["channel_name"] == channel_name]
    if status and status != "전체":
        results = [b for b in results if b["status"] == status]

    # 최신순 정렬
    return sorted(results, key=lambda b: b["created_at"], reverse=True)


def fetch_battery_detail(battery_id):
    """
    단일 배터리 상세 조회

    [나중에 API 연동 시]
    res = requests.get(f"{API_BASE_URL}/batteries/{battery_id}")
    return res.json()
    """
    for b in _DUMMY_BATTERIES:
        if b["id"] == battery_id:
            return b
    return None


def update_battery_status(battery_id, new_status, note=""):
    """
    배터리 상태 변경

    [나중에 API 연동 시]
    res = requests.patch(
        f"{API_BASE_URL}/batteries/{battery_id}/status",
        json={"status": new_status, "note": note}
    )
    return res.ok
    """
    for b in _DUMMY_BATTERIES:
        if b["id"] == battery_id:
            b["status"] = new_status
            return True
    return False


def get_channel_list():
    """발생채널 목록 (필터 드롭다운용)"""
    channels = sorted(set(b["channel_name"] for b in _DUMMY_BATTERIES))
    return ["전체"] + channels


def get_status_counts(channel_name=None):
    """상태별 개수 집계 (대시보드 요약 카드용)"""
    results = _DUMMY_BATTERIES
    if channel_name and channel_name != "전체":
        results = [b for b in results if b["channel_name"] == channel_name]

    counts = {}
    for b in results:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    return counts


def batteries_to_table_rows(batteries):
    """
    배터리 리스트를 표(st.dataframe) 표시용 딕셔너리 리스트로 변환
    컬럼: VIN, 모델명, 제조사, 용량, 등급, 상태, 추천업체
    (등급/상태는 색상 배지 스타일링을 위해 원본 텍스트 그대로 둠 — 스타일은 style_battery_table에서 적용)
    """
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
    """
    배터리 표에 등급/상태 색상 배지 스타일 적용 (pandas Styler)
    pandas 버전에 따라 .map / .applymap 중 사용 가능한 쪽 자동 선택
    """
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