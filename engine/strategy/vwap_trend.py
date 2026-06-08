"""VWAP trend-pullback strategy (primary).

Buys a pullback to anchored VWAP inside a confirmed up-trend (mirror for
shorts). Produces a Signal with full plain-language rationale so the co-pilot
can explain *why* to the human."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..models import OrderType, Regime, Side, Signal
from .base import Features, Strategy, build_features


def _take_profits(entry: float, stop: float, side: Side, exits: dict):
    d = abs(entry - stop)
    sign = side.sign
    tp1 = entry + sign * exits.get("tp1_r", 1.0) * d
    tp2 = entry + sign * exits.get("tp2_r", 2.0) * d
    return [
        (tp1, exits.get("tp1_fraction", 0.5)),
        (tp2, exits.get("tp2_fraction", 0.25)),
    ]


class VwapTrendStrategy(Strategy):
    name = "vwap_trend"

    def evaluate(self, symbol, df: pd.DataFrame,
                 htf: pd.DataFrame) -> Optional[Signal]:
        # Try long first, then short (anchor differs by side).
        for side in (Side.LONG, Side.SHORT):
            feats = build_features(df, htf, self.params, side_long=(side is Side.LONG))
            if feats is None:
                continue
            sig = self._check(symbol, side, feats)
            if sig is not None:
                return sig
        return None

    def _check(self, symbol, side: Side, f: Features) -> Optional[Signal]:
        want_regime = Regime.TREND_UP if side is Side.LONG else Regime.TREND_DOWN
        if f.regime is not want_regime:
            return None

        tol = self.params.get("pullback_tolerance_pct", 0.0005)
        no_chase = self.params.get("no_chase_atr_mult", 0.5)
        exits = self.params.get("_exits", {})

        rationale = [f"מגמת {'עליה' if side is Side.LONG else 'ירידה'} מאושרת "
                     f"(ADX={f.adx:.0f}, EMA{'>' if side is Side.LONG else '<'} + פילטר HTF)"]

        if side is Side.LONG:
            tagged = f.low <= f.vwap * (1 + tol)
            confirm = f.close > f.open and f.close > f.vwap
            extended = (f.close - f.vwap) > no_chase * f.atr
        else:
            tagged = f.high >= f.vwap * (1 - tol)
            confirm = f.close < f.open and f.close < f.vwap
            extended = (f.vwap - f.close) > no_chase * f.atr

        if not tagged:
            return None
        rationale.append("מחיר נגע ב-VWAP (pullback)")
        if not confirm:
            return None
        rationale.append("נר אישור סגר בכיוון המגמה (reclaim)")
        if extended:
            return None  # FOMO / no-chase guard
        rationale.append("המחיר לא מתוח — לא רדיפה")

        entry = f.close
        stop_atr = self.params.get("stop_atr_mult", 1.0)
        buf = self.params.get("stop_buffer_atr_mult", 0.25)
        if side is Side.LONG:
            sl = min(f.swing_low - buf * f.atr, f.vwap - stop_atr * f.atr)
        else:
            sl = max(f.swing_high + buf * f.atr, f.vwap + stop_atr * f.atr)

        tps = _take_profits(entry, sl, side, exits)
        rationale.append(
            f"SL מתחת ל-swing/VWAP−ATR, יעד ראשון ב-1R, שני ב-2R")

        return Signal(
            symbol=symbol, side=side, strategy=self.name,
            entry_type=OrderType.LIMIT, entry_price=entry, stop_loss=sl,
            take_profits=tps, atr=f.atr, regime=f.regime, rationale=rationale,
        )
