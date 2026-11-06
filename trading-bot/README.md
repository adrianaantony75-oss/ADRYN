# ADRYN Trading Bot — TradingView → webhook → orders

```
TradingView chart ──(alert webhook JSON)──▶ ADRYN bot (/webhook) ──▶ paper ledger  or  exchange via ccxt
  Pine strategy                               risk checks, sizing,       (Binance, Bybit, OKX,
  "ADRYN AI Signals"                          SL/TP, daily limits         Kraken, ... testnet first)
```

> **Risk warning.** This is an educational tool, not financial advice. The "AI" score is a
> rule-based confluence score (trend, EMA cross, RSI, MACD, volume), not a trained model or
> a guaranteed edge. Backtest it in TradingView and run it in **paper mode** before risking money.

## 1. Run the bot (paper trading, no keys needed)

```bash
cd trading-bot
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then edit BOT_PASSPHRASE to your own secret
python -m adryn_bot --port 8080
```

Open http://localhost:8080 for the trading desk (see below). The webhook dashboard with every alert received, open positions and trades is at http://localhost:8080/bot.

Check it works without TradingView:

```bash
python send_test_alert.py buy BTCUSDT 65000 --sl 64000 --tp 68000
python send_test_alert.py close BTCUSDT 66000
```

## 2. Give it a public HTTPS URL

TradingView can only reach a public address on **port 80 or 443**. Easiest options:

| Option | Command | Webhook URL |
|---|---|---|
| Cloudflare Tunnel (free) | `cloudflared tunnel --url http://localhost:8080` | `https://<random>.trycloudflare.com/webhook` |
| ngrok | `ngrok http 8080` | `https://<id>.ngrok-free.app/webhook` |
| VPS / cloud (Render, Railway, Fly.io, any VM) | `docker build -t adryn-bot . && docker run -p 80:8080 --env-file .env -v $PWD/data:/bot/data adryn-bot` | `https://your-domain/webhook` |

Tunnels die when your PC sleeps — use a VPS for 24/7 trading.

## 3. Connect TradingView

> Webhook alerts need a paid TradingView plan (Essential or higher). Free accounts can still
> use the strategy and backtest, but cannot send webhooks.

1. TradingView → **Pine Editor** → paste [`pine/adryn_ai_signals.pine`](pine/adryn_ai_signals.pine) → **Save** → **Add to chart**.
2. Open the strategy **Settings → Inputs** and set **Webhook passphrase** to the same value as
   `BOT_PASSPHRASE` in your `.env`. (Optional: set *Symbol override* if your exchange names the
   pair differently from the chart ticker.)
3. Check the **Strategy Tester** tab: net profit, drawdown, win rate. Tune inputs per market/timeframe.
4. Create an alert (⏰ icon):
   - **Condition:** `ADRYN AI Signals` → **`alert() function calls only`**
   - **Notifications → Webhook URL:** your URL from step 2, ending in `/webhook`
   - **Message:** leave as is (the script writes the JSON itself)
   - **Expiration:** open-ended
5. Watch the bot dashboard — every alert appears in *TradingView alerts received* with its status.

Payload the script sends (you can also hand-write this in any other TradingView alert):

```json
{"passphrase":"...","action":"buy","symbol":"BTCUSDT","price":65000,
 "stop_loss":64000,"take_profit":68000,"score":5,"timeframe":"60","strategy":"adryn_ai_signals"}
```

`action` is `buy`, `sell` or `close`. `stop_loss`, `take_profit`, `score` are optional.

## 4. Going live on an exchange (optional)

```bash
pip install ccxt
```

In `.env`: `BOT_MODE=ccxt`, `BOT_EXCHANGE=binance` (any ccxt id), `BOT_API_KEY`, `BOT_API_SECRET`,
and keep `BOT_SANDBOX=true` until you have watched it trade on the testnet. Create API keys with
**trade permission only — never withdrawal**. Spot accounts can't short; disable *Allow shorts* in
the Pine inputs or use a futures account.

## How the bot decides

- **Auth:** rejects any alert whose passphrase doesn't match (401).
- **Sizing:** risks `BOT_RISK_PER_TRADE` of equity between entry and stop, capped at
  `BOT_MAX_POSITION_PCT` of equity.
- **Signals:** `buy`/`sell` opens; an opposite signal reverses; a duplicate is ignored; `close` exits.
- **Stops:** each incoming alert first checks the open position's stop loss / take profit at the
  alert price. On an exchange, also place native stop orders if you need intrabar protection.
- **Limits:** `BOT_MIN_SCORE`, `BOT_MAX_TRADES_PER_DAY`, `BOT_MAX_DAILY_LOSS_PCT`,
  `BOT_ALLOWED_SYMBOLS`.
- **Kill switch:** `curl -X POST localhost:8080/halt -H 'Content-Type: application/json' -d '{"passphrase":"..."}'`
  (send `"halted": false` to resume). Closes still go through while halted.
- **State:** saved to `bot_state.json`, so restarts keep positions and P&L.
- **Telegram:** set `BOT_TELEGRAM_TOKEN` and `BOT_TELEGRAM_CHAT_ID` for a message on every trade.

Endpoints: `GET /` dashboard · `POST /webhook` · `GET /status` (JSON) · `GET /health` · `POST /halt`.

## Trading desk (one screen)

Open http://localhost:8080/desk on your second monitor and enter your `BOT_PASSPHRASE` in the top bar.
Left: candlestick chart (5 years daily in Swing mode, recent 5m/15m in Scalping/Intraday) with
BUY/SELL arrows (✓ won / ✗ lost in the backtest), EMAs, VWAP and a long/short position box
(green = target zone, red = stop zone). Or switch to **My screen** and press **Share screen**:
the browser shows only the window you pick, view-only (it cannot click or type), and the AI reads
it every minute and loads the symbol it sees. Right:

1. **Chart analyst**: trend, support/resistance, VWAP, RSI/ADX/volume.
2. **Market scanner**: ranks NIFTY 50, indices, US stocks or crypto by fresh signals, breakouts, breakdowns and fakeouts.
3. **Mentor**: plain-English guidance; optional AI second opinion from your shared screen (needs `ANTHROPIC_API_KEY`).
4. **Cross-checker**: higher-timeframe trend, room to target, volume, ADX, RSI, signal freshness, historical edge.
5. **Final verdict**: BUY / SELL / half size / SKIP with entry, SL, TP1-TP3 and quantity from your capital.

Data comes from FYERS when `FYERS_APP_ID` and `FYERS_ACCESS_TOKEN` are set (untested here, needs your account), otherwise Yahoo (delayed). Backtest numbers per setup are shown so you can judge accuracy yourself; no setup is guaranteed.

## FYERS auto-trader

`python -m adryn_bot.autotrader` checks your symbols every minute on closed candles and takes
only A+ signals: quality 5/5, every cross-check passed, full-size verdict. Target is
`AUTO_RR` x risk (1:2 by default), stop from the plan. In live mode it sends a market entry,
then a stop-loss (SL-M) and a target (limit) order, and cancels the other one when either fills.
Positions are squared off at `AUTO_SQUAREOFF`. Daily trade and loss limits stop it for the day.

`AUTO_MODE=paper` (default) sends nothing to FYERS: run it for a few weeks and check
`auto_state.json` before going live. Live order code is untested against a real FYERS account.

## Tests

```bash
pip install -e ".[dev]" && pytest -q
```
