"""FastAPI webhook server that TradingView alerts post to."""

from __future__ import annotations

import hmac
import html
import json
import logging
from collections import deque
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from .brokers import build_executor
from .config import Settings
from .engine import Engine
from .models import Signal
from .notify import notify

log = logging.getLogger("adryn_bot")


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or Engine(settings, build_executor(settings))
    alerts: deque[dict] = deque(maxlen=50)
    app = FastAPI(title="ADRYN Trading Bot", version="0.1.0")
    try:
        from .assistant.web import create_router

        app.include_router(create_router(settings.passphrase))
    except ImportError as exc:  # pandas/numpy not installed: webhook bot still works
        log.warning("trading desk disabled (%s); pip install pandas numpy", exc)

    if settings.passphrase == "change-me":
        log.warning("BOT_PASSPHRASE is the default 'change-me' — set your own before going live")

    def _auth(passphrase: str) -> None:
        if not hmac.compare_digest(passphrase.encode(), settings.passphrase.encode()):
            raise HTTPException(status_code=401, detail="bad passphrase")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.mode, "halted": engine.ledger.halted}

    @app.post("/webhook")
    async def webhook(request: Request) -> dict:
        # TradingView sends text/plain unless the message parses as JSON, so read raw bytes.
        raw = (await request.body()).decode("utf-8", errors="replace").strip()
        entry = {"time": datetime.now(UTC).isoformat(timespec="seconds"), "status": "invalid"}
        alerts.appendleft(entry)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError("payload must be a JSON object")
        except (ValueError, TypeError) as exc:
            entry["detail"] = "body is not a JSON object"
            raise HTTPException(status_code=400, detail="body must be a JSON object") from exc
        entry["payload"] = {k: v for k, v in data.items() if k != "passphrase"}
        _auth(str(data.get("passphrase", "")))
        try:
            sig = Signal.model_validate(data)
        except ValidationError as exc:
            entry["detail"] = "schema error"
            raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc

        result = engine.handle(sig)
        entry["status"] = result["status"]
        entry["detail"] = result.get("reason", "")
        log.info("signal %s %s @ %s -> %s", sig.action, sig.symbol, sig.price, result["status"])
        for evt in result.get("events", []):
            if evt and "kind" in evt:
                pnl = f" pnl={evt['pnl']}" if "pnl" in evt else ""
                notify(settings, f"ADRYN {evt['kind']} {evt['symbol']} qty={evt['qty']} "
                                 f"@ {evt['price']}{pnl}")
        return result

    @app.get("/status")
    def status() -> dict:
        return {**engine.snapshot(), "recent_alerts": list(alerts)}

    @app.post("/halt")
    async def halt(request: Request) -> dict:
        body = await request.json()
        _auth(str(body.get("passphrase", "")))
        engine.set_halted(bool(body.get("halted", True)))
        return {"halted": engine.ledger.halted}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        snap = engine.snapshot()
        esc = html.escape

        def rows(items: list[dict], cols: list[str]) -> str:
            if not items:
                return f"<tr><td colspan={len(cols)}><em>none yet</em></td></tr>"
            return "".join(
                "<tr>" + "".join(f"<td>{esc(str(i.get(c, '')))}</td>" for c in cols) + "</tr>"
                for i in items
            )

        def table(title: str, items: list[dict], cols: list[str]) -> str:
            head = "".join(f"<th>{c}</th>" for c in cols)
            return f"<h2>{title}</h2><table><tr>{head}</tr>{rows(items, cols)}</table>"

        alert_rows = [{"time": a["time"], "status": a["status"], "detail": a.get("detail", ""),
                       "payload": json.dumps(a.get("payload", {}))} for a in alerts]
        return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=10><title>ADRYN Trading Bot</title>
<style>body{{font:14px system-ui;margin:16px;background:#0f1115;color:#e6e6e6}}
table{{border-collapse:collapse;width:100%;margin-bottom:16px;display:block;overflow-x:auto}}
td,th{{border:1px solid #333;padding:4px 8px;text-align:left;white-space:nowrap}}
.k{{display:inline-block;margin:0 16px 8px 0}}.k b{{display:block;font-size:20px}}</style></head>
<body><h1>ADRYN Trading Bot</h1>
<div class=k>Mode<b>{esc(snap['mode'])}</b></div>
<div class=k>Status<b>{'HALTED' if snap['halted'] else 'running'}</b></div>
<div class=k>Cash<b>{snap['cash']:,.2f}</b></div>
<div class=k>Day P&amp;L<b>{snap['day_pnl']:,.2f}</b></div>
<div class=k>Trades today<b>{snap['trades_today']}</b></div>
{table("Open positions", snap["positions"],
       ["symbol", "qty", "entry", "stop_loss", "take_profit", "opened_at"])}
{table("TradingView alerts received", alert_rows, ["time", "status", "detail", "payload"])}
{table("Trades", list(reversed(snap["recent_trades"])),
       ["time", "kind", "symbol", "qty", "price", "pnl", "reason"])}
<p>Auto-refreshes every 10 s. Webhook URL: <code>POST /webhook</code></p></body></html>"""

    return app
