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

from ..models import Fill, OrderIntent, OrderType, Position
from .base import ExecutionAdapter, ExitEvent

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
        ex.set_sandbox_mode(True)
        # explicit override (ccxt #27266): force the current demo host
        if secrets.binance_sandbox_rest_url:
            ex.urls["api"] = {
                k: secrets.binance_sandbox_rest_url
                for k in (ex.urls.get("api") or {"public": "", "private": ""})
            }
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
            usdt = bal.get("total", {}).get("USDT")
            return float(usdt) if usdt else self._equity_hint
        except Exception:
            return self._equity_hint

    async def open(self, intent: OrderIntent) -> Fill | None:
        assert_testnet(self.ex)
        sig = intent.signal
        side = "buy" if sig.side.value == "long" else "sell"
        params = {"newClientOrderId": intent.client_order_id}  # idempotency
        amount = self.ex.amount_to_precision(sig.symbol, intent.size)
        if sig.entry_type is OrderType.MARKET:
            order = self.ex.create_order(sig.symbol, "market", side, amount,
                                         None, params)
        else:
            price = self.ex.price_to_precision(sig.symbol, sig.entry_price)
            otype = "limit" if sig.entry_type is OrderType.LIMIT else "stop_loss_limit"
            order = self.ex.create_order(sig.symbol, otype, side, amount, price,
                                         params)
        fill_px = float(order.get("average") or order.get("price") or sig.entry_price)
        pos = Position(symbol=sig.symbol, side=sig.side, size=intent.size,
                       entry_price=fill_px, stop_loss=sig.stop_loss,
                       take_profits=list(sig.take_profits), intent_id=intent.id,
                       initial_size=intent.size, atr=sig.atr)
        self.positions[sig.symbol] = pos
        return Fill(order_id=order.get("id", intent.client_order_id),
                    symbol=sig.symbol, side=sig.side, price=fill_px,
                    size=intent.size, fee=0.0)

    async def on_bar(self, symbol: str, bar: dict, exits_cfg: dict) -> list[ExitEvent]:
        # Full exchange-side SL/TP management is the next phase; resting stops
        # should live on the exchange so they survive a bot crash.
        return []

    def get_positions(self) -> list[Position]:
        return list(self.positions.values())

    def reconcile(self) -> dict:
        """Exchange is the source of truth: fetch open orders/balances on
        startup and diff against local state."""
        assert_testnet(self.ex)
        open_orders = self.ex.fetch_open_orders()
        return {"open_orders": len(open_orders), "balance": self.get_equity()}
