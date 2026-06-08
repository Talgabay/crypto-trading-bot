"""Replay backtester: feeds historical candles through the EXACT live pipeline
(TradingEngine + PaperBroker) in AUTO mode. Because it reuses the live code
path, backtest behaviour == live behaviour (council requirement). Costs
(fees+slippage) are modelled in PaperBroker, so results are not flattered."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pandas as pd

from engine.approval import ApprovalQueue
from engine.core import TradingEngine
from engine.data.feed import ReplayFeed
from engine.execution import PaperBroker
from engine.models import AutonomyMode
from engine.notify import NotificationHub


@dataclass
class BacktestResult:
    start_equity: float
    end_equity: float
    trades: int
    wins: int
    equity_curve: list[float] = field(default_factory=list)

    @property
    def return_pct(self) -> float:
        if not self.start_equity:
            return 0.0
        return (self.end_equity / self.start_equity - 1) * 100

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100) if self.trades else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        peak = -1e18
        mdd = 0.0
        for e in self.equity_curve:
            peak = max(peak, e)
            mdd = min(mdd, (e / peak - 1) if peak > 0 else 0)
        return mdd * 100

    def summary(self) -> str:
        return (f"trades={self.trades} win_rate={self.win_rate:.1f}% "
                f"return={self.return_pct:+.2f}% "
                f"maxDD={self.max_drawdown_pct:.2f}% "
                f"equity {self.start_equity:.0f}->{self.end_equity:.0f}")


def run_replay(settings, df_map: dict[str, pd.DataFrame],
               starting_equity: float = 10_000.0) -> BacktestResult:
    broker = PaperBroker(
        starting_equity=starting_equity,
        fee_rate=settings.risk.get("fee_round_trip_pct", 0.002) / 2,
        slippage_pct=settings.risk.get("slippage_assumption_pct", 0.0007),
    )
    engine = TradingEngine(
        settings, broker, ApprovalQueue(timeout_sec=1),
        NotificationHub(), autonomy=AutonomyMode.AUTO, persist=False,
    )
    feed = ReplayFeed(df_map, settings.universe.get("htf_timeframe", "1h"),
                      warmup=120)

    result = BacktestResult(start_equity=starting_equity,
                            end_equity=starting_equity, trades=0, wins=0)

    async def _drive():
        for ev in feed:
            await engine.process_bar(ev)
            result.equity_curve.append(broker.get_equity())
        result.end_equity = broker.get_equity()

    asyncio.run(_drive())
    # discipline.followed records every CLOSED trade with its realized pnl
    result.trades = engine.discipline.followed.total
    result.wins = engine.discipline.followed.wins
    return result
