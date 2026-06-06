"""
Screener metrics (Volatility, Sharpe, Drawdown, Return).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

def compute_metrics(prices: pd.Series) -> dict[str, float]:
    p = prices.dropna()
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
        return float(p.iloc[-1] / p.iloc[-1 - days] - 1.0)

    r1 = _ret(21)
    r3 = _ret(63)
    r6 = _ret(126)
    r12 = _ret(252)

    # Volatility (annualized)
    def _vol(days: int) -> float:
        if len(p) <= days:
            return np.nan
        rets = p.iloc[-days:].pct_change().dropna()
        if len(rets) < 2:
            return np.nan
        return float(rets.std() * np.sqrt(252))

    v1 = _vol(21)
    v3 = _vol(63)
    v12 = _vol(252)

    # Sharpe (assumes 0 risk-free rate for simplicity)
    sharpe12 = (r12 / v12) if v12 and v12 > 0 else np.nan

    # Max Drawdown 12m
    p12 = p.iloc[-252:]
    roll_max = p12.cummax()
    dd = (p12 - roll_max) / roll_max
    mdd = float(dd.min())

    return {
        "ret_1m": r1 * 100.0 if np.isfinite(r1) else np.nan,
        "ret_3m": r3 * 100.0 if np.isfinite(r3) else np.nan,
        "ret_6m": r6 * 100.0 if np.isfinite(r6) else np.nan,
        "ret_12m": r12 * 100.0 if np.isfinite(r12) else np.nan,
        "vol_1m": v1 * 100.0 if np.isfinite(v1) else np.nan,
        "vol_3m": v3 * 100.0 if np.isfinite(v3) else np.nan,
        "vol_12m": v12 * 100.0 if np.isfinite(v12) else np.nan,
        "sharpe_12m": sharpe12,
        "max_dd_12m": mdd * 100.0 if np.isfinite(mdd) else np.nan
    }

def run_screener(prices_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ticker in prices_df.columns:
        m = compute_metrics(prices_df[ticker])
        m["ticker"] = ticker
        rows.append(m)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
