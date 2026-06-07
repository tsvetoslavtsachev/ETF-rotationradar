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


# ── OHLCV-базирани метрики (ATR / Chandelier стоп / ликвидност) ──────────────
# Изискват High/Low/Close/Volume — затова идват от download_ohlcv(), не от
# download_prices() (който дава само Close).
ATR_PERIOD = 14           # период за ATR (Wilder smoothing)
CHANDELIER_LOOKBACK = 22  # прозорец за highest-high при Chandelier стопа
CHANDELIER_MULT = 3.0     # множител ATR за Chandelier стопа
DV_RECENT_DAYS = 20       # скорошен прозорец за среднодневен оборот ($)
DV_BASE_DAYS = 63         # базов прозорец за тренда на оборота
# Праг за "тънка" ликвидност — ЕВРИСТИКА, НЕ verified cutoff. Подлежи на калибрация.
LIQUIDITY_THIN_USD = 5_000_000  # ADV(20д) под това → liquidity_flag = "thin"

_OHLCV_NAN_RESULT = {
    "atr_14": np.nan, "atr_pct": np.nan,
    "chandelier_stop": np.nan, "stop_distance_pct": np.nan,
    "dollar_vol_20d": np.nan, "dollar_vol_trend": np.nan,
    "liquidity_flag": None,
}


def compute_ohlcv_metrics(high, low, close, volume) -> dict:
    """
    Метрики, които искат повече от Close:
      - atr_14 / atr_pct        : ATR(14) по Wilder + като % от цената (норм. волатилност)
      - chandelier_stop         : highest-high(22) − 3×ATR(14)  (дълъг trailing стоп)
      - stop_distance_pct       : (Close − стоп) / Close × 100 — служи и за оразмеряване
      - dollar_vol_20d          : среднодневен оборот в $ за последните 20 дни
      - dollar_vol_trend        : ADV(20д) спрямо ADV(63д), в %
      - liquidity_flag          : "thin" ако ADV(20д) < прага, иначе "ok"
    Входът са 1-D серии (или None, ако полето липсва) за ЕДИН тикър.
    """
    out = dict(_OHLCV_NAN_RESULT)
    if close is None:
        return out
    c = _to_1d_series(close).dropna()
    if len(c) < CHANDELIER_LOOKBACK + 1:
        return out

    # --- ATR + Chandelier (искат High/Low) ---
    if high is not None and low is not None:
        df = pd.concat(
            {"h": _to_1d_series(high), "l": _to_1d_series(low), "c": c}, axis=1
        ).dropna()
        if len(df) >= ATR_PERIOD + 1:
            prev_c = df["c"].shift(1)
            tr = pd.concat([
                df["h"] - df["l"],
                (df["h"] - prev_c).abs(),
                (df["l"] - prev_c).abs(),
            ], axis=1).max(axis=1)
            # Wilder smoothing == EMA с alpha = 1/period
            atr = tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False).mean()
            atr_last = float(atr.iloc[-1])
            c_last = float(df["c"].iloc[-1])
            out["atr_14"] = round(atr_last, 4)
            if c_last > 0:
                out["atr_pct"] = round(atr_last / c_last * 100.0, 4)
            if len(df) >= CHANDELIER_LOOKBACK:
                hh = float(df["h"].rolling(CHANDELIER_LOOKBACK).max().iloc[-1])
                chand = hh - CHANDELIER_MULT * atr_last
                out["chandelier_stop"] = round(chand, 4)
                if c_last > 0:
                    out["stop_distance_pct"] = round((c_last - chand) / c_last * 100.0, 4)

    # --- Оборот в $ + ликвиден флаг (иска Volume) ---
    if volume is not None:
        dv = (c * _to_1d_series(volume)).dropna()
        if len(dv) >= DV_RECENT_DAYS:
            adv_recent = float(dv.iloc[-DV_RECENT_DAYS:].mean())
            out["dollar_vol_20d"] = round(adv_recent, 2)
            out["liquidity_flag"] = "thin" if adv_recent < LIQUIDITY_THIN_USD else "ok"
            base_n = min(DV_BASE_DAYS, len(dv))
            adv_base = float(dv.iloc[-base_n:].mean())
            if adv_base > 0:
                out["dollar_vol_trend"] = round((adv_recent / adv_base - 1.0) * 100.0, 4)

    return out


def run_ohlcv_screener(ohlcv: "dict[str, pd.DataFrame]") -> pd.DataFrame:
    """
    Изчислява OHLCV метриките за всеки тикър в ohlcv["Close"].columns.
    `ohlcv` е dict от download_ohlcv() — {field: плосък DataFrame}.
    Връща DataFrame с колона `ticker` + новите метрики (за merge по ticker).
    """
    close = ohlcv.get("Close")
    if close is None or close.empty:
        return pd.DataFrame()
    high, low, volume = ohlcv.get("High"), ohlcv.get("Low"), ohlcv.get("Volume")

    def _col(frame, ticker):
        if frame is None or frame.empty or ticker not in frame.columns:
            return None
        return frame[ticker]

    rows = []
    for ticker in close.columns:
        m = compute_ohlcv_metrics(
            _col(high, ticker), _col(low, ticker), close[ticker], _col(volume, ticker)
        )
        m["ticker"] = ticker
        rows.append(m)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
