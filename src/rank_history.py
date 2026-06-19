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

# ── Movers since last week (Tier 3 UX) ─────────────────────────
# Седмица-за-седмица ΔRank diff + ротация в челото. Прозорецът, прагът и
# top_n са sign-off-нати от Цветослав (S19): седмично (~5 търговски дни),
# защото петъчният ритъм + 1м/3м вече покриват по-дългите хоризонти; праг
# |ΔRank|≥15 = горния децил на седмичните движения (p90=15.4, изчислено от
# 98 W-FRI двойки в ranks_history); топ-15 = същия cut като Rotation Radar.
MOVERS_WINDOW_BDAYS = 5
MOVERS_THRESHOLD = 15.0
MOVERS_TOP_N = 15


def _snapshot_on_or_before(history: pd.DataFrame, cutoff: pd.Timestamp):
    """Връща (дата, percentile_rank серия по ticker) за последния snapshot на/преди cutoff."""
    sub = history[history["date"] <= cutoff]
    if sub.empty:
        return None, pd.Series(dtype=float)
    last_date = sub["date"].max()
    snap = sub[sub["date"] == last_date].set_index("ticker")["percentile_rank"]
    return last_date, snap


def compute_movers(
    history: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    window_bdays: int = MOVERS_WINDOW_BDAYS,
    threshold: float = MOVERS_THRESHOLD,
    top_n: int = MOVERS_TOP_N,
    name_map: dict | None = None,
    category_map: dict | None = None,
) -> dict:
    """
    "Движения от миналата седмица" — сравнява текущия snapshot с snapshot
    ~window_bdays търговски дни назад. Чете готовата rank history (нула нови
    цени/вызови). Връща display-ready dict:
      up/down   — движители с |ΔRank| >= threshold (up низходящо, down по
                  най-отрицателния първи);
      entered/  — тикъри, влезли/напуснали топ-N по percentile_rank между
      left        двата snapshot-а (ротация в челото).
    Всеки ред: ticker / name / category / prev / now / delta (закръглени).
    `available=False` (празни списъци) ако историята е твърде къса.
    """
    name_map = name_map or {}
    category_map = category_map or {}
    empty = {
        "available": False, "as_of": None, "prev_date": None,
        "window_bdays": window_bdays, "threshold": threshold, "top_n": top_n,
        "up": [], "down": [], "entered": [], "left": [],
    }
    if history.empty:
        return empty

    if as_of is None:
        as_of = history["date"].max()
    as_of = pd.Timestamp(as_of)

    cur_date, cur = _snapshot_on_or_before(history, as_of)
    if cur_date is None or cur.empty:
        return empty
    cutoff = cur_date - pd.tseries.offsets.BusinessDay(window_bdays)
    prev_date, prev = _snapshot_on_or_before(history, cutoff)
    if prev_date is None or prev.empty:
        return empty

    common = cur.index.intersection(prev.index)
    delta = (cur[common] - prev[common]).dropna()

    def _round(v):
        return None if v is None or not np.isfinite(v) else int(round(float(v)))

    def row(t: str) -> dict:
        p = prev[t] if t in prev.index else np.nan
        n = cur[t] if t in cur.index else np.nan
        d = (n - p) if (np.isfinite(p) and np.isfinite(n)) else np.nan
        return {
            "ticker": t,
            "name": name_map.get(t, ""),
            "category": category_map.get(t, ""),
            "prev": _round(p), "now": _round(n), "delta": _round(d),
        }

    up = [row(t) for t in delta[delta >= threshold].sort_values(ascending=False).index]
    down = [row(t) for t in delta[delta <= -threshold].sort_values().index]

    cur_top = set(cur.nlargest(top_n).index)
    prev_top = set(prev.nlargest(top_n).index)
    entered = [row(t) for t in sorted(cur_top - prev_top, key=lambda t: -cur[t])]
    left = [row(t) for t in sorted(prev_top - cur_top, key=lambda t: -prev.get(t, 0))]

    return {
        "available": True,
        "as_of": cur_date.strftime("%Y-%m-%d"),
        "prev_date": prev_date.strftime("%Y-%m-%d"),
        "window_bdays": window_bdays, "threshold": threshold, "top_n": top_n,
        "up": up, "down": down, "entered": entered, "left": left,
    }


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
