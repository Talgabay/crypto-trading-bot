"""VWAP mean-reversion (range regime). Fades stretch from VWAP back toward it.
Activated by the regime router only when ADX indicates a range."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..indicators import vwap as vwap_ind
from ..models import OrderType, Regime, Side, Signal
from .base import Strategy, build_features


class VwapMeanRevStrategy(Strategy):
    name = "vwap_meanrev"

    def evaluate(self, symbol, df: pd.DataFrame,
                 htf: pd.DataFrame) -> Optional[Signal]:
        feats = build_features(df, htf, self.params, side_long=True)
        if feats is None or feats.regime is not Regime.RANGE:
            return None

        bands = vwap_ind.vwap_with_bands(feats.vwap_series, df, mult=2.0)
        upper = float(bands["upper"].iloc[-1])
        lower = float(bands["lower"].iloc[-1])
        c = feats.close
        buf = self.params.get("stop_buffer_atr_mult", 0.25)

        if c <= lower:  # stretched below -> long back to vwap
            side = Side.LONG
            sl = feats.swing_low - buf * feats.atr
            tp = feats.vwap
        elif c >= upper:  # stretched above -> short back to vwap
            side = Side.SHORT
            sl = feats.swing_high + buf * feats.atr
            tp = feats.vwap
        else:
            return None

        return Signal(
            symbol=symbol, side=side, strategy=self.name,
            entry_type=OrderType.LIMIT, entry_price=c, stop_loss=sl,
            take_profits=[(tp, 1.0)], atr=feats.atr, regime=Regime.RANGE,
            rationale=[
                f"שוק בריינג' (ADX={feats.adx:.0f})",
                "מחיר מתוח מ-VWAP — חזרה לממוצע",
            ],
        )
