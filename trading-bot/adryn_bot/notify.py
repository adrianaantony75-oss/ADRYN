"""Optional Telegram notifications for every executed trade."""

from __future__ import annotations

import json
import logging
import urllib.request

from .config import Settings

log = logging.getLogger("adryn_bot")


def notify(settings: Settings, text: str) -> None:
    if not settings.telegram_token or not settings.telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    body = json.dumps({"chat_id": settings.telegram_chat_id, "text": text}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except OSError as exc:  # never let notifications break trading
        log.warning("telegram notify failed: %s", exc)
