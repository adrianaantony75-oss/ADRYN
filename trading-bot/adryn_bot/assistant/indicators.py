"""Technical indicators on an OHLCV DataFrame (columns: open, high, low, close, volume)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (what TradingView uses for RSI/ATR/ADX)."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = rma(delta.clip(lower=0), n)
    down = rma(-delta.clip(upper=0), n)
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(down.notna(), 50.0)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(plus_dm, n) / tr
    minus_di = 100 * rma(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx.fillna(0), n)


def supertrend(df: pd.DataFrame, mult: float = 3.0, n: int = 10) -> tuple[pd.Series, pd.Series]:
    """Returns (line, direction) with direction -1 = uptrend, +1 = downtrend (TradingView style)."""
    a = atr(df, n).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    close = df["close"].to_numpy()
    upper = hl2 + mult * a
    lower = hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    direction = np.ones(len(df))
    line = np.full(len(df), np.nan)
    for i in range(1, len(df)):
        fl[i] = lower[i] if lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1] else fl[i - 1]
        fu[i] = upper[i] if upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1] else fu[i - 1]
        if np.isnan(a[i - 1]):
            direction[i] = 1
        elif line[i - 1] == fu[i - 1]:
            direction[i] = -1 if close[i] > fu[i] else 1
        else:
            direction[i] = 1 if close[i] < fl[i] else -1
        line[i] = fl[i] if direction[i] == -1 else fu[i]
    return pd.Series(line, index=df.index), pd.Series(direction, index=df.index)


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP, reset each calendar day (only meaningful on intraday data)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = tp * df["volume"]
    day = pd.Series(df.index.date if isinstance(df.index, pd.DatetimeIndex) else 0, index=df.index)
    vol = df["volume"].groupby(day).cumsum().replace(0, np.nan)
    return (pv.groupby(day).cumsum() / vol).fillna(tp)


def pivots(series: pd.Series, left: int, right: int, high: bool) -> pd.Series:
    """Confirmed pivot values placed on the bar where they become known (no look-ahead)."""
    win = left + right + 1
    roll = series.rolling(win).max() if high else series.rolling(win).min()
    centre = series.shift(right)
    is_pivot = centre == roll
    return centre.where(is_pivot)
