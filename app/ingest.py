# -*- coding: utf-8 -*-
"""相片接入。

兩個入口：網頁上載，以及掃描 data/inbox/<地盤代號>/。
每張相片各自歸檔入庫，不攔截內容相同的檔案。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image

from . import config
from .db import now_iso
from .detect import get_detector
from .models import IngestOutcome, IngestSummary

EXIF_DATETIME_ORIGINAL = 36867
PROCESSED_DIRNAME = "_processed"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_image_meta(path: Path) -> tuple[int | None, int | None, str | None]:
    """回傳 (寬, 高, 拍攝時間)。非影像或無 EXIF 時以 None 表示。"""
    try:
        with Image.open(path) as img:
            width, height = img.size
            captured_at = None
            exif = img.getexif()
            raw = exif.get(EXIF_DATETIME_ORIGINAL) if exif else None
            if raw:
                try:
                    captured_at = datetime.strptime(
                        str(raw), "%Y:%m:%d %H:%M:%S"
                    ).isoformat(timespec="seconds")
                except ValueError:
                    captured_at = None
            return width, height, captured_at
    except Exception:
        return None, None, None


def resolve_captured_at(path: Path, exif_captured_at: str | None) -> str:
    """拍攝時間：優先採用 EXIF，缺少時退回檔案修改時間。"""
    if exif_captured_at:
        return exif_captured_at
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def get_site(conn: sqlite3.Connection, site_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()


def get_site_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sites WHERE code = ? COLLATE NOCASE", (code,)
    ).fetchone()


def store_photo(
    conn: sqlite3.Connection,
    source_path: Path,
    site_id: int,
    source: str,
    original_name: str | None = None,
) -> IngestOutcome:
    """將單一檔案歸檔入庫。"""
    original_name = original_name or source_path.name
    suffix = source_path.suffix.lower()
    if suffix not in config.ALLOWED_SUFFIXES:
        return IngestOutcome("skipped", str(source_path), reason=f"不支援的檔案類型 {suffix}")

    site = get_site(conn, site_id)
    if site is None:
        return IngestOutcome("error", str(source_path), reason=f"地盤 id={site_id} 不存在")

    digest = sha256_file(source_path)
    width, height, exif_captured_at = read_image_meta(source_path)
    captured_at = resolve_captured_at(source_path, exif_captured_at)
    work_date = captured_at[:10]

    target_dir = config.PHOTO_DIR / site["code"] / work_date
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex[:12]}{suffix}"
    shutil.copy2(source_path, target_path)

    cursor = conn.execute(
        "INSERT INTO photos (site_id, sha256, original_name, stored_path, work_date,"
        " captured_at, received_at, source, width, height, file_bytes, detect_status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
        (
            site_id,
            digest,
            original_name,
            str(target_path.relative_to(config.DATA_DIR)),
            work_date,
            captured_at,
            now_iso(),
            source,
            width,
            height,
            source_path.stat().st_size,
        ),
    )
    return IngestOutcome("added", str(source_path), photo_id=cursor.lastrowid)


def _move_to_processed(path: Path, site_code: str) -> None:
    dest_dir = config.INBOX_DIR / PROCESSED_DIRNAME / site_code
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{path.name}"
    counter = 1
    while dest.exists():
        dest = dest.with_name(f"{dest.stem}-{counter}{dest.suffix}")
        counter += 1
    shutil.move(str(path), str(dest))


def scan_inbox(conn: sqlite3.Connection, move_processed: bool = True) -> IngestSummary:
    """掃描 data/inbox/<地盤代號>/ 下的所有相片。"""
    config.ensure_dirs()
    summary = IngestSummary()

    for site_dir in sorted(config.INBOX_DIR.iterdir()):
        if not site_dir.is_dir() or site_dir.name == PROCESSED_DIRNAME:
            continue
        site = get_site_by_code(conn, site_dir.name)
        if site is None:
            summary.record(
                IngestOutcome("skipped", str(site_dir), reason=f"未登記的地盤代號 {site_dir.name}")
            )
            continue

        for file_path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
            try:
                outcome = store_photo(conn, file_path, site["id"], source="inbox")
            except Exception as exc:  # 單一檔案失敗不應中斷整批接入
                outcome = IngestOutcome("error", str(file_path), reason=str(exc))
            summary.record(outcome)
            if move_processed and outcome.status == "added":
                _move_to_processed(file_path, site["code"])

    return summary


def run_detection(conn: sqlite3.Connection, photo_id: int, detector=None) -> int:
    """對單張相片執行偵測，回寫結果。回傳寫入的偵測項目數。"""
    detector = detector or get_detector()
    row = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if row is None:
        raise ValueError(f"相片 id={photo_id} 不存在")

    image_path = config.DATA_DIR / row["stored_path"]
    try:
        results = detector.analyse(image_path)
    except Exception as exc:
        conn.execute(
            "UPDATE photos SET detect_status = 'error', detect_error = ? WHERE id = ?",
            (str(exc), photo_id),
        )
        return 0

    conn.execute("DELETE FROM detections WHERE photo_id = ?", (photo_id,))
    written = 0
    for result in results:
        if result.confidence < config.CONFIDENCE_THRESHOLD:
            continue
        conn.execute(
            "INSERT INTO detections (photo_id, category, label, is_violation, confidence,"
            " bbox, detector, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                photo_id,
                result.category,
                result.label,
                int(result.is_violation),
                result.confidence,
                json.dumps(result.bbox) if result.bbox else None,
                detector.name,
                now_iso(),
            ),
        )
        written += 1

    conn.execute(
        "UPDATE photos SET detect_status = 'done', detect_error = NULL WHERE id = ?",
        (photo_id,),
    )
    return written


def run_pending_detections(conn: sqlite3.Connection, limit: int | None = None) -> dict:
    detector = get_detector()
    sql = "SELECT id FROM photos WHERE detect_status = 'pending' ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    photo_ids = [r["id"] for r in conn.execute(sql).fetchall()]

    detections = 0
    for photo_id in photo_ids:
        detections += run_detection(conn, photo_id, detector)

    return {"detector": detector.name, "photos": len(photo_ids), "detections": detections}
