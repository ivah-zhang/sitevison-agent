# -*- coding: utf-8 -*-
"""人手覆核。

AI 偵測結果一律先進入覆核佇列，由管工或安全主任確認或推翻；系統只作輔助
篩查，最終判定以覆核結果為準，日報亦以覆核結果為依據。
"""
from __future__ import annotations

import json
import sqlite3

from .db import now_iso
from .models import DECISION_CONFIRMED, DECISION_REJECTED

VALID_DECISIONS = {DECISION_CONFIRMED, DECISION_REJECTED}

_DETECTION_SELECT = """
SELECT d.id            AS detection_id,
       d.category, d.label, d.is_violation, d.confidence, d.bbox, d.detector,
       d.created_at    AS detected_at,
       p.id            AS photo_id,
       p.original_name, p.stored_path, p.work_date, p.captured_at, p.received_at,
       s.id            AS site_id,
       s.code          AS site_code,
       s.name          AS site_name,
       r.decision, r.reviewer, r.note, r.reviewed_at
FROM detections d
JOIN photos p ON p.id = d.photo_id
JOIN sites  s ON s.id = p.site_id
LEFT JOIN reviews r ON r.detection_id = d.id
"""


def _shape(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["is_violation"] = bool(item["is_violation"])
    item["bbox"] = json.loads(item["bbox"]) if item["bbox"] else None
    item["reviewed"] = item["decision"] is not None
    return item


def review_queue(
    conn: sqlite3.Connection,
    site_id: int | None = None,
    work_date: str | None = None,
    pending_only: bool = True,
    violations_only: bool = True,
    limit: int = 500,
) -> list[dict]:
    where = []
    params: list = []
    if violations_only:
        where.append("d.is_violation = 1")
    if pending_only:
        where.append("r.id IS NULL")
    if site_id:
        where.append("p.site_id = ?")
        params.append(site_id)
    if work_date:
        where.append("p.work_date = ?")
        params.append(work_date)

    sql = _DETECTION_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.is_violation DESC, d.confidence DESC, d.id LIMIT ?"
    params.append(limit)

    return [_shape(r) for r in conn.execute(sql, params).fetchall()]


def photo_detections(conn: sqlite3.Connection, photo_id: int) -> list[dict]:
    sql = _DETECTION_SELECT + " WHERE d.photo_id = ? ORDER BY d.is_violation DESC, d.id"
    return [_shape(r) for r in conn.execute(sql, (photo_id,)).fetchall()]


def list_photos(
    conn: sqlite3.Connection,
    site_id: int | None = None,
    work_date: str | None = None,
    limit: int = 300,
) -> list[dict]:
    where = []
    params: list = []
    if site_id:
        where.append("p.site_id = ?")
        params.append(site_id)
    if work_date:
        where.append("p.work_date = ?")
        params.append(work_date)

    sql = """
        SELECT p.*, s.code AS site_code, s.name AS site_name,
               (SELECT COUNT(*) FROM detections d
                 WHERE d.photo_id = p.id AND d.is_violation = 1) AS violation_count,
               (SELECT COUNT(*) FROM detections d
                  LEFT JOIN reviews r ON r.detection_id = d.id
                 WHERE d.photo_id = p.id AND d.is_violation = 1
                   AND r.id IS NULL) AS pending_count
        FROM photos p JOIN sites s ON s.id = p.site_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.work_date DESC, p.id DESC LIMIT ?"
    params.append(limit)

    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def submit_review(
    conn: sqlite3.Connection,
    detection_id: int,
    reviewer: str,
    decision: str,
    note: str = "",
) -> dict:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"無效的覆核決定：{decision}")
    if not reviewer.strip():
        raise ValueError("必須填寫覆核人姓名")

    exists = conn.execute("SELECT 1 FROM detections WHERE id = ?", (detection_id,)).fetchone()
    if exists is None:
        raise ValueError(f"偵測項目 id={detection_id} 不存在")

    conn.execute(
        "INSERT INTO reviews (detection_id, reviewer, decision, note, reviewed_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(detection_id) DO UPDATE SET"
        " reviewer = excluded.reviewer, decision = excluded.decision,"
        " note = excluded.note, reviewed_at = excluded.reviewed_at",
        (detection_id, reviewer.strip(), decision, note.strip(), now_iso()),
    )
    return {"detection_id": detection_id, "decision": decision, "reviewer": reviewer.strip()}


def confirmed_violations(
    conn: sqlite3.Connection, site_id: int, work_date: str
) -> list[dict]:
    """當日經覆核確認的違規，日報以此為準。"""
    sql = (
        _DETECTION_SELECT
        + " WHERE d.is_violation = 1 AND p.site_id = ? AND p.work_date = ?"
        " AND r.decision = ? ORDER BY d.confidence DESC"
    )
    rows = conn.execute(sql, (site_id, work_date, DECISION_CONFIRMED)).fetchall()
    return [_shape(r) for r in rows]


def pending_violations(
    conn: sqlite3.Connection, site_id: int, work_date: str
) -> list[dict]:
    sql = (
        _DETECTION_SELECT
        + " WHERE d.is_violation = 1 AND p.site_id = ? AND p.work_date = ?"
        " AND r.id IS NULL ORDER BY d.confidence DESC"
    )
    rows = conn.execute(sql, (site_id, work_date)).fetchall()
    return [_shape(r) for r in rows]


__all__ = [
    "DECISION_CONFIRMED",
    "DECISION_REJECTED",
    "confirmed_violations",
    "list_photos",
    "pending_violations",
    "photo_detections",
    "review_queue",
    "submit_review",
]
