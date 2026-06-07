# ETF Rotation Radar

A daily-updated dashboard tracking **momentum, relative strength, fundamentals, and a live macro-regime barometer** across 131 ETFs in 9 asset categories.

**Live Dashboard:** [tsvetoslavtsachev.github.io/ETF-rotationradar](https://tsvetoslavtsachev.github.io/ETF-rotationradar)

---

## What It Does

The ETF Rotation Radar applies the same systematic framework used in the SP500 and STOXX600 Rotation Radars, adapted specifically for ETFs:

- **Category-Relative Momentum Z-Score** — each ETF is ranked *within its own category* (US Sector, Thematic, Fixed Income, etc.), so `percentile_rank` answers "which ETF leads its class". A separate **absolute** momentum percentile drives the Macro Heatmap.
- **Rotation Quadrants (ΔRank)** — ETFs are classified into four quadrants based on their 6-month base rank and recent momentum change:
  - **Stable Winners** — high base, still rising
  - **Quality Dip** — high base, pulling back (buy-the-dip candidates)
  - **Risers** — low base, gaining momentum
  - **Chronic Losers** — low base, still falling
- **Pristine RS Line** — each ETF's price divided by its *category benchmark* (not always SPY), with EMA10/SMA50 crossover signals.
- **Behavioral Barometer (macro-regime banner)** — three dislocation indicators computed live every day: **HY-spread** (FRED `BAMLH0A0HYM2`), **XLE/SPY**, and **GLD/TLT**, each scored against base/alarm thresholds with a confluence verdict. Also exported as `docs/barometer_feed.json` for downstream tooling.
- **Fundamental Screener** — Return 1/3/12M, Sharpe, MaxDD, **distance from 52-week high**, **current drawdown**, Expense Ratio, Yield, P/E (equity ETFs only), AUM — all from free yfinance data, with a local cache to avoid rate limits.

> **Note:** leveraged / inverse / volatility products (e.g. 3x funds, VIX ETFs) are intentionally excluded — daily-reset leverage distorts 12-1 momentum z-scores relative to their category peers.

---

## Universe (131 ETFs, all >$100M AUM)

| Category | Count | Benchmark |
|---|---|---|
| US Equity | 10 | SPY |
| US Sector | 10 | SPY |
| Factor | 11 | SPY |
| Thematic | 31 | SPY |
| Intl Equity | 26 | VGK (Europe) / EEM (EM/Asia) / VT (Global) |
| Fixed Income | 18 | BND |
| Commodity | 16 | DBC |
| Real Estate | 5 | VNQ |
| Currency | 4 | UUP |

---

## Project Structure

```
ETF-rotationradar/
├── src/
│   ├── universe.py          # 131 ETFs with category and benchmark mapping
│   ├── prices.py            # yfinance price downloader
│   ├── signal_engine.py     # 12-1 momentum + category z-score
│   ├── rank_history.py      # ΔRank engine + quadrant classification
│   ├── rs_line.py           # RS Line vs category benchmark (EMA10/SMA50)
│   ├── screener.py          # Return, Vol, Sharpe, MaxDD, 52w-high dist, drawdown
│   ├── fundamentals.py      # Expense Ratio, Yield, P/E, AUM (yfinance, cached)
│   ├── fred.py              # Keyless FRED CSV fetch (cached, stale-fallback)
│   ├── barometer.py         # ELANA behavioral barometer (HY / XLE-SPY / GLD-TLT)
│   └── render.py            # Merges everything into docs/data.json + barometer_feed.json
├── scripts/
│   ├── daily_update.py      # Main pipeline (runs daily via GitHub Actions)
│   └── backfill_history.py  # One-time initialization of rank history
├── data/
│   └── ranks_history.parquet
├── docs/                    # GitHub Pages static site
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── data.json            # Generated daily
├── .github/workflows/
│   └── daily_update.yml     # Runs every weekday at 22:00 UTC
└── requirements.txt
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/tsvetoslavtsachev/ETF-rotationradar.git
cd ETF-rotationradar
pip install -r requirements.txt
```

### 2. Backfill history (run once)

```bash
python scripts/backfill_history.py
```

### 3. Run a manual update

```bash
python scripts/daily_update.py
```

### 4. Enable GitHub Pages

In repository Settings → Pages → Source: **Deploy from branch** → Branch: `main` → Folder: `/docs`

---

## Automation

GitHub Actions runs `scripts/daily_update.py` every weekday at **22:00 UTC** (after US market close). Results are committed to `data/ranks_history.parquet` and `docs/data.json`.

---

## Data Sources

All data is fetched via [yfinance](https://github.com/ranaroussi/yfinance) — **100% free, no API key required**.

| Data Type | Source | Notes |
|---|---|---|
| Adjusted Close Prices | yfinance | Used for all momentum and RS calculations |
| AUM (Total Assets) | yfinance `.info` | Used for universe filtering |
| Expense Ratio | yfinance `funds_data.fund_operations` | Available for most ETFs |
| Yield | yfinance `.info` | Trailing 12-month yield |
| P/E Ratio | yfinance `.info` `trailingPE` | Equity categories only; gated to a sane range |
| HY-spread | FRED `BAMLH0A0HYM2` (keyless CSV) | Barometer; cached with stale fallback |

---

## Related Projects

- [SP500-rotationradar](https://github.com/tsvetoslavtsachev/SP500-rotationradar) — Individual stock rotation for S&P 500
- [STOXX600-rotationradar](https://github.com/tsvetoslavtsachev/STOXX600-rotationradar) — Individual stock rotation for STOXX 600
- [ETF-Dashboard](https://github.com/tsvetoslavtsachev/ETF-Dashboard) — Broader ETF macro dashboard
