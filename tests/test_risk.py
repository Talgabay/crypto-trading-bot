from engine.models import OrderType, Regime, Side, Signal
from engine.risk import AccountState, RiskManager

PARAMS = {
    "risk_per_trade_pct": 0.005, "max_notional_pct": 0.25,
    "max_concurrent_positions": 3, "max_same_direction": 2,
    "daily_loss_limit_pct": 0.02, "max_trades_per_day": 8,
    "slippage_assumption_pct": 0.0007, "min_stop_distance_pct": 0.002,
    "fee_round_trip_pct": 0.002, "min_r_fee_multiple": 8,
}


def _sig(entry=100.0, stop=98.0):
    return Signal(symbol="BTC/USDT", side=Side.LONG, strategy="vwap_trend",
                  entry_type=OrderType.LIMIT, entry_price=entry, stop_loss=stop,
                  take_profits=[(104.0, 0.5), (108.0, 0.25)], atr=1.0,
                  regime=Regime.TREND_UP)


def _acct(**kw):
    base = dict(equity=10_000.0, start_of_day_equity=10_000.0)
    base.update(kw)
    return AccountState(**base)


def test_sizing_uses_risk_and_stop_distance():
    rm = RiskManager(PARAMS)
    d = rm.evaluate(_sig(100, 98), _acct())
    assert d.approved
    # risk 50 / (2 * 1.0007) ~= 24.98 units
    assert 24 < d.intent.size < 26


def test_rejects_tight_stop():
    rm = RiskManager(PARAMS)
    d = rm.evaluate(_sig(100, 99.95), _acct())  # 0.05% < min 0.2%
    assert not d.approved


def test_fee_gate_rejects_small_r():
    rm = RiskManager(PARAMS)
    # dist 1.0 (1%) passes min-stop but fails fee gate (need >= 1.6)
    d = rm.evaluate(_sig(100, 99.0), _acct())
    assert not d.approved
    assert "עמלות" in d.reason


def test_notional_cap_applies():
    rm = RiskManager(PARAMS)
    # huge equity -> uncapped size would exceed 25% notional cap
    d = rm.evaluate(_sig(100, 96.0), _acct(equity=1_000_000.0))
    assert d.approved
    assert d.intent.notional <= 0.25 * 1_000_000.0 + 1


def test_daily_loss_halts():
    rm = RiskManager(PARAMS)
    d = rm.evaluate(_sig(), _acct(daily_realized_pnl=-300.0))  # -3% < -2%
    assert not d.approved


def test_same_direction_guard():
    rm = RiskManager(PARAMS)
    d = rm.evaluate(_sig(100, 96.0),
                    _acct(open_sides=[Side.LONG, Side.LONG]))
    assert not d.approved


def test_cooldown_blocks():
    rm = RiskManager(PARAMS)
    d = rm.evaluate(_sig(100, 96.0), _acct(in_cooldown=True))
    assert not d.approved
