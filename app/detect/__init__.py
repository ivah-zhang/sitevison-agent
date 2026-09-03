# -*- coding: utf-8 -*-
"""偵測層：對外只暴露 Detector 介面與 get_detector 工廠。"""
from .base import Detector, get_detector

__all__ = ["Detector", "get_detector"]
