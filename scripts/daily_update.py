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
import time
from pathlib import Path
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.universe import (
    get_universe_tickers, get_benchmark_tickers,
    get_category_map, get_name_map, get_benchmark_map
)
from src.prices import download_ohlcv, download_prices
from src.signal_engine import compute_cross_section
from src.rank_history import append_snapshot, load_history, compute_delta_metrics
from src.fundamentals import fetch_fundamentals
from src.rs_line import generate_rs_signals
from src.screener import run_screener, run_ohlcv_screener
from src.fred import fetch_fred_series
from src.barometer import compute_barometer
from src.render import render_frontend_data

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"


def filter_prices(prices_df: pd.DataFrame, tickers: list) -> pd.DataFrame:
    """
    Връща само колоните за дадените тикъри.
    Работи независимо дали колоните са обикновен Index или MultiIndex.
    """
    if isinstance(prices_df.columns, pd.MultiIndex):
        # Сплескай MultiIndex до обикновен Index
        prices_df = prices_df.copy()
        prices_df.columns = prices_df.columns.get_level_values(-1)

    available = [t for t in tickers if t in prices_df.columns]
    return prices_df[available]


def main():
    print("=== ETF Rotation Radar: Daily Update ===")

    # 1. Get Universe
    tickers = get_universe_tickers()
    benchmarks = get_benchmark_tickers()
    all_tickers = list(set(tickers + benchmarks))
    print(f"Universe: {len(tickers)} ETFs, {len(benchmarks)} Benchmarks")

    # 2. Download Prices (OHLCV — едно сваляне; Close храни стария pipeline,
    #    пълният OHLCV храни новите метрики ATR/стоп/ликвидност)
    print("\nDownloading prices (last 2 years)...")
    ohlcv = download_ohlcv(all_tickers, period="2y")
    prices_df = ohlcv.get("Close", pd.DataFrame())
    if prices_df.empty:
        print("Failed to download prices. Exiting.")
        return
    print(f"Downloaded prices up to {prices_df.index[-1].strftime('%Y-%m-%d')}")
    print(f"Price DataFrame shape: {prices_df.shape}, columns type: {type(prices_df.columns).__name__}")

    # 3. Signal Engine & Rank History
    print("\nComputing cross-section and updating history...")
    category_map = get_category_map()

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

    # 4. Fundamentals (с кеш — рефетч само на липсващи/остарели)
    print("\nFetching fundamentals...")
    fundamentals = fetch_fundamentals(
        tickers, cache_path=DATA_DIR / "fundamentals.parquet", category_map=category_map
    )
    print(f"Fetched fundamentals for {len(fundamentals)} ETFs")

    # 5. RS Line Signals
    print("\nComputing RS Line signals...")
    benchmark_map = get_benchmark_map()
    rs_signals = generate_rs_signals(prices_df, benchmark_map)
    print(f"Generated RS signals for {len(rs_signals)} ETFs")

    # 6. Screener Metrics — филтрираме само ETF тикъри (без бенчмаркове)
    print("\nComputing screener metrics...")
    etf_prices = filter_prices(prices_df, tickers)
    print(f"ETF price slice shape: {etf_prices.shape}")
    screener = run_screener(etf_prices)
    print(f"Computed screener metrics for {len(screener)} ETFs")

    # 6b. OHLCV метрики — ATR(14), Chandelier стоп, оборот в $ + ликвиден флаг
    etf_ohlcv = {f: filter_prices(frame, tickers) for f, frame in ohlcv.items() if not frame.empty}
    ohlcv_metrics = run_ohlcv_screener(etf_ohlcv)
    print(f"Computed OHLCV metrics (ATR/stop/liquidity) for {len(ohlcv_metrics)} ETFs")

    # 6.5 Behavioral Barometer (ELANA дислокации) — 11 индикатора
    print("\nComputing behavioral barometer...")
    # Тикъри ИЗВЪН вселената (^VIX, ^MOVE, VUG, VTV) — само за барометъра,
    # не влизат в screener/momentum. Сваляме ги отделно и обединяваме.
    barometer_extra = download_prices(["^VIX", "^MOVE", "VUG", "VTV"], period="2y")
    barometer_prices = pd.concat([prices_df, barometer_extra], axis=1, sort=True)
    barometer_prices = barometer_prices.loc[:, ~barometer_prices.columns.duplicated()]
    # T10YIE се тегли ПЪРВА: fredgraph пуска заявки пестеливо (rate limit),
    # а тя единствена няма посят кеш. HY има stale-cache fallback и се движи
    # бавно — ден закъснение е приемлив.
    be = fetch_fred_series("T10YIE", cache_path=DATA_DIR / "fred_T10YIE.parquet")
    if be.dropna().empty:
        # Резервен път ПО ДЕФИНИЦИЯ: breakeven = 10г номинална минус 10г TIPS
        # доходност (DGS10 - DFII10) — същата стойност, същите прагове.
        print("T10YIE unavailable -> deriving breakeven as DGS10 - DFII10...")
        time.sleep(15)
        dgs10 = fetch_fred_series("DGS10", cache_path=DATA_DIR / "fred_DGS10.parquet")
        time.sleep(15)
        dfii10 = fetch_fred_series("DFII10", cache_path=DATA_DIR / "fred_DFII10.parquet")
        if len(dgs10.dropna()) and len(dfii10.dropna()):
            be = (dgs10 - dfii10).dropna()
            print(f"Derived breakeven: {len(be)} points, last={float(be.iloc[-1]):.2f}")
    time.sleep(15)
    hy = fetch_fred_series("BAMLH0A0HYM2", cache_path=DATA_DIR / "fred_BAMLH0A0HYM2.parquet")
    barometer = compute_barometer(
        barometer_prices, {"hy_spread": hy, "breakeven_10y": be}, latest_date
    )
    ind = {i["key"]: i["value"] for i in barometer["indicators"]}
    conf = barometer["confluence"]
    print(f"Barometer: HY={ind['hy_spread']} XLE/SPY={ind['xle_spy']} GLD/TLT={ind['gld_tlt']} "
          f"VIX={ind['vix']} BE={ind['breakeven_10y']} MOVE={ind['move']} "
          f"| alarm={conf['alarm_count']} base={conf['base_count']} net={conf['net']} "
          f"conf={conf['has_confluence']} {conf['direction'] or ''}")

    # 7. Render to JSON
    print("\nRendering frontend data...")
    name_map = get_name_map()
    output_path = DOCS_DIR / "data.json"
    render_frontend_data(
        deltas, screener, fundamentals, rs_signals,
        category_map, name_map, benchmark_map, output_path,
        barometer=barometer, ohlcv_df=ohlcv_metrics
    )

    print("\n=== Update Complete ===")


if __name__ == "__main__":
    main()
