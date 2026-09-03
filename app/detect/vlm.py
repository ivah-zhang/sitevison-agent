# -*- coding: utf-8 -*-
"""開放詞彙視覺語言模型（VLM）偵測器。

透過 OpenAI 相容的 chat completions 介面提交相片，要求模型以固定 JSON
結構回覆。新增違規類別只需在 CATEGORY_PROMPTS 增加一條文字描述，毋須
重新訓練模型 — 這正是申請書所述「以文字指令起步、少量標註微調」的做法。

啟用方式（PowerShell）：
    $env:CITF_DETECTOR = "vlm"
    $env:OPENAI_API_KEY = "sk-..."
    $env:OPENAI_BASE_URL = "https://api.openai.com/v1"
    $env:CITF_VLM_MODEL = "gpt-4o-mini"
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

import httpx

from .. import config
from ..models import CATEGORY_HARDHAT, CATEGORY_SMOKING, DetectionResult

CATEGORY_PROMPTS = {
    CATEGORY_HARDHAT: "每一位可見工人是否正確佩戴安全帽",
    CATEGORY_SMOKING: "畫面中是否有人吸煙或手持點燃香煙",
}

SYSTEM_PROMPT = (
    "你是建造業地盤安全檢查助理。分析相片並嚴格以 JSON 物件回覆，"
    "不要加入任何說明文字或 markdown 標記。"
)

USER_PROMPT = """請檢查這張香港地盤相片，判斷以下項目：
{checks}

以此 JSON 結構回覆：
{{"detections": [
  {{"category": "ppe_hardhat 或 smoking",
    "label": "簡短中文描述，例如「未佩戴安全帽」",
    "is_violation": true 或 false,
    "confidence": 0 至 1 之間的數字,
    "bbox": [x1, y1, x2, y2] 正規化座標，無法判斷時為 null}}
]}}

若相片中沒有工人或無法判斷，回覆 {{"detections": []}}。
寧可標示為疑似違規交由人手覆核，也不要漏報。"""


def _encode_image(image_path: Path) -> str:
    mime = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _parse_bbox(raw) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return tuple(float(v) for v in raw)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


class VLMDetector:
    name = "vlm"

    def __init__(self) -> None:
        if not config.VLM_API_KEY:
            raise RuntimeError(
                "未設定 OPENAI_API_KEY，無法使用 VLM 偵測器。"
                "請設定金鑰，或將 CITF_DETECTOR 設回 mock。"
            )
        self.model = config.VLM_MODEL
        self.name = f"vlm:{config.VLM_MODEL}"

    def analyse(self, image_path: Path) -> list[DetectionResult]:
        checks = "\n".join(f"- {desc}" for desc in CATEGORY_PROMPTS.values())
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT.format(checks=checks)},
                        {
                            "type": "image_url",
                            "image_url": {"url": _encode_image(image_path)},
                        },
                    ],
                },
            ],
        }

        response = httpx.post(
            f"{config.VLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.VLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.VLM_TIMEOUT,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"模型回覆非有效 JSON：{content[:200]}") from exc

        results: list[DetectionResult] = []
        for item in payload.get("detections", []):
            category = str(item.get("category", "")).strip()
            if category not in CATEGORY_PROMPTS:
                continue
            results.append(
                DetectionResult(
                    category=category,
                    label=str(item.get("label") or category),
                    is_violation=bool(item.get("is_violation")),
                    confidence=float(item.get("confidence") or 0.0),
                    bbox=_parse_bbox(item.get("bbox")),
                    note=self.name,
                )
            )
        return results
