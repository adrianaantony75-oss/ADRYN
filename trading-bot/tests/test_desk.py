from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from adryn_bot.assistant.analysis import Account, all_signals, analyze, compute, signal_at
from adryn_bot.assistant.backtest import backtest
from adryn_bot.assistant.crosscheck import cross_check, final_verdict, htf_trend
from adryn_bot.assistant.data import to_fyers_symbol
from adryn_bot.brokers import PaperExecutor
from adryn_bot.config import Settings
from adryn_bot.engine import Engine
from adryn_bot.server import create_app

PASS = "desk-secret"


def candles(n=600, seed=1, freq="15min", drift=0.0004):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.006, n)))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0, 0.004, n)) * close
    idx = pd.date_range("2026-01-05 09:15", periods=n, freq=freq)
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + spread,
                         "low": np.minimum(open_, close) - spread, "close": close,
                         "volume": rng.integers(1_000, 5_000, n).astype(float)}, index=idx)


def test_vectorised_signals_match_single_bar():
    d = compute(candles(), "intraday")
    sig = all_signals(d, 3)
    for i in range(200, len(d)):
        direction, setup, q = signal_at(d, i, 3)
        assert (direction, setup, q) == (sig["dir"].iat[i], sig["setup"].iat[i], sig["quality"].iat[i])


def test_analyze_plan_levels_are_consistent():
    df = candles()
    a = analyze(df, "intraday", Account(capital=50_000, risk_pct=1), lookback_signal=len(df) - 250)
    s = a["signal"]
    assert s is not None
    if s["direction"] == "BUY":
        assert s["stop_loss"] < s["entry"] < s["tp1"] < s["tp2"] < s["tp3"]
    else:
        assert s["stop_loss"] > s["entry"] > s["tp1"] > s["tp2"] > s["tp3"]
    assert s["risk_amount"] <= 50_000 * 0.01 + 1e-6
    assert isinstance(s["qty"], int)


def test_backtest_runs_and_reports():
    bt = backtest(candles(1500, seed=3), "intraday")
    assert bt["trades"] > 0
    assert 0 <= bt["win_rate_tp1"] <= 100


def test_crosscheck_and_verdict():
    df = candles()
    a = analyze(df, "intraday", lookback_signal=len(df) - 250)
    a["backtest"] = backtest(df, "intraday")
    checks = cross_check(a, htf_trend(candles(300, freq="1h")))
    assert checks and all({"name", "passed", "critical", "detail"} <= c.keys() for c in checks)
    v = final_verdict(a, checks)
    assert v["action"] and 0 <= v["confidence"] <= 100
    ai_no = final_verdict(a, checks, {"action": "WAIT", "comment": "x"})
    assert ai_no["confidence"] <= v["confidence"]
    assert final_verdict({"signal": None, "watch": ["w"]}, [])["action"] == "NO TRADE"


def test_fyers_symbol_mapping():
    assert to_fyers_symbol("RELIANCE.NS") == "NSE:RELIANCE-EQ"
    assert to_fyers_symbol("^NSEI") == "NSE:NIFTY50-INDEX"
    assert to_fyers_symbol("NSE:SBIN-EQ") == "NSE:SBIN-EQ"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from adryn_bot.assistant import web

    data = {"intraday": candles(), "h1": candles(300, seed=2, freq="1h")}
    monkeypatch.setattr(web, "default_fetcher", lambda: lambda sym, style: data[style])
    settings = Settings(passphrase=PASS, state_file=tmp_path / "s.json")
    return TestClient(create_app(settings, Engine(settings, PaperExecutor())))


def test_desk_endpoint(client):
    assert client.post("/api/desk", json={"symbol": "X"}).status_code == 401
    r = client.post("/api/desk", json={"symbol": "TEST.NS"}, headers={"X-Bot-Passphrase": PASS})
    assert r.status_code == 200, r.text
    j = r.json()
    assert {"analyst", "mentor", "checks", "verdict", "chart", "higher_tf"} <= j.keys()
    assert len(j["chart"]["candles"]) == 600
    assert client.get("/desk").status_code == 200


def test_scan_endpoint(client):
    r = client.post("/api/scan", json={"symbols": ["A.NS", "B.NS"]},
                    headers={"X-Bot-Passphrase": PASS})
    assert r.status_code == 200 and r.json()["count"] == 2
