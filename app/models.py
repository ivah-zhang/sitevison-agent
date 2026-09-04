# -*- coding: utf-8 -*-
"""偵測類別定義與跨模組共用的資料結構。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# 偵測類別。新增違規類別時只需在此登記，再於偵測器加上對應提示詞。
CATEGORY_HARDHAT = "ppe_hardhat"
CATEGORY_SMOKING = "smoking"

CATEGORY_LABELS = {
    CATEGORY_HARDHAT: "安全帽（PPE）",
    CATEGORY_SMOKING: "吸煙違規",
}

DECISION_CONFIRMED = "confirmed"  # 覆核確認屬實
DECISION_REJECTED = "rejected"    # 覆核判定為誤報

DECISION_LABELS = {
    DECISION_CONFIRMED: "確認違規",
    DECISION_REJECTED: "誤報",
}


@dataclass
class DetectionResult:
    """偵測器輸出的單項結果，與偵測器實作方式無關。"""

    category: str
    label: str
    is_violation: bool
    confidence: float
    bbox: Optional[tuple[float, float, float, float]] = None  # 正規化 xyxy
    note: str = ""

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)


@dataclass
class IngestOutcome:
    """單一檔案接入結果。"""

    status: str  # added | skipped | error
    path: str
    photo_id: Optional[int] = None
    reason: str = ""


@dataclass
class IngestSummary:
    added: int = 0
    skipped: int = 0
    error: int = 0
    items: list[IngestOutcome] = field(default_factory=list)

    def record(self, outcome: IngestOutcome) -> None:
        setattr(self, outcome.status, getattr(self, outcome.status) + 1)
        self.items.append(outcome)
