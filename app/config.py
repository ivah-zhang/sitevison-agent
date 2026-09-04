# -*- coding: utf-8 -*-
"""集中設定。所有設定均可用環境變數覆寫，方便由 mock 切換至真實模型。"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("CITF_DATA_DIR", BASE_DIR / "data"))
INBOX_DIR = DATA_DIR / "inbox"
PHOTO_DIR = DATA_DIR / "photos"
REPORT_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "citf.db"
WEB_DIR = BASE_DIR / "web"

# 偵測器：mock（預設，不需模型）或 vlm（需 API 金鑰）
DETECTOR = os.getenv("CITF_DETECTOR", "mock")

# 接入相片後是否立即執行偵測
AUTO_DETECT = os.getenv("CITF_AUTO_DETECT", "1") == "1"

# 線上演示環境：資料庫為空時自動生成並接入示範相片
DEMO_SEED = os.getenv("CITF_DEMO_SEED", "0") == "1"

# 低於此信心值的偵測結果不寫入資料庫
CONFIDENCE_THRESHOLD = float(os.getenv("CITF_CONFIDENCE_THRESHOLD", "0.35"))

# 視覺語言模型（VLM）設定 — 僅在 DETECTOR=vlm 時使用
VLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
VLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
VLM_MODEL = os.getenv("CITF_VLM_MODEL", "gpt-4o-mini")
VLM_TIMEOUT = float(os.getenv("CITF_VLM_TIMEOUT", "60"))

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# 報告內嵌相片的最長邊（像素）
REPORT_IMAGE_MAX_PX = 900


def ensure_dirs() -> None:
    for d in (DATA_DIR, INBOX_DIR, PHOTO_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
