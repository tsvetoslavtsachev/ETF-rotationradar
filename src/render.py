"""
Data rendering for the frontend.
Merges signals, fundamentals, RS line, and screener metrics into a single JSON.
"""

from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd


def _json_default(o):
    """Прави стойностите JSON-сериализуеми (pandas Timestamp, numpy скалари, дати)."""
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if o is pd.NaT:
        return None
    return str(o)

def render_frontend_data(
    deltas_df: pd.DataFrame,
    screener_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    rs_df: pd.DataFrame,
    category_map: dict[str, str],
    name_map: dict[str, str],
    benchmark_map: dict[str, str],
    output_path: Path,
    barometer: "dict | None" = None,
    ohlcv_df: "pd.DataFrame | None" = None,
    flows_df: "pd.DataFrame | None" = None,
    spark_map: "dict | None" = None,
    macro: "dict | None" = None,
    betas_df: "pd.DataFrame | None" = None,
    lookthrough_df: "pd.DataFrame | None" = None,
    cot_df: "pd.DataFrame | None" = None,
    movers: "dict | None" = None,
    heatstrip: "dict | None" = None,
) -> None:
    """
    Обединява всички данни и ги запазва като JSON за UI-а.
    """
    # Base structure from deltas
    df = deltas_df.copy()
    
    # Add metadata
    df["name"] = df["ticker"].map(name_map)
    df["category"] = df["ticker"].map(category_map)
    df["benchmark"] = df["ticker"].map(benchmark_map)

    # Фронтендът (Screener tab) сортира и рисува лента по `percentile_rank`,
    # но ΔRank енджинът връща същата стойност като `current_rank`. Излагаме я.
    if "current_rank" in df.columns:
        df["percentile_rank"] = df["current_rank"]
    
    # Merge Screener
    if not screener_df.empty:
        df = df.merge(screener_df, on="ticker", how="left")

    # Merge OHLCV-базирани метрики (ATR / Chandelier стоп / ликвидност)
    if ohlcv_df is not None and not ohlcv_df.empty:
        df = df.merge(ohlcv_df, on="ticker", how="left")

    # Merge fund-flow прокси (S15) — est_flow / est_flow_pct / flow_window_days / flow_dir
    if flows_df is not None and not flows_df.empty:
        df = df.merge(flows_df, on="ticker", how="left")

    # Merge 1г седмична бета / корелация спрямо SPY (S18) — beta_1y / corr_1y
    if betas_df is not None and not betas_df.empty:
        df = df.merge(betas_df, on="ticker", how="left")

    # Merge ETF look-through (S18 batch 3) — conc_top10 + JSON колони (парсват се долу)
    if lookthrough_df is not None and not lookthrough_df.empty:
        df = df.merge(lookthrough_df, on="ticker", how="left")

    # Merge COT позициониране (S18 batch 4) — cot_pctile + tooltip скалари
    if cot_df is not None and not cot_df.empty:
        df = df.merge(cot_df, on="ticker", how="left")

    # Merge Fundamentals
    if not fundamentals_df.empty:
        df = df.merge(fundamentals_df, on="ticker", how="left")
        
    # Merge RS Signals
    if not rs_df.empty:
        df = df.merge(rs_df[["ticker", "is_bullish", "days_in_trend", "last_signal"]], on="ticker", how="left")
        
    # Дата на payload-а — взимаме я ПРЕДИ да махнем колоната.
    as_of = df["as_of_date"].max() if ("as_of_date" in df.columns and not df.empty) else pd.Timestamp.now()
    if isinstance(as_of, pd.Timestamp):
        as_of_str = as_of.strftime("%Y-%m-%d")
    else:
        as_of_str = str(as_of)

    # as_of_date е per-record, но фронтендът ползва само payload-level `as_of` — махаме го.
    df = df.drop(columns=["as_of_date"], errors="ignore")

    # Handle NaNs
    df = df.replace({np.nan: None})

    # Convert to list of dicts
    records = df.to_dict(orient="records")

    # Sparkline серия per ETF (2г седмично-децимиран Close) — добавя се след
    # to_dict, за да не се бори с dtype-овете на df (списък в колона).
    if spark_map:
        for r in records:
            sp = spark_map.get(r.get("ticker"))
            if sp is not None:
                r["spark"] = sp

    # Look-through (S18 batch 3) — парсваме JSON-стринг колоните в nested списъци
    # (holdings/sectors за tooltip) и махаме суровите _json полета от payload-а.
    for r in records:
        for raw, key in (("top_holdings_json", "holdings"), ("top_sectors_json", "sectors")):
            if raw in r:
                val = r.pop(raw)
                if val:
                    try:
                        parsed = json.loads(val)
                        if parsed:
                            r[key] = parsed
                    except (ValueError, TypeError):
                        pass

    payload = {
        "as_of": as_of_str,
        "etfs": records,
        "categories": sorted(list(set(category_map.values()))),
    }
    if barometer is not None:
        payload["barometer"] = barometer
    if macro is not None:
        payload["macro"] = macro
    if movers is not None:
        payload["movers"] = movers
    if heatstrip is not None:
        payload["heatstrip"] = heatstrip

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)

    print(f"Rendered frontend data to {output_path} with {len(records)} ETFs")

    # Отделен feed за behavioral-tracker / vrm-tier-writer (shape: snapshot/readings/confluence)
    if barometer is not None:
        feed_path = output_path.parent / "barometer_feed.json"
        feed = {
            "as_of": barometer.get("as_of"),
            "snapshot": barometer.get("snapshot"),
            "readings": barometer.get("readings"),
            "confluence": barometer.get("confluence"),
        }
        with open(feed_path, "w", encoding="utf-8") as f:
            json.dump(feed, f, indent=2, ensure_ascii=False, default=_json_default)
        print(f"Wrote barometer feed to {feed_path}")
