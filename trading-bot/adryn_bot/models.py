"""Webhook payload schema sent by the Pine Script strategy."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Signal(BaseModel):
    passphrase: str
    action: Literal["buy", "sell", "close"]
    symbol: str = Field(min_length=1, max_length=40)
    price: float = Field(gt=0)
    stop_loss: float | None = None
    take_profit: float | None = None
    score: int | None = None
    timeframe: str | None = None
    strategy: str | None = None

    @field_validator("action", mode="before")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("stop_loss", "take_profit")
    @classmethod
    def _zero_is_none(cls, v: float | None) -> float | None:
        return None if v is None or v <= 0 else v
