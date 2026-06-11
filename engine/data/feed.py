"""Feeds that yield CLOSED-bar windows. The ReplayFeed runs historical data
through the EXACT same pipeline as live (council: replay-mode is the primary
backtester that guarantees backtest == live). LiveFeed polls ccxt.

Only closed candles are ever exposed -> no lookahead bias."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterator

import pandas as pd

from . import ohlcv


@dataclass
class BarEvent:
    symbol: str
    exec_df: pd.DataFrame   # closed bars up to & including the current one
    htf_df: pd.DataFrame
    bar: dict               # latest closed bar (open/high/low/close/volume)


class ReplayFeed:
    """Iterate a historical frame one closed bar at a time."""

    def __init__(self, df_map: dict[str, pd.DataFrame], htf_rule: str,
                 warmup: int = 120):
        self.df_map = df_map
        self.htf_rule = htf_rule
        self.warmup = warmup

    def __iter__(self) -> Iterator[BarEvent]:
        for symbol, df in self.df_map.items():
            for i in range(self.warmup, len(df)):
                exec_df = df.iloc[: i + 1]
                htf_df = ohlcv.resample_htf(exec_df, self.htf_rule)
                bar = df.iloc[i]
                yield BarEvent(
                    symbol=symbol, exec_df=exec_df, htf_df=htf_df,
                    bar={"open": float(bar["open"]), "high": float(bar["high"]),
                         "low": float(bar["low"]), "close": float(bar["close"]),
                         "volume": float(bar["volume"])},
                )


class SyntheticLiveFeed:
    """Streams synthetic closed bars on a timer so the UI/Telegram demo is
    'alive' without API keys. Same BarEvent shape as the real feeds."""

    def __init__(self, symbols: list[str], timeframe: str, htf_rule: str,
                 interval_sec: float = 2.0, warmup: int = 130, bars: int = 1500):
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf_rule = htf_rule
        self.interval_sec = interval_sec
        self.warmup = warmup
        self._full = {
            sym: ohlcv.synthetic_ohlcv(bars, seed=7 + i, timeframe=timeframe)
            for i, sym in enumerate(symbols)
        }
        self._i = {sym: warmup for sym in symbols}

    async def stream(self):
        while True:
            for sym in self.symbols:
                df = self._full[sym]
                i = self._i[sym]
                if i >= len(df):
                    self._i[sym] = self.warmup  # loop the demo
                    continue
                exec_df = df.iloc[: i + 1]
                htf = ohlcv.resample_htf(exec_df, self.htf_rule)
                bar = df.iloc[i]
                self._i[sym] = i + 1
                yield BarEvent(
                    symbol=sym, exec_df=exec_df, htf_df=htf,
                    bar={"open": float(bar["open"]), "high": float(bar["high"]),
                         "low": float(bar["low"]), "close": float(bar["close"]),
                         "volume": float(bar["volume"])},
                )
            await asyncio.sleep(self.interval_sec)


class LiveFeed:
    """Poll ccxt for closed candles and emit a BarEvent when a new bar closes."""

    def __init__(self, ex, symbols: list[str], timeframe: str, htf_rule: str,
                 poll_sec: int = 15, limit: int = 500):
        self.ex = ex
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf_rule = htf_rule
        self.poll_sec = poll_sec
        self.limit = limit
        self._last_ts: dict[str, pd.Timestamp] = {}

    async def stream(self):
        while True:
            for symbol in self.symbols:
                try:
                    df = ohlcv.fetch_ohlcv(self.ex, symbol, self.timeframe,
                                           self.limit)
                except Exception:
                    continue
                if len(df) < 2:
                    continue
                # drop the still-forming last candle; use the last CLOSED one
                closed = df.iloc[:-1]
                ts = closed.index[-1]
                if self._last_ts.get(symbol) == ts:
                    continue
                self._last_ts[symbol] = ts
                htf = ohlcv.resample_htf(closed, self.htf_rule)
                bar = closed.iloc[-1]
                yield BarEvent(
                    symbol=symbol, exec_df=closed, htf_df=htf,
                    bar={"open": float(bar["open"]), "high": float(bar["high"]),
                         "low": float(bar["low"]), "close": float(bar["close"]),
                         "volume": float(bar["volume"])},
                )
            await asyncio.sleep(self.poll_sec)
