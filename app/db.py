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
