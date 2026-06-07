"""
Signal Engine V2 — pure 12-1 momentum, category-relative z-score.
Adapted for ETFs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SKIP_DAYS = 21
MOM_12M_DAYS = 252
MIN_HISTORY_DAYS = MOM_12M_DAYS + 1

def _period_return(prices: pd.Series, lookback: int, skip: int) -> float:
    if len(prices) <= lookback:
        return np.nan
    end = prices.iloc[-1 - skip]
    start = prices.iloc[-1 - lookback]
    if not np.isfinite(start) or not np.isfinite(end) or start <= 0:
        return np.nan
    return float(end / start - 1.0)

def compute_ticker_mom(prices: pd.Series) -> float:
    prices = prices.dropna()
    if len(prices) < MIN_HISTORY_DAYS:
        return np.nan
    return _period_return(prices, MOM_12M_DAYS, SKIP_DAYS)

def compute_cross_section(
    prices_df: pd.DataFrame,
    category_map: dict[str, str],
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Изчислява category-relative scores за cross-section в дадена дата.
    """
    if as_of is None:
        sliced = prices_df
    else:
        sliced = prices_df.loc[:as_of]

    if len(sliced) < MIN_HISTORY_DAYS:
        return pd.DataFrame(
            columns=[
                "date", "ticker", "mom_12_1", "category", "category_zscore",
                "raw_score", "percentile_rank", "unadj_percentile",
            ]
        )

    rows = []
    for ticker in sliced.columns:
        mom = compute_ticker_mom(sliced[ticker])
        if not np.isfinite(mom):
            continue
        category = category_map.get(ticker, "Universe")
        rows.append({"ticker": ticker, "mom_12_1": mom, "category": category})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    global_mean = df["mom_12_1"].mean()
    global_std = df["mom_12_1"].std()

    def _category_z(s: pd.Series) -> pd.Series:
        if len(s) > 1 and s.std() > 0:
            return (s - s.mean()) / s.std()
        if np.isfinite(global_std) and global_std > 0:
            return (s - global_mean) / global_std
        return s * 0.0

    df["category_zscore"] = df.groupby("category")["mom_12_1"].transform(_category_z)
    df["raw_score"] = df["category_zscore"]
    # percentile_rank = ранг В РАМКИТЕ НА КАТЕГОРИЯТА (както README обещава:
    # "ranked within its own category"). Радарът показва "най-добрия в класа си".
    df["percentile_rank"] = df.groupby("category")["category_zscore"].rank(pct=True) * 100.0
    # unadj_percentile = ГЛОБАЛЕН ранг по абсолютен 12-1 momentum (abs_strength).
    # Ползва се от Macro Heatmap за истински кросс-категориен макро сигнал.
    df["unadj_percentile"] = df["mom_12_1"].rank(pct=True) * 100.0
    df["date"] = sliced.index[-1]

    return df[
        [
            "date", "ticker", "mom_12_1", "category", "category_zscore",
            "raw_score", "percentile_rank", "unadj_percentile",
        ]
    ].reset_index(drop=True)
