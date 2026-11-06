"""Desk sections 4 and 5: independent cross-check of the signal, then the final verdict."""

from __future__ import annotations

import pandas as pd

from . import indicators as ind


def htf_trend(df: pd.DataFrame) -> str:
    """UP / DOWN / SIDEWAYS on the higher timeframe (close vs EMA50, EMA21 vs EMA50)."""
    if df is None or len(df) < 60:
        return "UNKNOWN"
    c = df["close"]
    e21, e50 = ind.ema(c, 21).iat[-1], ind.ema(c, 50).iat[-1]
    if c.iat[-1] > e50 and e21 > e50:
        return "UP"
    if c.iat[-1] < e50 and e21 < e50:
        return "DOWN"
    return "SIDEWAYS"


def cross_check(a: dict, htf: str) -> list[dict]:
    """Each check: name, passed (True/False/None = not applicable), critical, detail."""
    s = a.get("signal")
    if not s:
        return []
    buy = s["direction"] == "BUY"
    lv, ix = a["levels"], a["indicators"]
    risk = abs(s["entry"] - s["stop_loss"]) or 1e-9
    fake = s["setup"].startswith("Fakeout")
    checks = []

    def add(name, passed, critical, detail):
        passed = None if passed is None else bool(passed)
        checks.append({"name": name, "passed": passed, "critical": critical, "detail": detail})

    want = "UP" if buy else "DOWN"
    add("Higher-timeframe trend agrees", None if htf == "UNKNOWN" else htf == want or fake,
        not fake, f"Higher timeframe is {htf}; trade is {s['direction']}"
        + (" (fakeouts trade against the break, so this is relaxed)" if fake else ""))

    block = lv.get("resistance") if buy else lv.get("support")
    if block and ((buy and block > s["entry"]) or (not buy and block < s["entry"])):
        room = abs(block - s["entry"]) / risk
        add("Room to the next level", room >= 1.0, True,
            f"Next {'resistance' if buy else 'support'} {block} is {room:.1f}R away (need >= 1R)")
    else:
        add("Room to the next level", True, True, "No opposing pivot level in the way")

    add("Volume confirms", ix["volume_ratio"] >= 1.2, False,
        f"Volume is {ix['volume_ratio']}x the 20-bar average (want >= 1.2x)")
    add("Market is trending, not chop", ix["adx"] > 18 or fake, False, f"ADX {ix['adx']}")
    rsi = ix["rsi"]
    add("Not chasing an extreme", rsi < 75 if buy else rsi > 25, False,
        f"RSI {rsi} ({'overbought' if rsi >= 75 else 'oversold' if rsi <= 25 else 'ok'})")
    add("Signal is fresh", (a.get("signal_bars_ago") or 0) <= 1, False,
        f"Signal printed {a.get('signal_bars_ago') or 0} bar(s) ago")
    bt = (a.get("backtest") or {}).get("by_setup", {}).get(s["setup"])
    if bt and bt["trades"] >= 10:
        add("Setup has a historical edge here", bt["avg_r"] > 0, False,
            f"{bt['trades']} past trades: TP1 hit {bt['win_rate_tp1']}%, avg {bt['avg_r']}R")
    else:
        n = bt["trades"] if bt else 0
        add("Setup has a historical edge here", None, False,
            f"Only {n} past trades of this setup on this symbol: not enough to judge")
    return checks


def final_verdict(a: dict, checks: list[dict], ai: dict | None = None) -> dict:
    s = a.get("signal")
    if not s:
        return {"action": "NO TRADE", "confidence": 0, "size": "none",
                "headline": "No valid setup. Wait for one of the watch levels to trigger.",
                "reasons": a.get("watch", [])[:3]}
    scored = [c for c in checks if c["passed"] is not None]
    passed = sum(c["passed"] for c in scored)
    crit_fail = [c for c in scored if c["critical"] and not c["passed"]]
    conf = round(100 * passed / len(scored)) if scored else 50
    conf = min(conf, 20 * s["quality"] + 10)
    reasons = [c["detail"] for c in checks if c["passed"] is False]
    if ai and ai.get("action") and ai["action"] != s["direction"]:
        conf -= 25
        reasons.append(f"AI mentor disagrees: {ai.get('comment', '')}".strip())
    if crit_fail or conf < 45:
        action, size = "SKIP", "none"
        headline = f"Skip this {s['direction']}: " + (crit_fail[0]["detail"] if crit_fail else "too few confirmations")
    elif conf < 70:
        action, size = f"{s['direction']} (half size)", "half"
        headline = f"{s['direction']} allowed with half quantity ({s['qty'] // 2 if isinstance(s['qty'], int) else round(s['qty'] / 2, 4)})."
    else:
        action, size = s["direction"], "full"
        headline = f"{s['direction']} {s['qty']} at {s['entry']}, SL {s['stop_loss']}, TP1 {s['tp1']} / TP2 {s['tp2']} / TP3 {s['tp3']}."
    return {"action": action, "confidence": max(0, conf), "size": size, "headline": headline,
            "reasons": reasons or ["All checks passed."]}
