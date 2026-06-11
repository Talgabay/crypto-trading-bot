"""OHLCV utilities: synthetic candle generation (demo/backtest/tests),
higher-timeframe resampling, and ccxt historical fetch.

All DataFrames returned here share one schema:
    index   : tz-aware (UTC) DatetimeIndex, one row per CLOSED candle
    columns : open, high, low, close, volume   (float64)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# deterministic anchor so a given (n, seed, timeframe) always yields the
# exact same frame — required for reproducible tests and backtests
_SYNTH_ANCHOR = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")


def timeframe_to_offset(timeframe: str) -> pd.Timedelta:
    """'15m' -> Timedelta(15 min). Supports m/h/d suffixes (ccxt style)."""
    unit = timeframe[-1].lower()
    qty = int(timeframe[:-1])
    if unit == "m":
        return pd.Timedelta(minutes=qty)
    if unit == "h":
        return pd.Timedelta(hours=qty)
    if unit == "d":
        return pd.Timedelta(days=qty)
    raise ValueError(f"unsupported timeframe: {timeframe!r}")


def synthetic_ohlcv(
    n: int,
    seed: int = 0,
    timeframe: str = "15m",
    start_price: float = 30_000.0,
) -> pd.DataFrame:
    """Regime-switching geometric random walk with intrabar range + volume.

    Alternates trending and ranging regimes so the strategy's trend gate,
    pullback and mean-reversion paths all get exercised in tests/backtests.
    Deterministic for a given (n, seed, timeframe).
    """
    rng = np.random.default_rng(seed)
    step = timeframe_to_offset(timeframe)
    idx = pd.date_range(end=_SYNTH_ANCHOR + step * n, periods=n,
                        freq=step, tz="UTC", name="ts")

    # piecewise drift: alternating up-trend / range / down-trend regimes
    drift = np.zeros(n)
    i = 0
    while i < n:
        length = int(rng.integers(40, 120))
        mu = rng.choice([0.0006, 0.0, -0.0005], p=[0.4, 0.35, 0.25])
        drift[i:i + length] = mu
        i += length

    vol = 0.004  # per-bar log-return stdev (~15m crypto scale)
    rets = drift + rng.normal(0.0, vol, n)
    close = start_price * np.exp(np.cumsum(rets))

    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]

    # intrabar range as a fraction of price, skewed by bar direction
    spread = np.abs(rng.normal(0.0, vol, n)) * close
    high = np.maximum(open_, close) + spread * rng.uniform(0.2, 1.0, n)
    low = np.minimum(open_, close) - spread * rng.uniform(0.2, 1.0, n)

    # volume correlates with absolute return (busy bars trade more)
    base_vol = rng.lognormal(mean=2.0, sigma=0.5, size=n)
    volume = base_vol * (1.0 + 25.0 * np.abs(rets))

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low,
         "close": close, "volume": volume},
        index=idx,
    )
    return df.astype("float64")


def resample_htf(df: pd.DataFrame, htf_timeframe: str) -> pd.DataFrame:
    """Resample an execution-timeframe frame to a higher timeframe.

    Only fully formed candles relative to the input are returned; the label
    is the bar OPEN time (ccxt convention), so the last HTF row may still be
    'in progress' when used live — callers treat the last exec bar as the
    most recent closed information, which is consistent with the live feed.
    """
    rule = timeframe_to_offset(htf_timeframe)
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open", "close"])


def fetch_ohlcv(exchange, symbol: str, timeframe: str,
                limit: int = 500) -> pd.DataFrame:
    """Fetch closed candles via a (sync) ccxt exchange into the shared schema."""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["ts", *OHLCV_COLUMNS])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").astype("float64")
    # ccxt's last row is usually the still-forming candle -> drop it so the
    # engine only ever sees CLOSED bars (exit rules assume closed bars)
    if len(df) > 1:
        df = df.iloc[:-1]
    return df
