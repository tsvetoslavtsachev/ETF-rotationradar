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

## Tier 1 — cheap, high intuition (do next)
- [ ] **ATR(14) + Chandelier stop** — requires `prices.py` to retain OHLC (currently Close-only). Volatility-scaled stop; `stop_distance_pct` doubles as a position-sizing number.
- [ ] **Dollar-volume trend + liquidity flag** — same one-line `prices.py` change (keep `Volume`). Flags thin thematic/currency ETFs where slippage swamps the signal.
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
