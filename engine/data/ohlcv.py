"""OHLCV utilities: fetch from ccxt, build the HTF frame, and a synthetic
generator so the bot can be demoed/tested without network or keys."""
from __future__ import annotations

import numpy as np
import pandas as pd

_TF_RULE = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}


def to_df(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts")


def fetch_ohlcv(ex, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return to_df(rows)


def resample_htf(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    pr = _TF_RULE.get(rule, rule)
    out = df.resample(pr, label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()
    return out


def synthetic_ohlcv(n: int = 800, seed: int = 7, start: str = "2026-01-01",
                    timeframe: str = "15m") -> pd.DataFrame:
    """Generate a believable price series with alternating trend/range
    regimes so strategies have something to bite on in a demo."""
    rng = np.random.default_rng(seed)
    freq = _TF_RULE.get(timeframe, "15min")
    idx = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")

    price = 30_000.0
    closes = []
    drift = 0.0
    for i in range(n):
        if i % 120 == 0:  # switch regime periodically
            drift = rng.choice([0.0006, -0.0006, 0.0])
        shock = rng.normal(0, 0.0035)
        price *= (1 + drift + shock)
        closes.append(price)

    closes = np.array(closes)
    highs = closes * (1 + np.abs(rng.normal(0, 0.0025, n)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.0025, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    vol = rng.uniform(50, 500, n)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vol}, index=idx)
