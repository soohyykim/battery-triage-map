# BATLINK (배트링크)

**Every Battery Finds Its Next Life.**

지역 폐차장과 배터리 처리기업을 AI 기반으로 연결하는 사용후 전기차 배터리 순환경제 매칭 플랫폼입니다.

> 제14회 산업통상부 공공데이터 활용 아이디어 공모전(제품·서비스 개발 부문) 출품작
> (제출명: Battery Triage Map / 팀원: 김남훈, 김수현, 함현우)

---

## 왜 만들었나

전기차 보급이 늘면서 사용후 배터리 발생량도 빠르게 늘고 있지만, 정작 배터리를 발생시키는 **폐차장은 배터리 상태를 판정할 역량이 없고, 어느 처리업체와 거래해야 할지 판단할 정보도 없습니다.** 반대로 처리업체 입장에서도 전국에 흩어진 폐차장 물량을 파악하기 어렵습니다.

BATLINK는 이 정보 비대칭을 풀기 위해, **배터리 등록 → AI 예비 판정 → 처리업체 추천 → 매물 등록 → 협의 요청**까지 이어지는 흐름을 하나의 플랫폼에 담았습니다.

---

## 핵심 기능

| 화면 | 대상 | 주요 기능 |
|---|---|---|
| 배터리 등록 | 폐차장 현장 담당자 | VIN QR 스캔/수동 입력, 차량·배터리 정보 입력, 즉시 AI 판정 |
| 배터리 관리 | 폐차장 사무실 | 판정 이력 조회·필터, 엑셀 대량 등록, 일괄 작업(판정/매물등록/처리완료), 판정서 PDF 발급 |
| 대시보드 | 폐차장 사무실 | 전체 현황·등급 분포·등록 추이·처리업체 지도·정산 내역·정책 브리핑 |
| 마켓 | 처리업체 | 조건 기반 매물 탐색, AI 추천 매물, 협의 요청 |

### 판정(Triage) 로직
- 연식·주행거리·화학계 기반 SOH Proxy(배터리 건강상태 예비 추정치) 계산
- 재활용 점수에 **한국광해광업공단 리튬·니켈·코발트 가격예측 데이터**를 반영 — 단순 상태 평가를 넘어 실제 광물 회수 가치까지 등급에 반영
- 침수·누액·과열·팽창·충격 1차 룰 기반 선별로 지정폐기물(Red) 즉시 분류

### 매칭(Matching) 로직
- 등급별 요구 진단역량(basic/kolas), 거리(haversine), 용량, 화학계 기준 처리업체 1~3순위 자동 매칭
- 판정과 매칭이 한 번의 요청으로 함께 처리되어 대기 시간 없음

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────┐
│  app.py (Streamlit, 단일 진입점)              │
│  st.navigation으로 역할별 화면 통합           │
│  ├─ 앱: 배터리 등록                           │
│  ├─ 웹·폐차장: 배터리 관리 / 대시보드 / 설정   │
│  └─ 웹·처리업체: 마켓                         │
└───────────────────┬───────────────────────────┘
                     │ HTTP
┌───────────────────▼───────────────────────────┐
│  FastAPI 백엔드 (api/main.py)                  │
│  /triage  /match  /report  /history  /pdf      │
│  services/ (triage, matching, mineral_price,   │
│             rule, rag, pdf, db)                │
└───────────────────┬───────────────────────────┘
                     │
              PostgreSQL (Render)
```

원래는 앱/웹(폐차장)/웹(처리업체) 3개를 별도 Streamlit 프로세스로 띄웠으나, 배포 환경에서 3개 앱 간 실시간 데이터 공유가 안 되는 구조적 한계가 있어 **`st.navigation` 기반 단일 앱으로 통합**했습니다.

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Streamlit, matplotlib, folium |
| 백엔드 | FastAPI, SQLAlchemy, PostgreSQL |
| 배포 | Streamlit Community Cloud (프론트) / Render (백엔드) — *현재 라이브 배포는 종료되었으며, 로컬 실행 방법은 아래를 참고하세요* |
| 외부 데이터 연동 | 한국광해광업공단 광물가격 API (실패 시 자체 검증 기본값으로 자동 폴백) |

---

## 로컬 실행

```bash
git clone <repo-url>
cd battery-triage-map
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# (최초 1회) 시연용 매물 데이터 채우기
python seed_listings.py

streamlit run app.py
```

백엔드를 로컬에서 직접 돌리려면 `api/requirements.txt`로 별도 가상환경을 구성한 뒤:
```bash
uvicorn api.main:app --reload
```

---

## 프로젝트 구조

```
battery-triage-map/
├── .devcontainer/
│   └── devcontainer.json
├── .github/
│   └── workflows/
│       └── deploy.yml
├── .streamlit/
│   └── config.toml            # 네이비 테마 (사이드바 개별 색상 포함)
├── api/                        # FastAPI 백엔드
│   ├── main.py                 # 엔드포인트
│   ├── requirements.txt        # 백엔드 전용 의존성
│   └── schemas.py
├── services/                   # 백엔드 비즈니스 로직 (api/와 별도 최상위 폴더)
│   ├── triage.py               # 판정 로직
│   ├── matching.py             # 매칭 로직
│   ├── mineral_price.py        # 광물가격 연동
│   ├── rule.py                 # 지정폐기물 1차 선별
│   ├── rag.py                  # 정책 리포트 생성 (Gemini RAG)
│   ├── pdf.py                  # PDF 발급
│   └── db.py
├── assets/
│   └── NanumGothic.ttf         # PDF 한글 출력용 폰트
├── data/
│   ├── policies/                # 정책 브리핑용 원본 PDF
│   ├── companies_mock.csv       # 처리업체 목업 DB
│   ├── battery_cases_demo.csv   # 시연용 배터리 케이스
│   ├── synthetic_batteries.csv  # 합성 배터리 데이터
│   ├── init_db.py
│   └── schema.sql
├── docs/
│   ├── company_data_description_v5_3.md
│   └── TROUBLESHOOTING.md       # 기술 트러블슈팅 회고
├── outputs/                     # 실행 결과물 저장용 (기본은 비어있음)
├── tests/
│   └── test_triage.py
├── app.py                       # Streamlit 통합 진입점
├── app_mobile.py                 # 배터리 등록 (앱)
├── app_junkyard.py                # 배터리 관리 · 대시보드 · 설정 (웹·폐차장)
├── app_company.py                 # 마켓 (웹·처리업체)
├── battery_data.py                # 프론트-백엔드 연동 데이터 레이어
├── ui_common.py                   # 공통 UI 컴포넌트 · CSS
├── seed_data.py / seed_listings.py  # 시연용 데이터 시드 스크립트
├── build_index.py                 # 정책 PDF 인덱싱
├── render.yaml                    # 백엔드 배포 설정 (Render)
├── requirements.txt                # 프론트 전용 의존성
└── .env.example
```

---

## 라이선스 / 데이터 출처

산업통상부 산하 공공기관 공공데이터(한국광해광업공단 광물가격예측 데이터, 한국산업단지공단 공장현황 등)를 활용했습니다. 상세 목록은 `docs/` 내 제출 서류를 참고하세요.
