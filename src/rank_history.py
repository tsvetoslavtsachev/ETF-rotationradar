"""
Rank History persistence + ΔRank Engine.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from src.signal_engine import compute_cross_section

HISTORY_COLUMNS = ["date", "ticker", "raw_score", "percentile_rank", "unadj_percentile"]

DELTA_1M_DAYS = 21
DELTA_3M_DAYS = 63
BASE_START_DAYS = 126
BASE_END_DAYS = 21

HIGH_BASE_THRESHOLD = 80.0
# S16 (2026-06-19): LOW 20→25 за симетрични опашки. base_rank_6m (6м средно на
# percentile) е компресирано към центъра → ≥80 хващаше 20.6%, но ≤20 само 12.3%.
# 25 изравнява долната опашка към горната ("riser"/"chronic_loser" вече не са
# недонаселени спрямо "stable_winner"/"decayer").
LOW_BASE_THRESHOLD = 25.0

def append_snapshot(history_path: Path, snapshot: pd.DataFrame) -> None:
    snap = snapshot[HISTORY_COLUMNS].copy()
    snap["date"] = pd.to_datetime(snap["date"])

    if history_path.exists():
        existing = pd.read_parquet(history_path)
        existing["date"] = pd.to_datetime(existing["date"])
        snap_keys = set(zip(snap["date"], snap["ticker"]))
        mask = [
            (d, t) not in snap_keys
            for d, t in zip(existing["date"], existing["ticker"])
        ]
        existing = existing.loc[mask]
        combined = pd.concat([existing, snap], ignore_index=True)
    else:
        combined = snap

    combined = combined.sort_values(["date", "ticker"]).reset_index(drop=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(history_path, index=False)

def load_history(history_path: Path) -> pd.DataFrame:
    if not history_path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    df = pd.read_parquet(history_path)
    df["date"] = pd.to_datetime(df["date"])
    return df

def _rank_at_offset(history: pd.DataFrame, target_date: pd.Timestamp, days_back: int) -> pd.Series:
    cutoff = target_date - pd.tseries.offsets.BusinessDay(days_back)
    sub = history[history["date"] <= cutoff]
    if sub.empty:
        return pd.Series(dtype=float)
    last_date = sub["date"].max()
    snap = sub[sub["date"] == last_date].set_index("ticker")["percentile_rank"]
    return snap

def _base_rank_window(history: pd.DataFrame, target_date: pd.Timestamp) -> pd.Series:
    upper = target_date - pd.tseries.offsets.BusinessDay(BASE_END_DAYS)
    lower = target_date - pd.tseries.offsets.BusinessDay(BASE_START_DAYS)
    window = history[(history["date"] >= lower) & (history["date"] <= upper)]
    if window.empty:
        return pd.Series(dtype=float)
    return window.groupby("ticker")["percentile_rank"].mean()

def _classify_quadrant(base: float, delta: float) -> str:
    if not np.isfinite(base) or not np.isfinite(delta):
        return "unknown"
    if base <= LOW_BASE_THRESHOLD and delta > 0:
        return "riser"
    if base >= HIGH_BASE_THRESHOLD and delta < 0:
        return "decayer"
    if base >= HIGH_BASE_THRESHOLD and delta >= 0:
        return "stable_winner"
    if base <= LOW_BASE_THRESHOLD and delta <= 0:
        return "chronic_loser"
    return "neutral"

def compute_delta_metrics(history: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()

    if as_of is None:
        as_of = history["date"].max()
    as_of = pd.Timestamp(as_of)

    current = history[history["date"] == as_of].set_index("ticker")
    if current.empty:
        latest_date = history[history["date"] <= as_of]["date"].max()
        if pd.isna(latest_date):
            return pd.DataFrame()
        current = history[history["date"] == latest_date].set_index("ticker")
        as_of = latest_date

    rank_now = current["percentile_rank"]
    abs_strength_now = current["unadj_percentile"]
    rank_1m = _rank_at_offset(history, as_of, DELTA_1M_DAYS)
    rank_3m = _rank_at_offset(history, as_of, DELTA_3M_DAYS)
    base = _base_rank_window(history, as_of)

    out = pd.DataFrame({
        "current_rank": rank_now,
        "abs_strength": abs_strength_now,
        "rank_1m_ago": rank_1m,
        "rank_3m_ago": rank_3m,
        "base_rank_6m": base,
    })
    out["delta_1m"] = out["current_rank"] - out["rank_1m_ago"]
    out["delta_3m"] = out["current_rank"] - out["rank_3m_ago"]
    out["quadrant_1m"] = [_classify_quadrant(b, d) for b, d in zip(out["base_rank_6m"], out["delta_1m"])]
    out["quadrant_3m"] = [_classify_quadrant(b, d) for b, d in zip(out["base_rank_6m"], out["delta_3m"])]
    out["as_of_date"] = as_of
    return out.reset_index()

def get_stable_winners(deltas: pd.DataFrame, window: str = "1m", limit: int = 20) -> pd.DataFrame:
    quad_col = f"quadrant_{window}"
    delta_col = f"delta_{window}"
    sw = deltas[deltas[quad_col] == "stable_winner"].copy()
    return sw.nlargest(limit, delta_col)

def get_quality_dip(deltas: pd.DataFrame, window: str = "1m", limit: int = 20) -> pd.DataFrame:
    quad_col = f"quadrant_{window}"
    delta_col = f"delta_{window}"
    qd = deltas[deltas[quad_col] == "decayer"].copy()
    return qd.nsmallest(limit, delta_col)

def get_faded_bounces(deltas: pd.DataFrame, window: str = "1m", limit: int = 20) -> pd.DataFrame:
    quad_col = f"quadrant_{window}"
    delta_col = f"delta_{window}"
    fb = deltas[deltas[quad_col] == "riser"].copy()
    return fb.nlargest(limit, delta_col)

def build_history_from_prices(
    prices_df: pd.DataFrame,
    sample_dates: pd.DatetimeIndex,
    category_map: dict[str, str],
) -> pd.DataFrame:
    rows = []
    for dt in sample_dates:
        slice_df = prices_df.loc[:dt]
        if len(slice_df) < 252:
            continue
        cs = compute_cross_section(slice_df, category_map=category_map, as_of=dt)
        if cs.empty:
            continue
        cs = cs[HISTORY_COLUMNS].dropna(subset=["raw_score"])
        rows.append(cs)
    if not rows:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.concat(rows, ignore_index=True)
