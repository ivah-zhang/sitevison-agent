# -*- coding: utf-8 -*-
"""啟動開發伺服器：python run.py"""
from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="啟動地盤 AI 安全監測系統")
    parser.add_argument("--host", default=os.getenv("CITF_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="修改程式碼後自動重啟")
    args = parser.parse_args()

    print(f"儀表板：http://{args.host}:{args.port}/")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
