# ETF Rotation Radar

A daily-updated dashboard tracking **momentum, relative strength, and fundamentals** across 135 ETFs in 10 asset categories.

**Live Dashboard:** [tsvetoslavtsachev.github.io/ETF-rotationradar](https://tsvetoslavtsachev.github.io/ETF-rotationradar)

---

## What It Does

The ETF Rotation Radar applies the same systematic framework used in the SP500 and STOXX600 Rotation Radars, adapted specifically for ETFs:

- **Category-Relative Momentum Z-Score** — each ETF is ranked within its own category (US Sector, Thematic, Fixed Income, etc.), not against the entire universe. This reveals which ETF is leading *within its class*.
- **Rotation Quadrants (ΔRank)** — ETFs are classified into four quadrants based on their 6-month base rank and recent momentum change:
  - **Stable Winners** — high base, still rising
  - **Quality Dip** — high base, pulling back (buy-the-dip candidates)
  - **Risers** — low base, gaining momentum
  - **Chronic Losers** — low base, still falling
- **Pristine RS Line** — each ETF's price divided by its *category benchmark* (not always SPY), with EMA10/SMA50 crossover signals.
- **Fundamental Screener** — Expense Ratio, Yield, P/E (equity ETFs), Duration (bond ETFs), AUM — all from free yfinance data.

---

## Universe (135 ETFs, all >$100M AUM)

| Category | Count | Benchmark |
|---|---|---|
| US Equity | 10 | SPY |
| US Sector | 10 | SPY |
| Factor | 11 | SPY |
| Thematic | 32 | SPY |
| Intl Equity | 26 | VGK (Europe) / EEM (EM/Asia) / VT (Global) |
| Fixed Income | 18 | BND |
| Commodity | 16 | DBC |
| Real Estate | 5 | VNQ |
| Currency | 4 | UUP |
| Volatility | 2 | SPY |

---

## Project Structure

```
ETF-rotationradar/
├── src/
│   ├── universe.py          # 135 ETFs with category and benchmark mapping
│   ├── prices.py            # yfinance price downloader
│   ├── signal_engine.py     # 12-1 momentum + category z-score
│   ├── rank_history.py      # ΔRank engine + quadrant classification
│   ├── rs_line.py           # RS Line vs category benchmark (EMA10/SMA50)
│   ├── screener.py          # Return, Volatility, Sharpe, MaxDD
│   └── fundamentals.py      # Expense Ratio, Yield, P/E, Duration (yfinance)
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
| P/E Ratio | yfinance `funds_data.equity_holdings` | Equity ETFs only |
| Duration | yfinance `funds_data.bond_holdings` | Bond ETFs only |

---

## Related Projects

- [SP500-rotationradar](https://github.com/tsvetoslavtsachev/SP500-rotationradar) — Individual stock rotation for S&P 500
- [STOXX600-rotationradar](https://github.com/tsvetoslavtsachev/STOXX600-rotationradar) — Individual stock rotation for STOXX 600
- [ETF-Dashboard](https://github.com/tsvetoslavtsachev/ETF-Dashboard) — Broader ETF macro dashboard
