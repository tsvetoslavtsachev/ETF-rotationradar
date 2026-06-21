"""
FRED (Federal Reserve Economic Data) — безплатно теглене на серии.

Два пътя, в ред на надеждност:
1. **Официален API** `api.stlouisfed.org` + `FRED_API_KEY` (env / GitHub secret) —
   ПРЕДПОЧИТАН. Отговаря за ~0.5с локално И в CI; не е bot-блокиран.
2. **Keyless `fredgraph.csv`** — fallback, ако няма ключ или API откаже. ⚠️ ЧУПЛИВ:
   от ~2026-06-07 fredgraph е силно rate-limit-нат/bot-филтриран — заявките
   увисват и от dev машината, и от GitHub runner-ите (datacenter IP). Държим го
   само като резерва.

Плюс за двата:
- parquet кеш + freshness (по подразбиране 1 ден),
- retry с backoff,
- fallback към stale кеш при мрежов проблем (важно за GitHub Actions).

INIT-22 урок (data-core S6b): keyless fredgraph bot-stall-ва НАВСЯКЪДЕ; официалният
API + ключ е робъстният път. Затова primary е API-то, keyless е label-нат резерв.
Stooq НЕ се ползва — блокиран от анти-бот (proof-of-work).
"""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_UA = "Mozilla/5.0 (ETF-RotationRadar; +https://github.com/tsvetoslavtsachev)"


def _parse_api_json(data: dict, series_id: str) -> pd.Series:
    """Чист парсер на FRED API JSON → pd.Series (тестваем без мрежа)."""
    obs = data.get("observations", [])
    dates, vals = [], []
    for o in obs:
        v = o.get("value")
        if v in (None, ".", ""):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        dates.append(o.get("date"))
        vals.append(fv)
    s = pd.Series(vals, index=pd.to_datetime(dates), name=series_id).dropna()
    if s.empty:
        raise ValueError(f"FRED API: няма използваеми наблюдения за {series_id}")
    return s


def _download_api(series_id: str, api_key: str, timeout: int = 30) -> pd.Series:
    """Официален FRED API (JSON). Хвърля при празен/невалиден отговор."""
    url = (f"{FRED_API_URL}?series_id={series_id}"
           f"&file_type=json&api_key={api_key}")
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return _parse_api_json(data, series_id)


def _download_csv(series_id: str, timeout: int = 60) -> pd.Series:
    """Keyless fredgraph.csv (резервен път)."""
    url = FRED_CSV_URL.format(sid=series_id)
    req = Request(url, headers={"User-Agent": _UA})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    df = pd.read_csv(io.BytesIO(raw), na_values=".")
    # Първата колона е дата, втората — стойността (FRED връща 'observation_date' или 'DATE')
    date_col = df.columns[0]
    val_col = df.columns[1]
    s = pd.Series(
        pd.to_numeric(df[val_col], errors="coerce").values,
        index=pd.to_datetime(df[date_col]),
        name=series_id,
    ).dropna()
    return s


def _fetch_remote(series_id: str) -> pd.Series:
    """
    Тегли серия от мрежата: официален API (ако има ключ) → keyless fredgraph.
    Хвърля, ако и двата паднат (за да задейства retry/stale-кеш горе).
    """
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            return _download_api(series_id, api_key)
        except Exception as e:
            print(f"FRED API падна за {series_id} ({e}); пробвам keyless fredgraph...")
    return _download_csv(series_id)


def fetch_fred_series(
    series_id: str,
    cache_path: "str | Path | None" = None,
    max_age_days: int = 1,
    max_retries: int = 3,
) -> pd.Series:
    """
    Връща pd.Series (DatetimeIndex -> float) за FRED серия.
    Primary = официален API + FRED_API_KEY; fallback = keyless fredgraph; после
    stale кеш; ако и той липсва — празна серия.
    """
    cpath = Path(cache_path) if cache_path is not None else None
    now = pd.Timestamp.now().normalize()

    # --- свеж кеш? ---
    cached: pd.Series | None = None
    if cpath is not None and cpath.exists():
        try:
            cdf = pd.read_parquet(cpath)
            cached = pd.Series(cdf["value"].values, index=pd.to_datetime(cdf["date"]), name=series_id)
            fetched_at = pd.Timestamp(cdf["fetched_at"].iloc[0]).normalize() if "fetched_at" in cdf else None
            if fetched_at is not None and (now - fetched_at).days <= max_age_days:
                return cached
        except Exception as e:
            print(f"FRED cache read failed for {series_id}: {e}")

    # --- теглене с backoff (API primary, keyless fallback вътре в _fetch_remote) ---
    for attempt in range(max_retries):
        try:
            s = _fetch_remote(series_id)
            if cpath is not None and len(s):
                out = pd.DataFrame({"date": s.index, "value": s.values})
                out["fetched_at"] = now
                cpath.parent.mkdir(parents=True, exist_ok=True)
                out.to_parquet(cpath, index=False)
            return s
        except Exception as e:
            if attempt < max_retries - 1:
                # По-дълъг backoff: keyless fredgraph rate-limit-ва на пориви; 20/40s
                # дава шанс прозорецът да отмине в рамките на същия run. (При API
                # ключ заявката рядко стига дотук.)
                wait = 20 * (attempt + 1)
                print(f"FRED {series_id} fetch failed ({e}); retry in {wait}s...")
                time.sleep(wait)
            else:
                print(f"FRED {series_id} fetch failed after {max_retries} tries: {e}")

    # --- fallback към stale кеш ---
    if cached is not None:
        print(f"FRED {series_id}: ползвам stale кеш ({len(cached)} точки)")
        return cached
    return pd.Series(dtype=float, name=series_id)
