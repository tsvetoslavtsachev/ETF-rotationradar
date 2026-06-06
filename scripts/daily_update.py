"""
Daily update script for ETF Rotation Radar.
1. Downloads prices
2. Updates rank history
3. Fetches fundamentals
4. Computes RS Line signals
5. Runs screener
6. Renders JSON for UI
"""

import sys
import os
from pathlib import Path
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.universe import (
    get_universe_tickers, get_benchmark_tickers, 
    get_category_map, get_name_map, get_benchmark_map
)
from src.prices import download_prices
from src.signal_engine import compute_cross_section
from src.rank_history import append_snapshot, load_history, compute_delta_metrics
from src.fundamentals import fetch_fundamentals
from src.rs_line import generate_rs_signals
from src.screener import run_screener
from src.render import render_frontend_data

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"

def main():
    print("=== ETF Rotation Radar: Daily Update ===")
    
    # 1. Get Universe
    tickers = get_universe_tickers()
    benchmarks = get_benchmark_tickers()
    all_tickers = list(set(tickers + benchmarks))
    print(f"Universe: {len(tickers)} ETFs, {len(benchmarks)} Benchmarks")
    
    # 2. Download Prices
    print("\nDownloading prices (last 2 years)...")
    prices_df = download_prices(all_tickers, period="2y")
    if prices_df.empty:
        print("Failed to download prices. Exiting.")
        return
    print(f"Downloaded prices up to {prices_df.index[-1].strftime('%Y-%m-%d')}")
    
    # 3. Signal Engine & Rank History
    print("\nComputing cross-section and updating history...")
    category_map = get_category_map()
    
    # For daily update, we only need the latest snapshot
    # In a real setup, we'd backfill first, but for now we just compute the latest
    latest_date = prices_df.index[-1]
    snapshot = compute_cross_section(prices_df, category_map=category_map, as_of=latest_date)
    
    history_path = DATA_DIR / "ranks_history.parquet"
    if not snapshot.empty:
        append_snapshot(history_path, snapshot)
        
    history = load_history(history_path)
    print(f"History contains {len(history)} records")
    
    # Compute deltas and quadrants
    deltas = compute_delta_metrics(history, as_of=latest_date)
    print(f"Computed deltas for {len(deltas)} ETFs")
    
    # 4. Fundamentals
    print("\nFetching fundamentals...")
    fundamentals = fetch_fundamentals(tickers)
    print(f"Fetched fundamentals for {len(fundamentals)} ETFs")
    
    # 5. RS Line Signals
    print("\nComputing RS Line signals...")
    benchmark_map = get_benchmark_map()
    rs_signals = generate_rs_signals(prices_df, benchmark_map)
    print(f"Generated RS signals for {len(rs_signals)} ETFs")
    
    # 6. Screener Metrics
    print("\nComputing screener metrics...")
    screener = run_screener(prices_df[tickers])
    print(f"Computed screener metrics for {len(screener)} ETFs")
    
    # 7. Render to JSON
    print("\nRendering frontend data...")
    name_map = get_name_map()
    output_path = DOCS_DIR / "data.json"
    render_frontend_data(
        deltas, screener, fundamentals, rs_signals, 
        category_map, name_map, benchmark_map, output_path
    )
    
    print("\n=== Update Complete ===")

if __name__ == "__main__":
    main()
