"""Watchlist scanner: ranks symbols by trend strength, fresh setups and breakout/fakeout tags."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .analysis import Account, analyze

log = logging.getLogger("adryn_bot")

Fetcher = Callable[[str, str], pd.DataFrame]


def rank_value(a: dict) -> float:
    """Higher = more actionable. Fresh high-quality signals first, then strong trends."""
    v = abs(a["trend_score"])
    if a["signal"]:
        v += 100 + 20 * a["signal"]["quality"] - 10 * (a["signal_bars_ago"] or 0)
    v += 15 * sum(t in a["tags"] for t in ("breakout", "breakdown", "fakeout", "volume spike"))
    return v


def scan(symbols: Iterable[str], fetch: Fetcher, style: str = "intraday",
         acct: Account | None = None, min_quality: int = 3, workers: int = 8) -> list[dict]:
    acct = acct or Account()

    def one(sym: str) -> dict | None:
        try:
            df = fetch(sym, style)
            if len(df) < 60:
                return None
            a = analyze(df, style, acct, min_quality)
            a["symbol"] = sym
            a["rank"] = round(rank_value(a), 1)
            return a
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the scan
            log.info("scan %s failed: %s", sym, exc)
            return {"symbol": sym, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for r in pool.map(one, symbols) if r]
    ok = sorted((r for r in results if "error" not in r), key=lambda r: -r["rank"])
    return ok + [r for r in results if "error" in r]
