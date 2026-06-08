"""Execution adapter interface. PaperBroker (sim) and CcxtBroker (testnet)
both implement it, so the engine is venue-agnostic."""
from __future__ import annotations

import abc
from dataclasses import dataclass

from ..models import Fill, OrderIntent, Position


@dataclass
class ExitEvent:
    position: Position
    price: float
    size: float
    pnl: float
    reason: str          # stop | tp1 | tp2 | trail | time | manual
    closed: bool         # True if the whole position is now closed


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
