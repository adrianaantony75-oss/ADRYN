"""Market data: FYERS API (live, India), Yahoo Finance (free, delayed) or your own CSV files."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

# Timeframe keys -> (Yahoo interval, Yahoo period, FYERS resolution, days of history).
# Yahoo limits intraday history to 60 days; FYERS allows up to 100 days per minute request.
TIMEFRAMES = {
    "scalping": ("5m", "60d", "5", 90),
    "intraday": ("15m", "60d", "15", 90),
    "h1": ("60m", "2y", "60", 300),
    "swing": ("1d", "5y", "D", 365 * 5),
    "weekly": ("1wk", "10y", "1W", 365 * 10),
}
STYLE_DATA = {k: v[:2] for k, v in TIMEFRAMES.items()}
# Higher timeframe used by the cross-checker to confirm the trade direction.
HIGHER_TF = {"scalping": "intraday", "intraday": "h1", "swing": "weekly"}

WATCHLISTS: dict[str, list[str]] = {
    "NIFTY 50": [
        "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS", "BHARTIARTL.NS",
        "ITC.NS", "SBIN.NS", "LT.NS", "HINDUNILVR.NS", "KOTAKBANK.NS", "AXISBANK.NS",
        "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", "HCLTECH.NS", "M&M.NS", "TITAN.NS",
        "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS", "ASIANPAINT.NS", "NESTLEIND.NS", "ONGC.NS",
        "JSWSTEEL.NS", "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
        "BAJAJFINSV.NS", "WIPRO.NS", "TECHM.NS", "GRASIM.NS", "HDFCLIFE.NS", "SBILIFE.NS",
        "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BRITANNIA.NS",
        "APOLLOHOSP.NS", "BAJAJ-AUTO.NS", "INDUSINDBK.NS", "SHRIRAMFIN.NS", "TRENT.NS",
        "BEL.NS", "HINDALCO.NS", "ETERNAL.NS", "JIOFIN.NS",
    ],
    "Indices": ["^NSEI", "^NSEBANK", "^GSPC", "^NDX"],
    "US large caps": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V",
        "AMD", "NFLX", "COST", "LLY", "UNH",
    ],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1) if df.columns.nlevels > 1 else df
    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    return df


def fetch_yahoo(symbol: str, style: str = "intraday") -> pd.DataFrame:
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Live data needs `pip install yfinance`") from exc
    interval, period = STYLE_DATA[style]
    df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=False,
                     threads=False)
    if df is None or df.empty:
        raise ValueError(f"no data for {symbol}")
    return _normalise(df)


def load_csv(path: str | Path) -> pd.DataFrame:
    """CSV with a time column first (or 'date'/'time'/'datetime') and OHLCV columns."""
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    tcol = next((c for c in ("datetime", "date", "time", "timestamp") if c in df.columns), df.columns[0])
    df = df.set_index(tcol)
    return _normalise(df)


def to_fyers_symbol(symbol: str) -> str:
    """RELIANCE.NS -> NSE:RELIANCE-EQ, ^NSEI -> NSE:NIFTY50-INDEX; FYERS symbols pass through."""
    s = symbol.strip().upper()
    if ":" in s:
        return s
    special = {"^NSEI": "NSE:NIFTY50-INDEX", "^NSEBANK": "NSE:NIFTYBANK-INDEX",
               "^BSESN": "BSE:SENSEX-INDEX"}
    if s in special:
        return special[s]
    if s.endswith(".NS"):
        return f"NSE:{s[:-3]}-EQ"
    if s.endswith(".BO"):
        return f"BSE:{s[:-3]}-A"
    return f"NSE:{s}-EQ"


def fetch_fyers(symbol: str, style: str = "intraday") -> pd.DataFrame:
    """Candles from the FYERS API v3 history endpoint.

    Needs FYERS_APP_ID (e.g. ABCD1234-100) and FYERS_ACCESS_TOKEN (generated daily by the
    FYERS login flow) in the environment / .env.
    """
    app_id, token = os.getenv("FYERS_APP_ID", ""), os.getenv("FYERS_ACCESS_TOKEN", "")
    if not app_id or not token:
        raise RuntimeError("set FYERS_APP_ID and FYERS_ACCESS_TOKEN for FYERS data")
    _, _, resolution, days = TIMEFRAMES[style]
    chunk = 100 if resolution not in {"D", "1W"} else 366
    end = int(time.time())
    start = end - days * 86400
    frames = []
    while start < end:
        stop = min(start + chunk * 86400, end)
        q = urllib.parse.urlencode({"symbol": to_fyers_symbol(symbol), "resolution": resolution,
                                    "date_format": 0, "range_from": start, "range_to": stop,
                                    "cont_flag": 1})
        req = urllib.request.Request(f"https://api-t1.fyers.in/data/history?{q}",
                                     headers={"Authorization": f"{app_id}:{token}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
        if body.get("s") != "ok":
            raise ValueError(f"FYERS: {body.get('message', body)}")
        if body.get("candles"):
            frames.append(pd.DataFrame(body["candles"],
                                       columns=["t", "open", "high", "low", "close", "volume"]))
        start = stop + 1
    if not frames:
        raise ValueError(f"no FYERS data for {symbol}")
    df = pd.concat(frames).drop_duplicates("t")
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True).tz_convert("Asia/Kolkata")
    return _normalise(df)


def default_fetcher():
    """FYERS when credentials are configured, else Yahoo (BOT_DATA_SOURCE overrides)."""
    src = os.getenv("BOT_DATA_SOURCE", "").lower()
    if src == "fyers" or (not src and os.getenv("FYERS_ACCESS_TOKEN")):
        return fetch_fyers
    return fetch_yahoo
