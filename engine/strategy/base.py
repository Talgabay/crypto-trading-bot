"""Strategy interface + shared feature computation.

A Strategy is a pure function of market state -> Optional[Signal]. The SAME
code runs in live and in replay/backtest, which is how we guarantee
backtest ~= live behaviour (council requirement)."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from ..indicators import trend, volatility, vwap
from ..models import Regime, Signal


@dataclass
class Features:
    """Latest indicator snapshot for the most recent CLOSED bar."""
    close: float
    open: float
    high: float
    low: float
    vwap: float
    vwap_series: pd.Series
    ema_fast: float
    ema_slow: float
    ema_fast_rising: bool
    adx: float
    atr: float
    swing_low: float
    swing_high: float
    htf_close: float
    htf_ema_slow: float
    regime: Regime


def build_features(df: pd.DataFrame, htf: pd.DataFrame, params: dict,
                   side_long: bool = True) -> Optional[Features]:
    """Compute features from CLOSED candles only. Returns None if not enough
    history (warm-up guard — prevents trading on half-formed indicators)."""
    ema_fast_p = params.get("ema_fast", 21)
    ema_slow_p = params.get("ema_slow", 50)
    adx_p = params.get("adx_period", 14)
    atr_p = params.get("atr_period", 14)
    warmup = max(ema_slow_p, adx_p, atr_p) + 5
    if len(df) < warmup or len(htf) < ema_slow_p + 2:
        return None

    anchor = vwap.prev_session_extreme_anchor(df, side_long=side_long)
    vwap_s = vwap.anchored_vwap(df, anchor)
    ema_fast_s = trend.ema(df["close"], ema_fast_p)
    ema_slow_s = trend.ema(df["close"], ema_slow_p)
    adx_df = trend.adx(df, adx_p)
    atr_s = volatility.atr(df, atr_p)
    htf_ema_slow = trend.ema(htf["close"], ema_slow_p)

    last = -1
    adx_min = params.get("adx_trend_min", 23)
    adx_val = float(adx_df["adx"].iloc[last]) if pd.notna(adx_df["adx"].iloc[last]) else 0.0
    c = float(df["close"].iloc[last])
    vw = float(vwap_s.iloc[last])
    ef = float(ema_fast_s.iloc[last])
    es = float(ema_slow_s.iloc[last])
    htf_c = float(htf["close"].iloc[last])
    htf_es = float(htf_ema_slow.iloc[last])

    # regime classification
    rising = trend.ema_rising(df["close"], ema_fast_p)
    if adx_val >= adx_min and c > vw and ef > es and rising and htf_c > htf_es:
        regime = Regime.TREND_UP
    elif adx_val >= adx_min and c < vw and ef < es and not rising and htf_c < htf_es:
        regime = Regime.TREND_DOWN
    elif adx_val <= params.get("adx_range_max", 18):
        regime = Regime.RANGE
    else:
        regime = Regime.NEUTRAL

    return Features(
        close=c, open=float(df["open"].iloc[last]),
        high=float(df["high"].iloc[last]), low=float(df["low"].iloc[last]),
        vwap=vw, vwap_series=vwap_s, ema_fast=ef, ema_slow=es,
        ema_fast_rising=rising, adx=adx_val, atr=float(atr_s.iloc[last]),
        swing_low=volatility.swing_low(df, 10),
        swing_high=volatility.swing_high(df, 10),
        htf_close=htf_c, htf_ema_slow=htf_es, regime=regime,
    )


class Strategy(abc.ABC):
    name: str = "base"

    def __init__(self, params: dict):
        self.params = params

    @abc.abstractmethod
    def evaluate(self, symbol: str, df: pd.DataFrame,
                 htf: pd.DataFrame) -> Optional[Signal]:
        ...
