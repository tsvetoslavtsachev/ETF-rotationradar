"""
1-годишна СЕДМИЧНА бета и корелация спрямо пазара (SPY) — per-ETF метрика (S18).

Конвенция на инструмента (Цветослав, S18): ТАКТИЧЕСКА бета за ротация — НЕ дългосрочна
оценъчна (cost-of-capital) бета. Седмични доходности (W-FRI) върху последните
BETA_WINDOW_WEEKS = 52 седмици (≈1 година):
  beta = cov(r_etf, r_mkt) / var(r_mkt)   — наклон спрямо пазара (1.0 = като SPY)
  corr = Pearson(r_etf, r_mkt)            — плътност на следване (≈1 плътно, ≈0 диверсификатор)

Защо СЕДМИЧНО, не дневно: международните/суровинните ETF (EWY=корейски акции, GLD=злато)
търгуват десинхронизирано спрямо US сесията → дневните доходности не се припокриват и
изкривяват бетата (даваше EWY 3.46, GLD 1.12 на дневна база). Седмичната доходност покрива
цялата седмица за двата пазара → структурно лекува десинхронизацията (вж. Dimson /
Scholes-Williams). Защо 1г, не 2г: инструментът е тактически (Rotation Radar) → отразява
ТЕКУЩИЯ режим; 2-годишната средна размива режимни промени (XLE сменяше знак −0.63→+0.36
според прозореца). Дефинитивно изчисление, без измислен праг. Изискваме пълен прозорец
(53 седмични цени), иначе тикърът се пропуска ('—' във фронтенда).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BETA_WINDOW_WEEKS = 52   # ≈1 година седмични доходности
MARKET = "SPY"           # пазарен бенчмарк


def compute_betas(
    prices_df: pd.DataFrame,
    tickers: list,
    market: str = MARKET,
    window: int = BETA_WINDOW_WEEKS,
) -> pd.DataFrame:
    """
    Връща df[ticker, beta_1y, corr_1y] — 1-годишна СЕДМИЧНА бета/корелация спрямо
    пазара. Пропуска тикъри без пълен прозорец или без валидна пазарна дисперсия.
    Празен df ако пазарът липсва в цените.
    """
    if market not in prices_df.columns:
        return pd.DataFrame(columns=["ticker", "beta_1y", "corr_1y"])

    weekly = prices_df.resample("W-FRI").last()
    rets = weekly.pct_change(fill_method=None)
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
            "beta_1y": round(beta, 2) if np.isfinite(beta) else None,
            "corr_1y": round(corr, 2) if np.isfinite(corr) else None,
        })
    return pd.DataFrame(rows, columns=["ticker", "beta_1y", "corr_1y"])
