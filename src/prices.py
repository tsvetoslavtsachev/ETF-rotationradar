"""
Price fetching using yfinance.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

def download_prices(
    tickers: list[str],
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    period: str | None = None,
) -> pd.DataFrame:
    """
    Изтегля adjusted close цени за списък от тикъри.
    """
    if not tickers:
        return pd.DataFrame()

    kwargs = {"auto_adjust": True, "progress": False, "threads": True}
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

    if raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.levels[0]:
            close = raw["Close"]
        else:
            close = raw.xs("Close", level=0, axis=1)
    else:
        close = pd.DataFrame({tickers[0]: raw["Close"]}) if len(tickers) == 1 else raw

    close.index = pd.to_datetime(close.index).normalize()
    close = close.dropna(axis=1, how="all")
    return close
