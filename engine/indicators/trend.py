"""EMA, ADX and directional movement. Pure functions over OHLCV DataFrames."""
from __future__ import annotations

import pandas as pd

from .volatility import true_range


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Wilder ADX. Returns DataFrame with columns adx, plus_di, minus_di."""
    up = df["high"].diff()
    down = -df["low"].diff()

    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down

    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    adx_ = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    return pd.DataFrame(
        {"adx": adx_, "plus_di": plus_di, "minus_di": minus_di}
    )


def ema_rising(series: pd.Series, period: int, lookback: int = 3) -> bool:
    """True if the EMA is higher than it was `lookback` bars ago."""
    e = ema(series, period)
    if len(e) <= lookback or pd.isna(e.iloc[-1]) or pd.isna(e.iloc[-1 - lookback]):
        return False
    return bool(e.iloc[-1] > e.iloc[-1 - lookback])
