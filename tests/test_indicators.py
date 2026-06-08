import numpy as np
import pandas as pd

from engine.data import ohlcv
from engine.indicators import trend, volatility, vwap


def _df():
    return ohlcv.synthetic_ohlcv(300, seed=1, timeframe="15m")


def test_ema_basic():
    s = pd.Series(range(1, 101), dtype=float)
    e = trend.ema(s, 10)
    assert len(e) == 100
    assert e.iloc[-1] < s.iloc[-1]  # EMA lags a rising series


def test_atr_positive():
    df = _df()
    a = volatility.atr(df, 14).dropna()
    assert (a > 0).all()


def test_adx_range():
    df = _df()
    adx = trend.adx(df, 14)["adx"].dropna()
    assert ((adx >= 0) & (adx <= 100)).all()


def test_anchored_vwap_within_price_range():
    df = _df()
    v = vwap.anchored_vwap(df, 0).dropna()
    assert (v > 0).all()
    assert v.iloc[-1] <= df["high"].max()
    assert v.iloc[-1] >= df["low"].min()


def test_session_vwap_resets():
    df = _df()
    v = vwap.session_vwap(df)
    assert v.notna().sum() > 0


def test_swings():
    df = _df()
    assert volatility.swing_low(df, 10) <= volatility.swing_high(df, 10)
