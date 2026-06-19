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
from src.macro_context import compute_macro_context, MACRO_SERIES
from src.flows import append_aum_snapshot, load_aum_history, compute_flows
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
        # S15 health: провал на свалянето е МЪРТЪВ канал → излизаме с грешка,
        # за да светне GitHub Action червен (не тихо зелено със застинали данни).
        print("ERROR: price download returned empty — dead data channel, failing loudly.")
        sys.exit(1)
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

    # 4b. Fund-flow прокси (S15) — записваме днешния AUM snapshot, после смятаме
    #     нетния поток за прозореца (мащаб+посока). Пълни се напред; "—" докато
    #     историята покрие прозореца.
    print("\nComputing fund-flow proxy...")
    aum_map = dict(zip(fundamentals["ticker"], fundamentals["aum"])) if not fundamentals.empty else {}
    aum_hist_path = DATA_DIR / "aum_history.parquet"
    append_aum_snapshot(aum_hist_path, aum_map, latest_date)
    aum_history = load_aum_history(aum_hist_path)
    flows = compute_flows(aum_history, prices_df, latest_date)
    n_snap = aum_history["date"].nunique() if not aum_history.empty else 0
    print(f"Flows: {len(flows)} ETFs with usable est. net flow "
          f"(AUM history: {n_snap} daily snapshots)")

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

    # 6.5 Behavioral Barometer (ELANA дислокации) — 10 индикатора (S15)
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

    # 6.7 Макро контекст strip (Tier 2, S17) — keyless FRED режимни overlays.
    #     DISPLAY-ONLY (не влиза в Барометър confluence). Всяка серия с parquet
    #     кеш + stale fallback; кратки паузи срещу fredgraph rate-limit.
    print("\nFetching macro-context FRED series...")
    macro_raw = {}
    for m in MACRO_SERIES:
        macro_raw[m["key"]] = fetch_fred_series(
            m["fred_id"], cache_path=DATA_DIR / f"fred_{m['fred_id']}.parquet"
        )
        time.sleep(8)
    macro_context = compute_macro_context(macro_raw, latest_date)
    mi = {i["key"]: i["value"] for i in macro_context["items"]}
    print(f"Macro: STLFSI4={mi['stlfsi']} NFCI={mi['nfci']} USD={mi['usd']} "
          f"2s10s={mi['curve_2s10s']} RecProb={mi['recession_prob']}")

    # 6.6 Sparkline серии — 2г седмично-децимиран Close per ETF (за Rotation Radar)
    spark_src = filter_prices(prices_df, tickers).resample("W-FRI").last()
    spark_map = {}
    for t in spark_src.columns:
        s = spark_src[t].dropna()
        if len(s) >= 8:
            spark_map[t] = [round(float(x), 3) for x in s.tail(104).tolist()]
    print(f"Built sparkline series for {len(spark_map)} ETFs")

    # 7. Render to JSON
    print("\nRendering frontend data...")
    name_map = get_name_map()
    output_path = DOCS_DIR / "data.json"
    render_frontend_data(
        deltas, screener, fundamentals, rs_signals,
        category_map, name_map, benchmark_map, output_path,
        barometer=barometer, ohlcv_df=ohlcv_metrics, flows_df=flows,
        spark_map=spark_map, macro=macro_context
    )

    print("\n=== Update Complete ===")


if __name__ == "__main__":
    main()
