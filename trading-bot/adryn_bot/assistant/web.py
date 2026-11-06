"""HTTP routes for the one-screen trading desk (served at /desk)."""

from __future__ import annotations

import hmac
import io
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .analysis import Account, all_signals, analyze, compute
from .backtest import backtest
from .crosscheck import cross_check, final_verdict, htf_trend
from .data import HIGHER_TF, WATCHLISTS, default_fetcher, load_csv
from .mentor import ai_mentor, rule_mentor
from .scanner import Fetcher, scan

log = logging.getLogger("adryn_bot")
PAGE = Path(__file__).with_name("page.html")
STYLE_PATTERN = "^(scalping|intraday|swing)$"
MAX_CHART_BARS = 3000


class Prefs(BaseModel):
    style: str = Field("intraday", pattern=STYLE_PATTERN)
    capital: float = Field(100_000, gt=0)
    risk_pct: float = Field(1.0, gt=0, le=10)
    max_alloc_pct: float = Field(100, gt=0, le=500)
    min_quality: int = Field(3, ge=1, le=5)
    whole_units: bool = True

    def account(self) -> Account:
        return Account(self.capital, self.risk_pct, self.max_alloc_pct,
                       whole_units=self.whole_units)


class DeskReq(Prefs):
    symbol: str = Field(min_length=1, max_length=40)


class ScanReq(Prefs):
    watchlist: str | None = None
    symbols: list[str] | None = Field(None, max_length=200)


def _ts(idx) -> list[int]:
    return [int(t.timestamp()) for t in pd.DatetimeIndex(idx)]


def _series(times: list[int], s: pd.Series) -> list[dict]:
    v = s.to_numpy(dtype=float)
    return [{"time": t, "value": round(float(x), 4)} for t, x in zip(times, v, strict=True)
            if np.isfinite(x)]


def chart_payload(df: pd.DataFrame, p: Prefs, bt: dict) -> dict:
    d = compute(df, p.style)
    sig = all_signals(d, p.min_quality)
    d, sig = d.iloc[-MAX_CHART_BARS:], sig.iloc[-MAX_CHART_BARS:]
    t = _ts(d.index)
    candles = [{"time": ti, "open": round(o, 4), "high": round(h, 4), "low": round(lo, 4),
                "close": round(c, 4)}
               for ti, o, h, lo, c in zip(t, d.open, d.high, d.low, d.close, strict=True)]
    volume = [{"time": ti, "value": float(v), "color": "#1fbf7555" if c >= o else "#f0506e55"}
              for ti, v, o, c in zip(t, d.volume, d.open, d.close, strict=True)]
    outcome = {r["time"]: r for r in bt.get("trade_log", [])}
    markers = []
    for ti, idx, dr, name, q in zip(t, d.index, sig["dir"], sig["setup"], sig["quality"], strict=True):
        if not dr:
            continue
        res = outcome.get(str(idx))
        tail = "" if res is None else (" ✓" if res["r"] > 0 else " ✗")
        markers.append({"time": ti, "position": "belowBar" if dr == 1 else "aboveBar",
                        "color": "#1fbf75" if dr == 1 else "#f0506e",
                        "shape": "arrowUp" if dr == 1 else "arrowDown",
                        "text": f"{'BUY' if dr == 1 else 'SELL'} Q{q}{tail}"})
    lines = {"ema_fast": _series(t, d.ema_fast), "ema_slow": _series(t, d.ema_slow),
             "ema_trend": _series(t, d.ema_trend)}
    if p.style != "swing":
        lines["vwap"] = _series(t, d.vwap)
    return {"candles": candles, "volume": volume, "lines": lines, "markers": markers}


def build_desk(df: pd.DataFrame, htf_df: pd.DataFrame | None, p: Prefs) -> dict:
    if len(df) < 60:
        raise HTTPException(422, "need at least 60 candles")
    t0 = time.perf_counter()
    a = analyze(df, p.style, p.account(), p.min_quality)
    bt = backtest(df, p.style, p.min_quality)
    a["backtest"] = {k: v for k, v in bt.items() if k not in {"trade_log", "recent"}}
    htf = htf_trend(htf_df)
    checks = cross_check(a, htf)
    verdict = final_verdict(a, checks)
    chart = chart_payload(df, p, bt)
    return {
        "analyst": a, "higher_tf": {"timeframe": HIGHER_TF[p.style], "trend": htf},
        "mentor": rule_mentor(a, htf, p.style), "checks": checks, "verdict": verdict,
        "chart": chart, "compute_ms": round(1000 * (time.perf_counter() - t0)),
    }


def create_router(passphrase: str, fetch: Fetcher | None = None, cache_seconds: int = 15) -> APIRouter:
    router = APIRouter()
    fetch = fetch or default_fetcher()
    cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
    last_desk: dict[str, dict] = {}

    def cached_fetch(sym: str, style: str) -> pd.DataFrame:
        key = (sym.upper(), style)
        ttl = cache_seconds if style in {"scalping", "intraday"} else cache_seconds * 20
        hit = cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        df = fetch(key[0], style)
        cache[key] = (time.time(), df)
        return df

    def auth(token: str | None) -> None:
        if not hmac.compare_digest((token or "").encode(), passphrase.encode()):
            raise HTTPException(401, "enter your bot passphrase in the settings bar")

    def htf_for(sym: str, style: str) -> pd.DataFrame | None:
        try:
            return cached_fetch(sym, HIGHER_TF[style])
        except Exception as exc:  # noqa: BLE001 - the cross-check marks it UNKNOWN instead
            log.info("higher timeframe for %s failed: %s", sym, exc)
            return None

    @router.get("/desk", response_class=HTMLResponse)
    @router.get("/assistant", response_class=HTMLResponse)
    def page() -> str:
        return PAGE.read_text(encoding="utf-8")

    @router.get("/api/watchlists")
    def watchlists(x_bot_passphrase: str | None = Header(None)) -> dict:
        auth(x_bot_passphrase)
        return WATCHLISTS

    @router.post("/api/desk")
    def desk(req: DeskReq, x_bot_passphrase: str | None = Header(None)) -> dict:
        auth(x_bot_passphrase)
        try:
            df = cached_fetch(req.symbol, req.style)
        except Exception as exc:
            raise HTTPException(502, f"data for {req.symbol}: {exc}") from exc
        out = {"symbol": req.symbol.upper(), **build_desk(df, htf_for(req.symbol, req.style), req)}
        last_desk[req.symbol.upper()] = out
        return out

    @router.post("/api/desk-csv")
    async def desk_csv(file: UploadFile = File(...), prefs: str = Form("{}"),
                       x_bot_passphrase: str | None = Header(None)) -> dict:
        auth(x_bot_passphrase)
        p = Prefs.model_validate(json.loads(prefs or "{}"))
        try:
            df = load_csv(io.BytesIO(await file.read()))
        except Exception as exc:
            raise HTTPException(422, f"could not read CSV: {exc}") from exc
        out = {"symbol": file.filename, **build_desk(df, None, p)}
        last_desk[str(file.filename).upper()] = out
        return out

    @router.post("/api/scan")
    def scan_list(req: ScanReq, x_bot_passphrase: str | None = Header(None)) -> dict:
        auth(x_bot_passphrase)
        symbols = req.symbols or WATCHLISTS.get(req.watchlist or "", [])
        if not symbols:
            raise HTTPException(422, "choose a watchlist or enter symbols")
        results = scan(symbols, cached_fetch, req.style, req.account(), req.min_quality)
        slim = [{k: r.get(k) for k in ("symbol", "price", "bias", "trend_score", "signal",
                                       "signal_bars_ago", "tags", "rank", "error")}
                for r in results]
        return {"count": len(slim), "results": slim}

    @router.post("/api/mentor-ai")
    async def mentor_ai(symbol: str = Form(...), question: str = Form(""),
                        image: UploadFile | None = File(None),
                        x_bot_passphrase: str | None = Header(None)) -> dict:
        auth(x_bot_passphrase)
        state = last_desk.get(symbol.upper())
        if not state:
            raise HTTPException(409, "analyse the symbol first")
        data, media = None, "image/png"
        if image is not None:
            data = await image.read()
            if len(data) > 5 * 1024 * 1024:
                raise HTTPException(413, "image larger than 5 MB")
            if image.content_type in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                media = image.content_type
        a = state["analyst"]
        context = {"symbol": state["symbol"], "style": a["style"], "price": a["price"],
                   "bias": a["bias"], "signal": a["signal"], "levels": a["levels"],
                   "indicators": a["indicators"], "higher_tf": state["higher_tf"],
                   "checks": state["checks"], "backtest": a.get("backtest")}
        try:
            ai = ai_mentor(context, data, media, question or None,
                           effort="low" if a["style"] == "scalping" else "medium")
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"AI request failed: {exc}") from exc
        return {"ai": ai, "verdict": final_verdict(a, state["checks"], ai)}

    return router
