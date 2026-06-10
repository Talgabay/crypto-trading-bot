"""Execution adapter interface. PaperBroker (sim) and CcxtBroker (testnet)
both implement it, so the engine is venue-agnostic."""
from __future__ import annotations

import abc
from dataclasses import dataclass

from ..models import Fill, OrderIntent, Position, Side


@dataclass
class ExitEvent:
    position: Position
    price: float
    size: float
    pnl: float
    reason: str          # stop | tp1 | tp2 | trail | time | manual
    closed: bool         # True if the whole position is now closed


def plan_exits(pos: Position, bar: dict, exits_cfg: dict) -> list[tuple[float, float, str]]:
    """Decide which exits trigger on this CLOSED bar: [(price, size, reason)].

    Shared by every venue (paper + ccxt) so the exit RULES are identical and
    only the execution differs. Mutates position management state exactly as
    the rules dictate: bars_open, tp flags, breakeven + trailing stop."""
    pos.bars_open += 1
    out: list[tuple[float, float, str]] = []
    high, low, close = bar["high"], bar["low"], bar["close"]
    long = pos.side is Side.LONG
    remaining = pos.size

    # 1) stop-loss (close-confirmed per config, else intrabar)
    if exits_cfg.get("close_confirmed_stop", True):
        stop_hit = close <= pos.stop_loss if long else close >= pos.stop_loss
        stop_px = close
    else:
        stop_hit = low <= pos.stop_loss if long else high >= pos.stop_loss
        stop_px = pos.stop_loss
    if stop_hit:
        out.append((stop_px, remaining, "stop"))
        return out

    # 2) take-profits (partial) + breakeven + trailing
    tps = pos.take_profits
    if not pos.tp1_done and len(tps) >= 1:
        tp_px, frac = tps[0]
        if (high >= tp_px) if long else (low <= tp_px):
            size = min(pos.initial_size * frac, remaining)
            remaining -= size
            out.append((tp_px, size, "tp1"))
            pos.tp1_done = True
            pos.stop_loss = pos.entry_price  # move to breakeven
            pos.breakeven_set = True
    if pos.tp1_done and not pos.tp2_done and len(tps) >= 2:
        tp_px, frac = tps[1]
        if (high >= tp_px) if long else (low <= tp_px):
            size = min(pos.initial_size * frac, remaining)
            remaining -= size
            out.append((tp_px, size, "tp2"))
            pos.tp2_done = True

    # trailing after tp1
    if pos.tp1_done and pos.atr > 0:
        trail = exits_cfg.get("trail_atr_mult", 1.0) * pos.atr
        if long:
            pos.stop_loss = max(pos.stop_loss, close - trail)
        else:
            pos.stop_loss = min(pos.stop_loss, close + trail)

    # 3) time stop
    if (not pos.tp1_done
            and pos.bars_open >= exits_cfg.get("time_stop_bars", 12)):
        out.append((close, remaining, "time"))

    return out


class ExecutionAdapter(abc.ABC):
    @abc.abstractmethod
    async def open(self, intent: OrderIntent) -> Fill | None:
        ...

    @abc.abstractmethod
    async def on_bar(self, symbol: str, bar: dict, exits_cfg: dict) -> list[ExitEvent]:
        """Process SL/TP/trailing/time-stop for the open position on `symbol`."""

    @abc.abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abc.abstractmethod
    def get_equity(self) -> float:
        ...
