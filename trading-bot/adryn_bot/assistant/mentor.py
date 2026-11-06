"""Desk section 3: the mentor. Instant rule-based read, plus an optional Claude second opinion."""

from __future__ import annotations

import base64
import json
import os

MODEL = os.getenv("BOT_AI_MODEL", "claude-opus-5-5")


def rule_mentor(a: dict, htf: str, style: str) -> list[str]:
    """Experienced-trader style guidance built from the engine read (instant, no API)."""
    s, lv, ix = a.get("signal"), a["levels"], a["indicators"]
    out = []
    if a["bias"] == "SIDEWAYS":
        out.append("The market has no clear direction. Most losses come from forcing trades here. "
                   "Sit on your hands until price leaves the range.")
    else:
        out.append(f"Trend is {a['bias'].lower()} on this timeframe and {htf.lower()} on the higher "
                   f"one. Trade with the bigger trend, not against it.")
    if s:
        side = "buy" if s["direction"] == "BUY" else "sell"
        out.append(f"Setup: {s['setup']}. Plan the trade before you take it: {side} near "
                   f"{s['entry']}, stop {s['stop_loss']}. If the stop is hit, you were wrong, "
                   f"exit without arguing with the market.")
        out.append(f"Book a third at TP1 {s['tp1']} and move the stop to entry. That turns it "
                   f"into a free trade. Let the rest run to {s['tp2']} and {s['tp3']}.")
        out.append(f"Maximum loss on this trade is {s['risk_amount']}. If that number makes you "
                   f"uncomfortable, cut the quantity.")
        if s["setup"].startswith("Fakeout"):
            out.append("Fakeouts are fast. If price does not move your way within 2-3 candles, exit.")
    else:
        out.append("No setup now. The best traders spend most of the day waiting.")
    if ix["rsi"] > 70 or ix["rsi"] < 30:
        out.append(f"RSI {ix['rsi']} is stretched. Do not chase; wait for a pullback.")
    if style == "scalping":
        out.append("Scalping: decide in seconds, never move your stop further away, and stop "
                   "trading after 2-3 losses in a row.")
    if lv.get("vwap") and style != "swing":
        out.append(f"VWAP {lv['vwap']}: institutions use it. Above it favours buyers, below favours sellers.")
    return out


AI_SYSTEM = """You are a veteran discretionary trader acting as a mentor. You receive the
computed state of a chart (JSON from a rule-based engine; treat its numbers as facts) and
sometimes a screenshot. Give your independent opinion: would you take the engine's trade,
the opposite, or wait? Be concrete with prices. Never promise profit. Keep each field short."""

AI_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "WAIT"]},
        "agrees_with_engine": {"type": "boolean"},
        "view": {"type": "string", "description": "2-4 sentences on what the chart is doing"},
        "plan": {"type": "string", "description": "if-then plan with exact levels"},
        "comment": {"type": "string", "description": "one sentence: main risk or why you disagree"},
    },
    "required": ["action", "agrees_with_engine", "view", "plan", "comment"],
    "additionalProperties": False,
}


def ai_mentor(context: dict, image: bytes | None = None, media_type: str = "image/png",
              question: str | None = None, effort: str = "low") -> dict:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("AI mentor needs `pip install anthropic`") from exc
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from the environment / .env
    content: list[dict] = []
    if image:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type,
            "data": base64.standard_b64encode(image).decode()}})
    text = (question or "Review this setup.") + "\n\nEngine state:\n" + json.dumps(context, default=str)
    content.append({"type": "text", "text": text})
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=AI_SYSTEM,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": AI_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the AI declined this request")
    raw = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(raw)
