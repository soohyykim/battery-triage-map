-- Battery Triage Map - DB 스키마 (테이블 3종) — 사람이 읽기 위한 참고용
-- ※ 실제 테이블 생성은 services/db.py 의 SQLAlchemy 정의가 담당한다
--   (python data/init_db.py 실행 시 SQLite/PostgreSQL 모두 자동 생성).
-- 이 파일은 구조를 한눈에 보기 위한 문서이며, 코드가 직접 읽지는 않는다.
-- 데엔 모듈(services/triage.py · matching.py)의 실제 출력 구조에 맞춰 정의한다.

-- ---------------------------------------------------------------------------
-- 1. triage_history : /triage 판정 1건 = 1행
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS triage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 입력값 (input_summary)
    manufacturer TEXT,
    model_name TEXT,
    vehicle_year INTEGER,
    mileage_km REAL,
    capacity_kwh REAL,
    chemistry TEXT,
    battery_count INTEGER DEFAULT 1,

    -- 점수
    soh_proxy_score REAL,
    reuse_score REAL,
    recycle_score REAL,
    data_confidence REAL,

    -- 판정 결과
    grade TEXT,                       -- Green / Yellow / Orange / Gray
    recommended_path TEXT,
    required_diagnostic_capability TEXT,
    collection_route TEXT,
    reason_codes TEXT,                -- 콤마로 연결된 코드 문자열

    -- 발생 위치(매칭용, 선택)
    origin_latitude REAL,
    origin_longitude REAL,

    -- 담당자 승인 (팀장 app.py)
    approved_by TEXT,
    approved_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_triage_grade ON triage_history(grade);
CREATE INDEX IF NOT EXISTS idx_triage_created ON triage_history(created_at);

-- ---------------------------------------------------------------------------
-- 2. companies : 처리업체 DB (companies_mock.csv 와 동일 컬럼)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    address TEXT,
    region TEXT,
    latitude REAL,
    longitude REAL,
    license_type TEXT,
    process_type TEXT,                -- reuse / recycle
    accepted_chemistry TEXT,          -- "NCM,LFP"
    accepted_grade TEXT,              -- "Orange,Gray"
    monthly_capacity_count INTEGER,
    diagnostic_capability TEXT,       -- none / basic / kolas
    is_active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_company_region ON companies(region);

-- ---------------------------------------------------------------------------
-- 3. match_history : /match 추천 결과 (판정 1건당 1~3행)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triage_id INTEGER,                -- triage_history.id 참조
    rank INTEGER,
    company_id TEXT,
    company_name TEXT,
    distance_km REAL,
    total_score REAL,
    process_type TEXT,
    diagnostic_capability TEXT,
    status TEXT DEFAULT '제안',        -- 제안 / 확정 / 취소
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (triage_id) REFERENCES triage_history(id)
);
CREATE INDEX IF NOT EXISTS idx_match_triage ON match_history(triage_id);
