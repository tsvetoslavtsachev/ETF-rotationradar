"""
Backfill rank history for all ETFs.
Run this once to initialize the history parquet file.
"""

import sys
import os
from pathlib import Path
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.universe import get_universe_tickers, get_benchmark_tickers, get_category_map
from src.prices import download_prices
from src.rank_history import build_history_from_prices, append_snapshot

DATA_DIR = Path(__file__).parent.parent / "data"

def main():
    print("=== ETF Rotation Radar: Backfill History ===")
    
    tickers = get_universe_tickers()
    benchmarks = get_benchmark_tickers()
    all_tickers = list(set(tickers + benchmarks))
    
    print(f"Downloading 3 years of prices for {len(all_tickers)} tickers...")
    prices_df = download_prices(all_tickers, period="3y")
    
    if prices_df.empty:
        print("Failed to download prices. Exiting.")
        return
    
    print(f"Downloaded {len(prices_df)} trading days")
    
    # Sample weekly to avoid too many API calls
    sample_dates = pd.DatetimeIndex(
        prices_df.index[prices_df.index.weekday == 4]  # Fridays
    )
    
    print(f"Building history from {len(sample_dates)} weekly snapshots...")
    category_map = get_category_map()
    history = build_history_from_prices(prices_df, sample_dates, category_map)
    
    if history.empty:
        print("No history built. Check that prices have enough history.")
        return
    
    history_path = DATA_DIR / "ranks_history.parquet"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history.to_parquet(history_path, index=False)
    
    print(f"\nSaved {len(history)} records to {history_path}")
    print(f"Date range: {history['date'].min()} to {history['date'].max()}")
    print(f"Unique ETFs: {history['ticker'].nunique()}")
    print("Backfill complete!")

if __name__ == "__main__":
    main()
