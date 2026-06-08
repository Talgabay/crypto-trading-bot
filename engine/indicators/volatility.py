"""ATR and swing-structure helpers. Pure functions over an OHLCV DataFrame
with columns: open, high, low, close, volume (DatetimeIndex, UTC)."""
from __future__ import annotations

import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    hl = df["high"] - df["low"]
    hc = (df["high"] - prev_close).abs()
    lc = (df["low"] - prev_close).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's ATR."""
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def swing_low(df: pd.DataFrame, lookback: int = 10) -> float:
    """Lowest low over the last `lookback` closed bars."""
    return float(df["low"].iloc[-lookback:].min())


def swing_high(df: pd.DataFrame, lookback: int = 10) -> float:
    """Highest high over the last `lookback` closed bars."""
    return float(df["high"].iloc[-lookback:].max())
