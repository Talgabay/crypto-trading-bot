"""RiskManager: converts a Signal into a sized, validated OrderIntent and
enforces all hard limits. This is the discipline backbone — the rules the
trader sets when calm and cannot override when emotional."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..models import OrderIntent, Side, Signal


@dataclass
class AccountState:
    equity: float
    start_of_day_equity: float
    open_sides: list[Side] = field(default_factory=list)
    daily_realized_pnl: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    in_cooldown: bool = False


@dataclass
class RiskDecision:
    approved: bool
    intent: Optional[OrderIntent] = None
    reason: str = ""


class RiskManager:
    def __init__(self, risk_params: dict):
        self.p = risk_params

    def evaluate(self, signal: Signal, acct: AccountState) -> RiskDecision:
        p = self.p
        entry = signal.entry_price
        dist = signal.stop_distance
        if dist <= 0 or entry <= 0:
            return RiskDecision(False, reason="stop distance / entry invalid")

        # --- cooldown / circuit breakers -----------------------------------
        if acct.in_cooldown:
            return RiskDecision(False, reason="בקירור (tilt) — אין כניסות חדשות")
        if acct.trades_today >= p.get("max_trades_per_day", 8):
            return RiskDecision(False, reason="הגעת למקסימום עסקאות להיום")

        # --- daily loss limit ----------------------------------------------
        dd = -p.get("daily_loss_limit_pct", 0.02) * acct.start_of_day_equity
        if acct.daily_realized_pnl <= dd:
            return RiskDecision(False, reason="גבול הפסד יומי — המערכת עצרה (HALT)")

        # --- minimum stop distance (anti tight-stop oversizing) ------------
        if dist / entry < p.get("min_stop_distance_pct", 0.002):
            return RiskDecision(False, reason="סטופ צמוד מדי — נדחה")

        # --- fee gate (1R must clear costs comfortably) --------------------
        rt_cost = p.get("fee_round_trip_pct", 0.0020) * entry
        if dist < p.get("min_r_fee_multiple", 8) * rt_cost:
            return RiskDecision(
                False, reason="1R קטן מדי ביחס לעמלות — אין edge, מדלגים")

        # --- position-count + correlation (same-direction) guards ----------
        if len(acct.open_sides) >= p.get("max_concurrent_positions", 3):
            return RiskDecision(False, reason="מקסימום פוזיציות במקביל")
        same_side = sum(1 for s in acct.open_sides if s == signal.side)
        if same_side >= p.get("max_same_direction", 2):
            return RiskDecision(
                False, reason="יותר מדי פוזיציות באותו כיוון (סיכון קורלציה)")

        # --- sizing --------------------------------------------------------
        risk_amount = acct.equity * p.get("risk_per_trade_pct", 0.005)
        slip = p.get("slippage_assumption_pct", 0.0007)
        eff_dist = dist * (1 + slip)  # size against worse-than-stop fill
        size = risk_amount / eff_dist
        notional = size * entry

        notes: list[str] = []
        cap = p.get("max_notional_pct", 0.25) * acct.equity
        if notional > cap:
            size = cap / entry
            notional = cap
            risk_amount = size * eff_dist
            notes.append("notional-capped — הסיכון בפועל נמוך מ-0.5%")

        equity_at_risk_pct = (size * eff_dist) / acct.equity if acct.equity else 0.0

        intent = OrderIntent(
            signal=signal, size=size, notional=notional,
            risk_amount=size * eff_dist, equity_at_risk_pct=equity_at_risk_pct,
            notes=notes,
        )
        return RiskDecision(True, intent=intent)
