"""
Screener metrics (Volatility, Sharpe, Drawdown, Return).
Compatible with pandas 2.x / 3.x and yfinance 1.x.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_1d_series(x) -> pd.Series:
    """
    Гарантира 1-D pd.Series с float стойности.
    Обработва: Series, DataFrame (1 или повече колони), numpy array.
    """
    if isinstance(x, pd.DataFrame):
        if x.shape[1] == 1:
            return x.iloc[:, 0].astype(float)
        # Ако има повече колони (MultiIndex остатък), вземи първата
        return x.iloc[:, 0].astype(float)
    if isinstance(x, pd.Series):
        return x.astype(float)
    # numpy array или друго
    return pd.Series(np.asarray(x).ravel(), dtype=float)


def compute_metrics(prices) -> dict[str, float]:
    p = _to_1d_series(prices).dropna()

    nan_result = {
        "ret_1m": np.nan, "ret_3m": np.nan, "ret_6m": np.nan, "ret_12m": np.nan,
        "vol_1m": np.nan, "vol_3m": np.nan, "vol_12m": np.nan,
        "sharpe_12m": np.nan, "max_dd_12m": np.nan,
        "dist_52w_high": np.nan, "drawdown_now": np.nan
    }

    if len(p) < 252:
        return nan_result

    # Returns
    def _ret(days: int) -> float:
        if len(p) <= days:
            return np.nan
        val_now  = float(p.iloc[-1])
        val_then = float(p.iloc[-1 - days])
        if val_then == 0 or not np.isfinite(val_then):
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
    if v12 is not None and np.isfinite(v12) and v12 > 0 and np.isfinite(r12):
        sharpe12 = r12 / v12
    else:
        sharpe12 = np.nan

    # Max Drawdown 12m (най-лошата точка за годината)
    p12      = p.iloc[-252:]
    roll_max = p12.cummax()
    dd       = (p12 - roll_max) / roll_max
    mdd      = float(dd.min())

    # Разстояние до 52-седмичния връх (колко под годишния максимум)
    hi_252 = float(p.iloc[-252:].max())
    last   = float(p.iloc[-1])
    dist_52w_high = (last / hi_252 - 1.0) if hi_252 > 0 else np.nan

    # Текущ drawdown — колко си НАДОЛУ сега спрямо пика в наличния прозорец
    peak = float(p.cummax().iloc[-1])
    drawdown_now = (last / peak - 1.0) if peak > 0 else np.nan

    def _pct(v):
        return round(float(v) * 100.0, 4) if np.isfinite(v) else np.nan

    return {
        "ret_1m":     _pct(r1),
        "ret_3m":     _pct(r3),
        "ret_6m":     _pct(r6),
        "ret_12m":    _pct(r12),
        "vol_1m":     _pct(v1),
        "vol_3m":     _pct(v3),
        "vol_12m":    _pct(v12),
        "sharpe_12m": round(float(sharpe12), 4) if np.isfinite(sharpe12) else np.nan,
        "max_dd_12m": _pct(mdd),
        "dist_52w_high": _pct(dist_52w_high),
        "drawdown_now":  _pct(drawdown_now),
    }


def run_screener(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    Изчислява метрики за всеки тикър в prices_df.
    prices_df трябва да е плосък DataFrame (не MultiIndex колони).
    """
    # Ако колоните са MultiIndex, сплескай до последното ниво (тикъри)
    if isinstance(prices_df.columns, pd.MultiIndex):
        prices_df = prices_df.copy()
        prices_df.columns = prices_df.columns.get_level_values(-1)

    rows = []
    for ticker in prices_df.columns:
        col = prices_df[ticker]
        m = compute_metrics(col)
        m["ticker"] = ticker
        rows.append(m)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
