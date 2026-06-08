"""CLI: run the replay backtest on synthetic data (default) or ccxt-fetched
historical OHLCV.

    python -m backtest.run                      # synthetic demo
    python -m backtest.run --symbol BTC/USDT    # live testnet data
"""
from __future__ import annotations

import argparse

from engine.config import get_settings
from engine.data import ohlcv

from .replay import run_replay


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="fetch real OHLCV for symbol")
    ap.add_argument("--bars", type=int, default=800)
    ap.add_argument("--equity", type=float, default=10_000.0)
    args = ap.parse_args()

    settings = get_settings()
    tf = settings.universe.get("timeframe", "15m")

    if args.symbol:
        from engine.execution.ccxt_adapter import build_exchange
        ex = build_exchange(settings.secrets)
        df = ohlcv.fetch_ohlcv(ex, args.symbol, tf, limit=args.bars)
        df_map = {args.symbol: df}
    else:
        df_map = {
            "BTC/USDT": ohlcv.synthetic_ohlcv(args.bars, seed=7, timeframe=tf),
            "ETH/USDT": ohlcv.synthetic_ohlcv(args.bars, seed=21, timeframe=tf),
        }

    print(f"Running replay backtest ({tf}) over "
          f"{', '.join(df_map)} ...")
    result = run_replay(settings, df_map, starting_equity=args.equity)
    print(result.summary())


if __name__ == "__main__":
    main()
