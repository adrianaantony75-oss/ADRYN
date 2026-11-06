"""Trading engine: keeps the ledger, applies risk rules and routes orders."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .brokers import Executor
from .config import Settings
from .models import Signal
from .risk import check_limits, position_size


@dataclass
class Position:
    symbol: str
    qty: float  # positive = long, negative = short
    entry: float
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: str = ""

    def pnl(self, price: float) -> float:
        return (price - self.entry) * self.qty


@dataclass
class Ledger:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)
    day: str = ""
    day_start_equity: float = 0.0
    day_pnl: float = 0.0
    trades_today: int = 0
    halted: bool = False


def _now() -> datetime:
    return datetime.now(UTC)


class Engine:
    def __init__(self, settings: Settings, executor: Executor, state_file: Path | None = None):
        self.settings = settings
        self.executor = executor
        self.state_file = state_file if state_file is not None else settings.state_file
        self._lock = threading.Lock()
        self.ledger = self._load()

    # ---------- persistence ----------
    def _load(self) -> Ledger:
        if self.state_file and self.state_file.exists():
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            raw["positions"] = {k: Position(**v) for k, v in raw.get("positions", {}).items()}
            return Ledger(**raw)
        return Ledger(cash=self.settings.starting_cash)

    def _save(self) -> None:
        if not self.state_file:
            return
        data = asdict(self.ledger)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    # ---------- accounting ----------
    def equity(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        value = self.ledger.cash
        for p in self.ledger.positions.values():
            value += p.pnl(marks.get(p.symbol, p.entry))
        return value

    def _roll_day(self) -> None:
        today = _now().date().isoformat()
        if self.ledger.day != today:
            self.ledger.day = today
            self.ledger.day_start_equity = self.equity()
            self.ledger.day_pnl = 0.0
            self.ledger.trades_today = 0

    def _record(self, kind: str, symbol: str, qty: float, price: float, **extra) -> dict:
        trade = {
            "time": _now().isoformat(timespec="seconds"),
            "kind": kind,
            "symbol": symbol,
            "qty": qty,
            "price": price,
            **extra,
        }
        self.ledger.trades.append(trade)
        self.ledger.trades = self.ledger.trades[-500:]
        return trade

    def _close(self, symbol: str, price: float, reason: str) -> dict | None:
        pos = self.ledger.positions.get(symbol)
        if pos is None:
            return None
        order = self.executor.market_order(symbol, "sell" if pos.qty > 0 else "buy", abs(pos.qty))
        pnl = pos.pnl(price)
        self.ledger.cash += pnl
        self.ledger.day_pnl += pnl
        del self.ledger.positions[symbol]
        return self._record("close", symbol, -pos.qty, price, pnl=round(pnl, 2),
                            reason=reason, order=order)

    def _open(self, sig: Signal) -> dict:
        side = 1 if sig.action == "buy" else -1
        qty = position_size(self.settings, self.equity(), sig.price, sig.stop_loss)
        if qty <= 0:
            return {"status": "skipped", "reason": "position size is zero"}
        order = self.executor.market_order(sig.symbol, sig.action, qty)
        self.ledger.positions[sig.symbol] = Position(
            symbol=sig.symbol, qty=side * qty, entry=sig.price, stop_loss=sig.stop_loss,
            take_profit=sig.take_profit, opened_at=_now().isoformat(timespec="seconds"),
        )
        self.ledger.trades_today += 1
        return self._record("open", sig.symbol, side * qty, sig.price, sl=sig.stop_loss,
                            tp=sig.take_profit, score=sig.score, order=order)

    def _check_exits(self, symbol: str, price: float) -> dict | None:
        pos = self.ledger.positions.get(symbol)
        if pos is None:
            return None
        long = pos.qty > 0
        if pos.stop_loss and (price <= pos.stop_loss if long else price >= pos.stop_loss):
            return self._close(symbol, pos.stop_loss, "stop_loss")
        if pos.take_profit and (price >= pos.take_profit if long else price <= pos.take_profit):
            return self._close(symbol, pos.take_profit, "take_profit")
        return None

    # ---------- public API ----------
    def handle(self, sig: Signal) -> dict:
        s = self.settings
        with self._lock:
            self._roll_day()
            events: list[dict] = []
            if s.allowed_symbols and sig.symbol not in s.allowed_symbols:
                return {"status": "rejected", "reason": f"symbol {sig.symbol} not allowed"}

            exit_evt = self._check_exits(sig.symbol, sig.price)
            if exit_evt:
                events.append(exit_evt)

            if sig.action == "close":
                evt = self._close(sig.symbol, sig.price, "signal")
                self._save()
                if evt:
                    events.append(evt)
                return {"status": "ok" if events else "no_position", "events": events}

            if self.ledger.halted:
                self._save()
                return {"status": "rejected", "reason": "bot is halted", "events": events}
            if sig.score is not None and sig.score < s.min_score:
                self._save()
                return {"status": "rejected", "reason": f"score {sig.score} < {s.min_score}",
                        "events": events}

            pos = self.ledger.positions.get(sig.symbol)
            wanted = 1 if sig.action == "buy" else -1
            if pos is not None and (pos.qty > 0) == (wanted > 0):
                self._save()
                return {"status": "ignored", "reason": "already in position", "events": events}
            if pos is not None:
                events.append(self._close(sig.symbol, sig.price, "reverse"))

            blocked = check_limits(s, self.ledger.trades_today, self.ledger.day_pnl,
                                   self.ledger.day_start_equity)
            if blocked:
                self._save()
                return {"status": "rejected", "reason": blocked, "events": events}

            events.append(self._open(sig))
            self._save()
            return {"status": "ok", "events": events}

    def set_halted(self, halted: bool) -> None:
        with self._lock:
            self.ledger.halted = halted
            self._save()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self.settings.mode,
                "halted": self.ledger.halted,
                "cash": round(self.ledger.cash, 2),
                "equity_at_entry": round(self.equity(), 2),
                "day": self.ledger.day,
                "day_pnl": round(self.ledger.day_pnl, 2),
                "trades_today": self.ledger.trades_today,
                "positions": [asdict(p) for p in self.ledger.positions.values()],
                "recent_trades": self.ledger.trades[-20:],
            }
