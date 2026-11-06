from __future__ import annotations

from datetime import datetime

import pandas as pd

from adryn_bot import autotrader as at
from adryn_bot.autotrader import IST, AutoSettings, AutoTrader, FyersOrders, closed_candles


def frame(rows, start="2026-11-09 09:15", freq="15min"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz=IST)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


def test_closed_candles_drops_forming_bar():
    df = frame([[1, 1, 1, 1, 1]] * 3)  # bars at 09:15, 09:30, 09:45
    assert len(closed_candles(df, "intraday", datetime(2026, 11, 9, 9, 50, tzinfo=IST))) == 2
    assert len(closed_candles(df, "intraday", datetime(2026, 11, 9, 10, 0, tzinfo=IST))) == 3


def test_order_body():
    b = FyersOrders.order_body("SBIN.NS", 10, -1, "sl-m", "INTRADAY", stop=801.234)
    assert b["symbol"] == "NSE:SBIN-EQ" and b["type"] == 3 and b["side"] == -1
    assert b["stopPrice"] == 801.23 and b["qty"] == 10


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_paper_trade_hits_target_and_respects_limits(tmp_path, monkeypatch):
    plan = {"direction": "BUY", "qty": 10, "entry": 100.0, "stop_loss": 98.0, "target": 104.0,
            "setup": "Breakout", "confidence": 90}
    calls = {"n": 0}

    def fake_plan(df, htf, s):
        calls["n"] += 1
        return plan

    monkeypatch.setattr(at, "a_plus_plan", fake_plan)
    bars = [[100, 100.5, 99.5, 100, 1000]] * 260
    data = {"df": frame(bars)}
    s = AutoSettings(symbols=["SBIN.NS"], max_trades_per_day=1, state_file=tmp_path / "a.json")
    clock = Clock(datetime(2026, 11, 9, 10, 1, tzinfo=IST))  # Monday
    trader = AutoTrader(s, fetch=lambda sym, style: data["df"], clock=clock)

    ev = trader.step()
    assert any(e.startswith("ENTER BUY SBIN.NS x10") for e in ev)
    # next bar runs to the target
    data["df"] = pd.concat([data["df"], frame([[100, 104.5, 99.9, 104, 1000]],
                                              start="2026-11-09 10:15")])
    clock.t = datetime(2026, 11, 9, 10, 31, tzinfo=IST)
    ev = trader.step()
    assert any("EXIT SBIN.NS target" in e for e in ev)
    assert trader.day_pnl == 40.0
    trader.step()  # daily trade limit reached: no new entry
    assert trader.trades_today == 1 and not trader.open


def test_square_off(tmp_path, monkeypatch):
    monkeypatch.setattr(at, "a_plus_plan", lambda *a: {
        "direction": "SELL", "qty": 5, "entry": 100.0, "stop_loss": 103.0, "target": 94.0,
        "setup": "Breakdown", "confidence": 90})
    df = frame([[100, 100.5, 99.5, 100, 1000]] * 260)
    s = AutoSettings(symbols=["X.NS"], state_file=tmp_path / "a.json")
    clock = Clock(datetime(2026, 11, 9, 14, 0, tzinfo=IST))
    trader = AutoTrader(s, fetch=lambda sym, style: df, clock=clock)
    trader.step()
    assert "X.NS" in trader.open
    clock.t = datetime(2026, 11, 9, 15, 11, tzinfo=IST)
    ev = trader.step()
    assert any("square-off" in e for e in ev) and not trader.open
