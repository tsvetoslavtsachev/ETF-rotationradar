"""
COT позициониране (S18 batch 4) — CFTC Commitments of Traders, keyless Socrata.

За commodity/rate ETF: къде стои спекулативното позициониране спрямо собствената си
3-годишна история (percentile). Net = дълги − къси на спекулантите:
  • Стоки → Disaggregated (72hh-3qpy), Managed Money net (m_money_long − m_money_short)
  • Лихви → Traders in Financial Futures (gpe5-46if), Leveraged Funds net (lev_money_*)
(Конвенцията MM=стоки / LEV=финансови е същата като INIT-22 cot-monitor.)

Високо percentile = тълпата струпана дълга (контра-предупреждение); ниско = струпана къса.
Само за мапнатите ETF; останалите → None. Пинираме по `cftc_contract_market_code`
(НЕ по име) — CFTC преименува контрактите; заявка по име е крехка (урок от INIT-22).

Архитектура като look-through: отделен модул, собствен кеш `data/cot.parquet` (седмичен
refresh), seed-нат в commit-а → CI тръгва топъл. Keyless — без app token (проверено).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
import pandas as pd

SOCRATA = "https://publicreporting.cftc.gov/resource"
DATASETS = {"disagg": "72hh-3qpy", "tff": "gpe5-46if"}

# Полета за net по тип трейдър (disaggregated MM ползва _all суфикс; TFF LEV — не)
NET_FIELDS = {
    "mm": ("m_money_positions_long_all", "m_money_positions_short_all"),
    "lev": ("lev_money_positions_long", "lev_money_positions_short"),
}
KIND_LABEL = {"mm": "Managed money", "lev": "Leveraged funds"}

PCT_WINDOW = 156   # ~3 години седмични отчета за percentile
HIST_LIMIT = 200   # колко седмици да теглим (>window за пълен прозорец)
MIN_HIST = 8       # под толкова седмици percentile е безсмислен

# ETF → (dataset, cftc_code, net_kind, контракт-етикет). Verified кодове (резолвнати
# от живия CFTC; TLT по дюрация→Ultra Bond, алтернатива класич. Bond 020601).
COT_MAP = {
    "GLD":  ("disagg", "088691", "mm", "Gold (COMEX)"),
    "IAU":  ("disagg", "088691", "mm", "Gold (COMEX)"),
    "SLV":  ("disagg", "084691", "mm", "Silver"),
    "CPER": ("disagg", "085692", "mm", "Copper"),
    "USO":  ("disagg", "067651", "mm", "WTI Crude (NYMEX)"),
    "UNG":  ("disagg", "023651", "mm", "Nat Gas (NYMEX)"),
    "WEAT": ("disagg", "001602", "mm", "Wheat SRW"),
    "CORN": ("disagg", "002602", "mm", "Corn"),
    "PALL": ("disagg", "075651", "mm", "Palladium"),
    "PPLT": ("disagg", "076651", "mm", "Platinum"),
    "SHY":  ("tff", "042601", "lev", "UST 2Y Note"),
    "IEF":  ("tff", "043602", "lev", "UST 10Y Note"),
    "TLT":  ("tff", "020604", "lev", "Ultra UST Bond"),
}

COLUMNS = ["ticker", "cot_pctile", "cot_net", "cot_pct_oi", "cot_date", "cot_market", "cot_kind"]


def summarize_cot(rows, net_kind, window=PCT_WINDOW):
    """
    Чиста трансформация (без мрежа) — за тестване. `rows` са Socrata записи,
    подредени по дата НИЗХОДЯЩО (най-новият пръв). Връща dict с percentile +
    последни стойности, или None при недостатъчна история.
    """
    lf, sf = NET_FIELDS[net_kind]
    series = []  # (net, oi) в реда на входа (desc)
    for r in rows:
        try:
            net = int(float(r[lf])) - int(float(r[sf]))
            oi = float(r.get("open_interest_all") or 0)
            series.append((net, oi, r["report_date_as_yyyy_mm_dd"][:10]))
        except (KeyError, ValueError, TypeError):
            continue
    if not series:
        return None
    cur_net, cur_oi, cur_date = series[0]
    win = [net for net, _, _ in series[:window]]
    if len(win) < MIN_HIST:
        return None
    below = sum(1 for n in win if n <= cur_net)
    return {
        "cot_pctile": round(below / len(win) * 100),
        "cot_net": cur_net,
        "cot_pct_oi": round(cur_net / cur_oi * 100, 1) if cur_oi else None,
        "cot_date": cur_date,
    }


def _rate_limited(err: Exception) -> bool:
    m = str(err).lower()
    return "429" in m or "too many requests" in m or "rate limit" in m


def _fetch_one(ticker: str, max_retries: int = 3):
    """Тегли историята за един контракт от Socrata и обобщава. (record, success)."""
    dataset, code, kind, label = COT_MAP[ticker]
    url = (f"{SOCRATA}/{DATASETS[dataset]}.json?cftc_contract_market_code={code}"
           f"&$order=report_date_as_yyyy_mm_dd%20DESC&$limit={HIST_LIMIT}")
    empty = {"ticker": ticker, "cot_pctile": None, "cot_net": None, "cot_pct_oi": None,
             "cot_date": None, "cot_market": label, "cot_kind": KIND_LABEL[kind]}
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "etf-radar/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                rows = json.loads(r.read())
            summ = summarize_cot(rows, kind)
            if summ is None:
                return empty, True  # валиден отговор, но без достатъчно история
            rec = {"ticker": ticker, "cot_market": label, "cot_kind": KIND_LABEL[kind]}
            rec.update(summ)
            return rec, True
        except Exception as e:
            if _rate_limited(e) and attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            print(f"Error fetching COT for {ticker} ({code}): {e}")
            return empty, False
    return empty, False


def compute_cot(
    tickers: list[str],
    cache_path: "str | Path | None" = None,
    max_age_days: int = 6,
) -> pd.DataFrame:
    """
    Връща df[COLUMNS] за мапнатите ETF (COT_MAP). Кеш с ~седмичен fresh-праг
    (COT излиза петък за вторник) + stale-fallback. Тегли само мапнатите тикъри.
    """
    targets = [t for t in tickers if t in COT_MAP]
    now = pd.Timestamp.now().normalize()

    cache: dict[str, dict] = {}
    cpath = Path(cache_path) if cache_path is not None else None
    if cpath is not None and cpath.exists():
        try:
            for _, r in pd.read_parquet(cpath).iterrows():
                cache[r["ticker"]] = r.to_dict()
        except Exception as e:
            print(f"Could not read COT cache: {e}")

    print(f"COT for {len(targets)} mapped ETFs (cache: {len(cache)} known)...")
    records = []
    n_fetched = n_cached = n_stale = 0
    for i, ticker in enumerate(targets):
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
        time.sleep(0.5)  # учтиво към Socrata

    df = pd.DataFrame(records, columns=COLUMNS + ["fetched_at"]) if records \
        else pd.DataFrame(columns=COLUMNS + ["fetched_at"])
    print(f"COT: {n_fetched} fetched, {n_cached} cached, {n_stale} stale-fallback")

    if cpath is not None and not df.empty:
        try:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cpath, index=False)
        except Exception as e:
            print(f"Could not write COT cache: {e}")

    return df[COLUMNS] if not df.empty else df
