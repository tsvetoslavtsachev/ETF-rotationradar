"""
Smoke test: exercise the full analytics chain on a tiny universe (~12 tickers)
to validate pandas 3.0 / yfinance 1.3 compatibility before running the full pipeline.
Does NOT call fundamentals (slow, 135 sequential .info calls).
"""
import sys, os, traceback
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.prices import download_prices, download_ohlcv
from src.signal_engine import compute_cross_section
from src.rank_history import build_history_from_prices, compute_delta_metrics
from src.rs_line import generate_rs_signals
from src.screener import run_screener, run_ohlcv_screener
from src.render import render_frontend_data
from src.barometer import compute_barometer, INDICATORS
from src.fred import fetch_fred_series

# Tiny universe: >=2 per category so category z-scores are well-defined
UNIVERSE = [
    {"symbol": "SPY", "name": "SPDR S&P 500", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "QQQ", "name": "Invesco Nasdaq 100", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "XLK", "name": "Technology Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLF", "name": "Financial Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "GLD", "name": "SPDR Gold", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "GDX", "name": "Gold Miners", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "DBC", "name": "DB Commodity", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "TLT", "name": "20+ Yr Treasury", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "BND", "name": "Total Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "VGK", "name": "FTSE Europe", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWG", "name": "MSCI Germany", "category": "Intl Equity", "benchmark": "VGK"},
]

cat_map = {e["symbol"]: e["category"] for e in UNIVERSE}
name_map = {e["symbol"]: e["name"] for e in UNIVERSE}
bm_map = {e["symbol"]: e["benchmark"] for e in UNIVERSE}
tickers = [e["symbol"] for e in UNIVERSE]

def step(label):
    print(f"\n{'='*60}\n{label}\n{'='*60}")

try:
    step("1. download_prices (2y)")
    prices = download_prices(tickers, period="2y")
    print(f"shape={prices.shape}, columns_type={type(prices.columns).__name__}")
    print(f"columns={list(prices.columns)}")
    print(f"date range: {prices.index[0].date()} -> {prices.index[-1].date()}")
    assert not isinstance(prices.columns, pd.MultiIndex), "columns are still MultiIndex!"
    assert prices.shape[1] >= 8, "too few tickers downloaded"

    step("2. compute_cross_section (latest)")
    cs = compute_cross_section(prices, category_map=cat_map, as_of=prices.index[-1])
    print(cs.to_string())
    assert not cs.empty, "cross section empty"

    step("3. build_history_from_prices (weekly Fridays)")
    sample_dates = pd.DatetimeIndex(prices.index[prices.index.weekday == 4])
    hist = build_history_from_prices(prices, sample_dates, cat_map)
    print(f"history rows={len(hist)}, dates={hist['date'].nunique()}, tickers={hist['ticker'].nunique()}")
    print(f"date range: {hist['date'].min()} -> {hist['date'].max()}")
    assert not hist.empty, "history empty"

    step("4. compute_delta_metrics")
    deltas = compute_delta_metrics(hist, as_of=prices.index[-1])
    cols = ["ticker","current_rank","base_rank_6m","delta_1m","delta_3m","quadrant_1m","quadrant_3m"]
    print(deltas[cols].to_string())
    assert not deltas.empty, "deltas empty"

    step("5. generate_rs_signals")
    rs = generate_rs_signals(prices, bm_map)
    print(rs.to_string())

    step("6. run_screener")
    scr = run_screener(prices[tickers])
    print(scr.to_string())
    assert not scr.empty, "screener empty"

    step("6b. download_ohlcv + run_ohlcv_screener (ATR/stop/liquidity)")
    ohlcv = download_ohlcv(tickers, period="2y")
    assert {"High", "Low", "Close", "Volume"}.issubset(ohlcv.keys()), "OHLCV missing fields"
    assert not ohlcv["Close"].empty, "OHLCV Close empty"
    ohlcv_scr = run_ohlcv_screener(ohlcv)
    print(ohlcv_scr.to_string())
    assert not ohlcv_scr.empty, "ohlcv screener empty"
    spy = ohlcv_scr[ohlcv_scr["ticker"] == "SPY"].iloc[0]
    assert np.isfinite(spy["atr_14"]) and np.isfinite(spy["stop_distance_pct"]), "SPY ATR/stop not finite"
    assert np.isfinite(spy["dollar_vol_20d"]) and spy["liquidity_flag"] == "ok", "SPY liquidity wrong"

    step("7. render_frontend_data")
    out = Path(__file__).parent.parent / "docs" / "_smoke_data.json"
    fund_empty = pd.DataFrame(columns=["ticker"])
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out, ohlcv_df=ohlcv_scr)
    import json
    payload = json.load(open(out))
    print(f"as_of={payload['as_of']}, n_etfs={len(payload['etfs'])}, categories={payload['categories']}")
    print("Sample record:", json.dumps(payload['etfs'][0], indent=2))

    step(f"8. compute_barometer ({len(INDICATORS)} indicators)")
    bar_tickers = ["SPY", "XLE", "GLD", "TLT", "TIP", "IEF", "HYG", "LQD", "XLY", "XLP",
                   "IWM", "IWF", "IWD", "VUG", "VTV", "^VIX", "^MOVE"]
    bpx = download_prices(bar_tickers, period="2y")
    data_dir = Path(__file__).parent.parent / "data"
    hy = fetch_fred_series("BAMLH0A0HYM2", cache_path=data_dir / "fred_BAMLH0A0HYM2.parquet")
    be = fetch_fred_series("T10YIE", cache_path=data_dir / "fred_T10YIE.parquet")
    bar = compute_barometer(bpx, {"hy_spread": hy, "breakeven_10y": be}, bpx.index[-1])
    for i in bar["indicators"]:
        print(f"  {i['name']:14s} val={i['value']} zone={i['zone']:7s} kind={i['kind']:8s} z={i['z']}")
    print("confluence:", bar["confluence"])
    assert len(bar["indicators"]) == len(INDICATORS), "indicator count mismatch"
    unknown = [i["name"] for i in bar["indicators"] if i["zone"] == "unknown"]
    assert len(unknown) <= 2, f"too many unknown indicators: {unknown}"
    vix = next(i for i in bar["indicators"] if i["key"] == "vix")
    assert vix["value"] and 5 < vix["value"] < 100, "VIX value implausible"
    hyg = next(i for i in bar["indicators"] if i["key"] == "hyg_lqd")
    assert hyg["kind"] == "robust_z" and hyg["z"] is not None, "HYG/LQD z missing"

    print("\n\n>>> SMOKE TEST PASSED <<<")
except Exception:
    print("\n\n>>> SMOKE TEST FAILED <<<")
    traceback.print_exc()
    sys.exit(1)
