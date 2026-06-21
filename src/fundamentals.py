"""
Fetch fundamental data for ETFs using yfinance.
Extracts AUM, Expense Ratio, Yield, P/E (equity), Duration (bond).

Надеждност:
- Кеш в parquet — рефетчваме само липсващи/остарели тикъри (fundamentals се
  менят бавно), което рязко намалява заявките и риска от rate-limit.
- Retry с backoff при "Too Many Requests" (429).
- При неуспех падаме обратно към остарелия кеш вместо да връщаме празно.
"""

from __future__ import annotations

import time
from pathlib import Path
import pandas as pd
import yfinance as yf

# NB: `duration` е премахнат — yfinance bond_holdings дава ненадеждни стойности
# (напр. TLT ~3.5г при реални ~16г), а грешно число към абонати е по-лошо от никакво.
COLUMNS = ["ticker", "aum", "shares_out", "expense_ratio", "yield", "pe_ratio", "holdings_turnover"]

# Категории, за които P/E има смисъл. За облигации/суровини/валути/волатилност
# info["trailingPE"] връща боклук (напр. SHY ~3720, AGG ~125) — занулява се.
EQUITY_CATEGORIES = {"US Equity", "US Sector", "Factor", "Thematic", "Intl Equity", "Real Estate"}
PE_MIN, PE_MAX = 3.0, 100.0  # допълнителен sanity предпазител


def _empty_record(ticker: str) -> dict:
    rec = {c: None for c in COLUMNS}
    rec["ticker"] = ticker
    return rec


def _is_rate_limited(err: Exception) -> bool:
    msg = str(err).lower()
    return "too many requests" in msg or "rate limit" in msg or "429" in msg


def _fetch_one(ticker: str, max_retries: int = 3) -> tuple[dict, bool]:
    """Връща (record, success). При 429 прави backoff и опитва пак."""
    for attempt in range(max_retries):
        record = _empty_record(ticker)
        try:
            tk = yf.Ticker(ticker)
            info = tk.info

            aum = info.get("totalAssets") or info.get("netAssets")
            if aum:
                record["aum"] = float(aum)

            # Дялове (shares outstanding) — основният вход за flows v2. Идва от
            # СЪЩИЯ .info dict (нула нови заявки). Менят се само при
            # creation/redemption → чист поток (price × Δshares).
            so = info.get("sharesOutstanding")
            if so:
                record["shares_out"] = float(so)

            div_yield = info.get("yield") or info.get("trailingAnnualDividendYield")
            if div_yield:
                record["yield"] = float(div_yield) * 100.0  # дроб -> процент

            # P/E — trailingPE директно от info (надеждно: SPY ~26.7).
            # funds_data.equity_holdings "Price/Earnings" връща реципрочна стойност
            # (~0.037 за SPY) и 0.0 за облигационни фондове — затова НЕ го ползваме.
            pe = info.get("trailingPE")
            if pe and float(pe) > 0:
                record["pe_ratio"] = float(pe)

            # Funds data (по-нов yfinance API) — Expense Ratio, Turnover, Duration
            try:
                fd = tk.funds_data

                if getattr(fd, "fund_operations", None) is not None:
                    ops = fd.fund_operations
                    if not ops.empty and ticker in ops.columns:
                        if "Annual Report Expense Ratio" in ops.index:
                            val = ops.loc["Annual Report Expense Ratio", ticker]
                            if pd.notna(val):
                                record["expense_ratio"] = float(val) * 100.0
                        if "Annual Holdings Turnover" in ops.index:
                            val = ops.loc["Annual Holdings Turnover", ticker]
                            if pd.notna(val):
                                record["holdings_turnover"] = float(val) * 100.0
            except (AttributeError, KeyError, TypeError, IndexError, ValueError):
                # funds_data липсва/непълна за някои ETF-и — толерираме само
                # очакваните data-shape грешки (реален бъг ще се вдигне нагоре).
                pass

            return record, True

        except Exception as e:
            if _is_rate_limited(e) and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  rate-limited on {ticker}, retry in {wait}s...")
                time.sleep(wait)
                continue
            print(f"Error fetching fundamentals for {ticker}: {e}")
            return record, False

    return _empty_record(ticker), False


def fetch_fundamentals(
    tickers: list[str],
    cache_path: "str | Path | None" = None,
    max_age_days: int = 7,
    category_map: "dict[str, str] | None" = None,
) -> pd.DataFrame:
    """
    Изтегля фундаментални данни с кеш.
    Връща DataFrame с колони COLUMNS (без fetched_at).
    Ако е подаден category_map, P/E се занулява за неакционерни категории.
    """
    now = pd.Timestamp.now().normalize()

    # --- зареди кеш ---
    cache: dict[str, dict] = {}
    cpath = Path(cache_path) if cache_path is not None else None
    if cpath is not None and cpath.exists():
        try:
            cdf = pd.read_parquet(cpath)
            for _, r in cdf.iterrows():
                cache[r["ticker"]] = r.to_dict()
        except Exception as e:
            print(f"Could not read fundamentals cache: {e}")

    print(f"Fetching fundamentals for {len(tickers)} ETFs (cache: {len(cache)} known)...")

    records = []
    n_fetched = n_cached = n_stale = 0

    for i, ticker in enumerate(tickers):
        c = cache.get(ticker)
        fresh = False
        if c is not None and pd.notna(c.get("fetched_at")):
            age = (now - pd.Timestamp(c["fetched_at"]).normalize()).days
            if age <= max_age_days:
                fresh = True

        if fresh:
            rec = {k: c.get(k) for k in COLUMNS}
            rec["fetched_at"] = c["fetched_at"]
            records.append(rec)
            n_cached += 1
            continue

        rec, ok = _fetch_one(ticker)
        if not ok and c is not None:
            # padаме обратно към stale кеш вместо празно; пазим стария timestamp,
            # за да се пробва пак следващия път
            rec = {k: c.get(k) for k in COLUMNS}
            rec["fetched_at"] = c.get("fetched_at", now)
            n_stale += 1
        else:
            rec["fetched_at"] = now
            n_fetched += 1

        records.append(rec)
        if (i + 1) % 20 == 0:
            time.sleep(1)

    df = pd.DataFrame(records)
    print(f"Fundamentals: {n_fetched} fetched, {n_cached} cached, {n_stale} stale-fallback")

    # Гейт за P/E: само акционерни категории + sanity граници (зануляваме боклука).
    def _gate_pe(row):
        pe = row.get("pe_ratio")
        if pe is None or not (PE_MIN <= pe <= PE_MAX):
            return None
        if category_map is not None and category_map.get(row["ticker"]) not in EQUITY_CATEGORIES:
            return None
        return pe
    if not df.empty:
        df["pe_ratio"] = df.apply(_gate_pe, axis=1)

    # --- запиши кеш ---
    if cpath is not None and not df.empty:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cpath, index=False)
        except Exception as e:
            print(f"Could not write fundamentals cache: {e}")

    return df[COLUMNS]
