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


_OHLCV_FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def download_ohlcv(
    tickers: list[str],
    start: "pd.Timestamp | str | None" = None,
    end: "pd.Timestamp | str | None" = None,
    period: "str | None" = None,
) -> "dict[str, pd.DataFrame]":
    """
    Сваля OHLCV (adjusted) за списък тикъри с ЕДНО извикване на yfinance.
    Връща dict {field: DataFrame}, всеки плосък (DatetimeIndex × тикъри като колони),
    field ∈ {"Open","High","Low","Close","Volume"}.

    Това е надмножество на download_prices(): out["Close"] е идентичен на стария
    плосък frame, така че целият downstream pipeline работи без промяна.
    auto_adjust=True → OHLC са split/dividend-adjusted; Volume е реалният обем
    (за скорошен оборот в $ ефектът от корекцията е пренебрежим).
    """
    empty = {f: pd.DataFrame() for f in _OHLCV_FIELDS}
    if not tickers:
        return empty

    kwargs: dict = {"auto_adjust": True, "progress": False, "threads": True}
    if period:
        kwargs["period"] = period
    else:
        kwargs["start"] = start
        kwargs["end"] = end

    try:
        raw = yf.download(tickers, **kwargs)
    except Exception as e:
        print(f"Error downloading OHLCV: {e}")
        return empty

    if raw is None or raw.empty:
        return empty

    out: dict[str, pd.DataFrame] = {}
    for field in _OHLCV_FIELDS:
        if isinstance(raw.columns, pd.MultiIndex):
            if field not in raw.columns.get_level_values(0):
                continue
            frame = raw[field].copy()
        else:
            # Единичен тикър без MultiIndex
            if field not in raw.columns:
                continue
            frame = raw[[field]].copy()
            frame.columns = [tickers[0]]

        frame.index = pd.to_datetime(frame.index).normalize()
        frame = frame.dropna(axis=1, how="all")
        out[field] = frame.astype(float)

    # Гарантираме, че всички ключове съществуват (дори празни)
    for f in _OHLCV_FIELDS:
        out.setdefault(f, pd.DataFrame())
    return out
