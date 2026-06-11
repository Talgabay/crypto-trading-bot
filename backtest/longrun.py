"""Long-horizon research backtest on FREE public Binance history.

Fetches paginated 15m klines from the public mainnet API (no key/account
needed), caches them under data/history/, replays the EXACT live pipeline
chronologically across all symbols (concurrent-position and daily-loss
limits bind realistically), and prints a research report: totals, monthly
breakdown, max drawdown, and a buy-and-hold benchmark.

    python -m backtest.longrun                  # 365 days, settings.yaml universe
    python -m backtest.longrun --days 730
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pandas as pd

from engine.approval import ApprovalQueue
from engine.config import Settings
from engine.core import TradingEngine
from engine.data import ohlcv
from engine.data.feed import BarEvent
from engine.execution import PaperBroker
from engine.models import AutonomyMode
from engine.notify import NotificationHub

CACHE = Path(__file__).resolve().parent.parent / "data" / "history"
WINDOW = 600  # rolling feature window; indicators converge well within it


def fetch_history(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Paginated fetch from the public mainnet data API, cached to CSV."""
    import ccxt

    CACHE.mkdir(parents=True, exist_ok=True)
    fname = CACHE / f"{symbol.replace('/', '_')}_{timeframe}_{days}d.csv"
    if fname.exists():
        df = pd.read_csv(fname, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    ex = ccxt.binance({"enableRateLimit": True})  # public market data only
    since = ex.milliseconds() - days * 86_400_000
    rows: list[list] = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = ohlcv.to_df(rows)
    df = df[~df.index.duplicated()]
    df.to_csv(fname)
    return df


class ChronoWindowFeed:
    """Replay all symbols merged on one clock (like live), with a rolling
    window per event — full-prefix frames would make a year-long replay
    O(n^2) in indicator time."""

    def __init__(self, df_map: dict[str, pd.DataFrame], htf_rule: str,
                 warmup: int = 130):
        self.df_map = df_map
        self.htf_rule = htf_rule
        self.warmup = warmup

    def __iter__(self):
        timeline: list[tuple[pd.Timestamp, str, int]] = []
        for sym, df in self.df_map.items():
            timeline += [(df.index[i], sym, i)
                         for i in range(self.warmup, len(df))]
        timeline.sort(key=lambda t: (t[0], t[1]))
        for ts, sym, i in timeline:
            df = self.df_map[sym]
            lo = max(0, i + 1 - WINDOW)
            exec_df = df.iloc[lo:i + 1]
            htf_df = ohlcv.resample_htf(exec_df, self.htf_rule)
            bar = df.iloc[i]
            yield BarEvent(
                symbol=sym, exec_df=exec_df, htf_df=htf_df,
                bar={"open": float(bar["open"]), "high": float(bar["high"]),
                     "low": float(bar["low"]), "close": float(bar["close"]),
                     "volume": float(bar["volume"])},
            )


def run(days: int, equity: float) -> None:
    settings = Settings()
    symbols = settings.universe.get("symbols", ["BTC/USDT"])
    tf = settings.universe.get("timeframe", "15m")
    htf = settings.universe.get("htf_timeframe", "1h")

    print(f"Fetching {days}d of {tf} history for {len(symbols)} symbols "
          f"(free public API, cached in data/history/)...")
    df_map = {}
    for sym in symbols:
        df_map[sym] = fetch_history(sym, tf, days)
        print(f"  {sym}: {len(df_map[sym])} bars "
              f"({df_map[sym].index[0].date()} -> {df_map[sym].index[-1].date()})")

    broker = PaperBroker(
        starting_equity=equity,
        fee_rate=settings.risk.get("fee_round_trip_pct", 0.002) / 2,
        slippage_pct=settings.risk.get("slippage_assumption_pct", 0.0007),
    )
    engine = TradingEngine(settings, broker, ApprovalQueue(timeout_sec=1),
                           NotificationHub(), autonomy=AutonomyMode.AUTO,
                           persist=False)
    feed = ChronoWindowFeed(df_map, htf)

    stamps: list[pd.Timestamp] = []
    curve: list[float] = []

    async def _drive():
        n = 0
        for ev in feed:
            await engine.process_bar(ev)
            stamps.append(ev.exec_df.index[-1])
            curve.append(broker.get_equity())
            n += 1
            if n % 20_000 == 0:
                print(f"  ...{n} bars processed, equity={curve[-1]:.0f}")

    asyncio.run(_drive())

    eq = pd.Series(curve, index=pd.DatetimeIndex(stamps)).groupby(level=0).last()
    end_equity = float(eq.iloc[-1])
    total_ret = end_equity / equity - 1
    yrs = days / 365
    cagr = (end_equity / equity) ** (1 / yrs) - 1 if yrs > 0 else 0.0
    peak = eq.cummax()
    maxdd = float(((eq / peak) - 1).min())

    monthly = eq.resample("ME").last().pct_change().dropna()
    first_month = eq.resample("ME").last().iloc[0] / equity - 1

    trades = engine.discipline.followed.total
    wins = engine.discipline.followed.wins

    print("\n================ RESULTS ================")
    print(f"period: {eq.index[0].date()} -> {eq.index[-1].date()} | "
          f"symbols: {len(symbols)}")
    print(f"trades={trades} win_rate="
          f"{(wins / trades * 100) if trades else 0:.1f}% "
          f"return={total_ret * 100:+.2f}% (CAGR {cagr * 100:+.1f}%/yr) "
          f"maxDD={maxdd * 100:.2f}%")
    print(f"equity {equity:.0f} -> {end_equity:.0f}")

    print("\n--- monthly returns ---")
    print(f"{eq.index[0].to_period('M')}: {first_month * 100:+.2f}% (partial)")
    for ts, r in monthly.items():
        print(f"{ts.to_period('M')}: {r * 100:+.2f}%")
    red = int((monthly < 0).sum()) + (1 if first_month < 0 else 0)
    tot_m = len(monthly) + 1
    print(f"red months: {red}/{tot_m} | "
          f"best {monthly.max() * 100:+.2f}% | worst {monthly.min() * 100:+.2f}%")

    print("\n--- buy & hold benchmark (same period) ---")
    bh = []
    for sym, df in df_map.items():
        r = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        bh.append(r)
        print(f"{sym}: {r * 100:+.2f}%")
    print(f"equal-weight portfolio: {sum(bh) / len(bh) * 100:+.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--equity", type=float, default=10_000.0)
    args = ap.parse_args()
    run(args.days, args.equity)


if __name__ == "__main__":
    main()
