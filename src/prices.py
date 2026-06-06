"""
Price fetching using yfinance.
Compatible with yfinance >= 0.2.x (including 1.x with MultiIndex columns).
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def download_prices(
    tickers: list[str],
    start: "pd.Timestamp | str | None" = None,
    end: "pd.Timestamp | str | None" = None,
    period: "str | None" = None,
) -> pd.DataFrame:
    """
    Изтегля adjusted close цени за списък от тикъри.
    Връща DataFrame с DatetimeIndex и тикъри като колони.
    Работи с всички версии на yfinance (включително 1.x).
    """
    if not tickers:
        return pd.DataFrame()

    kwargs: dict = {"auto_adjust": True, "progress": False, "threads": True}
    if period:
        kwargs["period"] = period
    else:
        kwargs["start"] = start
        kwargs["end"] = end

    try:
        raw = yf.download(tickers, **kwargs)
    except Exception as e:
        print(f"Error downloading prices: {e}")
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    # --- Нормализиране на колоните ---
    if isinstance(raw.columns, pd.MultiIndex):
        # Стандартен случай: (field, ticker) MultiIndex
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"].copy()
        else:
            # Fallback: вземи първото ниво
            close = raw.xs(raw.columns.get_level_values(0)[0], level=0, axis=1).copy()
    else:
        # Единичен тикър без MultiIndex
        if "Close" in raw.columns:
            close = raw[["Close"]].copy()
            close.columns = [tickers[0]]
        else:
            close = raw.copy()

    # Гарантираме чист DatetimeIndex
    close.index = pd.to_datetime(close.index).normalize()

    # Премахваме колони с изцяло NaN
    close = close.dropna(axis=1, how="all")

    # Гарантираме float dtype
    close = close.astype(float)

    return close
