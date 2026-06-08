"""Strategy registry + regime router."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..models import Signal
from .base import Strategy
from .vwap_meanrev import VwapMeanRevStrategy
from .vwap_trend import VwapTrendStrategy

REGISTRY: dict[str, type[Strategy]] = {
    VwapTrendStrategy.name: VwapTrendStrategy,
    VwapMeanRevStrategy.name: VwapMeanRevStrategy,
}


class RegimeRouter(Strategy):
    """Runs trend-pullback in trend regimes and mean-reversion in ranges.
    Each child only fires in its own regime, so trying both is safe."""
    name = "regime_router"

    def __init__(self, params: dict):
        super().__init__(params)
        self.trend = VwapTrendStrategy(params)
        self.meanrev = VwapMeanRevStrategy(params)

    def evaluate(self, symbol, df, htf) -> Optional[Signal]:
        return self.trend.evaluate(symbol, df, htf) or \
            self.meanrev.evaluate(symbol, df, htf)


def build_strategy(settings) -> Strategy:
    """Merge strategy + exits params and instantiate the active strategy."""
    params = dict(settings.strategy)
    params["_exits"] = dict(settings.exits)
    params.update({k: v for k, v in settings.exits.items()})

    if settings.strategy.get("regime_switch"):
        return RegimeRouter(params)
    name = settings.strategy.get("active", "vwap_trend")
    return REGISTRY.get(name, VwapTrendStrategy)(params)
