"""Order executors. Paper is the default; CCXT connects 100+ crypto exchanges."""

from __future__ import annotations

from typing import Protocol

from .config import Settings


class Executor(Protocol):
    name: str

    def market_order(self, symbol: str, side: str, qty: float) -> dict: ...


class PaperExecutor:
    """Simulated fills at the alert price; nothing leaves this machine."""

    name = "paper"

    def market_order(self, symbol: str, side: str, qty: float) -> dict:
        return {"executor": "paper", "symbol": symbol, "side": side, "qty": qty}


class CCXTExecutor:
    """Sends real market orders through ccxt (install with `pip install ccxt`).

    Use BOT_SANDBOX=true (the default) to trade on the exchange testnet first.
    Spot markets cannot short: use a futures account for sell-to-open signals.
    """

    name = "ccxt"

    def __init__(self, settings: Settings):
        try:
            import ccxt  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("BOT_MODE=ccxt needs `pip install ccxt`") from exc
        if not settings.api_key or not settings.api_secret:
            raise RuntimeError("BOT_MODE=ccxt needs BOT_API_KEY and BOT_API_SECRET")
        exchange_cls = getattr(ccxt, settings.exchange)
        self.exchange = exchange_cls(
            {"apiKey": settings.api_key, "secret": settings.api_secret, "enableRateLimit": True}
        )
        if settings.sandbox:
            self.exchange.set_sandbox_mode(True)
        self.exchange.load_markets()

    def _market(self, symbol: str) -> str:
        if symbol in self.exchange.markets:
            return symbol
        by_id = getattr(self.exchange, "markets_by_id", {}) or {}
        match = by_id.get(symbol)
        if match:
            return (match[0] if isinstance(match, list) else match)["symbol"]
        raise ValueError(f"unknown symbol on {self.exchange.id}: {symbol}")

    def market_order(self, symbol: str, side: str, qty: float) -> dict:
        market = self._market(symbol)
        amount = float(self.exchange.amount_to_precision(market, qty))
        order = self.exchange.create_order(market, "market", side, amount)
        return {"executor": self.exchange.id, "id": order.get("id"), "symbol": market,
                "side": side, "qty": amount, "status": order.get("status")}


def build_executor(settings: Settings) -> Executor:
    if settings.mode == "paper":
        return PaperExecutor()
    if settings.mode == "ccxt":
        return CCXTExecutor(settings)
    raise ValueError(f"unknown BOT_MODE {settings.mode!r} (use paper or ccxt)")
