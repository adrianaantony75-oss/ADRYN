"""Signal engine mirroring pine/adryn_pro_assistant.pine, plus a plain-English trade plan."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import indicators as ind

STYLES = {
    #            fast slow trend range swing st_mult atr_stop
    "scalping": (9, 21, 50, 15, 3, 2.0, 1.0),
    "intraday": (21, 50, 200, 20, 5, 3.0, 1.5),
    "swing": (21, 50, 200, 55, 5, 3.0, 2.0),
}


@dataclass
class Account:
    capital: float = 100_000.0
    risk_pct: float = 1.0
    max_alloc_pct: float = 100.0
    tp_r: tuple[float, float, float] = (1.0, 2.0, 3.0)
    whole_units: bool = True  # stocks trade in whole shares; set False for crypto


def compute(df: pd.DataFrame, style: str = "intraday") -> pd.DataFrame:
    """Add indicator, setup and quality columns. Needs >= ~60 bars; 250+ recommended."""
    fast, slow, trend, rng, swing, st_mult, _ = STYLES[style]
    d = df.copy()
    c = d["close"]
    d["atr"] = ind.atr(d)
    d["ema_fast"], d["ema_slow"], d["ema_trend"] = ind.ema(c, fast), ind.ema(c, slow), ind.ema(c, trend)
    d["rsi"] = ind.rsi(c)
    d["adx"] = ind.adx(d)
    d["st_line"], d["st_dir"] = ind.supertrend(d, st_mult, 10)
    d["vwap"] = ind.vwap(d)
    vol_avg = d["volume"].rolling(20).mean()
    d["vol_ratio"] = (d["volume"] / vol_avg.replace(0, np.nan)).fillna(1.0)
    d["range_high"] = d["high"].rolling(rng).max().shift()
    d["range_low"] = d["low"].rolling(rng).min().shift()
    d["swing_low"] = d["low"].rolling(swing * 2).min()
    d["swing_high"] = d["high"].rolling(swing * 2).max()
    d["resistance"] = ind.pivots(d["high"], swing, swing, True).ffill()
    d["support"] = ind.pivots(d["low"], swing, swing, False).ffill()

    up = (c > d["ema_trend"]) & (d["ema_fast"] > d["ema_slow"]) & (d["st_dir"] < 0)
    down = (c < d["ema_trend"]) & (d["ema_fast"] < d["ema_slow"]) & (d["st_dir"] > 0)
    d["up_trend"], d["down_trend"] = up, down
    green, red = c > d["open"], c < d["open"]
    rh, rl = d["range_high"], d["range_low"]

    d["pull_long"] = up & (d["low"] <= d["ema_fast"]) & (c > d["ema_fast"]) & green & d["rsi"].between(45, 70)
    d["pull_short"] = down & (d["high"] >= d["ema_fast"]) & (c < d["ema_fast"]) & red & d["rsi"].between(30, 55)
    d["bo_long"] = (c > rh) & (c.shift() <= rh.shift()) & (d["vol_ratio"] > 1.5) & (c > d["ema_slow"])
    d["bo_short"] = (c < rl) & (c.shift() >= rl.shift()) & (d["vol_ratio"] > 1.5) & (c < d["ema_slow"])
    broke_up = (d["high"].shift() > rh.shift()) | (d["high"].shift(2) > rh.shift(2))
    broke_dn = (d["low"].shift() < rl.shift()) | (d["low"].shift(2) < rl.shift(2))
    d["fake_short"] = broke_up & (c < rh) & red & (c < c.shift())
    d["fake_long"] = broke_dn & (c > rl) & green & (c > c.shift())
    intraday = _is_intraday(d)
    vw_up = (c > d["vwap"]) & (c.shift() <= d["vwap"].shift())
    vw_dn = (c < d["vwap"]) & (c.shift() >= d["vwap"].shift())
    d["vw_long"] = intraday & vw_up & (c > d["ema_fast"]) & (d["vol_ratio"] > 1.2) & (d["rsi"] > 50)
    d["vw_short"] = intraday & vw_dn & (c < d["ema_fast"]) & (d["vol_ratio"] > 1.2) & (d["rsi"] < 50)

    vol_ok = (d["vol_ratio"] > 1.2).astype(int)
    adx_ok = (d["adx"] > 20).astype(int)
    d["q_long"] = ((c > d["ema_trend"]).astype(int) + (d["st_dir"] < 0).astype(int) + adx_ok
                   + vol_ok + d["rsi"].between(50, 70, inclusive="neither").astype(int))
    d["q_short"] = ((c < d["ema_trend"]).astype(int) + (d["st_dir"] > 0).astype(int) + adx_ok
                    + vol_ok + d["rsi"].between(30, 50, inclusive="neither").astype(int))
    rngbar = (d["high"] - d["low"]).replace(0, np.nan)
    d["q_fake_long"] = 2 + vol_ok + (d["rsi"] < 40).astype(int) + ((c - d["low"]) > rngbar * 0.6).astype(int)
    d["q_fake_short"] = 2 + vol_ok + (d["rsi"] > 60).astype(int) + ((d["high"] - c) > rngbar * 0.6).astype(int)
    return d


def _is_intraday(d: pd.DataFrame) -> bool:
    if not isinstance(d.index, pd.DatetimeIndex) or len(d) < 3:
        return False
    return bool(pd.Series(d.index).diff().median() < pd.Timedelta(days=1))


def signal_at(d: pd.DataFrame, i: int, min_quality: int = 3) -> tuple[int, str, int]:
    """(direction, setup name, quality) for bar i; direction 0 = no signal."""
    r = d.iloc[i]
    long_raw = [("Breakout", r.bo_long), ("VWAP reclaim", r.vw_long), ("Trend pullback", r.pull_long)]
    short_raw = [("Breakdown", r.bo_short), ("VWAP reject", r.vw_short), ("Trend pullback", r.pull_short)]
    for name, hit in long_raw:
        if hit and r.q_long >= min_quality:
            return 1, name, int(r.q_long)
    for name, hit in short_raw:
        if hit and r.q_short >= min_quality:
            return -1, name, int(r.q_short)
    if r.fake_long and r.q_fake_long >= min_quality:
        return 1, "Fakeout reversal (bear trap)", int(r.q_fake_long)
    if r.fake_short and r.q_fake_short >= min_quality:
        return -1, "Fakeout reversal (bull trap)", int(r.q_fake_short)
    return 0, "", 0


def all_signals(d: pd.DataFrame, min_quality: int = 3) -> pd.DataFrame:
    """Vectorised signal_at for every bar: columns dir (1/-1/0), setup, quality."""
    ql, qs = d["q_long"], d["q_short"]
    conds = [
        d.bo_long & (ql >= min_quality), d.vw_long & (ql >= min_quality),
        d.pull_long & (ql >= min_quality), d.bo_short & (qs >= min_quality),
        d.vw_short & (qs >= min_quality), d.pull_short & (qs >= min_quality),
        d.fake_long & (d.q_fake_long >= min_quality), d.fake_short & (d.q_fake_short >= min_quality),
    ]
    names = ["Breakout", "VWAP reclaim", "Trend pullback", "Breakdown", "VWAP reject",
             "Trend pullback", "Fakeout reversal (bear trap)", "Fakeout reversal (bull trap)"]
    dirs = [1, 1, 1, -1, -1, -1, 1, -1]
    quals = [ql, ql, ql, qs, qs, qs, d.q_fake_long, d.q_fake_short]
    c = [x.fillna(False).astype(bool).to_numpy() for x in conds]
    return pd.DataFrame({
        "dir": np.select(c, dirs, 0),
        "setup": np.select(c, names, ""),
        "quality": np.select(c, [q.to_numpy() for q in quals], 0).astype(int),
    }, index=d.index)


@dataclass
class Plan:
    direction: str
    setup: str
    quality: int
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    qty: float
    risk_amount: float
    capital_used: float
    reward_tp2: float


def make_plan(d: pd.DataFrame, i: int, direction: int, setup: str, quality: int,
              acct: Account, style: str) -> Plan:
    r = d.iloc[i]
    atr_stop = STYLES[style][6]
    entry = float(r.close)
    if direction == 1:
        sl = min(max(r.swing_low - r.atr * 0.1, entry - r.atr * atr_stop), entry - r.atr * 0.5)
    else:
        sl = max(min(r.swing_high + r.atr * 0.1, entry + r.atr * atr_stop), entry + r.atr * 0.5)
    risk_unit = abs(entry - sl)
    tps = [entry + direction * risk_unit * m for m in acct.tp_r]
    qty = acct.capital * acct.risk_pct / 100 / risk_unit if risk_unit > 0 else 0.0
    qty = min(qty, acct.capital * acct.max_alloc_pct / 100 / entry)
    qty = math.floor(qty) if acct.whole_units else round(qty, 4)
    return Plan(
        direction="BUY" if direction == 1 else "SELL", setup=setup, quality=quality,
        entry=round(entry, 4), stop_loss=round(float(sl), 4),
        tp1=round(tps[0], 4), tp2=round(tps[1], 4), tp3=round(tps[2], 4),
        qty=qty, risk_amount=round(qty * risk_unit, 2), capital_used=round(qty * entry, 2),
        reward_tp2=round(qty * risk_unit * acct.tp_r[1], 2),
    )


def analyze(df: pd.DataFrame, style: str = "intraday", acct: Account | None = None,
            min_quality: int = 3, lookback_signal: int = 3) -> dict:
    """Full read of the chart: bias, latest setup + plan, key levels and if-then guidance."""
    acct = acct or Account()
    d = compute(df, style)
    last = d.iloc[-1]
    price = float(last.close)

    plan, sig_age = None, None
    for back in range(lookback_signal):
        i = len(d) - 1 - back
        direction, setup, q = signal_at(d, i, min_quality)
        if direction:
            plan = make_plan(d, i, direction, setup, q, acct, style)
            sig_age = back
            break

    bias = "BULLISH" if last.up_trend else "BEARISH" if last.down_trend else "SIDEWAYS"
    score = _trend_score(last)
    res, sup = _f(last.resistance), _f(last.support)
    rh, rl = _f(last.range_high), _f(last.range_low)
    a = float(last.atr)

    notes = [
        (f"Price {price:.2f} is {'above' if price > last.ema_trend else 'below'} the "
        f"{STYLES[style][2]} EMA (long-term trend)."),
        (f"Supertrend is {'UP' if last.st_dir < 0 else 'DOWN'}; ADX {last.adx:.0f} = "
        f"{'trending' if last.adx > 25 else 'weak trend' if last.adx > 18 else 'choppy, avoid'}."),
        (f"RSI {last.rsi:.0f} ({'overbought' if last.rsi > 70 else 'oversold' if last.rsi < 30 else 'neutral zone'}); "
        f"volume {last.vol_ratio:.1f}x average."),
    ]
    watch = []
    if rh:
        watch.append(f"BUY breakout only if a candle CLOSES above {rh:.2f} with volume > 1.5x average. "
                     f"Wick above then close back below = fakeout, do not chase.")
    if rl:
        watch.append(f"SELL breakdown only if a candle CLOSES below {rl:.2f} with volume. "
                     f"Quick reclaim back above = bear trap (possible buy).")
    if bias == "BULLISH":
        watch.append(f"In this uptrend, best buy zone is a pullback to {last.ema_fast:.2f} "
                     f"(fast EMA) holding above {last.ema_slow:.2f}.")
    elif bias == "BEARISH":
        watch.append(f"In this downtrend, best sell zone is a bounce into {last.ema_fast:.2f} "
                     f"failing below {last.ema_slow:.2f}.")
    else:
        watch.append("Sideways market: trade only clean breakouts of the range, or stay out.")

    return {
        "price": round(price, 4),
        "time": str(d.index[-1]),
        "style": style,
        "bias": bias,
        "trend_score": score,
        "signal": asdict(plan) if plan else None,
        "signal_bars_ago": sig_age,
        "levels": {
            "resistance": res, "support": sup, "range_high": rh, "range_low": rl,
            "ema_fast": round(float(last.ema_fast), 4), "ema_slow": round(float(last.ema_slow), 4),
            "ema_trend": round(float(last.ema_trend), 4), "vwap": round(float(last.vwap), 4),
            "atr": round(a, 4),
        },
        "indicators": {"rsi": round(float(last.rsi), 1), "adx": round(float(last.adx), 1),
                       "volume_ratio": round(float(last.vol_ratio), 2),
                       "supertrend": "UP" if last.st_dir < 0 else "DOWN"},
        "notes": notes,
        "watch": watch,
        "tags": _tags(d),
    }


def _f(v) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 4)


def _trend_score(r) -> int:
    """-100 (strong down) .. +100 (strong up)."""
    s = 0
    s += 25 if r.close > r.ema_trend else -25
    s += 20 if r.ema_fast > r.ema_slow else -20
    s += 20 if r.st_dir < 0 else -20
    s += 15 if r.rsi > 55 else -15 if r.rsi < 45 else 0
    s = s * (1.25 if r.adx > 25 else 1.0 if r.adx > 18 else 0.6)
    return int(max(-100, min(100, s)))


def _tags(d: pd.DataFrame) -> list[str]:
    tail = d.iloc[-3:]
    tags = []
    if tail.bo_long.any():
        tags.append("breakout")
    if tail.bo_short.any():
        tags.append("breakdown")
    if tail.fake_long.any() or tail.fake_short.any():
        tags.append("fakeout")
    if tail.pull_long.any() or tail.pull_short.any():
        tags.append("pullback")
    last = d.iloc[-1]
    if last.up_trend and last.adx > 25:
        tags.append("strong uptrend")
    if last.down_trend and last.adx > 25:
        tags.append("strong downtrend")
    if last.vol_ratio > 2:
        tags.append("volume spike")
    if last.range_high and last.close < last.range_high and (last.range_high - last.close) < last.atr * 0.5:
        tags.append("near resistance")
    if last.range_low and last.close > last.range_low and (last.close - last.range_low) < last.atr * 0.5:
        tags.append("near support")
    return tags
