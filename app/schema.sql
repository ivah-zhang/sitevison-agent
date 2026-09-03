-- 地盤 AI 安全監測及自動記錄系統 — 資料庫結構

CREATE TABLE IF NOT EXISTS sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    address     TEXT    NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS photos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    sha256        TEXT    NOT NULL UNIQUE,
    original_name TEXT    NOT NULL,
    stored_path   TEXT    NOT NULL,
    work_date     TEXT    NOT NULL,
    captured_at   TEXT,
    received_at   TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    width         INTEGER,
    height        INTEGER,
    file_bytes    INTEGER,
    detect_status TEXT    NOT NULL DEFAULT 'pending',
    detect_error  TEXT
);

CREATE INDEX IF NOT EXISTS idx_photos_site_date ON photos(site_id, work_date);
CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(detect_status);

-- 同一張相片重覆傳入的紀錄，用於量化去重成效
CREATE TABLE IF NOT EXISTS duplicates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256        TEXT    NOT NULL,
    original_name TEXT    NOT NULL,
    site_id       INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    photo_id      INTEGER REFERENCES photos(id) ON DELETE CASCADE,
    seen_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS detections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id     INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    category     TEXT    NOT NULL,
    label        TEXT    NOT NULL,
    is_violation INTEGER NOT NULL,
    confidence   REAL    NOT NULL,
    bbox         TEXT,
    detector     TEXT    NOT NULL,
    created_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detections_photo ON detections(photo_id);
CREATE INDEX IF NOT EXISTS idx_detections_violation ON detections(is_violation);

-- 人手覆核：AI 只作初步篩查，最終判定以覆核結果為準
CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER NOT NULL UNIQUE REFERENCES detections(id) ON DELETE CASCADE,
    reviewer     TEXT    NOT NULL,
    decision     TEXT    NOT NULL,
    note         TEXT    NOT NULL DEFAULT '',
    reviewed_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id         INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    work_date       TEXT    NOT NULL,
    path            TEXT    NOT NULL,
    photo_count     INTEGER NOT NULL DEFAULT 0,
    violation_count INTEGER NOT NULL DEFAULT 0,
    generated_at    TEXT    NOT NULL,
    generated_by    TEXT    NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_site_date ON reports(site_id, work_date);
