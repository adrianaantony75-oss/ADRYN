"""Run with: python -m adryn_bot  (or: python -m adryn_bot --port 80)"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="ADRYN TradingView webhook bot")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
