# Roadmap / Backlog

All items are **free** (no paid API). Grouped by value-to-effort.

## ✅ Shipped (2026-06-07)
- Working end-to-end pipeline (Python 3.14 / pandas 3.0 / yfinance 1.3); 8 bug fixes
- Within-category momentum rank; Macro Heatmap on absolute momentum
- Leveraged/inverse/vol products excluded; unreliable bond Duration dropped
- **Behavioral Barometer** banner (HY-spread + XLE/SPY + GLD/TLT) + `barometer_feed.json`
- Screener: distance-from-52w-high and current-drawdown columns
- Fundamentals parquet cache + retry/backoff (survives yfinance 429)
- **Light/dark theme toggle** (persisted; light mode = paste-ready Members screenshots)
- **OHLCV fetch path** (`download_ohlcv`) — single yfinance call; Close feeds the old pipeline unchanged (zero blast radius), full OHLCV feeds the new metrics
- **ATR(14) + Chandelier stop** (`atr_pct`, `chandelier_stop`, `stop_distance_pct`) + **dollar-volume / liquidity** (`dollar_vol_20d`, `dollar_vol_trend`, `liquidity_flag`) — 3 new Screener columns (ATR%, Stop%, $Vol/d)
- **Barometer expanded 3 → 12 dislocations** — added VIX, 10Y breakeven (FRED T10YIE), TIP/IEF (breakeven proxy), MOVE, HYG/LQD, XLY/XLP, IWM/SPY, IWF/IWD, VUG/VTV. Config-driven `INDICATORS` with two threshold mechanisms: `abs` (sourced from VRM2 — no invented numbers) and `robust_z` (median/MAD, self-calibrating, for ratios with no published threshold). Net-based confluence. Extra tickers (^VIX/^MOVE/VUG/VTV) fetched separately so they never leak into the screener. Workflow now also commits `docs/barometer_feed.json`.

## Tier 1 — cheap, high intuition (do next)
- [x] ~~**ATR(14) + Chandelier stop**~~ — shipped 2026-06-07 (ATR14 Wilder; Chandelier = highest-high(22) − 3×ATR; `stop_distance_pct` = position-sizing number)
- [x] ~~**Dollar-volume trend + liquidity flag**~~ — shipped 2026-06-07 (ADV20 in $; trend = ADV20/ADV63; `liquidity_flag` thin <$5M heuristic)
- [ ] **CSV / Excel export of the Screener** — client-side, zero-dep (CSV) / SheetJS (xlsx). Clean handoff into the weekly publication pipeline.
- [x] ~~**Light/dark theme toggle**~~ — shipped 2026-06-07
- [ ] **Per-ETF inline SVG sparklines** — 2y weekly-decimated Close; ~15 lines vanilla JS. "Shape of the trend" next to each rank.

## Tier 2 — macro / regime overlays (tie into the barometer)
- [ ] Credit-stress strip: HY OAS + **STLFSI4** / **NFCI** (FRED, keyless)
- [ ] USD + yield-curve context: FRED **DTWEXBGS**, **T10Y2Y**
- [ ] Gold/Copper ratio (GLD / COPX) — growth-vs-fear tell
- [ ] Rolling 90-day beta & correlation to SPY (prices already in pipeline)
- [ ] Recession-probability gauge: FRED **RECPROUSM156N**
- [ ] ETF look-through: sector weights + top-10 concentration (yfinance `funds_data`)
- [ ] CFTC COT positioning for commodity/rate ETFs (CFTC Socrata CSV, keyless)

## Tier 3 — bigger UX
- [ ] "Movers since last run" diff panel (`ranks_history.parquet` already stores the series)
- [ ] Category-rotation-over-time heat-strip (10 cats × ~26 weeks)
- [ ] Printable weekly BG snapshot (`@media print` + `window.print()`)

## Open question (needs owner confirmation)
- [ ] **XLE/SPY barometer thresholds basis** — pipeline computes the ratio from *dividend-adjusted* closes (~0.078, fits the 0.060/0.070 thresholds). Confirm the published thresholds are calibrated on the adjusted basis; otherwise recalibrate. (GLD/TLT is unaffected — gold pays no dividend.)

## Known minor items (deferred, from the audit)
- [ ] Sharpe uses rf=0 (inflates ~0.3–0.4 for low-return assets) — add configurable `rf` or a UI footnote
- [ ] `days_in_trend` uses calendar days, not trading days
- [ ] ΔRank windows use `BusinessDay` (ignores US market holidays) — minor misalignment near holidays
- [ ] **Liquidity threshold** `LIQUIDITY_THIN_USD = $5M` (screener.py) is a heuristic, not a calibrated cutoff — currently flags SIZE/CNRG/FINX/FAN; currency ETFs (FXF ~$6M, FXY ~$9M) sit just above. Tune if you want them flagged.
- [ ] **Chandelier basis** uses ATR(14) + 22-day high + 3× (honours backlog's "ATR(14)"); the classic Chandelier uses ATR(22). Named constants in screener.py — 1-line switch.
- [ ] **10Y breakeven (T10YIE) FRED fetch** — `fred.stlouisfed.org` was unreachable from the dev machine during build (yfinance fine; FRED timed out even sandbox-off). Zone logic verified with synthetic data; the chip shows "unknown" until a FRED-reachable run (CI nightly) warms `data/fred_T10YIE.parquet`. Not a code bug.
- [ ] **IWF/IWD vs VUG/VTV overlap** — both are growth/value; kept both for now. Check correlation/redundancy and drop one if it adds no independent signal.
- [ ] **Breakeven: FRED rate vs TIP/IEF proxy** — running BOTH on purpose (true T10YIE rate + yfinance TIP/IEF robust-z proxy) to compare which tracks better over time; consolidate to one once observed.
- [ ] **Growth/value stress direction** — IWF/IWD & VUG/VTV use `stress_dir="high"` (growth-euphoria = alarm) as a documented assumption (genuinely two-sided). Flip the constant in barometer.py if you prefer the other reading.
- [ ] **Net-confluence semantics changed** — barometer confluence is now net (`|alarm − base| ≥ 2`) across 11 indicators, not raw ≥2. The `behavioral-tracker` skill reads `barometer_feed.json` (now 11 indicators) and may need updating to match.
