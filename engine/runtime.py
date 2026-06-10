"""Shared runtime wiring used by both the API (hosted engine) and the headless
runner. Picks PaperBroker (paper mode), a live or synthetic feed, and the
notification channels (Telegram + UI)."""
from __future__ import annotations

import logging

from .approval import ApprovalQueue
from .config import get_settings
from .core import TradingEngine
from .data.feed import LiveFeed, SyntheticLiveFeed
from .db import init_db
from .execution import PaperBroker
from .models import AutonomyMode
from .notify import NotificationHub, TelegramChannel
from .notify.ws_channel import WsHub

log = logging.getLogger("runtime")


class Runtime:
    def __init__(self, use_live: bool | None = None):
        self.settings = get_settings()
        init_db(self.settings.secrets.database_url)

        self.ws_hub = WsHub()
        self.approvals = ApprovalQueue(
            timeout_sec=self.settings.coach.get("approval_timeout_sec", 90))
        self.notify = NotificationHub()
        self.notify.register(self.ws_hub)

        self.telegram = TelegramChannel(
            self.settings.secrets.telegram_bot_token,
            self.settings.secrets.telegram_chat_id,
            on_action=self._on_telegram_action,
        )
        if self.telegram.enabled:
            self.notify.register(self.telegram)

        # live = real testnet feed AND real testnet order execution.
        # falls back to paper/synthetic when keys are missing.
        if use_live is None:
            use_live = self.settings.secrets.use_live
        self.use_live = bool(use_live) and bool(
            self.settings.secrets.binance_testnet_api_key)

        if self.use_live:
            from .execution.ccxt_adapter import CcxtBroker
            self.broker = CcxtBroker(self.settings.secrets)
            log.info("using CcxtBroker — orders go to the exchange TESTNET")
        else:
            self.broker = PaperBroker(
                starting_equity=10_000.0,
                fee_rate=self.settings.risk.get("fee_round_trip_pct", 0.002) / 2,
                slippage_pct=self.settings.risk.get("slippage_assumption_pct", 0.0007),
            )
        autonomy = AutonomyMode(self.settings.coach.get("default_autonomy", "approve"))
        self.engine = TradingEngine(
            self.settings, self.broker, self.approvals, self.notify,
            autonomy=autonomy, persist=True)

        self._feed = self._build_feed()

    def _build_feed(self):
        u = self.settings.universe
        symbols = u.get("symbols", ["BTC/USDT"])
        tf = u.get("timeframe", "15m")
        htf = u.get("htf_timeframe", "1h")
        if self.use_live:
            from .execution.ccxt_adapter import build_exchange
            ex = build_exchange(self.settings.secrets)
            log.info("using LIVE testnet feed")
            return LiveFeed(ex, symbols, tf, htf)
        log.info("using SYNTHETIC feed (no keys / demo)")
        return SyntheticLiveFeed(symbols, tf, htf)

    async def _on_telegram_action(self, intent_id: str, action: str) -> None:
        self.approvals.resolve(intent_id, action)

    async def start_telegram(self) -> None:
        if self.telegram.enabled:
            await self.telegram.start()

    async def run(self) -> None:
        async for ev in self._feed.stream():
            try:
                await self.engine.process_bar(ev)
                await self.ws_hub.push("tick", {
                    "symbol": ev.symbol, "price": ev.bar["close"],
                    "state": self.engine.status.state.value,
                    "equity": round(self.broker.get_equity(), 2),
                })
            except Exception:
                log.exception("error processing bar for %s", ev.symbol)
