# -*- coding: utf-8 -*-
"""儀表板與報告共用的統計查詢。"""
from __future__ import annotations

import sqlite3
from datetime import date

from .models import DECISION_CONFIRMED, DECISION_REJECTED


def latest_work_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(work_date) AS d FROM photos").fetchone()
    return row["d"] or date.today().isoformat()


def site_daily(conn: sqlite3.Connection, site_id: int, work_date: str) -> dict:
    """單一地盤單日統計。AI 標示與覆核結果分開呈現，兩者不可混同。"""
    photo_count = conn.execute(
        "SELECT COUNT(*) AS n FROM photos WHERE site_id = ? AND work_date = ?",
        (site_id, work_date),
    ).fetchone()["n"]

    base = (
        " FROM detections d JOIN photos p ON p.id = d.photo_id"
        " LEFT JOIN reviews r ON r.detection_id = d.id"
        " WHERE p.site_id = ? AND p.work_date = ? AND d.is_violation = 1"
    )
    params = (site_id, work_date)

    ai_flagged = conn.execute("SELECT COUNT(*) AS n" + base, params).fetchone()["n"]
    confirmed = conn.execute(
        "SELECT COUNT(*) AS n" + base + " AND r.decision = ?",
        (*params, DECISION_CONFIRMED),
    ).fetchone()["n"]
    rejected = conn.execute(
        "SELECT COUNT(*) AS n" + base + " AND r.decision = ?",
        (*params, DECISION_REJECTED),
    ).fetchone()["n"]
    pending = conn.execute(
        "SELECT COUNT(*) AS n" + base + " AND r.id IS NULL", params
    ).fetchone()["n"]

    by_category = {
        r["category"]: r["n"]
        for r in conn.execute(
            "SELECT d.category, COUNT(*) AS n" + base + " GROUP BY d.category", params
        ).fetchall()
    }

    reviewed = confirmed + rejected
    return {
        "site_id": site_id,
        "work_date": work_date,
        "photo_count": photo_count,
        "ai_flagged": ai_flagged,
        "confirmed": confirmed,
        "rejected": rejected,
        "pending_review": pending,
        "review_progress": round(reviewed / ai_flagged * 100, 1) if ai_flagged else 100.0,
        "false_positive_rate": round(rejected / reviewed * 100, 1) if reviewed else 0.0,
        "by_category": by_category,
    }


def dashboard(conn: sqlite3.Connection, work_date: str | None = None) -> dict:
    work_date = work_date or latest_work_date(conn)
    sites = conn.execute("SELECT * FROM sites WHERE active = 1 ORDER BY code").fetchall()

    rows = []
    for site in sites:
        entry = site_daily(conn, site["id"], work_date)
        entry.update(
            {"site_code": site["code"], "site_name": site["name"], "address": site["address"]}
        )
        report = conn.execute(
            "SELECT id, generated_at FROM reports WHERE site_id = ? AND work_date = ?",
            (site["id"], work_date),
        ).fetchone()
        entry["report_id"] = report["id"] if report else None
        entry["report_generated_at"] = report["generated_at"] if report else None
        rows.append(entry)

    totals = {
        key: sum(r[key] for r in rows)
        for key in (
            "photo_count",
            "ai_flagged",
            "confirmed",
            "rejected",
            "pending_review",
        )
    }
    reviewed = totals["confirmed"] + totals["rejected"]
    totals["review_progress"] = (
        round(reviewed / totals["ai_flagged"] * 100, 1) if totals["ai_flagged"] else 100.0
    )
    totals["site_count"] = len(rows)

    return {"work_date": work_date, "sites": rows, "totals": totals}


def available_dates(conn: sqlite3.Connection, limit: int = 30) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT work_date FROM photos ORDER BY work_date DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r["work_date"] for r in rows]
