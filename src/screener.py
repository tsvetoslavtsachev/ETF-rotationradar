"""
Screener metrics (Volatility, Sharpe, Drawdown, Return).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_series(x) -> pd.Series:
    """
    Гарантира, че входът е 1-D pd.Series с float стойности.
    Поправя проблема при yfinance >= 0.2.50 където prices_df[ticker]
    може да върне DataFrame с 1 колона вместо Series.
    """
    if isinstance(x, pd.DataFrame):
        x = x.squeeze(axis=1)
    if isinstance(x, pd.Series):
        # Ако Series има MultiIndex колони (рядко), вземи първата стойност
        return x.astype(float)
    return pd.Series(x, dtype=float)


def compute_metrics(prices) -> dict[str, float]:
    p = _to_series(prices).dropna()

    if len(p) < 252:
        return {
            "ret_1m": np.nan, "ret_3m": np.nan, "ret_6m": np.nan, "ret_12m": np.nan,
            "vol_1m": np.nan, "vol_3m": np.nan, "vol_12m": np.nan,
            "sharpe_12m": np.nan, "max_dd_12m": np.nan
        }

    # Returns
    def _ret(days: int) -> float:
        if len(p) <= days:
            return np.nan
        val_now = float(p.iloc[-1])
        val_then = float(p.iloc[-1 - days])
        if val_then == 0:
            return np.nan
        return val_now / val_then - 1.0

    r1  = _ret(21)
    r3  = _ret(63)
    r6  = _ret(126)
    r12 = _ret(252)

    # Volatility (annualized)
    def _vol(days: int) -> float:
        if len(p) <= days:
            return np.nan
        rets = p.iloc[-days:].pct_change().dropna()
        if len(rets) < 2:
            return np.nan
        return float(rets.std() * np.sqrt(252))

    v1  = _vol(21)
    v3  = _vol(63)
    v12 = _vol(252)

    # Sharpe (risk-free = 0)
    sharpe12 = (r12 / v12) if (v12 is not None and np.isfinite(v12) and v12 > 0 and np.isfinite(r12)) else np.nan

    # Max Drawdown 12m
    p12 = p.iloc[-252:]
    roll_max = p12.cummax()
    dd = (p12 - roll_max) / roll_max
    mdd = float(dd.min())

    def _pct(v):
        return round(v * 100.0, 4) if np.isfinite(v) else np.nan

    return {
        "ret_1m":    _pct(r1),
        "ret_3m":    _pct(r3),
        "ret_6m":    _pct(r6),
        "ret_12m":   _pct(r12),
        "vol_1m":    _pct(v1),
        "vol_3m":    _pct(v3),
        "vol_12m":   _pct(v12),
        "sharpe_12m": round(float(sharpe12), 4) if np.isfinite(sharpe12) else np.nan,
        "max_dd_12m": _pct(mdd),
    }


def run_screener(prices_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ticker in prices_df.columns:
        col = prices_df[ticker]
        # Squeeze в случай на MultiIndex колони
        if isinstance(col, pd.DataFrame):
            col = col.squeeze(axis=1)
        m = compute_metrics(col)
        m["ticker"] = ticker
        rows.append(m)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
