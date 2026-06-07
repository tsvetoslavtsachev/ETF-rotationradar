"""
Pristine RS Line calculation for ETFs relative to their specific benchmark.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

def compute_rs_line(
    ticker_prices: pd.Series,
    benchmark_prices: pd.Series,
    ema_window: int = 10,
    sma_window: int = 50,
) -> pd.DataFrame:
    """
    Изчислява RS Line и нейните пълзящи средни за даден тикър спрямо бенчмарк.
    """
    df = pd.DataFrame({
        "price": ticker_prices,
        "benchmark": benchmark_prices
    }).dropna()

    if len(df) < sma_window:
        return pd.DataFrame()

    df["rs_line"] = df["price"] / df["benchmark"]
    df["rs_ema10"] = df["rs_line"].ewm(span=ema_window, adjust=False).mean()
    df["rs_sma50"] = df["rs_line"].rolling(window=sma_window).mean()
    
    # Crossover signals
    df["ema_above_sma"] = df["rs_ema10"] > df["rs_sma50"]
    # .diff() оставя NaN на ред 0; pandas смята NaN != 0 за True, което иначе
    # вкарва ред 0 във "crossovers" и води до int(NaN) -> ValueError за серии
    # без нито един реален crossover. fillna(0) го предотвратява.
    df["signal_change"] = df["ema_above_sma"].astype(int).diff().fillna(0)
    
    # +1 = Bullish crossover (EMA10 crosses above SMA50)
    # -1 = Bearish crossover (EMA10 crosses below SMA50)
    
    return df

def generate_rs_signals(
    prices_df: pd.DataFrame,
    benchmark_map: dict[str, str]
) -> pd.DataFrame:
    """
    Генерира последния RS статус за всички ETF-и.
    """
    rows = []
    skipped_missing_bm = []  # тикъри без наличен бенчмарк в данните

    for ticker in prices_df.columns:
        bm_ticker = benchmark_map.get(ticker)
        if not bm_ticker or bm_ticker not in prices_df.columns:
            if ticker in benchmark_map:  # има зададен бенчмарк, но липсва в цените
                skipped_missing_bm.append(ticker)
            continue

        # Don't calculate RS for the benchmark against itself
        if ticker == bm_ticker:
            continue
            
        rs_df = compute_rs_line(prices_df[ticker], prices_df[bm_ticker])
        if rs_df.empty:
            continue
            
        last_row = rs_df.iloc[-1]
        
        # Calculate days since last crossover
        crossovers = rs_df[rs_df["signal_change"] != 0].copy()
        if not crossovers.empty:
            last_cross_date = crossovers.index[-1]
            days_since = (rs_df.index[-1] - last_cross_date).days
            last_signal = crossovers.iloc[-1]["signal_change"]
        else:
            days_since = np.nan
            last_signal = 0
            
        rows.append({
            "ticker": ticker,
            "benchmark": bm_ticker,
            "rs_line": float(last_row["rs_line"]),
            "rs_ema10": float(last_row["rs_ema10"]),
            "rs_sma50": float(last_row["rs_sma50"]),
            "is_bullish": bool(last_row["ema_above_sma"]),
            "days_in_trend": days_since,
            "last_signal": int(last_signal)
        })
        
    if skipped_missing_bm:
        print(f"  RS: {len(skipped_missing_bm)} тикъра без бенчмарк в цените: {skipped_missing_bm}")

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
