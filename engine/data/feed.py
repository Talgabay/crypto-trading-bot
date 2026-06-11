"""Bar feeds. One event contract (`BarEvent`) drives both replay and live so
backtest behaviour == live behaviour (the engine cannot tell them apart).

    ReplayFeed        : sync iterator over historical frames (backtest/tests)
    SyntheticLiveFeed : async stream of generated bars (demo, no keys)
    LiveFeed          : async stream polling ccxt for new CLOSED candles
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import pandas as pd

from . import ohlcv

log = logging.getLogger(__name__)


@dataclass
class BarEvent:
    """A single CLOSED candle plus full history up to (and including) it.

    exec_df / htf_df are sliced with NO lookahead: the last row of exec_df is
    the bar in `bar`, and htf_df is resampled only from that visible history.
    """
    symbol: str
    bar: dict            # keys: ts, open, high, low, close, volume
    exec_df: pd.DataFrame
    htf_df: pd.DataFrame


def _bar_dict(df: pd.DataFrame, i: int) -> dict:
    row = df.iloc[i]
    return {
        "ts": df.index[i],
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row["volume"]),
    }


class ReplayFeed:
    """Iterate historical frames bar-by-bar, interleaved across symbols in
    chronological order, emitting a BarEvent per closed bar after `warmup`.
    """

    def __init__(self, df_map: dict[str, pd.DataFrame],
                 htf_timeframe: str = "1h", warmup: int = 120) -> None:
        self.df_map = {s: df.sort_index() for s, df in df_map.items()}
        self.htf_timeframe = htf_timeframe
        self.warmup = warmup

    def __iter__(self):
        # merge (timestamp, symbol, position) across symbols -> chronological
        schedule: list[tuple[pd.Timestamp, str, int]] = []
        for sym, df in self.df_map.items():
            for i in range(self.warmup, len(df)):
                schedule.append((df.index[i], sym, i))
        schedule.sort(key=lambda t: (t[0], t[1]))

        for _, sym, i in schedule:
            df = self.df_map[sym]
            exec_df = df.iloc[: i + 1]
            htf_df = ohlcv.resample_htf(exec_df, self.htf_timeframe)
            yield BarEvent(symbol=sym, bar=_bar_dict(df, i),
                           exec_df=exec_df, htf_df=htf_df)


class SyntheticLiveFeed:
    """Demo feed: pre-generates synthetic history per symbol, then streams it
    bar-by-bar with a short real-time delay (no exchange, no keys)."""

    def __init__(self, symbols: list[str], timeframe: str = "15m",
                 htf_timeframe: str = "1h", history_bars: int = 1_000,
                 interval_sec: float = 2.0) -> None:
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf_timeframe = htf_timeframe
        self.interval_sec = interval_sec
        self._frames = {
            sym: ohlcv.synthetic_ohlcv(history_bars, seed=idx * 101 + 7,
                                       timeframe=timeframe)
            for idx, sym in enumerate(symbols)
        }
        self._warmup = 200

    async def stream(self):
        frames = self._frames
        length = min(len(df) for df in frames.values())
        for i in range(self._warmup, length):
            for sym in self.symbols:
                df = frames[sym]
                exec_df = df.iloc[: i + 1]
                htf_df = ohlcv.resample_htf(exec_df, self.htf_timeframe)
                yield BarEvent(symbol=sym, bar=_bar_dict(df, i),
                               exec_df=exec_df, htf_df=htf_df)
            await asyncio.sleep(self.interval_sec)
        log.info("synthetic feed exhausted (%d bars)", length)


class LiveFeed:
    """Polls a (sync) ccxt exchange and emits a BarEvent whenever a NEW closed
    candle appears for a symbol. ccxt calls run in a thread so the event loop
    is never blocked."""

    def __init__(self, exchange, symbols: list[str], timeframe: str = "15m",
                 htf_timeframe: str = "1h", history_bars: int = 500,
                 poll_sec: float = 10.0) -> None:
        self.exchange = exchange
        self.symbols = symbols
        self.timeframe = timeframe
        self.htf_timeframe = htf_timeframe
        self.history_bars = history_bars
        self.poll_sec = poll_sec
        self._last_ts: dict[str, pd.Timestamp] = {}

    async def _fetch(self, symbol: str) -> pd.DataFrame:
        return await asyncio.to_thread(
            ohlcv.fetch_ohlcv, self.exchange, symbol,
            self.timeframe, self.history_bars,
        )

    async def stream(self):
        while True:
            for sym in self.symbols:
                try:
                    df = await self._fetch(sym)
                except Exception:
                    log.exception("fetch_ohlcv failed for %s", sym)
                    continue
                if df.empty:
                    continue
                ts = df.index[-1]
                if self._last_ts.get(sym) == ts:
                    continue  # no new closed bar yet
                self._last_ts[sym] = ts
                htf_df = ohlcv.resample_htf(df, self.htf_timeframe)
                yield BarEvent(symbol=sym, bar=_bar_dict(df, len(df) - 1),
                               exec_df=df, htf_df=htf_df)
            await asyncio.sleep(self.poll_sec)
