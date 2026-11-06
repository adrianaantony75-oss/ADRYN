"""Position sizing and safety limits."""

from __future__ import annotations

from .config import Settings


def position_size(settings: Settings, equity: float, price: float, stop: float | None) -> float:
    """Units to trade so a stop-out loses ~risk_per_trade of equity, capped by max_position_pct."""
    cap_units = equity * settings.max_position_pct / price
    if stop is None or stop <= 0 or stop == price:
        return round(cap_units, 8)
    risk_units = equity * settings.risk_per_trade / abs(price - stop)
    return round(max(0.0, min(risk_units, cap_units)), 8)


def check_limits(settings: Settings, trades_today: int, day_pnl: float, day_start_equity: float) -> str | None:
    """Return a reason string if trading must be blocked, else None."""
    if trades_today >= settings.max_trades_per_day:
        return f"daily trade limit reached ({settings.max_trades_per_day})"
    if day_start_equity > 0 and -day_pnl / day_start_equity >= settings.max_daily_loss_pct:
        return f"daily loss limit reached ({settings.max_daily_loss_pct:.0%})"
    return None
