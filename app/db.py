# -*- coding: utf-8 -*-
"""SQLite 存取層。每個請求各自開連線，避免跨執行緒共用。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from . import config

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_dirs()
    with get_conn() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _drop_dedup_schema(conn)


def _drop_dedup_schema(conn: sqlite3.Connection) -> None:
    """舊庫若仍有去重表或 sha256 唯一約束，升級時拆除。"""
    conn.execute("DROP TABLE IF EXISTS duplicates")

    unique_sha = False
    for idx in conn.execute("PRAGMA index_list('photos')"):
        if not idx["unique"]:
            continue
        cols = [c["name"] for c in conn.execute(f"PRAGMA index_info('{idx['name']}')")]
        if cols == ["sha256"]:
            unique_sha = True
            break
    if not unique_sha:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TABLE photos_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            sha256        TEXT    NOT NULL,
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
        INSERT INTO photos_new SELECT * FROM photos;
        DROP TABLE photos;
        ALTER TABLE photos_new RENAME TO photos;
        CREATE INDEX IF NOT EXISTS idx_photos_site_date ON photos(site_id, work_date);
        CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(detect_status);
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


DEFAULT_SITES = [
    ("HY", "蠔涌地盤", "西貢蠔涌"),
    ("OKR", "愛群道地盤", "灣仔愛群道"),
    ("KCL", "葵涌物流中心", "葵涌"),
]


def seed_sites(sites=DEFAULT_SITES) -> int:
    """建立預設地盤，已存在者略過。回傳新增數目。"""
    created = 0
    with get_conn() as conn:
        for code, name, address in sites:
            exists = conn.execute("SELECT 1 FROM sites WHERE code = ?", (code,)).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO sites (code, name, address, created_at) VALUES (?, ?, ?, ?)",
                (code, name, address, now_iso()),
            )
            created += 1
    return created


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]
