"""FYERS auto-trader: takes only A+ signals with a fixed risk:reward, paper mode by default.

Run:  python -m adryn_bot.autotrader            (reads .env)

A+ means: quality 5/5, the signal printed on the last CLOSED candle, every cross-check that
can be judged passed (higher-timeframe trend, room to target, volume, ADX, RSI, historical
edge) and the final verdict is a full-size trade. Most days that is zero to a few trades.

Live order flow (AUTO_MODE=live): market entry -> stop-loss (SL-M) + target (limit) orders;
when one exits, the bot cancels the other. Open positions are squared off at AUTO_SQUAREOFF.
Paper mode simulates the same thing on candle highs/lows and sends nothing to FYERS.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .assistant.analysis import Account, analyze
from .assistant.backtest import backtest
from .assistant.crosscheck import cross_check, final_verdict, htf_trend
from .assistant.data import HIGHER_TF, fetch_fyers, to_fyers_symbol
from .config import _bool, _load_dotenv

log = logging.getLogger("adryn_bot.auto")
IST = ZoneInfo("Asia/Kolkata")
BAR_MINUTES = {"scalping": 5, "intraday": 15}


@dataclass
class AutoSettings:
    mode: str = "paper"  # paper | live
    symbols: list[str] = field(default_factory=lambda: ["RELIANCE.NS", "HDFCBANK.NS", "SBIN.NS"])
    style: str = "intraday"  # scalping | intraday
    rr: float = 2.0  # target = rr x risk (2.0 = 1:2, 3.0 = 1:3)
    capital: float = 100_000.0
    risk_pct: float = 0.5
    max_trades_per_day: int = 3
    max_daily_loss: float = 1_500.0
    product: str = "INTRADAY"
    start: str = "09:30"  # skip the opening volatility
    last_entry: str = "14:45"
    squareoff: str = "15:10"
    allow_short: bool = True
    state_file: Path = Path("auto_state.json")

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> AutoSettings:
        if env_file:
            _load_dotenv(Path(env_file))
        g = os.getenv
        syms = [s.strip() for s in g("AUTO_SYMBOLS", "").split(",") if s.strip()]
        return cls(
            mode=g("AUTO_MODE", "paper").lower(),
            symbols=syms or cls().symbols,
            style=g("AUTO_STYLE", "intraday").lower(),
            rr=float(g("AUTO_RR", "2")),
            capital=float(g("AUTO_CAPITAL", "100000")),
            risk_pct=float(g("AUTO_RISK_PCT", "0.5")),
            max_trades_per_day=int(g("AUTO_MAX_TRADES", "3")),
            max_daily_loss=float(g("AUTO_MAX_DAILY_LOSS", "1500")),
            product=g("AUTO_PRODUCT", "INTRADAY"),
            start=g("AUTO_START", "09:30"),
            last_entry=g("AUTO_LAST_ENTRY", "14:45"),
            squareoff=g("AUTO_SQUAREOFF", "15:10"),
            allow_short=_bool("AUTO_ALLOW_SHORT", True),
            state_file=Path(g("AUTO_STATE_FILE", "auto_state.json")),
        )


# ───────── A+ filter ─────────
def a_plus_plan(df: pd.DataFrame, htf_df: pd.DataFrame | None, s: AutoSettings) -> dict | None:
    """Return the trade plan if the last closed candle is an A+ signal, else None."""
    acct = Account(s.capital, s.risk_pct, 100.0, tp_r=(1.0, s.rr, s.rr), whole_units=True)
    a = analyze(df, s.style, acct, min_quality=5, lookback_signal=1)
    sig = a.get("signal")
    if not sig or sig["qty"] < 1:
        return None
    if sig["direction"] == "SELL" and not s.allow_short:
        return None
    a["backtest"] = backtest(df, s.style, min_quality=5)
    checks = cross_check(a, htf_trend(htf_df))
    verdict = final_verdict(a, checks)
    if verdict["size"] != "full" or any(c["passed"] is False for c in checks):
        log.info("signal %s %s rejected: %s", sig["direction"], sig["setup"], verdict["reasons"])
        return None
    return {**sig, "target": sig["tp2"], "confidence": verdict["confidence"],
            "checks": [c["name"] for c in checks if c["passed"]]}


def closed_candles(df: pd.DataFrame, style: str, now: datetime) -> pd.DataFrame:
    """Drop the still-forming candle so signals never repaint."""
    if df.empty:
        return df
    last = df.index[-1]
    last = last.tz_convert(IST) if last.tzinfo else last.tz_localize(IST)
    if last + timedelta(minutes=BAR_MINUTES[style]) > now:
        return df.iloc[:-1]
    return df


# ───────── FYERS orders ─────────
class FyersOrders:
    """Minimal FYERS API v3 order client (REST). Needs FYERS_APP_ID and FYERS_ACCESS_TOKEN."""

    BASE = "https://api-t1.fyers.in/api/v3"

    def __init__(self, app_id: str | None = None, token: str | None = None):
        self.app_id = app_id or os.getenv("FYERS_APP_ID", "")
        self.token = token or os.getenv("FYERS_ACCESS_TOKEN", "")
        if not self.app_id or not self.token:
            raise RuntimeError("AUTO_MODE=live needs FYERS_APP_ID and FYERS_ACCESS_TOKEN")

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.BASE + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"{self.app_id}:{self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = json.loads(resp.read())
        if out.get("s") != "ok":
            raise RuntimeError(f"FYERS {path}: {out.get('message', out)}")
        return out

    @staticmethod
    def order_body(symbol: str, qty: int, side: int, kind: str, product: str,
                   limit: float = 0, stop: float = 0) -> dict:
        types = {"limit": 1, "market": 2, "sl-m": 3, "sl-l": 4}
        return {"symbol": to_fyers_symbol(symbol), "qty": int(qty), "type": types[kind],
                "side": side, "productType": product, "limitPrice": round(limit, 2),
                "stopPrice": round(stop, 2), "validity": "DAY", "disclosedQty": 0,
                "offlineOrder": False, "stopLoss": 0, "takeProfit": 0}

    def place(self, **kw) -> str:
        return self._call("POST", "/orders/sync", self.order_body(**kw))["id"]

    def cancel(self, order_id: str) -> None:
        self._call("DELETE", "/orders/sync", {"id": order_id})

    def orders(self) -> dict[str, dict]:
        return {o["id"]: o for o in self._call("GET", "/orders").get("orderBook", [])}


FILLED, CANCELLED, REJECTED = 2, 1, 5  # FYERS order status codes


# ───────── Trader ─────────
@dataclass
class Trade:
    symbol: str
    side: str
    qty: int
    entry: float
    stop: float
    target: float
    setup: str
    opened: str
    entry_id: str = ""
    sl_id: str = ""
    tp_id: str = ""
    closed: str = ""
    exit_price: float = 0.0
    pnl: float = 0.0
    reason: str = ""


class AutoTrader:
    def __init__(self, s: AutoSettings, fetch=fetch_fyers, broker: FyersOrders | None = None,
                 clock=lambda: datetime.now(IST)):
        self.s, self.fetch, self.clock = s, fetch, clock
        self.broker = broker if broker is not None else (FyersOrders() if s.mode == "live" else None)
        self.open: dict[str, Trade] = {}
        self.history: list[Trade] = []
        self.day = ""
        self.day_pnl = 0.0
        self.trades_today = 0
        self._load()

    # persistence
    def _load(self) -> None:
        if self.s.state_file.exists():
            raw = json.loads(self.s.state_file.read_text(encoding="utf-8"))
            self.open = {k: Trade(**v) for k, v in raw.get("open", {}).items()}
            self.history = [Trade(**t) for t in raw.get("history", [])]
            self.day, self.day_pnl = raw.get("day", ""), raw.get("day_pnl", 0.0)
            self.trades_today = raw.get("trades_today", 0)

    def _save(self) -> None:
        data = {"open": {k: asdict(v) for k, v in self.open.items()},
                "history": [asdict(t) for t in self.history[-500:]], "day": self.day,
                "day_pnl": self.day_pnl, "trades_today": self.trades_today}
        self.s.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _hm(self, now: datetime) -> str:
        return now.strftime("%H:%M")

    # main step, call once per minute
    def step(self) -> list[str]:
        now = self.clock()
        events: list[str] = []
        if self.day != now.date().isoformat():
            self.day, self.day_pnl, self.trades_today = now.date().isoformat(), 0.0, 0
        if now.weekday() >= 5:
            return events
        self._manage_open(now, events)
        hm = self._hm(now)
        if hm >= self.s.squareoff:
            for sym in list(self.open):
                self._exit(sym, None, "square-off", now, events)
        elif self.s.start <= hm <= self.s.last_entry:
            self._look_for_entries(now, events)
        self._save()
        for e in events:
            log.info(e)
        return events

    def _look_for_entries(self, now: datetime, events: list[str]) -> None:
        if self.trades_today >= self.s.max_trades_per_day:
            return
        if -self.day_pnl >= self.s.max_daily_loss:
            return
        for sym in self.s.symbols:
            if sym in self.open or self.trades_today >= self.s.max_trades_per_day:
                continue
            try:
                df = closed_candles(self.fetch(sym, self.s.style), self.s.style, now)
                htf = self.fetch(sym, HIGHER_TF[self.s.style])
            except Exception as exc:  # noqa: BLE001 - skip a symbol on data errors
                events.append(f"{sym}: data error {exc}")
                continue
            if len(df) < 250:
                continue
            plan = a_plus_plan(df, htf, self.s)
            if plan:
                self._enter(sym, plan, now, events)

    def _enter(self, sym: str, p: dict, now: datetime, events: list[str]) -> None:
        side = 1 if p["direction"] == "BUY" else -1
        t = Trade(sym, p["direction"], int(p["qty"]), p["entry"], p["stop_loss"], p["target"],
                  p["setup"], now.isoformat(timespec="seconds"))
        if self.broker:
            try:
                t.entry_id = self.broker.place(symbol=sym, qty=t.qty, side=side, kind="market",
                                               product=self.s.product)
                t.sl_id = self.broker.place(symbol=sym, qty=t.qty, side=-side, kind="sl-m",
                                            product=self.s.product, stop=t.stop)
                t.tp_id = self.broker.place(symbol=sym, qty=t.qty, side=-side, kind="limit",
                                            product=self.s.product, limit=t.target)
            except Exception as exc:  # noqa: BLE001 - never leave a naked position silently
                events.append(f"{sym}: ORDER ERROR {exc} — check FYERS positions now")
                if t.entry_id:
                    self.open[sym] = t
                return
        self.open[sym] = t
        self.trades_today += 1
        events.append(f"ENTER {t.side} {sym} x{t.qty} @ {t.entry} SL {t.stop} TGT {t.target} "
                      f"({t.setup}, 1:{self.s.rr:g}, conf {p['confidence']}%)")

    def _manage_open(self, now: datetime, events: list[str]) -> None:
        if not self.open:
            return
        if self.broker:
            book = self.broker.orders()
            for sym, t in list(self.open.items()):
                sl, tp = book.get(t.sl_id, {}), book.get(t.tp_id, {})
                if sl.get("status") == FILLED:
                    self._close(sym, float(sl.get("tradedPrice") or t.stop), "stop-loss", now,
                                events, cancel=t.tp_id)
                elif tp.get("status") == FILLED:
                    self._close(sym, float(tp.get("tradedPrice") or t.target), "target", now,
                                events, cancel=t.sl_id)
            return
        for sym, t in list(self.open.items()):  # paper: check candles since entry
            try:
                df = self.fetch(sym, self.s.style)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: price check failed: %s", sym, exc)
                continue
            opened = pd.Timestamp(t.opened)
            idx = df.index.tz_convert(IST) if df.index.tz is not None else df.index.tz_localize(IST)
            bars = df[idx > opened]
            buy = t.side == "BUY"
            for _, r in bars.iterrows():
                if (r.low <= t.stop) if buy else (r.high >= t.stop):  # stop first: conservative
                    self._close(sym, t.stop, "stop-loss", now, events)
                    break
                if (r.high >= t.target) if buy else (r.low <= t.target):
                    self._close(sym, t.target, "target", now, events)
                    break

    def _exit(self, sym: str, price: float | None, reason: str, now: datetime,
              events: list[str]) -> None:
        t = self.open[sym]
        side = 1 if t.side == "BUY" else -1
        if self.broker:
            for oid in (t.sl_id, t.tp_id):
                try:
                    self.broker.cancel(oid)
                except Exception as exc:  # noqa: BLE001 - may already be filled/cancelled
                    log.info("%s: cancel %s skipped: %s", sym, oid, exc)
            self.broker.place(symbol=sym, qty=t.qty, side=-side, kind="market",
                              product=self.s.product)
        if price is None:
            try:
                price = float(self.fetch(sym, self.s.style)["close"].iat[-1])
            except Exception:  # noqa: BLE001
                price = t.entry
        self._close(sym, price, reason, now, events)

    def _close(self, sym: str, price: float, reason: str, now: datetime, events: list[str],
               cancel: str = "") -> None:
        t = self.open.pop(sym)
        if cancel and self.broker:
            try:
                self.broker.cancel(cancel)
            except Exception:  # noqa: BLE001
                events.append(f"{sym}: could not cancel order {cancel} — cancel it in FYERS")
        sign = 1 if t.side == "BUY" else -1
        t.exit_price, t.reason = round(price, 2), reason
        t.pnl = round((price - t.entry) * sign * t.qty, 2)
        t.closed = now.isoformat(timespec="seconds")
        self.day_pnl += t.pnl
        self.history.append(t)
        events.append(f"EXIT {sym} {reason} @ {t.exit_price} P&L {t.pnl} (day {self.day_pnl:.2f})")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    s = AutoSettings.from_env()
    if s.style not in BAR_MINUTES:
        raise SystemExit("AUTO_STYLE must be scalping or intraday")
    if s.mode == "live":
        log.warning("LIVE MODE: real orders will be sent to FYERS for %s", ", ".join(s.symbols))
    trader = AutoTrader(s)
    log.info("auto-trader started: %s mode, %s, 1:%g, symbols %s", s.mode, s.style, s.rr,
             s.symbols)
    while True:
        try:
            trader.step()
        except Exception:
            log.exception("step failed")
        time.sleep(60 - datetime.now().second + 2)  # just after each minute, candles closed


if __name__ == "__main__":
    main()
