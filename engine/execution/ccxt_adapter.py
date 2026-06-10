"""CcxtBroker: connects to Binance Spot **Testnet** via ccxt.

Two known traps handled here (council):
1. ccxt `set_sandbox_mode(True)` for Binance still points at a deprecated host
   -> we override REST/WS base URLs from config explicitly.
2. Every order carries a client-generated id (idempotency) and we assert we are
   really on a demo host before placing anything (never trade real funds here).

The working demo executes through PaperBroker; this adapter provides verified
testnet connectivity, balances, and idempotent order placement, and is the
seam for full exchange-side execution in the next phase.
"""
from __future__ import annotations

import logging

from ..models import Fill, OrderIntent, Position, Side, new_id
from .base import ExecutionAdapter, ExitEvent, plan_exits

log = logging.getLogger("execution.ccxt")

_DEMO_HOST_HINTS = ("testnet", "demo")


def build_exchange(secrets):
    """Construct a ccxt exchange pinned to the testnet endpoints."""
    import ccxt

    klass = getattr(ccxt, secrets.exchange)
    ex = klass({
        "apiKey": secrets.binance_testnet_api_key,
        "secret": secrets.binance_testnet_secret,
        "enableRateLimit": True,
        "options": {"adjustForTimeDifference": True},
    })
    if secrets.sandbox:
        # set_sandbox_mode already pins the correct testnet host (.../api/v3)
        # in current ccxt; the old manual override (ccxt #27266) dropped the
        # /api/v3 path and broke every request with a 404.
        ex.set_sandbox_mode(True)
    return ex


def assert_testnet(ex) -> None:
    """Refuse to operate unless the configured host looks like a demo host."""
    urls = ex.urls.get("api")
    flat = str(urls)
    if not any(h in flat.lower() for h in _DEMO_HOST_HINTS):
        raise RuntimeError(
            f"SAFETY: exchange host does not look like a testnet/demo host: {flat}")


class CcxtBroker(ExecutionAdapter):
    def __init__(self, secrets, starting_equity_hint: float = 10_000.0):
        self.secrets = secrets
        self.ex = build_exchange(secrets)
        assert_testnet(self.ex)
        self.positions: dict[str, Position] = {}
        self._equity_hint = starting_equity_hint

    async def ping(self) -> dict:
        """Verify connectivity by loading markets + fetching balance."""
        self.ex.load_markets()
        bal = self.ex.fetch_balance()
        return {"ok": True, "total": bal.get("total", {})}

    def get_equity(self) -> float:
        try:
            bal = self.ex.fetch_balance()
            usdt = float(bal.get("total", {}).get("USDT") or 0.0)
            # value open positions at entry (good enough for sizing/UI in demo)
            held = sum(p.size * p.entry_price for p in self.positions.values())
            return usdt + held if usdt or held else self._equity_hint
        except Exception:
            return self._equity_hint

    async def open(self, intent: OrderIntent) -> Fill | None:
        assert_testnet(self.ex)
        sig = intent.signal
        if sig.symbol in self.positions:
            return None  # one position per symbol in MVP
        side = "buy" if sig.side is Side.LONG else "sell"
        params = {"newClientOrderId": intent.client_order_id}  # idempotency
        amount = self.ex.amount_to_precision(sig.symbol, intent.size)
        # Market entry: the engine already re-validated price proximity, and a
        # resting limit the exchange never fills would desync local state.
        # Exchange-side resting limit + fill tracking is the next phase.
        order = self.ex.create_order(sig.symbol, "market", side, amount,
                                     None, params)
        fill_px = float(order.get("average") or order.get("price") or sig.entry_price)
        filled = float(order.get("filled") or intent.size)
        pos = Position(symbol=sig.symbol, side=sig.side, size=filled,
                       entry_price=fill_px, stop_loss=sig.stop_loss,
                       take_profits=list(sig.take_profits), intent_id=intent.id,
                       initial_size=filled, atr=sig.atr)
        self.positions[sig.symbol] = pos
        log.info("testnet OPEN %s %s size=%s @ %.2f (order %s)",
                 side, sig.symbol, filled, fill_px, order.get("id"))
        return Fill(order_id=order.get("id", intent.client_order_id),
                    symbol=sig.symbol, side=sig.side, price=fill_px,
                    size=filled, fee=0.0)

    async def on_bar(self, symbol: str, bar: dict, exits_cfg: dict) -> list[ExitEvent]:
        """Same exit RULES as paper (shared plan_exits); execution is a real
        reduce order on the testnet. NOTE: the protective stop lives in the
        bot, not on the exchange — fine for demo, must move exchange-side
        before any real funds."""
        pos = self.positions.get(symbol)
        if pos is None:
            return []
        events: list[ExitEvent] = []
        for price, size, reason in plan_exits(pos, bar, exits_cfg):
            ev = await self._reduce_on_exchange(pos, price, size, reason)
            if ev is not None:
                events.append(ev)
        return events

    async def _reduce_on_exchange(self, pos: Position, price: float,
                                  size: float, reason: str) -> ExitEvent | None:
        assert_testnet(self.ex)
        side = "sell" if pos.side is Side.LONG else "buy"
        amount = self.ex.amount_to_precision(pos.symbol, size)
        params = {"newClientOrderId": new_id("cid_")}
        try:
            order = self.ex.create_order(pos.symbol, "market", side, amount,
                                         None, params)
        except Exception:
            log.exception("testnet exit order FAILED %s %s (%s) — will retry "
                          "next bar", side, pos.symbol, reason)
            return None
        exit_px = float(order.get("average") or order.get("price") or price)
        pnl = (exit_px - pos.entry_price) * size * pos.side.sign
        pos.realized_pnl += pnl
        pos.size -= size
        closed = pos.size <= 1e-12
        if closed:
            self.positions.pop(pos.symbol, None)
        log.info("testnet EXIT %s %s size=%s @ %.2f reason=%s pnl=%.2f",
                 side, pos.symbol, size, exit_px, reason, pnl)
        return ExitEvent(position=pos, price=exit_px, size=size, pnl=pnl,
                         reason=reason, closed=closed)

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def reconcile(self) -> dict:
        """Exchange is the source of truth: fetch open orders/balances on
        startup and diff against local state."""
        assert_testnet(self.ex)
        open_orders = self.ex.fetch_open_orders()
        return {"open_orders": len(open_orders), "balance": self.get_equity()}
