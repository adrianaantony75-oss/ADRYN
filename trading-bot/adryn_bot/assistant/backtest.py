"""Honest historical check of the signal engine: which level is hit first after each signal."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from .analysis import STYLES, Account, all_signals, compute, make_plan


def backtest(df: pd.DataFrame, style: str = "intraday", min_quality: int = 3,
             max_hold: int = 50, acct: Account | None = None) -> dict:
    """Simulate: 1/3 off at TP1 (stop then moves to entry), 1/3 at TP2, 1/3 at TP3.

    Conservative: if SL and a target are inside the same candle, the stop is assumed first.
    Results are in R (multiples of the risk per trade). Fees and slippage are not included.
    """
    acct = acct or Account(whole_units=False)
    d = compute(df, style)
    sig = all_signals(d, min_quality)
    sdir, ssetup, squal = sig["dir"].to_numpy(), sig["setup"].to_numpy(), sig["quality"].to_numpy()
    warmup = max(STYLES[style][2], 60)
    trades = []
    i = warmup
    while i < len(d) - 1:
        direction, setup, q = int(sdir[i]), str(ssetup[i]), int(squal[i])
        if not direction:
            i += 1
            continue
        p = make_plan(d, i, direction, setup, q, acct, style)
        risk = abs(p.entry - p.stop_loss)
        if risk <= 0:
            i += 1
            continue
        stop, hit, result, exit_i = p.stop_loss, 0, 0.0, None
        targets = [p.tp1, p.tp2, p.tp3]
        rs = [abs(t - p.entry) / risk for t in targets]
        for j in range(i + 1, min(i + 1 + max_hold, len(d))):
            hi, lo = d["high"].iat[j], d["low"].iat[j]
            stopped = lo <= stop if direction == 1 else hi >= stop
            if stopped:
                remaining = (3 - hit) / 3
                result += remaining * ((stop - p.entry) * direction / risk)
                exit_i = j
                break
            while hit < 3 and (hi >= targets[hit] if direction == 1 else lo <= targets[hit]):
                result += rs[hit] / 3
                hit += 1
                stop = p.entry if hit == 1 else targets[hit - 2]
            if hit == 3:
                exit_i = j
                break
        if exit_i is None:  # timed out: close remainder at last close
            exit_i = min(i + max_hold, len(d) - 1)
            result += (3 - hit) / 3 * ((d["close"].iat[exit_i] - p.entry) * direction / risk)
        trades.append({"time": str(d.index[i]), "dir": p.direction, "setup": setup, "quality": q,
                       "tp_hits": hit, "r": round(result, 3)})
        i = exit_i + 1

    return {"trades": len(trades), **_stats(trades), "by_setup": _by_setup(trades),
            "recent": trades[-10:], "trade_log": trades}


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"win_rate_tp1": None, "avg_r": None, "total_r": 0.0, "profit_factor": None}
    wins = [t for t in trades if t["tp_hits"] >= 1]
    gains = sum(t["r"] for t in trades if t["r"] > 0)
    losses = -sum(t["r"] for t in trades if t["r"] < 0)
    total = sum(t["r"] for t in trades)
    return {
        "win_rate_tp1": round(100 * len(wins) / len(trades), 1),
        "avg_r": round(total / len(trades), 3),
        "total_r": round(total, 2),
        "profit_factor": round(gains / losses, 2) if losses else None,
    }


def _by_setup(trades: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[t["setup"]].append(t)
    return {k: {"trades": len(v), **_stats(v)} for k, v in groups.items()}
