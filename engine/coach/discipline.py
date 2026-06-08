"""DisciplineGuard + TiltDetector: the emotional-guardrail core.

These enforce the rules a trader keeps when calm but breaks when emotional:
- tilt detection -> enforced cooldown (anti revenge-trading)
- override friction -> when the human wants to break a rule, require explicit
  confirmation and show them their own historical override track record.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class TiltState:
    consecutive_losses: int = 0
    cooldown_until: float = 0.0

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until


class TiltDetector:
    def __init__(self, params: dict):
        self.max_streak = params.get("consecutive_loss_cooldown", 3)
        self.cooldown_minutes = params.get("cooldown_minutes", 120)
        self.state = TiltState()

    def record_trade(self, pnl: float) -> str | None:
        """Update streak; return a coach message if cooldown is triggered."""
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

        if self.state.consecutive_losses >= self.max_streak:
            self.state.cooldown_until = time.time() + self.cooldown_minutes * 60
            self.state.consecutive_losses = 0
            return (f"⏸️ {self.max_streak} הפסדים ברצף — מפעיל קירור של "
                    f"{self.cooldown_minutes} דק'. זה בדיוק הרגע שבו revenge "
                    f"trading הורג חשבונות. ננשום.")
        return None


@dataclass
class OverrideStats:
    total: int = 0
    wins: int = 0
    pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0


class DisciplineGuard:
    """Tracks the human's manual-override track record and produces the
    friction message shown before a rule is broken."""

    def __init__(self):
        self.override = OverrideStats()
        self.followed = OverrideStats()

    def record(self, was_override: bool, pnl: float) -> None:
        bucket = self.override if was_override else self.followed
        bucket.total += 1
        bucket.pnl += pnl
        if pnl >= 0:
            bucket.wins += 1

    def friction_message(self, what: str) -> str:
        o = self.override
        msg = [f"⚠️ אתה עומד לשבור חוק: {what}."]
        if o.total:
            msg.append(
                f"היסטוריית ה-overrides שלך: {o.wins}/{o.total} מנצחים "
                f"({o.win_rate*100:.0f}%), P&L מצטבר {o.pnl:+.2f}.")
        msg.append("בטוח? לחיצה שנייה לאישור.")
        return "\n".join(msg)

    def discipline_score(self) -> float:
        """0-100: rewards following the plan and a positive override record."""
        total = self.followed.total + self.override.total
        if not total:
            return 100.0
        adherence = self.followed.total / total
        return round(100 * adherence, 1)
