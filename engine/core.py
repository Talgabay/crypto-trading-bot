"""TradingEngine: the orchestration that wires every layer together and runs
identically over a live feed or a replay feed.

Pipeline per closed bar:
  manage open positions -> (if running) strategy -> risk -> coach/narrate
  -> approval (UI+Telegram, with execution-time re-validation) -> execute
  -> journal + discipline/tilt + equity snapshot + daily-loss kill switch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .approval import ApprovalQueue
from .coach import DisciplineGuard, TiltDetector, narrator
from .data.feed import BarEvent
from .db import repo
from .execution.base import ExecutionAdapter
from .models import (ApprovalStatus, AutonomyMode, EngineState, OrderIntent,
                     Side)
from .notify import NotificationHub
from .risk import AccountState, RiskManager

log = logging.getLogger("engine")


@dataclass
class DayBook:
    day: Optional[object] = None
    start_equity: float = 0.0
    realized_pnl: float = 0.0
    trades: int = 0


@dataclass
class EngineStatus:
    state: EngineState = EngineState.RUNNING
    autonomy: AutonomyMode = AutonomyMode.APPROVE
    last_price: dict = field(default_factory=dict)


class TradingEngine:
    def __init__(self, settings, broker: ExecutionAdapter,
                 approvals: ApprovalQueue, notify: NotificationHub,
                 autonomy: AutonomyMode, persist: bool = True):
        from .strategy import build_strategy

        self.s = settings
        self.broker = broker
        self.approvals = approvals
        self.notify = notify
        self.strategy = build_strategy(settings)
        self.risk = RiskManager(settings.risk)
        self.tilt = TiltDetector(settings.risk)
        self.discipline = DisciplineGuard()
        self.persist = persist
        self.status = EngineStatus(autonomy=autonomy)
        self.day = DayBook(start_equity=broker.get_equity())
        self.consecutive_losses = 0
        self._now: float | None = None  # bar-close epoch (simulated in replay)

    # --- public controls ---------------------------------------------------
    def set_state(self, state: EngineState) -> None:
        self.status.state = state

    def set_autonomy(self, mode: AutonomyMode) -> None:
        self.status.autonomy = mode

    # --- main per-bar entrypoint ------------------------------------------
    async def process_bar(self, ev: BarEvent) -> None:
        self.status.last_price[ev.symbol] = ev.bar["close"]
        ts = ev.exec_df.index[-1]
        self._now = ts.timestamp() if hasattr(ts, "timestamp") else None
        self._roll_day(ev)

        await self._manage_positions(ev)

        if self.status.state in (EngineState.HALTED, EngineState.PAUSED):
            return
        if self.tilt.state.in_cooldown(self._now):
            self.set_state(EngineState.COOLDOWN)
            return
        if self.status.state is EngineState.COOLDOWN:
            self.set_state(EngineState.RUNNING)

        await self._maybe_enter(ev)

    # --- position management ----------------------------------------------
    async def _manage_positions(self, ev: BarEvent) -> None:
        events = await self.broker.on_bar(ev.symbol, ev.bar, self.s.exits)
        for ex in events:
            self.day.realized_pnl += ex.pnl
            msg = narrator.narrate_exit(ex.position, ex.price, ex.reason)
            await self.notify.text(msg)
            if self.persist:
                repo.log_narration(msg)
                repo.update_journal_outcome(
                    ex.position.intent_id, ex.pnl,
                    ex.position.r_multiple(ex.price))
                repo.snapshot_equity(self.broker.get_equity(),
                                     self.day.realized_pnl)
            if ex.closed:
                cooldown_msg = self.tilt.record_trade(
                    ex.position.realized_pnl, self._now)
                self.discipline.record(False, ex.position.realized_pnl)
                if cooldown_msg:
                    await self.notify.text(cooldown_msg)
                    if self.persist:
                        repo.record_discipline("cooldown", cooldown_msg)

        # daily-loss kill switch
        dd = -self.s.risk.get("daily_loss_limit_pct", 0.02) * self.day.start_equity
        if self.day.realized_pnl <= dd and self.status.state is not EngineState.HALTED:
            self.set_state(EngineState.HALTED)
            msg = narrator.narrate_halt("הגענו לגבול ההפסד היומי")
            await self.notify.text(msg)
            if self.persist:
                repo.record_discipline("halt", msg)

    # --- entries -----------------------------------------------------------
    async def _maybe_enter(self, ev: BarEvent) -> None:
        signal = self.strategy.evaluate(ev.symbol, ev.exec_df, ev.htf_df)
        if signal is None:
            return

        acct = self._account_state()
        decision = self.risk.evaluate(signal, acct)
        if not decision.approved:
            if self.s.coach.get("narrate", True):
                await self.notify.text(
                    f"👀 setup ב-{signal.symbol} נפסל: {decision.reason}")
            return

        intent = decision.intent
        alert = narrator.build_alert(intent, self.approvals.timeout_sec)
        await self.notify.text(alert["narration"])
        await self.notify.alert(alert)
        if self.persist:
            repo.log_narration(alert["narration"])

        result = await self.approvals.request(
            intent, self.status.autonomy, revalidate=self._revalidate,
            alert=alert)

        if result.status in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED,
                             ApprovalStatus.OVERRIDDEN):
            await self._execute(result.intent, result.status, result.was_override)
        else:
            if self.s.coach.get("narrate", True):
                await self.notify.text(
                    f"⏭️ {signal.symbol}: {result.status.value} — לא נכנסנו")

    async def _execute(self, intent: OrderIntent, status: ApprovalStatus,
                       was_override: bool) -> None:
        fill = await self.broker.open(intent)
        if fill is None:
            return
        self.day.trades += 1
        pos = next((p for p in self.broker.get_positions()
                    if p.intent_id == intent.id), None)
        if pos is not None:
            await self.notify.text(narrator.narrate_fill(pos))
        if self.persist:
            sig = intent.signal
            repo.record_journal(
                symbol=sig.symbol, side=sig.side.value, strategy=sig.strategy,
                decision=status.value, was_override=was_override,
                entry_price=sig.entry_price, stop_loss=sig.stop_loss,
                risk_reward=sig.risk_reward, size=intent.size,
                rationale=sig.rationale, intent_id=intent.id)

    # --- helpers -----------------------------------------------------------
    async def _revalidate(self, intent: OrderIntent) -> bool:
        """Execution-time guard: price must still be near the signal entry."""
        last = self.status.last_price.get(intent.symbol)
        if last is None:
            return True
        drift = abs(last - intent.signal.entry_price) / intent.signal.entry_price
        # reject if price moved more than half the stop distance away
        max_drift = (intent.signal.stop_distance / intent.signal.entry_price) * 0.5
        return drift <= max_drift

    def _account_state(self) -> AccountState:
        positions = self.broker.get_positions()
        return AccountState(
            equity=self.broker.get_equity(),
            start_of_day_equity=self.day.start_equity or self.broker.get_equity(),
            open_sides=[p.side for p in positions],
            daily_realized_pnl=self.day.realized_pnl,
            trades_today=self.day.trades,
            in_cooldown=self.tilt.state.in_cooldown(self._now),
        )

    def _roll_day(self, ev: BarEvent) -> None:
        ts = ev.exec_df.index[-1]
        day = ts.astimezone(timezone.utc).date() if isinstance(ts, datetime) \
            else ts.date()
        if self.day.day != day:
            self.day = DayBook(day=day, start_equity=self.broker.get_equity())
            if self.status.state is EngineState.HALTED:
                self.set_state(EngineState.RUNNING)  # new day resets the halt
