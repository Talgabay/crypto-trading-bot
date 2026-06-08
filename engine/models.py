"""Core domain models shared across the engine, API, backtester and notifiers."""
from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


class Side(str, enum.Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


class OrderType(str, enum.Enum):
    LIMIT = "limit"
    STOP = "stop"
    MARKET = "market"


class AutonomyMode(str, enum.Enum):
    AUTO = "auto"        # bot decides for you
    APPROVE = "approve"  # bot asks you (human-in-the-loop)
    ADVISE = "advise"    # bot only tells you; no execution


class EngineState(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    HALTED = "halted"      # kill switch / daily loss limit
    COOLDOWN = "cooldown"  # tilt detection enforced pause


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"
    OVERRIDDEN = "overridden"  # human broke a rule deliberately


class Regime(str, enum.Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    NEUTRAL = "neutral"


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@dataclass
class Signal:
    """Output of a Strategy: a proposed trade with full rationale."""
    symbol: str
    side: Side
    strategy: str
    entry_type: OrderType
    entry_price: float
    stop_loss: float
    take_profits: list[tuple[float, float]]  # [(price, fraction), ...]
    atr: float
    regime: Regime
    rationale: list[str] = field(default_factory=list)  # plain-language reasons
    created_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: new_id("sig_"))

    @property
    def stop_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def risk_reward(self) -> float:
        if not self.take_profits or self.stop_distance == 0:
            return 0.0
        first_tp = self.take_profits[0][0]
        return abs(first_tp - self.entry_price) / self.stop_distance


@dataclass
class OrderIntent:
    """A Signal after the RiskManager has sized and validated it."""
    signal: Signal
    size: float                 # units of base asset
    notional: float
    risk_amount: float
    equity_at_risk_pct: float
    client_order_id: str = field(default_factory=lambda: new_id("cid_"))
    notes: list[str] = field(default_factory=list)  # e.g. "notional-capped"
    id: str = field(default_factory=lambda: new_id("int_"))

    @property
    def symbol(self) -> str:
        return self.signal.symbol

    @property
    def side(self) -> Side:
        return self.signal.side


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    price: float
    size: float
    fee: float
    ts: float = field(default_factory=time.time)


@dataclass
class Position:
    symbol: str
    side: Side
    size: float                 # remaining size
    entry_price: float
    stop_loss: float
    take_profits: list[tuple[float, float]]
    intent_id: str
    initial_size: float = 0.0
    atr: float = 0.0
    bars_open: int = 0
    opened_at: float = field(default_factory=time.time)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    tp1_done: bool = False
    tp2_done: bool = False
    breakeven_set: bool = False
    id: str = field(default_factory=lambda: new_id("pos_"))

    def __post_init__(self):
        if self.initial_size == 0.0:
            self.initial_size = self.size

    def unrealized_pnl(self, mark: float) -> float:
        return (mark - self.entry_price) * self.size * self.side.sign

    def r_multiple(self, mark: float) -> float:
        dist = abs(self.entry_price - self.stop_loss)
        if dist == 0:
            return 0.0
        return ((mark - self.entry_price) * self.side.sign) / dist
