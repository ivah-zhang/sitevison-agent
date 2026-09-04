# -*- coding: utf-8 -*-
"""生成示範相片放入收件匣，讓系統可即時演示。

繪製的是示意圖而非真實工地相片：mock 偵測器不讀取影像內容，因此示範資料
只需在流程與界面上具代表性。切換至真實模型時請改用實際地盤相片。

用法：
    python seed_demo.py                 # 3 個地盤 × 2 天 × 12 張
    python seed_demo.py --days 3 --per-day 15
    python seed_demo.py --clean         # 先清空 data/ 再生成
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app import config
from app.db import DEFAULT_SITES, init_db, seed_sites

WIDTH, HEIGHT = 800, 600
SKY_TOP = (150, 185, 215)
SKY_BOTTOM = (216, 228, 238)
GROUND = (150, 143, 132)
HELMET_COLOURS = [(230, 170, 30), (215, 80, 55), (240, 240, 240)]

SCENES = ["外牆棚架", "樓面澆注", "機電安裝", "地基工程", "室內裝修", "物料吊運"]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("msyh.ttc", "msjh.ttc", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _draw_worker(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float, helmet: bool,
                 rng: random.Random) -> None:
    h = int(70 * scale)
    w = int(20 * scale)
    body_colour = rng.choice([(60, 90, 140), (200, 120, 40), (70, 110, 80)])
    draw.rectangle([x, y, x + w, y + h], fill=body_colour)
    draw.rectangle([x, y + h, x + w // 2 - 1, y + h + int(28 * scale)], fill=(50, 55, 65))
    draw.rectangle([x + w // 2 + 1, y + h, x + w, y + h + int(28 * scale)], fill=(50, 55, 65))

    head_r = int(11 * scale)
    cx = x + w // 2
    cy = y - head_r
    draw.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=(224, 190, 160))
    if helmet:
        colour = rng.choice(HELMET_COLOURS)
        draw.pieslice(
            [cx - head_r - 3, cy - head_r - 5, cx + head_r + 3, cy + head_r - 2],
            start=180, end=360, fill=colour,
        )
        draw.rectangle([cx - head_r - 5, cy - 2, cx + head_r + 5, cy + 2], fill=colour)

    # 反光背心橫紋
    draw.rectangle([x, y + int(h * 0.45), x + w, y + int(h * 0.55)], fill=(235, 235, 120))


def render_photo(path: Path, site_code: str, site_name: str, moment: datetime,
                 index: int, rng: random.Random) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=tuple(int(SKY_TOP[i] + (SKY_BOTTOM[i] - SKY_TOP[i]) * ratio) for i in range(3)),
        )

    horizon = int(HEIGHT * 0.68)
    draw.rectangle([0, horizon, WIDTH, HEIGHT], fill=GROUND)

    # 背景建築
    x = -20
    while x < WIDTH:
        bw = rng.randint(90, 190)
        bh = rng.randint(120, 300)
        shade = rng.randint(150, 185)
        draw.rectangle([x, horizon - bh, x + bw, horizon], fill=(shade, shade - 6, shade - 14))
        for row in range(horizon - bh + 18, horizon - 12, 34):
            for col in range(x + 12, x + bw - 14, 30):
                draw.rectangle([col, row, col + 16, row + 20], fill=(shade - 32, shade - 28, shade - 22))
        x += bw + rng.randint(8, 26)

    # 棚架
    sx, sw = rng.randint(40, 300), rng.randint(220, 380)
    for col in range(sx, sx + sw, 46):
        draw.line([(col, horizon), (col, horizon - 250)], fill=(120, 110, 96), width=4)
    for row in range(horizon - 250, horizon, 52):
        draw.line([(sx, row), (sx + sw, row)], fill=(132, 122, 104), width=4)

    # 工人
    worker_count = rng.randint(1, 4)
    for _ in range(worker_count):
        wx = rng.randint(60, WIDTH - 120)
        scale = rng.uniform(0.85, 1.5)
        wy = horizon - int(70 * scale) - rng.randint(0, 40)
        _draw_worker(draw, wx, wy, scale, helmet=rng.random() > 0.2, rng=rng)

    # 相片說明條
    draw.rectangle([0, HEIGHT - 42, WIDTH, HEIGHT], fill=(18, 40, 61))
    label = f"{site_code} {site_name} | {SCENES[index % len(SCENES)]} | {moment:%Y-%m-%d %H:%M}"
    draw.text((14, HEIGHT - 31), label, font=_font(17), fill=(235, 241, 247))
    draw.text((WIDTH - 96, HEIGHT - 31), f"#{index:03d}", font=_font(17), fill=(160, 185, 210))

    image.save(path, "JPEG", quality=88)
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成示範相片")
    parser.add_argument("--days", type=int, default=2, help="生成最近多少天的資料")
    parser.add_argument("--per-day", type=int, default=12, help="每個地盤每天相片數")
    parser.add_argument("--clean", action="store_true", help="先清空 data/ 目錄")
    parser.add_argument("--seed", type=int, default=20260903)
    args = parser.parse_args()

    if args.clean and config.DATA_DIR.exists():
        shutil.rmtree(config.DATA_DIR)
        print(f"已清空 {config.DATA_DIR}")

    config.ensure_dirs()
    init_db()
    created = seed_sites()
    print(f"地盤：新增 {created} 個，共 {len(DEFAULT_SITES)} 個")

    rng = random.Random(args.seed)
    total = 0
    for site_code, site_name, _address in DEFAULT_SITES:
        inbox = config.INBOX_DIR / site_code
        inbox.mkdir(parents=True, exist_ok=True)
        generated: list[Path] = []

        for day_offset in range(args.days):
            work_day = date.today() - timedelta(days=day_offset)
            for i in range(args.per_day):
                moment = datetime.combine(
                    work_day, time(8, 0)
                ) + timedelta(minutes=rng.randint(0, 9 * 60))
                filename = f"IMG-{work_day:%Y%m%d}-{site_code}-{i:03d}.jpg"
                path = inbox / filename
                render_photo(path, site_code, site_name, moment, i, rng)
                generated.append(path)
                total += 1

        print(f"  {site_code} {site_name}：{len(generated)} 張")

    print(f"\n共生成 {total} 張示範相片，位於 {config.INBOX_DIR}")
    print("下一步：python run.py 啟動服務後，於儀表板按「掃描收件匣」")


if __name__ == "__main__":
    main()
