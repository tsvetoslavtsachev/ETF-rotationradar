"""
ETF look-through (S18 batch 3) — секторни тегла + концентрация на топ holdings.

Дава „какво има ВЪТРЕ" в ETF-а от yfinance `funds_data`:
  • conc_top10  — сумата на топ holding-ите (обикн. топ-10) като % → концентрационен риск
  • top_holdings — топ-5 [symbol, %] (за tooltip)
  • top_sectors  — топ-3 [сектор, %] (за tooltip)

Има смисъл само за АКЦИОННИ ETF — суровинни/облигационни (GLD, TLT) връщат празно
от yfinance (коректно) и се пропускат. Кеш в parquet (nested полета като JSON стрингове)
по модела на fundamentals: рефетч само на липсващи/остарели; stale-fallback при провал.

Архитектура: ОТДЕЛЕН модул (не пипа работещия fundamentals.py) — нулев blast radius,
без кеш-миграция. Цената е 1 funds_data вызов per equity ETF при изтекъл кеш (рядко).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import pandas as pd
import yfinance as yf

from src.fundamentals import EQUITY_CATEGORIES  # споделена дефиниция кои са акционни

N_HOLD = 5   # топ-N holdings в tooltip-а
N_SECT = 3   # топ-N сектора в tooltip-а

# yfinance sector keys → човешки етикети (непокрит ключ → title-case fallback)
SECTOR_LABELS = {
    "realestate": "Real Estate", "consumer_cyclical": "Cons. Cyclical",
    "basic_materials": "Materials", "consumer_defensive": "Cons. Defensive",
    "technology": "Technology", "communication_services": "Communication",
    "financial_services": "Financials", "utilities": "Utilities",
    "industrials": "Industrials", "energy": "Energy", "healthcare": "Healthcare",
}

COLUMNS = ["ticker", "conc_top10", "top_holdings_json", "top_sectors_json"]


def summarize_funds(sector_weightings, top_holdings_df, n_hold=N_HOLD, n_sect=N_SECT):
    """
    Чиста трансформация (без мрежа) — за тестване и за извличане.
    Връща (conc_top10 %, holds [[sym, %], ...], sects [[label, %], ...]).
    conc е None ако няма holdings (не-акционен ETF).
    """
    conc, holds = None, []
    th = top_holdings_df
    if th is not None and hasattr(th, "empty") and not th.empty and "Holding Percent" in th.columns:
        pcts = pd.to_numeric(th["Holding Percent"], errors="coerce").dropna()
        if len(pcts):
            conc = round(float(pcts.sum()) * 100.0, 1)
        for sym, row in th.head(n_hold).iterrows():
            p = pd.to_numeric(row.get("Holding Percent"), errors="coerce")
            if pd.notna(p):
                holds.append([str(sym), round(float(p) * 100.0, 2)])

    sects = []
    sw = sector_weightings or {}
    nz = [(k, float(v)) for k, v in sw.items() if v and float(v) > 0]
    nz.sort(key=lambda kv: -kv[1])
    for k, v in nz[:n_sect]:
        sects.append([SECTOR_LABELS.get(k, k.replace("_", " ").title()), round(v * 100.0, 1)])

    return conc, holds, sects


def _rate_limited(err: Exception) -> bool:
    m = str(err).lower()
    return "too many requests" in m or "rate limit" in m or "429" in m


def _fetch_one(ticker: str, max_retries: int = 3):
    """Връща (record_dict, success). При 429 backoff + retry."""
    for attempt in range(max_retries):
        try:
            fd = yf.Ticker(ticker).funds_data
            sw = getattr(fd, "sector_weightings", None)
            th = getattr(fd, "top_holdings", None)
            conc, holds, sects = summarize_funds(sw, th)
            return {
                "ticker": ticker,
                "conc_top10": conc,
                "top_holdings_json": json.dumps(holds),
                "top_sectors_json": json.dumps(sects),
            }, True
        except Exception as e:
            if _rate_limited(e) and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  rate-limited on {ticker} (look-through), retry in {wait}s...")
                time.sleep(wait)
                continue
            print(f"Error fetching look-through for {ticker}: {e}")
            return {"ticker": ticker, "conc_top10": None,
                    "top_holdings_json": "[]", "top_sectors_json": "[]"}, False
    return {"ticker": ticker, "conc_top10": None,
            "top_holdings_json": "[]", "top_sectors_json": "[]"}, False


def compute_lookthrough(
    tickers: list[str],
    category_map: "dict[str, str] | None" = None,
    cache_path: "str | Path | None" = None,
    max_age_days: int = 7,
) -> pd.DataFrame:
    """
    Връща df[ticker, conc_top10, top_holdings_json, top_sectors_json].
    Тегли само АКЦИОННИ ETF (category_map ∈ EQUITY_CATEGORIES); останалите се
    пропускат (не-акционните връщат празно от yfinance така или иначе). Кеш с
    7-дневен fresh-праг + stale-fallback по модела на fundamentals.
    """
    if category_map is not None:
        equity = [t for t in tickers if category_map.get(t) in EQUITY_CATEGORIES]
    else:
        equity = list(tickers)

    now = pd.Timestamp.now().normalize()
    cache: dict[str, dict] = {}
    cpath = Path(cache_path) if cache_path is not None else None
    if cpath is not None and cpath.exists():
        try:
            for _, r in pd.read_parquet(cpath).iterrows():
                cache[r["ticker"]] = r.to_dict()
        except Exception as e:
            print(f"Could not read look-through cache: {e}")

    print(f"Look-through for {len(equity)} equity ETFs (cache: {len(cache)} known)...")
    records = []
    n_fetched = n_cached = n_stale = 0
    for i, ticker in enumerate(equity):
        c = cache.get(ticker)
        if c is not None and pd.notna(c.get("fetched_at")):
            if (now - pd.Timestamp(c["fetched_at"]).normalize()).days <= max_age_days:
                rec = {k: c.get(k) for k in COLUMNS}
                rec["fetched_at"] = c["fetched_at"]
                records.append(rec)
                n_cached += 1
                continue

        rec, ok = _fetch_one(ticker)
        if not ok and c is not None:
            rec = {k: c.get(k) for k in COLUMNS}
            rec["fetched_at"] = c.get("fetched_at", now)
            n_stale += 1
        else:
            rec["fetched_at"] = now
            n_fetched += 1
        records.append(rec)
        if (i + 1) % 20 == 0:
            time.sleep(1)

    df = pd.DataFrame(records, columns=COLUMNS + ["fetched_at"]) if records \
        else pd.DataFrame(columns=COLUMNS + ["fetched_at"])
    print(f"Look-through: {n_fetched} fetched, {n_cached} cached, {n_stale} stale-fallback")

    if cpath is not None and not df.empty:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cpath, index=False)
        except Exception as e:
            print(f"Could not write look-through cache: {e}")

    return df[COLUMNS] if not df.empty else df
