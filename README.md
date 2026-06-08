# 🤝 Crypto Trading Co-Pilot

A **psychological co-pilot** for crypto day-trading — not just a bot. Its real
job is to bridge the *psychological gap* that makes independent traders fail:
FOMO, moving stops, revenge trading, over-trading, freezing on the trigger.

It is a **partner**: it watches the market, narrates what's happening, computes
entries/stops/targets, **decides for you when you let it**, and **gives you the
final say when you want it** — without ever letting emotion break the rules you
set when you were calm.

> ⚠️ **Paper / demo only.** `TRADING_MODE=paper`. No real funds. Going live is
> deliberately *not* a UI toggle (see Safety).

## What it does
- **Strategy:** VWAP trend-pullback (primary) with an ADX **regime switch** to
  VWAP mean-reversion in ranges. Anchored VWAP (not arbitrary 00:00-UTC session
  VWAP), 15m execution + 1h trend filter, EMA + ADX trend gate, no-chase guard.
- **Entries/exits:** limit on pullback (stop for breakouts), SL at
  `min(swing, VWAP−ATR)` with an anti-stop-hunt buffer & close-confirmed exits,
  R-multiple take-profits (TP1 50% @1R → breakeven, TP2 25% @2R, ATR trailing
  runner), time-stop.
- **Risk / budget:** position sizing from `risk_per_trade %` and stop distance,
  notional cap, max concurrent + same-direction (correlation) caps, **fee
  gate** (skip trades whose 1R can't clear costs), **daily-loss kill switch**,
  slippage-aware sizing.
- **Co-pilot layer (the differentiator):** live narration, proactive alerts,
  **tilt detection + enforced cooldown**, **override friction** (breaking a
  rule shows your own historical override track record), an auto trade
  **journal** and **discipline score** comparing *following the plan* vs
  *overriding*.
- **Channels:** **Telegram** (alerts + approve/reject from your phone) **and** a
  **React dashboard** (positions, P&L, narration feed, journal, controls).
- **Autonomy modes:** `auto` (decide for me) · `approve` (ask me) · `advise`
  (just tell me) — switchable live.

## Architecture
```
Exchange/Synthetic feed → DataFeed → IndicatorEngine → StrategyEngine
   → RiskManager → Coach(Narrator/DisciplineGuard/TiltDetector)
   → ApprovalQueue (UI + Telegram, re-validated at execution)
   → ExecutionManager (PaperBroker / ccxt testnet) → SQLite
FastAPI (REST + WebSocket) ←→ React dashboard
Replay backtester reuses the EXACT live pipeline (backtest == live)
```
See `engine/` (data, indicators, strategy, risk, coach, approval, execution,
notify, db), `api/`, `backtest/`, `ui/`.

## Quick start (demo, no keys)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                 # works as-is for the synthetic demo
pytest -q                            # run the test suite
python -m backtest.run               # replay backtest on synthetic data
uvicorn api.app:app --port 8000      # engine + API (synthetic feed)
cd ui && npm install && npm run dev  # dashboard on http://localhost:3002
```

### Live paper trading (Binance Spot **Testnet**)
1. Create a key at https://testnet.binance.vision/ and fill `.env`.
2. Add a Telegram bot via @BotFather → set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
3. `python -m engine.main --live` (or run the API and the engine picks up keys).

## Safety
- `TRADING_MODE=paper` and a startup assertion refuse any non-testnet host.
- ccxt Binance sandbox URL is overridden explicitly (ccxt #27266).
- Orders carry a client-generated id (idempotency); the exchange is the source
  of truth for reconciliation.
- Before any real money: separate keys with **withdrawal disabled**, IP
  allowlist, hard caps below the config layer, and a deliberate env-level
  switch — never a UI toggle.

## Status
MVP, end-to-end, paper-only. Built phase-by-phase: indicators → strategy →
replay backtest → paper execution → approval/API → dashboard. Not financial
advice; for research/education.
