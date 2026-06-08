"""ApprovalQueue: the human-in-the-loop core.

Holds PENDING intents, fans an alert to all channels, and waits for a decision
from ANY channel (UI or Telegram) with a timeout. First decision wins
(idempotent). On approval it RE-VALIDATES at execution time against a live
price callback — a 90s-old signal must not execute blindly (council)."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from ..models import ApprovalStatus, AutonomyMode, OrderIntent

log = logging.getLogger("approval")


@dataclass
class ApprovalResult:
    status: ApprovalStatus
    intent: OrderIntent
    modifications: dict = field(default_factory=dict)
    was_override: bool = False


@dataclass
class _Pending:
    intent: OrderIntent
    future: asyncio.Future
    created_at: float
    alert: dict = field(default_factory=dict)


class ApprovalQueue:
    def __init__(self, timeout_sec: int = 90):
        self.timeout_sec = timeout_sec
        self._pending: dict[str, _Pending] = {}

    def pending_alerts(self) -> list[str]:
        return list(self._pending.keys())

    def pending_payloads(self) -> list[dict]:
        return [p.alert for p in self._pending.values() if p.alert]

    async def request(
        self,
        intent: OrderIntent,
        mode: AutonomyMode,
        revalidate: Optional[Callable[[OrderIntent], Awaitable[bool]]] = None,
        alert: Optional[dict] = None,
    ) -> ApprovalResult:
        """Block until the human decides, or auto-resolve per autonomy mode."""
        if mode is AutonomyMode.AUTO:
            return ApprovalResult(ApprovalStatus.APPROVED, intent)
        if mode is AutonomyMode.ADVISE:
            # advise-only: never executes
            return ApprovalResult(ApprovalStatus.REJECTED, intent)

        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[intent.id] = _Pending(intent, fut, time.time(), alert or {})
        try:
            result: ApprovalResult = await asyncio.wait_for(
                fut, timeout=self.timeout_sec)
        except asyncio.TimeoutError:
            log.info("approval %s expired", intent.id)
            return ApprovalResult(ApprovalStatus.EXPIRED, intent)
        finally:
            self._pending.pop(intent.id, None)

        # Re-validate APPROVED/MODIFIED intents at execution time.
        if result.status in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED):
            if revalidate is not None:
                ok = await revalidate(result.intent)
                if not ok:
                    log.info("approval %s stale at execution — expiring",
                             intent.id)
                    return ApprovalResult(ApprovalStatus.EXPIRED, result.intent)
        return result

    def resolve(self, intent_id: str, action: str,
                modifications: Optional[dict] = None,
                was_override: bool = False) -> bool:
        """Called by UI/Telegram. First call wins (idempotent)."""
        pending = self._pending.get(intent_id)
        if pending is None or pending.future.done():
            return False
        status = {
            "approve": ApprovalStatus.APPROVED,
            "reject": ApprovalStatus.REJECTED,
            "modify": ApprovalStatus.MODIFIED,
        }.get(action, ApprovalStatus.REJECTED)

        intent = pending.intent
        if status is ApprovalStatus.MODIFIED and modifications:
            intent = self._apply_modifications(intent, modifications)

        pending.future.set_result(
            ApprovalResult(status, intent, modifications or {}, was_override))
        return True

    @staticmethod
    def _apply_modifications(intent: OrderIntent, mods: dict) -> OrderIntent:
        """Sanity-bounded modify: stop must stay on the correct side, size > 0.
        Out-of-bounds modifications are ignored (kept at original)."""
        sig = intent.signal
        new_stop = mods.get("stop_loss")
        if new_stop is not None:
            if sig.side.value == "long" and new_stop < sig.entry_price:
                sig.stop_loss = float(new_stop)
            elif sig.side.value == "short" and new_stop > sig.entry_price:
                sig.stop_loss = float(new_stop)
        new_size = mods.get("size")
        if new_size is not None and float(new_size) > 0:
            intent.size = float(new_size)
            intent.notional = intent.size * sig.entry_price
        return intent
