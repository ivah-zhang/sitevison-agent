# -*- coding: utf-8 -*-
"""偵測器介面。

所有偵測器輸入一張相片、輸出一組 DetectionResult。系統其餘部分只依賴此
介面，因此由 mock 換成真實視覺語言模型（VLM）時不需改動接入、覆核、
報告及儀表板任何一環。
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import DetectionResult


@runtime_checkable
class Detector(Protocol):
    name: str

    def analyse(self, image_path: Path) -> list[DetectionResult]:
        """回傳該相片的偵測結果；無所見時回傳空清單。"""
        ...


def get_detector(name: str | None = None) -> Detector:
    from .. import config

    key = (name or config.DETECTOR).lower()
    if key == "mock":
        from .mock import MockDetector

        return MockDetector()
    if key == "vlm":
        from .vlm import VLMDetector

        return VLMDetector()
    raise ValueError(f"未知偵測器：{key}（可用：mock、vlm）")
