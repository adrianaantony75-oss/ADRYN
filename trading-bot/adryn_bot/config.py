"""Settings loaded from environment variables (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in {'"', "'"} and value[0] in value[1:]:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()
            if value.startswith("#"):
                value = ""
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    passphrase: str = "change-me"
    mode: str = "paper"  # paper | ccxt
    exchange: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True
    starting_cash: float = 10_000.0
    risk_per_trade: float = 0.01  # fraction of equity risked per trade
    max_position_pct: float = 0.25  # cap on notional per position
    max_trades_per_day: int = 10
    max_daily_loss_pct: float = 0.05
    min_score: int = 0
    allowed_symbols: frozenset[str] = field(default_factory=frozenset)
    state_file: Path = Path("bot_state.json")
    telegram_token: str = ""
    telegram_chat_id: str = ""

    @classmethod
    def from_env(cls, env_file: str | os.PathLike[str] | None = ".env") -> Settings:
        if env_file:
            _load_dotenv(Path(env_file))
        symbols = os.getenv("BOT_ALLOWED_SYMBOLS", "")
        return cls(
            passphrase=os.getenv("BOT_PASSPHRASE", "change-me"),
            mode=os.getenv("BOT_MODE", "paper").lower(),
            exchange=os.getenv("BOT_EXCHANGE", "binance"),
            api_key=os.getenv("BOT_API_KEY", ""),
            api_secret=os.getenv("BOT_API_SECRET", ""),
            sandbox=_bool("BOT_SANDBOX", True),
            starting_cash=float(os.getenv("BOT_STARTING_CASH", "10000")),
            risk_per_trade=float(os.getenv("BOT_RISK_PER_TRADE", "0.01")),
            max_position_pct=float(os.getenv("BOT_MAX_POSITION_PCT", "0.25")),
            max_trades_per_day=int(os.getenv("BOT_MAX_TRADES_PER_DAY", "10")),
            max_daily_loss_pct=float(os.getenv("BOT_MAX_DAILY_LOSS_PCT", "0.05")),
            min_score=int(os.getenv("BOT_MIN_SCORE", "0")),
            allowed_symbols=frozenset(
                s.strip().upper() for s in symbols.split(",") if s.strip()
            ),
            state_file=Path(os.getenv("BOT_STATE_FILE", "bot_state.json")),
            telegram_token=os.getenv("BOT_TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.getenv("BOT_TELEGRAM_CHAT_ID", ""),
        )
