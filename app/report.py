# -*- coding: utf-8 -*-
"""每日 Word 報告生成。

報告以覆核結果為準：AI 標示但未經覆核的項目另列「待覆核」，不計入確認違規，
並在附註聲明系統只作輔助，不取代法定人手安全巡查。
"""
from __future__ import annotations

import io
import sqlite3
from datetime import datetime
from html import escape
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from PIL import Image

from . import config, review, stats
from .db import now_iso
from .models import CATEGORY_LABELS

CJK_FONT = "Microsoft JhengHei"
DISCLAIMER = (
    "附註：本報告由人工智能（AI）系統自動篩查相片後生成，所有違規項目均經"
    "管工或安全主任人手覆核確認。系統只作輔助用途，不取代法定人手安全巡查。"
)


def _format_time(value: str | None) -> str:
    if not value:
        return "—"
    return str(value)[:19].replace("T", " ")


def _apply_cjk_font(document: Document) -> None:
    for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3"):
        try:
            style = document.styles[style_name]
        except KeyError:
            continue
        style.font.name = CJK_FONT
        rpr = style.element.get_or_add_rPr()
        rpr.get_or_add_rFonts().set(qn("w:eastAsia"), CJK_FONT)


def _thumbnail(image_path: Path, max_px: int = config.REPORT_IMAGE_MAX_PX) -> io.BytesIO | None:
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_px, max_px))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=82)
            buffer.seek(0)
            return buffer
    except Exception:
        return None


def _key_value_table(document: Document, pairs: list[tuple[str, str]]) -> None:
    table = document.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for key, value in pairs:
        cells = table.add_row().cells
        cells[0].text = key
        cells[1].text = value
        for paragraph in cells[0].paragraphs:
            for run in paragraph.runs:
                run.bold = True


def _violation_block(document: Document, item: dict, index: int) -> None:
    heading = document.add_paragraph()
    run = heading.add_run(
        f"{index}. {CATEGORY_LABELS.get(item['category'], item['category'])} — {item['label']}"
    )
    run.bold = True
    run.font.size = Pt(11)

    image_path = config.DATA_DIR / item["stored_path"]
    thumb = _thumbnail(image_path)
    if thumb is not None:
        document.add_picture(thumb, width=Cm(11))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    detail = [
        f"相片檔案：{item['original_name']}",
        f"拍攝時間：{_format_time(item['captured_at'] or item['received_at'])}",
        f"AI 信心值：{item['confidence']:.2f}（偵測器：{item['detector']}）",
    ]
    if item.get("decision"):
        detail.append(f"覆核：{item['reviewer']} 於 {_format_time(item['reviewed_at'])} 確認")
    if item.get("note"):
        detail.append(f"覆核備註：{item['note']}")

    paragraph = document.add_paragraph("\n".join(detail))
    paragraph.paragraph_format.space_after = Pt(10)


def _photo_index_table(document: Document, photos: list[dict]) -> None:
    table = document.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    for cell, title in zip(table.rows[0].cells, ("#", "相片檔案", "時間", "AI 篩查結果")):
        cell.text = title
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for i, photo in enumerate(photos, start=1):
        cells = table.add_row().cells
        cells[0].text = str(i)
        cells[1].text = photo["original_name"]
        cells[2].text = _format_time(photo["captured_at"] or photo["received_at"])
        if photo["violation_count"]:
            summary = f"標示 {photo['violation_count']} 項待處理違規"
            if photo["pending_count"]:
                summary += f"（{photo['pending_count']} 項待覆核）"
        else:
            summary = "無異常"
        cells[3].text = summary


def collect_report_data(conn: sqlite3.Connection, site_id: int, work_date: str) -> dict:
    """彙整日報所需資料。Word 生成與線上預覽共用，確保兩者內容一致。"""
    site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if site is None:
        raise ValueError(f"地盤 id={site_id} 不存在")

    existing = conn.execute(
        "SELECT * FROM reports WHERE site_id = ? AND work_date = ?", (site_id, work_date)
    ).fetchone()

    return {
        "site": dict(site),
        "work_date": work_date,
        "summary": stats.site_daily(conn, site_id, work_date),
        "photos": review.list_photos(conn, site_id=site_id, work_date=work_date, limit=1000),
        "confirmed": review.confirmed_violations(conn, site_id, work_date),
        "pending": review.pending_violations(conn, site_id, work_date),
        "saved_report": dict(existing) if existing else None,
    }


def generate_daily_report(
    conn: sqlite3.Connection,
    site_id: int,
    work_date: str,
    generated_by: str = "",
) -> dict:
    data = collect_report_data(conn, site_id, work_date)
    site = data["site"]
    summary = data["summary"]
    photos = data["photos"]
    confirmed = data["confirmed"]
    pending = data["pending"]

    document = Document()
    _apply_cjk_font(document)

    title = document.add_heading("每日地盤安全及施工記錄報告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _key_value_table(
        document,
        [
            ("地盤", f"{site['name']}（{site['code']}）"),
            ("地址", site["address"] or "—"),
            ("工作日期", work_date),
            ("報告生成時間", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("生成人", generated_by or "系統自動生成"),
        ],
    )

    document.add_heading("一、當日概要", level=1)
    _key_value_table(
        document,
        [
            ("接收相片總數", f"{summary['photo_count']} 張"),
            ("重覆相片攔截", f"{summary['duplicates_blocked']} 張"),
            ("AI 標示違規", f"{summary['ai_flagged']} 項"),
            ("覆核確認違規", f"{summary['confirmed']} 項"),
            ("覆核判定誤報", f"{summary['rejected']} 項"),
            ("尚待覆核", f"{summary['pending_review']} 項"),
            ("覆核完成度", f"{summary['review_progress']}%"),
        ],
    )

    document.add_heading("二、覆核確認違規詳情", level=1)
    if confirmed:
        for index, item in enumerate(confirmed, start=1):
            _violation_block(document, item, index)
    else:
        document.add_paragraph("當日無經覆核確認的違規項目。")

    if pending:
        document.add_heading("三、尚待覆核項目", level=1)
        document.add_paragraph(
            "下列項目由 AI 標示但尚未經人手覆核，未計入確認違規，須於下一工作日完成覆核。"
        )
        for index, item in enumerate(pending, start=1):
            captured = _format_time(item["captured_at"] or item["received_at"])
            document.add_paragraph(
                f"{index}. {CATEGORY_LABELS.get(item['category'], item['category'])}"
                f" — {item['label']}（信心值 {item['confidence']:.2f}，"
                f"相片 {item['original_name']}，{captured}）",
                style="List Bullet",
            )

    document.add_heading("四、當日相片索引", level=1)
    if photos:
        _photo_index_table(document, photos)
    else:
        document.add_paragraph("當日未接收任何相片。")

    document.add_heading("五、覆核及簽署", level=1)
    _key_value_table(
        document,
        [("管工簽署", ""), ("安全主任簽署", ""), ("日期", "")],
    )

    note = document.add_paragraph(DISCLAIMER)
    note.runs[0].font.size = Pt(9)

    target_dir = config.REPORT_DIR / site["code"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{work_date}_{site['code']}_每日安全記錄報告.docx"
    document.save(target_path)

    relative = str(target_path.relative_to(config.DATA_DIR))
    conn.execute(
        "INSERT INTO reports (site_id, work_date, path, photo_count, violation_count,"
        " generated_at, generated_by) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(site_id, work_date) DO UPDATE SET"
        " path = excluded.path, photo_count = excluded.photo_count,"
        " violation_count = excluded.violation_count,"
        " generated_at = excluded.generated_at, generated_by = excluded.generated_by",
        (
            site_id,
            work_date,
            relative,
            summary["photo_count"],
            summary["confirmed"],
            now_iso(),
            generated_by,
        ),
    )
    row = conn.execute(
        "SELECT id FROM reports WHERE site_id = ? AND work_date = ?", (site_id, work_date)
    ).fetchone()

    return {
        "report_id": row["id"],
        "site_code": site["code"],
        "site_name": site["name"],
        "work_date": work_date,
        "path": relative,
        "photo_count": summary["photo_count"],
        "confirmed": summary["confirmed"],
        "pending_review": summary["pending_review"],
    }


_PREVIEW_CSS = """
:root { --border:#d8dee5; --muted:#6b7785; --danger:#c0392b; --warn:#b8730b; --ink:#1c2530; }
* { box-sizing:border-box; }
body { margin:0; background:#eef1f4; color:var(--ink); line-height:1.65;
       font-family:"Microsoft JhengHei","PingFang HK","Segoe UI",system-ui,sans-serif; }
.toolbar { position:sticky; top:0; z-index:5; display:flex; gap:10px; align-items:center;
           background:#12283d; color:#fff; padding:10px 20px; font-size:13px; }
.toolbar a, .toolbar button { font:inherit; padding:6px 13px; border-radius:6px; cursor:pointer;
           border:1px solid rgba(255,255,255,.25); background:rgba(255,255,255,.1);
           color:#fff; text-decoration:none; }
.toolbar a:hover, .toolbar button:hover { background:rgba(255,255,255,.2); }
.toolbar .spacer { flex:1; }
.sheet { max-width:820px; margin:22px auto; background:#fff; padding:42px 48px;
         box-shadow:0 2px 10px rgba(16,27,40,.1); }
h1 { text-align:center; font-size:23px; margin:0 0 26px; }
h2 { font-size:16px; margin:30px 0 12px; padding-bottom:6px; border-bottom:2px solid var(--ink); }
table { width:100%; border-collapse:collapse; margin-bottom:6px; }
th, td { border:1px solid var(--border); padding:7px 11px; text-align:left; vertical-align:top; }
th { background:#f5f7f9; font-weight:600; width:170px; }
table.index th { width:auto; }
table.index td.n { text-align:right; width:44px; }
.violation { border:1px solid var(--border); border-left:4px solid var(--danger);
             padding:14px 16px; margin-bottom:16px; page-break-inside:avoid; }
.violation h3 { margin:0 0 10px; font-size:15px; color:var(--danger); }
.violation img { display:block; max-width:100%; border:1px solid var(--border); margin-bottom:10px; }
.violation dl { display:grid; grid-template-columns:96px 1fr; gap:3px 12px; margin:0; font-size:13px; }
.violation dt { color:var(--muted); }
.violation dd { margin:0; }
ul.pending { margin:0; padding-left:22px; }
ul.pending li { margin-bottom:5px; }
.tag { display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; }
.tag.danger { background:#fbeae8; color:var(--danger); }
.tag.warn { background:#fdf3e2; color:var(--warn); }
.note { margin-top:26px; font-size:12px; color:var(--muted); border-top:1px solid var(--border);
        padding-top:12px; }
.empty { color:var(--muted); }
@media print {
  @page { size:A4; margin:16mm; }
  body { background:#fff; }
  .toolbar { display:none; }
  .sheet { max-width:none; margin:0; padding:0; box-shadow:none; }
}
"""


def _row(label: str, value: str) -> str:
    return f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"


def render_report_html(conn: sqlite3.Connection, site_id: int, work_date: str) -> str:
    """線上預覽。內容與 Word 報告一致，可直接列印或另存 PDF。"""
    data = collect_report_data(conn, site_id, work_date)
    site, summary = data["site"], data["summary"]
    saved = data["saved_report"]

    title = f"{site['name']}（{site['code']}） {work_date} 每日安全記錄報告"

    header_rows = "".join(
        [
            _row("地盤", f"{site['name']}（{site['code']}）"),
            _row("地址", site["address"] or "—"),
            _row("工作日期", work_date),
            _row(
                "報告狀態",
                f"已生成 Word 報告 · {_format_time(saved['generated_at'])}"
                if saved
                else "尚未生成 Word 報告（本頁為即時預覽）",
            ),
        ]
    )

    summary_rows = "".join(
        [
            _row("接收相片總數", f"{summary['photo_count']} 張"),
            _row("重覆相片攔截", f"{summary['duplicates_blocked']} 張"),
            _row("AI 標示違規", f"{summary['ai_flagged']} 項"),
            _row("覆核確認違規", f"{summary['confirmed']} 項"),
            _row("覆核判定誤報", f"{summary['rejected']} 項"),
            _row("尚待覆核", f"{summary['pending_review']} 項"),
            _row("覆核完成度", f"{summary['review_progress']}%"),
        ]
    )

    if data["confirmed"]:
        blocks = []
        for index, item in enumerate(data["confirmed"], start=1):
            details = [
                ("相片檔案", item["original_name"]),
                ("拍攝時間", _format_time(item["captured_at"] or item["received_at"])),
                ("AI 信心值", f"{item['confidence']:.2f}（偵測器：{item['detector']}）"),
                ("覆核", f"{item['reviewer']} 於 {_format_time(item['reviewed_at'])} 確認"),
            ]
            if item.get("note"):
                details.append(("覆核備註", item["note"]))
            dl = "".join(
                f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in details
            )
            category = CATEGORY_LABELS.get(item["category"], item["category"])
            blocks.append(
                f"<div class='violation'>"
                f"<h3>{index}. {escape(category)} — {escape(item['label'])}</h3>"
                f"<img src='/api/photos/{item['photo_id']}/file' alt='{escape(item['original_name'])}'>"
                f"<dl>{dl}</dl></div>"
            )
        confirmed_html = "".join(blocks)
    else:
        confirmed_html = "<p class='empty'>當日無經覆核確認的違規項目。</p>"

    if data["pending"]:
        items = "".join(
            "<li>{category} — {label}（信心值 {conf:.2f}，相片 {name}，{time}）</li>".format(
                category=escape(CATEGORY_LABELS.get(item["category"], item["category"])),
                label=escape(item["label"]),
                conf=item["confidence"],
                name=escape(item["original_name"]),
                time=_format_time(item["captured_at"] or item["received_at"]),
            )
            for item in data["pending"]
        )
        pending_html = (
            "<h2>三、尚待覆核項目</h2>"
            "<p>下列項目由 AI 標示但尚未經人手覆核，未計入確認違規，須於下一工作日完成覆核。</p>"
            f"<ul class='pending'>{items}</ul>"
        )
    else:
        pending_html = ""

    if data["photos"]:
        rows = []
        for i, photo in enumerate(data["photos"], start=1):
            if photo["violation_count"]:
                cls = "warn" if photo["pending_count"] else "danger"
                text = f"標示 {photo['violation_count']} 項"
                if photo["pending_count"]:
                    text += f"（{photo['pending_count']} 項待覆核）"
                result = f"<span class='tag {cls}'>{escape(text)}</span>"
            else:
                result = "無異常"
            rows.append(
                f"<tr><td class='n'>{i}</td>"
                f"<td>{escape(photo['original_name'])}</td>"
                f"<td>{_format_time(photo['captured_at'] or photo['received_at'])}</td>"
                f"<td>{result}</td></tr>"
            )
        index_html = (
            "<table class='index'><thead><tr><th class='n'>#</th><th>相片檔案</th>"
            "<th>拍攝時間</th><th>AI 篩查結果</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        index_html = "<p class='empty'>當日未接收任何相片。</p>"

    download = (
        f"<a href='/api/reports/{saved['id']}/download'>下載 .docx</a>"
        if saved
        else "<span style='opacity:.65'>尚未生成 .docx</span>"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{_PREVIEW_CSS}</style>
</head>
<body>
<div class="toolbar">
  <a href="/web/reports.html">← 返回報告列表</a>
  <span class="spacer"></span>
  {download}
  <button onclick="window.print()">列印 / 儲存 PDF</button>
</div>
<div class="sheet">
  <h1>每日地盤安全及施工記錄報告</h1>
  <table>{header_rows}</table>

  <h2>一、當日概要</h2>
  <table>{summary_rows}</table>

  <h2>二、覆核確認違規詳情</h2>
  {confirmed_html}

  {pending_html}

  <h2>{'四' if pending_html else '三'}、當日相片索引</h2>
  {index_html}

  <h2>{'五' if pending_html else '四'}、覆核及簽署</h2>
  <table>
    <tr><th>管工簽署</th><td style="height:44px"></td></tr>
    <tr><th>安全主任簽署</th><td style="height:44px"></td></tr>
    <tr><th>日期</th><td style="height:30px"></td></tr>
  </table>

  <p class="note">{escape(DISCLAIMER)}</p>
</div>
</body>
</html>"""


def list_reports(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT r.*, s.code AS site_code, s.name AS site_name FROM reports r"
        " JOIN sites s ON s.id = r.site_id"
        " ORDER BY r.work_date DESC, s.code LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
