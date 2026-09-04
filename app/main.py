# -*- coding: utf-8 -*-
"""FastAPI 應用入口。"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, ingest, report, review, stats
from .db import get_conn, init_db, now_iso, seed_sites
from .detect import get_detector


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    init_db()
    seed_sites()
    for site in _site_codes():
        (config.INBOX_DIR / site).mkdir(parents=True, exist_ok=True)
    yield


def _site_codes() -> list[str]:
    with get_conn() as conn:
        return [r["code"] for r in conn.execute("SELECT code FROM sites").fetchall()]


app = FastAPI(title="地盤 AI 安全監測及自動記錄系統", version="0.1.0", lifespan=lifespan)


class SiteIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1)
    address: str = ""


class ReviewIn(BaseModel):
    reviewer: str = Field(min_length=1)
    decision: str
    note: str = ""


class ReportIn(BaseModel):
    site_id: int
    work_date: str
    generated_by: str = ""


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/web/index.html")


@app.get("/web/reports.html", include_in_schema=False)
def reports_merged():
    return RedirectResponse("/web/index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "detector": config.DETECTOR,
        "auto_detect": config.AUTO_DETECT,
        "data_dir": str(config.DATA_DIR),
        "time": now_iso(),
    }


# ---------------------------------------------------------------- 地盤

@app.get("/api/sites")
def list_sites():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM sites ORDER BY code").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/sites", status_code=201)
def create_site(payload: SiteIn):
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sites WHERE code = ? COLLATE NOCASE", (payload.code,)
        ).fetchone()
        if exists:
            raise HTTPException(409, f"地盤代號 {payload.code} 已存在")
        cursor = conn.execute(
            "INSERT INTO sites (code, name, address, created_at) VALUES (?, ?, ?, ?)",
            (payload.code.upper(), payload.name, payload.address, now_iso()),
        )
        site_id = cursor.lastrowid
    (config.INBOX_DIR / payload.code.upper()).mkdir(parents=True, exist_ok=True)
    return {"id": site_id, "code": payload.code.upper()}


# ---------------------------------------------------------------- 儀表板

@app.get("/api/dashboard")
def dashboard(date: str | None = None):
    with get_conn() as conn:
        return stats.dashboard(conn, date)


@app.get("/api/dates")
def dates():
    with get_conn() as conn:
        return {"dates": stats.available_dates(conn)}


# ---------------------------------------------------------------- 接入與偵測

@app.post("/api/ingest/scan")
def scan_inbox():
    with get_conn() as conn:
        summary = ingest.scan_inbox(conn)
        detection = (
            ingest.run_pending_detections(conn) if config.AUTO_DETECT else {"photos": 0}
        )
    return {
        "added": summary.added,
        "skipped": summary.skipped,
        "error": summary.error,
        "detection": detection,
        "items": [vars(item) for item in summary.items[:200]],
    }


@app.post("/api/ingest/upload")
def upload_photos(site_id: int = Form(...), files: list[UploadFile] = File(...)):
    added, skipped, errors = 0, 0, []
    temp_dir = Path(tempfile.mkdtemp(prefix="citf-upload-"))
    try:
        with get_conn() as conn:
            for upload in files:
                name = Path(upload.filename or "photo.jpg").name
                temp_path = temp_dir / name
                with temp_path.open("wb") as fh:
                    shutil.copyfileobj(upload.file, fh)
                try:
                    outcome = ingest.store_photo(
                        conn, temp_path, site_id, source="upload", original_name=name
                    )
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
                    continue
                if outcome.status == "added":
                    added += 1
                else:
                    skipped += 1
                    errors.append(f"{name}: {outcome.reason}")
            detection = (
                ingest.run_pending_detections(conn) if config.AUTO_DETECT else {"photos": 0}
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "added": added,
        "skipped": skipped,
        "errors": errors,
        "detection": detection,
    }


@app.post("/api/detect/run")
def run_detection(limit: int | None = None):
    with get_conn() as conn:
        return ingest.run_pending_detections(conn, limit)


@app.post("/api/detect/rerun/{photo_id}")
def rerun_detection(photo_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE photos SET detect_status = 'pending' WHERE id = ?", (photo_id,))
        written = ingest.run_detection(conn, photo_id, get_detector())
        return {"photo_id": photo_id, "detections": written}


# ---------------------------------------------------------------- 相片

@app.get("/api/photos")
def list_photos(site_id: int | None = None, date: str | None = None, limit: int = 300):
    with get_conn() as conn:
        return review.list_photos(conn, site_id=site_id, work_date=date, limit=limit)


@app.get("/api/photos/{photo_id}/detections")
def photo_detections(photo_id: int):
    with get_conn() as conn:
        return review.photo_detections(conn, photo_id)


@app.get("/api/photos/{photo_id}/file")
def photo_file(photo_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stored_path, original_name FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "相片不存在")
    path = config.DATA_DIR / row["stored_path"]
    if not path.exists():
        raise HTTPException(404, "相片檔案已遺失")
    return FileResponse(path)


# ---------------------------------------------------------------- 覆核

@app.get("/api/review/queue")
def review_queue(
    site_id: int | None = None,
    date: str | None = None,
    pending_only: bool = True,
    violations_only: bool = True,
    limit: int = 500,
):
    with get_conn() as conn:
        return review.review_queue(
            conn,
            site_id=site_id,
            work_date=date,
            pending_only=pending_only,
            violations_only=violations_only,
            limit=limit,
        )


@app.post("/api/review/{detection_id}")
def submit_review(detection_id: int, payload: ReviewIn):
    with get_conn() as conn:
        try:
            return review.submit_review(
                conn, detection_id, payload.reviewer, payload.decision, payload.note
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------- 報告

@app.get("/api/reports")
def list_reports(limit: int = 100):
    with get_conn() as conn:
        return report.list_reports(conn, limit)


@app.get("/api/reports/preview", response_class=HTMLResponse)
def preview_report(site_id: int, date: str):
    """線上預覽：即時反映最新覆核結果，毋須先生成 .docx。"""
    with get_conn() as conn:
        try:
            return HTMLResponse(report.render_report_html(conn, site_id, date))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc


@app.get("/api/reports/{report_id}/preview", response_class=HTMLResponse)
def preview_saved_report(report_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT site_id, work_date FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "報告不存在")
        return HTMLResponse(
            report.render_report_html(conn, row["site_id"], row["work_date"])
        )


@app.post("/api/reports/generate")
def generate_report(payload: ReportIn):
    with get_conn() as conn:
        try:
            return report.generate_daily_report(
                conn, payload.site_id, payload.work_date, payload.generated_by
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@app.post("/api/reports/generate-all")
def generate_all_reports(work_date: str = Body(..., embed=True), generated_by: str = Body("", embed=True)):
    results = []
    with get_conn() as conn:
        sites = conn.execute("SELECT id FROM sites WHERE active = 1 ORDER BY code").fetchall()
        for site in sites:
            results.append(
                report.generate_daily_report(conn, site["id"], work_date, generated_by)
            )
    return {"work_date": work_date, "reports": results}


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "報告不存在")
    path = config.DATA_DIR / row["path"]
    if not path.exists():
        raise HTTPException(404, "報告檔案已遺失")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


app.mount("/web", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
