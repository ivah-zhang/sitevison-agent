# -*- coding: utf-8 -*-
"""模擬偵測器。

不讀取影像內容，而是以檔案 SHA-256 作為亂數種子產生結果，因此同一張相片
每次偵測結果完全一致，覆核流程與報告才有可測試性。僅供搭建及演示流程，
準確度數字不具意義。
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from ..models import CATEGORY_HARDHAT, CATEGORY_SMOKING, DetectionResult

# 各類別的模擬違規發生率
HARDHAT_VIOLATION_RATE = 0.18
SMOKING_RATE = 0.07


def _seed_from_file(image_path: Path) -> int:
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    return int(digest[:16], 16)


def _bbox(rng: random.Random) -> tuple[float, float, float, float]:
    x1 = rng.uniform(0.02, 0.70)
    y1 = rng.uniform(0.02, 0.60)
    x2 = min(1.0, x1 + rng.uniform(0.12, 0.28))
    y2 = min(1.0, y1 + rng.uniform(0.20, 0.38))
    return (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))


class MockDetector:
    name = "mock"

    def analyse(self, image_path: Path) -> list[DetectionResult]:
        rng = random.Random(_seed_from_file(image_path))
        results: list[DetectionResult] = []

        worker_count = rng.choices([0, 1, 2, 3, 4, 5], weights=[5, 25, 30, 20, 12, 8])[0]
        for _ in range(worker_count):
            violation = rng.random() < HARDHAT_VIOLATION_RATE
            results.append(
                DetectionResult(
                    category=CATEGORY_HARDHAT,
                    label="未佩戴安全帽" if violation else "已佩戴安全帽",
                    is_violation=violation,
                    confidence=round(
                        rng.uniform(0.55, 0.94) if violation else rng.uniform(0.72, 0.99), 3
                    ),
                    bbox=_bbox(rng),
                    note="模擬結果",
                )
            )

        if worker_count and rng.random() < SMOKING_RATE:
            results.append(
                DetectionResult(
                    category=CATEGORY_SMOKING,
                    label="疑似吸煙",
                    is_violation=True,
                    confidence=round(rng.uniform(0.48, 0.88), 3),
                    bbox=_bbox(rng),
                    note="模擬結果",
                )
            )

        return results
