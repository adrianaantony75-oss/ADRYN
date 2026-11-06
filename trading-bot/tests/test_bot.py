from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from adryn_bot.brokers import PaperExecutor
from adryn_bot.config import Settings, _load_dotenv
from adryn_bot.engine import Engine
from adryn_bot.risk import position_size
from adryn_bot.server import create_app

PASS = "test-secret"


@pytest.fixture
def setup(tmp_path):
    settings = Settings(passphrase=PASS, state_file=tmp_path / "state.json",
                        max_trades_per_day=3, min_score=3)
    engine = Engine(settings, PaperExecutor())
    return settings, engine, TestClient(create_app(settings, engine))


def alert(action="buy", symbol="BTCUSDT", price=100.0, **kw):
    return {"passphrase": PASS, "action": action, "symbol": symbol, "price": price,
            "stop_loss": kw.pop("sl", 0), "take_profit": kw.pop("tp", 0), "score": 5, **kw}


def post(client, body):
    # TradingView posts as text/plain
    return client.post("/webhook", content=json.dumps(body),
                       headers={"Content-Type": "text/plain"})


def test_rejects_bad_passphrase(setup):
    _, _, c = setup
    r = post(c, {**alert(), "passphrase": "nope"})
    assert r.status_code == 401


def test_rejects_non_json(setup):
    _, _, c = setup
    r = c.post("/webhook", content="BTCUSDT buy", headers={"Content-Type": "text/plain"})
    assert r.status_code == 400


def test_open_and_close_long_with_pnl(setup):
    _, engine, c = setup
    r = post(c, alert("buy", price=100, sl=95, tp=110))
    assert r.json()["status"] == "ok"
    pos = engine.ledger.positions["BTCUSDT"]
    # 1% of 10k = 100 risk / 5 per unit = 20 units, cap 25% = 25 units -> 20
    assert pos.qty == pytest.approx(20)
    r = post(c, alert("close", price=105))
    assert r.json()["events"][0]["pnl"] == pytest.approx(100)
    assert engine.ledger.cash == pytest.approx(10_100)
    assert "BTCUSDT" not in engine.ledger.positions


def test_reverse_and_duplicate(setup):
    _, engine, c = setup
    post(c, alert("buy", price=100, sl=95))
    assert post(c, alert("buy", price=101)).json()["status"] == "ignored"
    r = post(c, alert("sell", price=90, sl=95)).json()
    kinds = [e["kind"] for e in r["events"]]
    assert kinds == ["close", "open"]
    assert engine.ledger.positions["BTCUSDT"].qty < 0


def test_stop_loss_hit_on_next_alert(setup):
    _, _, c = setup
    post(c, alert("buy", price=100, sl=95, tp=120))
    r = post(c, alert("sell", price=94, sl=99)).json()
    assert r["events"][0]["reason"] == "stop_loss"
    assert r["events"][0]["pnl"] == pytest.approx(-100)


def test_min_score_and_daily_limit(setup):
    _, _, c = setup
    assert post(c, {**alert(), "score": 1}).json()["status"] == "rejected"
    for sym in ["A", "B", "C"]:
        assert post(c, alert(symbol=sym)).json()["status"] == "ok"
    r = post(c, alert(symbol="D")).json()
    assert r["status"] == "rejected" and "limit" in r["reason"]


def test_halt_blocks_new_trades_but_allows_close(setup):
    _, _, c = setup
    post(c, alert("buy", symbol="ETHUSDT"))
    assert c.post("/halt", json={"passphrase": PASS}).json()["halted"] is True
    assert post(c, alert(symbol="SOLUSDT")).json()["status"] == "rejected"
    assert post(c, alert("close", symbol="ETHUSDT")).json()["status"] == "ok"


def test_state_persists(setup):
    settings, _, c = setup
    post(c, alert("buy", price=100, sl=90))
    reloaded = Engine(settings, PaperExecutor())
    assert "BTCUSDT" in reloaded.ledger.positions


def test_dashboard_and_status(setup):
    _, _, c = setup
    post(c, alert("buy"))
    assert "ADRYN Trading Bot" in c.get("/").text
    s = c.get("/status").json()
    assert s["positions"][0]["symbol"] == "BTCUSDT"
    assert "passphrase" not in json.dumps(s["recent_alerts"])


def test_position_size_cap():
    s = Settings(risk_per_trade=0.5, max_position_pct=0.1)
    assert position_size(s, 10_000, 100, 99) == pytest.approx(10)


def test_dotenv_inline_comments(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("X_A=abc   # note\nX_B=   # empty\nX_C=\"a # b\"\n")
    for k in ("X_A", "X_B", "X_C"):
        monkeypatch.delenv(k, raising=False)
    _load_dotenv(f)
    import os
    assert (os.environ["X_A"], os.environ["X_B"], os.environ["X_C"]) == ("abc", "", "a # b")
