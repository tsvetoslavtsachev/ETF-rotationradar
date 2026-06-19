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
- [x] ~~**CSV export of the Screener**~~ — **S17 (2026-06-19)**: client-side, zero-dep `⤓ CSV` бутон; изнася текущия филтриран+сортиран изглед със СУРОВИ стойности (чист handoff към публикацията). `etf-screener-{as_of}.csv`. (xlsx/SheetJS = 1-add ако потрябва.)
- [x] ~~**Light/dark theme toggle**~~ — shipped 2026-06-07
- [x] ~~**Per-ETF inline SVG sparklines**~~ — **S17 (2026-06-19)**: 2г седмично-децимиран Close (104 точки, W-FRI), inline SVG до всеки ранг в Rotation Radar; зелено/червено по посока. Backend: `spark_map` в daily_update→render; frontend `sparkline()`.

## Tier 2 — macro / regime overlays (tie into the barometer)
**S17 batch 1 (2026-06-19): FRED макро-стрип** — нов `🌐 Макро контекст` панел под Барометъра (`src/macro_context.py`, DISPLAY-ONLY, не влиза в confluence). 5 keyless FRED серии, зони base/gray/alarm. Дефинитивни котви сорснати (0 = норма за STLFSI4/NFCI/2s10s); band-овете документирани конвенции (±0.10 dead-band, 2s10s watch 0.50, recession 20/50).
- [x] ~~Credit-stress strip: STLFSI4 / NFCI~~ — **S17**. (HY OAS вече е в Барометъра.)
- [x] ~~USD + yield-curve context: DTWEXBGS, T10Y2Y~~ — **S17** (USD=robust_z, 2s10s=spread зона).
- [x] ~~Recession-probability gauge: RECPROUSM156N~~ — **S17** (Chauvet-Piger smoothed %).
- [x] ~~Gold/Copper ratio (GLD / COPX) — growth-vs-fear tell~~ — **S18 (2026-06-19)**: 6-ти display-only макро-чип (robust_z; COPX=миньори не фючърси, документирана конвенция). И GLD, и COPX вече във вселената → нула нови вызови.
- [x] ~~Rolling beta & correlation to SPY~~ — **S18 (2026-06-19)**: вградено като **1-годишна СЕДМИЧНА** бета/корелация (`beta_1y`/`corr_1y`, 52 W-FRI доходности), НЕ 90д дневна. Решение след сравнение 90д/252д/52с/104с: седмично лекува десинхрона на intl/суровинни ETF (EWY дневна 3.46→седмична 2.2; GLD 1.12→0.51); 1г (не 2г Bloomberg) защото инструментът е тактически — 2г размива режима (XLE −0.63→+0.36). Конвенция за целия инструмент (ETF, акции). 2 Screener колони + sort + CSV.
- [x] ~~ETF look-through: sector weights + top-10 concentration (yfinance `funds_data`)~~ — **S18 batch 3 (2026-06-19)**: `src/lookthrough.py` (отделен модул, собствен кеш `data/lookthrough.parquet`, само акционни ~93 ETF). Концентрация (топ-10 %) = сортируема Screener колона „Конц.%"; hover tooltip = топ-5 holdings + топ-3 сектора. GLD/TLT self-gate (празно). XLK 61.8% / EWY 61.2% (top-heavy) vs SPY 39.2%. Имена на holdings = symbols (за intl напр. 000660.KS; човешки имена = 1-add ако потрябва).
- [ ] CFTC COT positioning for commodity/rate ETFs (CFTC Socrata CSV, keyless)  *(batch 4)*

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
- [ ] **10Y breakeven (T10YIE) FRED fetch** — FRED fredgraph is heavily rate-limited/bot-filtered since ~2026-06-07: requests hang from BOTH the dev machine and GitHub runners (one lucky HY slot got through 2026-06-09 21:08 UTC; all retries since timed out). Mitigations already in place: T10YIE fetched first, 20/40s backoffs, inter-series pauses, derived fallback (DGS10 − DFII10 = breakeven by definition), stale-cache fallback once seeded, TIP/IEF robust-z proxy chip running alongside. The nightly cron retries every weekday — no action needed; chip shows "unknown" until a fetch wins. Zone logic verified with synthetic data. Not a code bug.
- [ ] **IWF/IWD vs VUG/VTV overlap** — both are growth/value; kept both for now. Check correlation/redundancy and drop one if it adds no independent signal.
- [ ] **Breakeven: FRED rate vs TIP/IEF proxy** — running BOTH on purpose (true T10YIE rate + yfinance TIP/IEF robust-z proxy) to compare which tracks better over time; consolidate to one once observed.
- [ ] **Growth/value stress direction** — IWF/IWD & VUG/VTV use `stress_dir="high"` (growth-euphoria = alarm) as a documented assumption (genuinely two-sided). Flip the constant in barometer.py if you prefer the other reading.
- [ ] **Net-confluence semantics changed** — barometer confluence is now net (`|alarm − base| ≥ 2`) across 11 indicators, not raw ≥2. The `behavioral-tracker` skill reads `barometer_feed.json` (now 11 indicators) and may need updating to match.

## S15 — owner calibration sign-off (2026-06-18)
Decisions from the review-first audit:
1. **XLE/SPY threshold — REBUILD.** Old `0.070` alarm fires 66% of the last 2y (current 0.0738 ≈ 2y median 0.0736, robust-z ≈ +0.02). Stale, not a basis issue (verified: adjusted == nominal at the latest bar). → convert to `robust_z` (joins the self-calibrating bucket; current lands `base`) unless absolute-level semantics are required.
2. **Breakeven TIP/IEF proxy — RETIRE.** Real T10YIE is live again (06-17, BE=2.29; `fred_T10YIE.parquet` seeded). Keep T10YIE-primary + derived `DGS10−DFII10` fallback; drop the proxy.
3. **Growth/value redundancy — KEEP VUG/VTV, DROP IWF/IWD** (both measured growth-vs-value; Vanguard pair retained).
5. **Flows v1 — SHIP proxy** (whole universe, coarse, scale+direction). `est_flow ≈ AUM_now − AUM_prior×(1+market_ret)` over ~21 trading days. New `src/flows.py` + `data/aum_history.parquet` (forward-accumulating, no backfill → "—" until window fills). Screener column `Flow%`.
6. **Health exit-code — DONE (a):** `daily_update.py` now `sys.exit(1)` on empty prices (dead channel → red Action, not silent green). No on-page banner (owner chose (a) only).

### S15 BUILT (2026-06-18, pending push approval)
- barometer.py: 12→10 indicators; XLE/SPY abs→robust_z; removed TIP/IEF + IWF/IWD.
- daily_update.py: health exit(1); flows section; pass flows to render.
- src/flows.py (new) + render.py flows merge; index.html/app.js `Flow%` column.
- smoke_test.py: 10-indicator + XLE robust_z + synthetic flows assertions — **PASS**.
- behavioral-tracker SKILL.md → v2.0 (reads barometer_feed.json, 10 indicators, net confluence).
- Verify gates green: smoke_test ✓ · empty-prices→exit1 ✓ · full daily_update (data to 06-18, XLE=base, EXIT=0) ✓ · preview :8137 (10 chips, XLE green, Flow col, no console errors) ✓.

### Flows — open validation gate (watch over next ~weeks)
- AUM refresh cadence: fundamentals cache is 7-day → AUM moves ~weekly. If `totalAssets` is too sticky, short-window flows are noisy (synthetic QQQ test showed flat-AUM-during-rally → spurious "outflow"). Watch the daily `Flows: N ETFs with usable...` log + first real values; if unusable → fallback to issuer CSV (shares-out × price) for ~30 flagships.
- No backfill: column is "—" until ~MIN_WINDOW_DAYS (3) of history accumulates; full signal at ~21 trading days.

### Optional hardening (not done, flag only)
- FRED keyless `fredgraph.csv` is fragile (06-07 outage). INIT-22 lesson: official `api.stlouisfed.org` + `FRED_API_KEY` is more robust. Breakeven works now (T10YIE live), so deferred.

### Deferred heuristics — reconsider + test once flows/health infra exists (decision 4)
"What each currently drives" — so we know what a recalibration would move. `[VERDICT]` = changes a shown classification; `[display]` = cosmetic.
- [x] ~~**Quadrant 80/20**~~ → **S16: LOW 20→25** (виж секцията долу). `[VERDICT]` РЕШЕН 2026-06-19
- [x] ~~**CONF_NET=2**~~ → **S16: alarm-страна на raw alarm_count≥2** (net мъртва). `[VERDICT]` РЕШЕН 2026-06-19
- [x] ~~**robust_z 1.0/2.0/504**~~ → **S16: W=504 & праг 2.0 запазени; VUG/VTV→2.5**. `[VERDICT]` РЕШЕН 2026-06-19
- **Liquidity $5M** (screener.py) → `liquidity_flag` thin/ok → position-sizing caution. `[flag]`
- **ΔRank BusinessDay / US holidays** (rank_history.py) → 1m/3m rank-change windows → feeds quadrant. `[minor verdict]`
- **Chandelier ATR(14) vs classic ATR(22)** (screener.py) → chandelier_stop + stop_distance_pct → trailing-stop level. `[display]`
- **Sharpe rf=0** (screener.py) → Sharpe column; inflates ~0.3–0.4 for low-return assets. `[display]`
- **days_in_trend calendar days** (rs_line.py) → "days in trend" on RS cards (~+40% vs trading days). `[display]`
- **trend_4w ±2%** (barometer.py) → up/down/flat arrow per indicator. `[display]`
- **PE gate 3–100** (fundamentals.py) → show/null a P/E → data hygiene. `[display]`

## S16 — verdict-flipper калибрация (BACKTEST-FIRST, 2026-06-19)
Read-only харнес `scripts/backtest_thresholds.py` (reuse-ва живия barometer/quadrant
код; guard: реплика на robust_z == live, Δ=0). Бектест 2г, после калибрация.
Trust-map → решения на Цветослав → retune. Всички base-rate числа verified (изчислени).

**Измерено (2г):**
- **Quadrant**: base_rank_6m ≥80 хваща 20.6%, ≤20 само 12.3% (компресия към центъра).
  Гранична трепка ~8–9%/седмица (приемлива). → **LOW 20→25** (долна опашка 12.3%→17.1%,
  симетрична с 20.6% горе). HIGH 80 запазен.
- **CONF_NET**: net=alarm−base пали тревога **0/101 седмици** — base доминира структурно
  (8/10 калм по подразбиране), net закован ≈ −8. Стойността "2" недостижима. raw
  alarm_count≥2 пали 6.9% и ляга върху реален стрес (апр'25 HY+VIX, лято'25, март'26).
  → **alarm-страна сменена на raw alarm_count≥2** (`ALARM_CONF`); калм-страна остава net
  (`CONF_NET`). Ключове в confluence dict непроменени → app.js без структурна промяна.
- **robust_z**: per-сензор alarm base-rate @504 — XLE/SPY 2.2% ✓, IWM/SPY 8.0% ✓ (здрави);
  MOVE 0.2% / HYG/LQD 0% / XLY/XLP 0% (неми in-sample, коректно калм — НЕ разхлабени);
  VUG/VTV **23%** ⚠ (растежен ТРЕНД, не дислокация; диво прозорец-чувствителен 1/11/23%
  при 756/252/504). → **W=504 & праг 2.0 запазени; VUG/VTV собствен z_alarm=2.5** (→4.98%,
  измерено). Механизъм: per-индикатор `"z_alarm"` override в INDICATORS + `_zone_z(...,z_alarm)`.

**Странична последица (флагната):** вдигането на VUG/VTV на 2.5 го маха и от confluence
броя в седмиците с 2.0≤z<2.5 → alarm-tilt пада 6.9%→**5.0%**; падналите са точно
VUG-driven (лято'25). Оцелелите 5 alarm-седмици са по-твърдите HY/VIX/XLE клъстери.
Чипът и confluence-приносът ползват ЕДИН праг (2.5) — консистентно.

**VUG/VTV остава ЕДНОСТРАНЕН (само еуфория, високо z) — нарочно.** Въпрос (Цветослав):
хваща ли обратното — бягство към дефанзивни? Измерено: VUG/VTV z за 2г не слезе под
−1.14 (дефанзивна опашка z≤−2 = 0.0%, нула дни). И по принцип долната страна е
ДВУСМИСЛЕНА: value = и циклични (финанси/енергия/индустрия), не само дефанзивни → срив
на growth/value може да е здрава рефлация, не стрес. Чистото бягство към дефанзивни се
лови от **XLY/XLP** (`stress_dir="low"`), не от тук. Затова НЕ правим VUG/VTV two-sided.

**Verify gates green:** smoke_test ✓ (нов assert за alarm_conf_threshold + VUG z_alarm)
· daily_update exit 0 (днес alarm=0/base=10 "Спокоен режим") · preview :8137 (10 чипа,
нов банер текст, VUG чип "|z|>2.5", 0 console грешки).

**TODO — редовен калибрационен инструмент (1–2×/год):** `backtest_thresholds.py` е
диагностичният скелет. Да се обвие в редовен ритуал — semi-annual re-run, който мери
base-rate drift на трите обръщача и флагва ако нещо излезе от диапазона (напр. XLE/SPY >
10%, VUG/VTV пак > 8%, quadrant трепка > 15%). Кандидат за scheduled task. Прагът НЕ се
пипа авто — само се показва trust-map за човешко sign-off (като S16).
