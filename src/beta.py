"""
90-дневна бета и корелация спрямо пазара (SPY) — per-ETF Screener метрики (S18).

На вече свалените цени (нула нови yfinance вызови). Дневни прости доходности върху
последните BETA_WINDOW ТЪРГОВСКИ дни (не календарни):
  beta = cov(r_etf, r_mkt) / var(r_mkt)   — наклон спрямо пазара (1.0 = като SPY)
  corr = Pearson(r_etf, r_mkt)            — плътност на следване (≈1 плътно, ≈0 диверсификатор)

Дефинитивно изчисление (без измислен праг). Конвенция: 90 търговски дни ≈ 4.3 месеца;
изискваме пълен прозорец, иначе тикърът се пропуска ('—' във фронтенда).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BETA_WINDOW = 90    # търговски дни
MARKET = "SPY"      # пазарен бенчмарк


def compute_betas(
    prices_df: pd.DataFrame,
    tickers: list,
    market: str = MARKET,
    window: int = BETA_WINDOW,
) -> pd.DataFrame:
    """
    Връща df[ticker, beta_90d, corr_90d]. Пропуска тикъри без пълен прозорец
    или без валидна пазарна дисперсия. Празен df ако пазарът липсва в цените.
    """
    if market not in prices_df.columns:
        return pd.DataFrame(columns=["ticker", "beta_90d", "corr_90d"])

    rets = prices_df.pct_change(fill_method=None)
    mkt = rets[market]
    rows = []
    for t in tickers:
        if t not in rets.columns:
            continue
        pair = pd.concat([rets[t], mkt], axis=1, keys=["etf", "mkt"]).dropna()
        pair = pair.tail(window)
        if len(pair) < window:
            continue
        var_m = float(pair["mkt"].var())
        if not np.isfinite(var_m) or var_m == 0:
            continue
        cov = float(pair["etf"].cov(pair["mkt"]))
        corr = float(pair["etf"].corr(pair["mkt"]))
        beta = cov / var_m
        rows.append({
            "ticker": t,
            "beta_90d": round(beta, 2) if np.isfinite(beta) else None,
            "corr_90d": round(corr, 2) if np.isfinite(corr) else None,
        })
    return pd.DataFrame(rows, columns=["ticker", "beta_90d", "corr_90d"])
