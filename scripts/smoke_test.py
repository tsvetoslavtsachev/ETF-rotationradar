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
from src.rank_history import build_history_from_prices, compute_delta_metrics, compute_movers
from src.rs_line import generate_rs_signals
from src.screener import run_screener, run_ohlcv_screener
from src.render import render_frontend_data
from src.barometer import compute_barometer, INDICATORS
from src.flows import append_aum_snapshot, load_aum_history, compute_flows
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

    step("6c. compute_betas (1Y weekly beta/corr to SPY)")
    from src.beta import compute_betas
    betas = compute_betas(prices, tickers)
    print(betas.to_string())
    assert not betas.empty, "betas empty"
    assert {"beta_1y", "corr_1y"}.issubset(betas.columns), "beta/corr columns renamed?"
    spy_b = betas[betas["ticker"] == "SPY"]
    assert not spy_b.empty, "SPY beta row missing"
    # SPY спрямо себе си: beta = var/var = 1.0, corr = 1.0 (точно, до закръгляне)
    assert abs(spy_b["beta_1y"].iloc[0] - 1.0) < 0.05, "SPY beta to itself should be ~1.0"
    assert abs(spy_b["corr_1y"].iloc[0] - 1.0) < 0.02, "SPY corr to itself should be ~1.0"

    step("7. render_frontend_data")
    out = Path(__file__).parent.parent / "docs" / "_smoke_data.json"
    fund_empty = pd.DataFrame(columns=["ticker"])
    spark_map = {
        t: [round(float(x), 3) for x in prices[t].resample("W-FRI").last().dropna().tail(104).tolist()]
        for t in tickers if t in prices.columns
    }
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out,
                         ohlcv_df=ohlcv_scr, spark_map=spark_map, betas_df=betas)
    import json
    payload = json.load(open(out))
    print(f"as_of={payload['as_of']}, n_etfs={len(payload['etfs'])}, categories={payload['categories']}")
    print("Sample record:", json.dumps(payload['etfs'][0], indent=2))
    assert any(isinstance(e.get("spark"), list) and len(e["spark"]) >= 2 for e in payload["etfs"]), \
        "sparkline data missing from rendered payload"
    assert any(e.get("beta_1y") is not None for e in payload["etfs"]), \
        "beta_1y missing from rendered payload"

    step(f"8. compute_barometer ({len(INDICATORS)} indicators)")
    # S15: 10 индикатора. TIP/IEF + IWF/IWD махнати; XLE/SPY вече robust_z.
    bar_tickers = ["SPY", "XLE", "GLD", "TLT", "HYG", "LQD", "XLY", "XLP",
                   "IWM", "VUG", "VTV", "^VIX", "^MOVE"]
    bpx = download_prices(bar_tickers, period="2y")
    data_dir = Path(__file__).parent.parent / "data"
    hy = fetch_fred_series("BAMLH0A0HYM2", cache_path=data_dir / "fred_BAMLH0A0HYM2.parquet")
    be = fetch_fred_series("T10YIE", cache_path=data_dir / "fred_T10YIE.parquet")
    bar = compute_barometer(bpx, {"hy_spread": hy, "breakeven_10y": be}, bpx.index[-1])
    for i in bar["indicators"]:
        print(f"  {i['name']:14s} val={i['value']} zone={i['zone']:7s} kind={i['kind']:8s} z={i['z']}")
    print("confluence:", bar["confluence"])
    assert len(bar["indicators"]) == len(INDICATORS) == 10, "indicator count mismatch (expect 10)"
    keys = {i["key"] for i in bar["indicators"]}
    assert not ({"tip_ief", "iwf_iwd"} & keys), "retired indicators still present"
    unknown = [i["name"] for i in bar["indicators"] if i["zone"] == "unknown"]
    assert len(unknown) <= 2, f"too many unknown indicators: {unknown}"
    vix = next(i for i in bar["indicators"] if i["key"] == "vix")
    assert vix["value"] and 5 < vix["value"] < 100, "VIX value implausible"
    hyg = next(i for i in bar["indicators"] if i["key"] == "hyg_lqd")
    assert hyg["kind"] == "robust_z" and hyg["z"] is not None, "HYG/LQD z missing"
    xle = next(i for i in bar["indicators"] if i["key"] == "xle_spy")
    assert xle["kind"] == "robust_z", "XLE/SPY should be robust_z after S15"
    # S16: VUG/VTV има вдигнат собствен alarm-праг 2.5 (trend-contamination)
    vug = next(i for i in bar["indicators"] if i["key"] == "vug_vtv")
    assert vug["z_alarm"] == 2.5, "VUG/VTV z_alarm should be 2.5 after S16"
    # S16: confluence alarm-страната пали на суров alarm_count ≥ ALARM_CONF
    c = bar["confluence"]
    assert c["alarm_conf_threshold"] == 2, "alarm_conf_threshold should be 2"
    if c["alarm_count"] >= c["alarm_conf_threshold"]:
        assert c["has_confluence"] and c["direction"] == "alarm", "alarm cluster should tilt alarm"
    if c["direction"] == "alarm":
        assert c["alarm_count"] >= c["alarm_conf_threshold"], "alarm tilt requires raw alarm_count"

    step("9. flows proxy (synthetic 2-snapshot AUM history)")
    import tempfile
    flow_path = Path(tempfile.gettempdir()) / "_smoke_aum_history.parquet"
    if flow_path.exists():
        flow_path.unlink()
    d_now = prices.index[-1]
    d_prior = prices.index[-22]  # ~1 месец назад
    # снимка отпреди месец: SPY с базов AUM; снимка сега: SPY +5% AUM (приток)
    append_aum_snapshot(flow_path, {"SPY": 100_000_000_000.0, "QQQ": 50_000_000_000.0}, d_prior)
    append_aum_snapshot(flow_path, {"SPY": 105_000_000_000.0, "QQQ": 50_000_000_000.0}, d_now)
    aum_hist = load_aum_history(flow_path)
    assert aum_hist["date"].nunique() == 2, "expected 2 AUM snapshots"
    flows = compute_flows(aum_hist, prices, d_now)
    print(flows.to_string())
    assert not flows.empty, "flows empty with 2 valid snapshots"
    spy_flow = flows[flows["ticker"] == "SPY"]
    assert not spy_flow.empty and np.isfinite(spy_flow["est_flow"].iloc[0]), "SPY flow not finite"
    assert spy_flow["flow_window_days"].iloc[0] >= 3, "flow window too short"
    flow_path.unlink()

    step("10. macro context (synthetic, без мрежа)")
    from src.macro_context import compute_macro_context, compute_gold_copper_item, MACRO_SERIES
    synth = {
        "stlfsi": pd.Series([0.5] * 40, index=pd.date_range("2025-01-01", periods=40, freq="W-FRI")),
        "nfci": pd.Series([-0.4] * 40, index=pd.date_range("2025-01-01", periods=40, freq="W-FRI")),
        "curve_2s10s": pd.Series([-0.2] * 60, index=pd.date_range("2025-01-01", periods=60, freq="D")),
        "recession_prob": pd.Series([5.0] * 40, index=pd.date_range("2025-01-01", periods=40, freq="MS")),
        # usd липсва нарочно → unknown
    }
    mc = compute_macro_context(synth, pd.Timestamp("2026-01-01"))
    zmap = {i["key"]: i["zone"] for i in mc["items"]}
    print("macro zones:", zmap)
    assert len(mc["items"]) == len(MACRO_SERIES), "macro item count mismatch"
    assert zmap["stlfsi"] == "alarm", "STLFSI4 0.5 (>0) трябва да е стрес"
    assert zmap["nfci"] == "base", "NFCI -0.4 (<0) трябва да е норма"
    assert zmap["curve_2s10s"] == "alarm", "инверсия (<0) трябва да е стрес"
    assert zmap["recession_prob"] == "base", "5% recession prob трябва да е калм"
    assert zmap["usd"] == "unknown", "липсваща USD серия трябва да е unknown"
    # GLD/COPX item (S18) — синтетичен: тих базис + рязък последен скок нагоре
    # (бягство към злато) → силно положителен robust_z → stress_dir high → alarm.
    n = 520
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    vals = np.full(n, 4.0) + ((np.arange(n) % 2) * 0.04 - 0.02)  # тих базис ±0.02
    vals[-8:] = np.linspace(4.0, 5.2, 8)                          # скорошен скок
    synth_px = pd.DataFrame({"GLD": vals * 50.0, "COPX": np.full(n, 50.0)}, index=idx)
    gc = compute_gold_copper_item(synth_px, idx[-1])
    print("GLD/COPX item:", gc)
    assert gc["value"] is not None and gc["z"] is not None, "GLD/COPX value/z missing"
    assert gc["zone"] == "alarm", "рязко растящ GLD/COPX (страх) трябва да е стрес"
    # липсваща COPX крак → unknown (smoke вселената няма COPX)
    gc_missing = compute_gold_copper_item(prices, prices.index[-1])
    assert gc_missing["zone"] == "unknown", "липсваща COPX трябва да е unknown"
    # daily_update append-ва GLD/COPX като 6-ти item; огледалваме това тук
    mc["items"].append(gc)
    # render coverage: macro попада в payload-а (5 FRED + 1 price-derived = 6)
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out,
                         ohlcv_df=ohlcv_scr, spark_map=spark_map, macro=mc)
    payload2 = json.load(open(out))
    assert payload2.get("macro") and len(payload2["macro"]["items"]) == len(MACRO_SERIES) + 1, \
        "macro context (5 FRED + GLD/COPX) missing from rendered payload"

    step("11. ETF look-through (synthetic summarize + render coverage, без мрежа)")
    from src.lookthrough import summarize_funds
    th = pd.DataFrame(
        {"Name": ["NVIDIA Corp", "Apple Inc", "Microsoft Corp"],
         "Holding Percent": [0.13, 0.12, 0.085]},
        index=pd.Index(["NVDA", "AAPL", "MSFT"], name="Symbol"))
    sw = {"technology": 0.30, "financial_services": 0.13, "healthcare": 0.10, "energy": 0.0}
    conc, holds, sects = summarize_funds(sw, th)
    print(f"conc={conc} holds={holds} sects={sects}")
    assert conc == 33.5, f"top-10 concentration should be 33.5, got {conc}"
    assert holds[0] == ["NVDA", 13.0], "top holding should be NVDA 13.0%"
    assert len(sects) == 3 and sects[0] == ["Technology", 30.0], "sectors top should be Technology 30%"
    assert all(lbl != "energy" for lbl, _ in sects), "zero-weight sector should be dropped"
    # render coverage: JSON колоните се парсват в nested holdings/sectors; суровите се махат
    lt = pd.DataFrame([{
        "ticker": "QQQ", "conc_top10": conc,
        "top_holdings_json": json.dumps(holds), "top_sectors_json": json.dumps(sects)}])
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out,
                         ohlcv_df=ohlcv_scr, spark_map=spark_map, lookthrough_df=lt)
    payload3 = json.load(open(out))
    qqq = next(e for e in payload3["etfs"] if e["ticker"] == "QQQ")
    assert qqq.get("conc_top10") == conc, "conc_top10 missing from payload"
    assert isinstance(qqq.get("holdings"), list) and qqq["holdings"][0][0] == "NVDA", \
        "parsed holdings missing from payload"
    assert "top_holdings_json" not in qqq, "raw JSON column should be stripped from payload"

    step("12. COT positioning (synthetic summarize + render coverage, без мрежа)")
    from src.cot import summarize_cot
    # текущ net силно над историята → percentile ~100; net=190, OI=1000 → 19% от OI
    cot_rows = [{"m_money_positions_long_all": "200", "m_money_positions_short_all": "10",
                 "open_interest_all": "1000", "report_date_as_yyyy_mm_dd": "2026-06-09T00:00:00.000"}]
    cot_rows += [{"m_money_positions_long_all": "100", "m_money_positions_short_all": "80",
                  "open_interest_all": "1000", "report_date_as_yyyy_mm_dd": f"2026-0{1+i%6}-01T00:00:00.000"}
                 for i in range(11)]
    summ = summarize_cot(cot_rows, "mm")
    print(f"cot summ={summ}")
    assert summ["cot_pctile"] == 100, "current net above all history should be ~100 pctile"
    assert summ["cot_net"] == 190 and summ["cot_pct_oi"] == 19.0, "net/%OI mismatch"
    assert summ["cot_date"] == "2026-06-09", "report date parse failed"
    # TFF leveraged-money полета (различен суфикс) се разпознават
    lev = summarize_cot([{"lev_money_positions_long": "50", "lev_money_positions_short": "70",
                          "open_interest_all": "500", "report_date_as_yyyy_mm_dd": "2026-06-09"}] * 10, "lev")
    assert lev["cot_net"] == -20, "leveraged net (long-short) should be -20"
    # render coverage: cot скаларите влизат в payload-а (GLD е в smoke вселената)
    cot_df = pd.DataFrame([{"ticker": "GLD", "cot_pctile": 100, "cot_net": 190, "cot_pct_oi": 19.0,
                            "cot_date": "2026-06-09", "cot_market": "Gold (COMEX)", "cot_kind": "Managed money"}])
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out,
                         ohlcv_df=ohlcv_scr, spark_map=spark_map, cot_df=cot_df)
    payload4 = json.load(open(out))
    gld = next(e for e in payload4["etfs"] if e["ticker"] == "GLD")
    assert gld.get("cot_pctile") == 100 and gld.get("cot_market") == "Gold (COMEX)", \
        "COT fields missing from payload"

    step("13. movers since last week (synthetic ΔRank diff + render coverage, без мрежа)")
    # Две snapshot дати ~5 търговски дни апарт. Конструираме ранговете така, че:
    #   QQQ +25 (движител нагоре, влиза в топ-2) · XLF -25 (надолу, напуска топ-2)
    #   XLK -20 (движител надолу) · GLD +20 (движител нагоре, под топ-2)
    mv_hist = pd.DataFrame([
        {"date": "2026-06-11", "ticker": "SPY", "percentile_rank": 90.0},
        {"date": "2026-06-11", "ticker": "QQQ", "percentile_rank": 50.0},
        {"date": "2026-06-11", "ticker": "XLK", "percentile_rank": 30.0},
        {"date": "2026-06-11", "ticker": "XLF", "percentile_rank": 85.0},
        {"date": "2026-06-11", "ticker": "GLD", "percentile_rank": 20.0},
        {"date": "2026-06-18", "ticker": "SPY", "percentile_rank": 92.0},
        {"date": "2026-06-18", "ticker": "QQQ", "percentile_rank": 75.0},
        {"date": "2026-06-18", "ticker": "XLK", "percentile_rank": 10.0},
        {"date": "2026-06-18", "ticker": "XLF", "percentile_rank": 60.0},
        {"date": "2026-06-18", "ticker": "GLD", "percentile_rank": 40.0},
    ])
    mv_hist["date"] = pd.to_datetime(mv_hist["date"])
    mv = compute_movers(mv_hist, as_of=pd.Timestamp("2026-06-18"),
                        threshold=15.0, top_n=2, name_map=name_map, category_map=cat_map)
    print("movers:", {k: (len(v) if isinstance(v, list) else v) for k, v in mv.items()})
    assert mv["available"], "movers should be available with 2 snapshots"
    assert mv["prev_date"] == "2026-06-11" and mv["as_of"] == "2026-06-18", "movers dates wrong"
    up_t = {r["ticker"] for r in mv["up"]}
    down_t = {r["ticker"] for r in mv["down"]}
    assert up_t == {"QQQ", "GLD"}, f"up movers wrong: {up_t}"
    assert down_t == {"XLF", "XLK"}, f"down movers wrong: {down_t}"
    qqq_up = next(r for r in mv["up"] if r["ticker"] == "QQQ")
    assert qqq_up["delta"] == 25 and qqq_up["prev"] == 50 and qqq_up["now"] == 75, "QQQ row values wrong"
    assert mv["up"][0]["ticker"] == "QQQ", "up should be sorted by ΔRank desc (QQQ +25 first)"
    assert mv["down"][0]["ticker"] == "XLF", "down should be sorted most-negative first (XLF -25)"
    assert {r["ticker"] for r in mv["entered"]} == {"QQQ"}, "QQQ should enter top-2"
    assert {r["ticker"] for r in mv["left"]} == {"XLF"}, "XLF should leave top-2"
    # праг: при threshold=30 само ±25/±20 НЕ палят → празни списъци, но available
    mv_strict = compute_movers(mv_hist, as_of=pd.Timestamp("2026-06-18"), threshold=30.0, top_n=2)
    assert mv_strict["available"] and not mv_strict["up"] and not mv_strict["down"], \
        "threshold=30 should yield no movers but stay available"
    # render coverage: movers попада в payload-а
    render_frontend_data(deltas, scr, fund_empty, rs, cat_map, name_map, bm_map, out,
                         ohlcv_df=ohlcv_scr, spark_map=spark_map, movers=mv)
    payload5 = json.load(open(out))
    assert payload5.get("movers") and payload5["movers"]["available"], "movers missing from payload"
    assert len(payload5["movers"]["up"]) == 2 and len(payload5["movers"]["entered"]) == 1, \
        "movers payload structure wrong"

    print("\n\n>>> SMOKE TEST PASSED <<<")
except Exception:
    print("\n\n>>> SMOKE TEST FAILED <<<")
    traceback.print_exc()
    sys.exit(1)
