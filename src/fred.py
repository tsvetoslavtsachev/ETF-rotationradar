"""
FRED (Federal Reserve Economic Data) — безплатно теглене без API ключ.

Ползва публичния `fredgraph.csv` endpoint (без ключ), с:
- parquet кеш + freshness (по подразбиране 1 ден),
- retry с backoff,
- fallback към stale кеш при мрежов проблем (важно за GitHub Actions).

Stooq НЕ се ползва — проверено е блокиран от анти-бот (proof-of-work), пада в CI.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_UA = "Mozilla/5.0 (ETF-RotationRadar; +https://github.com/tsvetoslavtsachev)"


def _download_csv(series_id: str, timeout: int = 30) -> pd.Series:
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


def fetch_fred_series(
    series_id: str,
    cache_path: "str | Path | None" = None,
    max_age_days: int = 1,
    max_retries: int = 3,
) -> pd.Series:
    """
    Връща pd.Series (DatetimeIndex -> float) за FRED серия.
    При неуспех пада към stale кеш; ако и той липсва — връща празна серия.
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

    # --- теглене с backoff ---
    for attempt in range(max_retries):
        try:
            s = _download_csv(series_id)
            if cpath is not None and len(s):
                out = pd.DataFrame({"date": s.index, "value": s.values})
                out["fetched_at"] = now
                cpath.parent.mkdir(parents=True, exist_ok=True)
                out.to_parquet(cpath, index=False)
            return s
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                print(f"FRED {series_id} fetch failed ({e}); retry in {wait}s...")
                time.sleep(wait)
            else:
                print(f"FRED {series_id} fetch failed after {max_retries} tries: {e}")

    # --- fallback към stale кеш ---
    if cached is not None:
        print(f"FRED {series_id}: ползвам stale кеш ({len(cached)} точки)")
        return cached
    return pd.Series(dtype=float, name=series_id)
