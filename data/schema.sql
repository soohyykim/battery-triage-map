-- Battery Triage Map - SQLite ?ㅽ궎留?(?뚯씠釉?3醫?
-- ?곸슜: python data/init_db.py

CREATE TABLE IF NOT EXISTS triage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    battery_id TEXT NOT NULL,
    chemistry TEXT, grade TEXT, risk_level TEXT, risk_score REAL,
    soh REAL, voltage REAL, temperature REAL,
    swelling INTEGER, leakage INTEGER, cycle_count INTEGER,
    triggered_rules TEXT, recommended_route TEXT,
    region TEXT, lat REAL, lon REAL,
    approved_by TEXT, approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_triage_battery ON triage_history(battery_id);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, permit_no TEXT,
    region TEXT, address TEXT, lat REAL, lon REAL,
    handling_types TEXT, chemistry_supported TEXT,
    capacity_ton REAL, phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_company_region ON companies(region);

CREATE TABLE IF NOT EXISTS match_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triage_id INTEGER, company_id INTEGER, rank INTEGER,
    distance_km REAL, score REAL, status TEXT DEFAULT '?쒖븞',
    handling_method TEXT, quantity INTEGER,
    vehicle_no TEXT, scheduled_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (triage_id) REFERENCES triage_history(id),
    FOREIGN KEY (company_id) REFERENCES companies(id)
);
CREATE INDEX IF NOT EXISTS idx_match_triage ON match_history(triage_id);
