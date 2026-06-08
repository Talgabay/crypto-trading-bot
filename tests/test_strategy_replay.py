from engine.config import get_settings
from engine.coach.discipline import DisciplineGuard, TiltDetector
from engine.data import ohlcv
from engine.strategy import build_strategy
from backtest.replay import run_replay


def test_strategy_runs_without_error():
    settings = get_settings()
    strat = build_strategy(settings)
    df = ohlcv.synthetic_ohlcv(400, seed=3, timeframe="15m")
    htf = ohlcv.resample_htf(df, "1h")
    # should not raise; may or may not produce a signal on the last bar
    strat.evaluate("BTC/USDT", df, htf)


def test_replay_smoke():
    settings = get_settings()
    df_map = {"BTC/USDT": ohlcv.synthetic_ohlcv(600, seed=7, timeframe="15m")}
    result = run_replay(settings, df_map, starting_equity=10_000.0)
    assert result.end_equity > 0
    assert isinstance(result.summary(), str)
    assert result.trades >= 0


def test_tilt_triggers_cooldown():
    td = TiltDetector({"consecutive_loss_cooldown": 3, "cooldown_minutes": 60})
    assert td.record_trade(-10) is None
    assert td.record_trade(-10) is None
    msg = td.record_trade(-10)
    assert msg is not None
    assert td.state.in_cooldown()


def test_discipline_score():
    g = DisciplineGuard()
    g.record(was_override=False, pnl=10)
    g.record(was_override=True, pnl=-5)
    assert 0 <= g.discipline_score() <= 100
