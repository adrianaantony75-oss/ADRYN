"""Pretend to be TradingView: post a test alert to your running bot.

    python send_test_alert.py buy BTCUSDT 65000 --url http://localhost:8080/webhook
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

p = argparse.ArgumentParser()
p.add_argument("action", choices=["buy", "sell", "close"])
p.add_argument("symbol")
p.add_argument("price", type=float)
p.add_argument("--sl", type=float, default=0)
p.add_argument("--tp", type=float, default=0)
p.add_argument("--url", default="http://localhost:8080/webhook")
p.add_argument("--passphrase", default=os.getenv("BOT_PASSPHRASE", "change-me"))
a = p.parse_args()

body = {"passphrase": a.passphrase, "action": a.action, "symbol": a.symbol, "price": a.price,
        "stop_loss": a.sl, "take_profit": a.tp, "score": 5, "strategy": "manual_test"}
req = urllib.request.Request(a.url, json.dumps(body).encode(), {"Content-Type": "text/plain"})
with urllib.request.urlopen(req, timeout=10) as resp:
    print(resp.status, resp.read().decode())
