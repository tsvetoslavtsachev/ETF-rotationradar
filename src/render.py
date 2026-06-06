"""
Data rendering for the frontend.
Merges signals, fundamentals, RS line, and screener metrics into a single JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

def render_frontend_data(
    deltas_df: pd.DataFrame,
    screener_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    rs_df: pd.DataFrame,
    category_map: dict[str, str],
    name_map: dict[str, str],
    benchmark_map: dict[str, str],
    output_path: Path
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
    
    # Merge Screener
    if not screener_df.empty:
        df = df.merge(screener_df, on="ticker", how="left")
        
    # Merge Fundamentals
    if not fundamentals_df.empty:
        df = df.merge(fundamentals_df, on="ticker", how="left")
        
    # Merge RS Signals
    if not rs_df.empty:
        df = df.merge(rs_df[["ticker", "is_bullish", "days_in_trend", "last_signal"]], on="ticker", how="left")
        
    # Handle NaNs
    df = df.replace({np.nan: None})
    
    # Convert to list of dicts
    records = df.to_dict(orient="records")
    
    # Create final payload
    as_of = df["as_of_date"].max() if not df.empty else pd.Timestamp.now()
    if isinstance(as_of, pd.Timestamp):
        as_of_str = as_of.strftime("%Y-%m-%d")
    else:
        as_of_str = str(as_of)
        
    payload = {
        "as_of": as_of_str,
        "etfs": records,
        "categories": sorted(list(set(category_map.values())))
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
        
    print(f"Rendered frontend data to {output_path} with {len(records)} ETFs")
