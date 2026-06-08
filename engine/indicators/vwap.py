"""VWAP variants. The council recommended *anchored* VWAP for 24/7 crypto
(calendar-session VWAP anchored at 00:00 UTC is arbitrary on a market with no
open/close). We support both, plus a band built from the rolling std of the
typical-price deviation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3.0


def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """Cumulative VWAP starting at integer position `anchor_idx`."""
    tp = _typical_price(df)
    vol = df["volume"].clip(lower=0)
    pv = (tp * vol).to_numpy()
    v = vol.to_numpy()

    out = np.full(len(df), np.nan)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(anchor_idx, len(df)):
        cum_pv += pv[i]
        cum_v += v[i]
        out[i] = cum_pv / cum_v if cum_v > 0 else tp.iloc[i]
    return pd.Series(out, index=df.index)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets each UTC calendar day (secondary confluence level)."""
    tp = _typical_price(df)
    pv = tp * df["volume"].clip(lower=0)
    day = df.index.tz_convert("UTC").date if df.index.tz else df.index.date
    grp = pd.Series(day, index=df.index)
    cum_pv = pv.groupby(grp).cumsum()
    cum_v = df["volume"].clip(lower=0).groupby(grp).cumsum().replace(0, np.nan)
    return cum_pv / cum_v


def prev_session_extreme_anchor(df: pd.DataFrame, side_long: bool) -> int:
    """Anchor index = the bar of the previous UTC session's extreme.

    For longs we anchor at the prior session LOW (are buyers since the low in
    profit?); for shorts, the prior session HIGH. Falls back to the start of
    the current session, then to 0.
    """
    if df.index.tz is None:
        days = pd.Series(df.index.date, index=df.index)
    else:
        days = pd.Series(df.index.tz_convert("UTC").date, index=df.index)

    unique_days = list(dict.fromkeys(days.tolist()))
    if len(unique_days) >= 2:
        prev_day = unique_days[-2]
        mask = (days == prev_day).to_numpy()
        idxs = np.where(mask)[0]
        sub = df.iloc[idxs]
        if side_long:
            local = int(sub["low"].to_numpy().argmin())
        else:
            local = int(sub["high"].to_numpy().argmax())
        return int(idxs[local])

    # only one session available -> anchor at its start
    cur_day = unique_days[-1]
    idxs = np.where((days == cur_day).to_numpy())[0]
    return int(idxs[0]) if len(idxs) else 0


def vwap_with_bands(
    vwap: pd.Series, df: pd.DataFrame, mult: float = 1.0
) -> pd.DataFrame:
    """Bands from the rolling std of close-to-VWAP deviation."""
    dev = (df["close"] - vwap)
    sd = dev.rolling(20, min_periods=5).std()
    return pd.DataFrame(
        {"vwap": vwap, "upper": vwap + mult * sd, "lower": vwap - mult * sd}
    )
