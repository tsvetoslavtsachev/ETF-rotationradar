"""
Intermarket корелационна леща (INIT-22 S17, Build B).

Порт на уникалната леща от старото ETF-Dashboard (`fetch_data.py:320`
compute_intermarket_correlations) преди неговия retire: за всеки ETF —
корелацията на доходностите му спрямо 10 кросmarket котви-репери (акции/
облигации/злато/петрол/долар/EM/кредит/уран/чипове/отбрана). „С кого се движи
всеки фонд."

Конвенция: СЕДМИЧНИ доходности (W-FRI), два прозореца — 26 седмици (~полугодие,
„скорошно скачване") и 52 седмици (~година, „структурно скачване"). Седмично, а
НЕ дневно (както старото табло), по СЪЩАТА причина като бетата в S18: дневните
корелации подценяват международните/суровинните ETF спрямо US-сесийните котви
заради часовия десинхрон (вж. Dimson / Scholes-Williams). А котвите
GLD/USO/EEM/UUP са самата сърцевина на кросmarket четенето — ако техните колони
са систематично подценени, лещата губи смисъл точно където е най-ценна.

Чете вече свалените цени (всичките 10 котви са във вселената на ETF-rr) → нула
нови заявки. ADDITIVE към ETF-rr.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 10-те кросmarket котви-репери. Всичките са във вселената на ETF-rr (проверено
# S17 Build B ред по ред в universe.py) → нула нови заявки.
INTERMARKET_ANCHORS = ["SPY", "TLT", "GLD", "USO", "UUP", "EEM", "HYG", "URA", "SOXX", "ITA"]

# Седмични прозорци (W-FRI доходности).
WINDOW_SHORT_WEEKS = 26   # ≈ полугодие — „скорошно скачване"
WINDOW_LONG_WEEKS = 52    # ≈ година — „структурно скачване" (конвенцията на бетата)
MIN_OBS_SHORT = 20        # от 26 възможни седмични доходности
MIN_OBS_LONG = 40         # от 52 възможни


def _rolling_corr(a: pd.Series, b: pd.Series, window: int, min_obs: int):
    """Pearson корелация на последните `window` припокрити седмици; None ако < min_obs."""
    pair = pd.concat([a, b], axis=1).dropna().tail(window)
    if len(pair) < min_obs:
        return None
    c = pair.iloc[:, 0].corr(pair.iloc[:, 1])
    return round(float(c), 2) if np.isfinite(c) else None


def compute_intermarket(prices_df: pd.DataFrame, anchors: "list | None" = None) -> dict:
    """
    За всеки ETF в `prices_df` → седмична корелация спрямо всяка котва, два прозореца.

    Връща dict, готов за payload:
      {
        "basis":   "weekly",
        "windows": [26, 52],
        "anchors": [<котви, налични в цените>],
        "data":    {ticker: {anchor: {"c26": float|None, "c52": float|None}}},
      }
    Котвата спрямо себе си се пропуска. ETF без нито един валиден прозорец отпада.
    """
    anchors = anchors or INTERMARKET_ANCHORS
    meta = {"basis": "weekly", "windows": [WINDOW_SHORT_WEEKS, WINDOW_LONG_WEEKS]}
    empty = {**meta, "anchors": [], "data": {}}
    if prices_df is None or prices_df.empty:
        return empty

    # Сплескай евентуален MultiIndex (както filter_prices прави) + махни дубли колони.
    df = prices_df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    df = df.loc[:, ~df.columns.duplicated()]

    # Седмични доходности (W-FRI) — конвенцията на инструмента.
    weekly = df.resample("W-FRI").last()
    rets = weekly.pct_change(fill_method=None)

    present = [a for a in anchors if a in rets.columns]
    if not present:
        return empty

    data: dict = {}
    for sym in rets.columns:
        sret = rets[sym]
        block: dict = {}
        for anchor in present:
            if anchor == sym:
                continue
            aret = rets[anchor]
            c26 = _rolling_corr(sret, aret, WINDOW_SHORT_WEEKS, MIN_OBS_SHORT)
            c52 = _rolling_corr(sret, aret, WINDOW_LONG_WEEKS, MIN_OBS_LONG)
            if c26 is not None or c52 is not None:
                block[anchor] = {"c26": c26, "c52": c52}
        if block:
            data[sym] = block

    return {**meta, "anchors": present, "data": data}
