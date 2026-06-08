"""PaperBroker: simulated execution against live/replayed prices with an
explicit fee + slippage model (council: never use frictionless fills — they
flatter the strategy). Manages SL/TP1/TP2/breakeven/trailing/time-stop."""
from __future__ import annotations

import logging

from ..models import Fill, OrderIntent, Position, Side
from .base import ExecutionAdapter, ExitEvent

log = logging.getLogger("execution.paper")


class PaperBroker(ExecutionAdapter):
    def __init__(self, starting_equity: float = 10_000.0,
                 fee_rate: float = 0.001, slippage_pct: float = 0.0005):
        self.equity = starting_equity
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []

    # --- ExecutionAdapter ---------------------------------------------------
    async def open(self, intent: OrderIntent) -> Fill | None:
        sig = intent.signal
        if sig.symbol in self.positions:
            return None  # one position per symbol in MVP
        # slippage works against us on entry
        fill_price = sig.entry_price * (1 + self.slippage_pct * sig.side.sign)
        fee = fill_price * intent.size * self.fee_rate
        self.equity -= fee
        pos = Position(
            symbol=sig.symbol, side=sig.side, size=intent.size,
            entry_price=fill_price, stop_loss=sig.stop_loss,
            take_profits=list(sig.take_profits), intent_id=intent.id,
            initial_size=intent.size, atr=sig.atr, fees_paid=fee,
        )
        self.positions[sig.symbol] = pos
        fill = Fill(order_id=intent.client_order_id, symbol=sig.symbol,
                    side=sig.side, price=fill_price, size=intent.size, fee=fee)
        self.fills.append(fill)
        return fill

    async def on_bar(self, symbol: str, bar: dict, exits_cfg: dict) -> list[ExitEvent]:
        pos = self.positions.get(symbol)
        if pos is None:
            return []
        pos.bars_open += 1
        events: list[ExitEvent] = []
        high, low, close = bar["high"], bar["low"], bar["close"]
        long = pos.side is Side.LONG

        # 1) stop-loss (close-confirmed per config, else intrabar)
        if exits_cfg.get("close_confirmed_stop", True):
            stop_hit = close <= pos.stop_loss if long else close >= pos.stop_loss
            stop_px = close
        else:
            stop_hit = low <= pos.stop_loss if long else high >= pos.stop_loss
            stop_px = pos.stop_loss
        if stop_hit:
            events.append(self._close(pos, stop_px, "stop"))
            return events

        # 2) take-profits (partial) + breakeven + trailing
        tps = pos.take_profits
        if not pos.tp1_done and len(tps) >= 1:
            tp_px = tps[0][0]
            if (high >= tp_px) if long else (low <= tp_px):
                events.append(self._partial(pos, tp_px, tps[0][1], "tp1"))
                pos.tp1_done = True
                pos.stop_loss = pos.entry_price  # move to breakeven
                pos.breakeven_set = True
        if pos.tp1_done and not pos.tp2_done and len(tps) >= 2:
            tp_px = tps[1][0]
            if (high >= tp_px) if long else (low <= tp_px):
                events.append(self._partial(pos, tp_px, tps[1][1], "tp2"))
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
            events.append(self._close(pos, close, "time"))

        return events

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def get_equity(self) -> float:
        mark_pnl = sum(p.unrealized_pnl(p.entry_price) for p in self.positions.values())
        return self.equity + mark_pnl

    # --- helpers ------------------------------------------------------------
    def _partial(self, pos: Position, price: float, fraction: float,
                 reason: str) -> ExitEvent:
        size = pos.initial_size * fraction
        size = min(size, pos.size)
        return self._reduce(pos, price, size, reason)

    def _close(self, pos: Position, price: float, reason: str) -> ExitEvent:
        return self._reduce(pos, price, pos.size, reason)

    def _reduce(self, pos: Position, price: float, size: float,
                reason: str) -> ExitEvent:
        exit_px = price * (1 - self.slippage_pct * pos.side.sign)
        pnl = (exit_px - pos.entry_price) * size * pos.side.sign
        fee = exit_px * size * self.fee_rate
        self.equity += pnl - fee
        pos.realized_pnl += pnl - fee
        pos.fees_paid += fee
        pos.size -= size
        closed = pos.size <= 1e-12
        if closed:
            self.positions.pop(pos.symbol, None)
        return ExitEvent(position=pos, price=exit_px, size=size,
                         pnl=pnl - fee, reason=reason, closed=closed)
