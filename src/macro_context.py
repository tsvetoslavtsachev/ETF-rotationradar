"""
Макро контекст strip (Tier 2, S17) — keyless FRED режимни overlays.

DISPLAY-ONLY: НЕ влиза в Барометър confluence (той е калибриран отделно в barometer.py).
Дава режимен фон: финансов стрес, доларови условия, форма на кривата, рецесионна
вероятност. Пет серии от FRED (keyless fredgraph, parquet кеш + stale fallback).

Зони: base (норма/калм) · gray (внимание) · alarm (стрес) · unknown.

Прагове — честно за anti-illusion:
  • Дефинитивните КОТВИ са сорснати, не измислени:
      STLFSI4 / NFCI — конструирани с 0 = средни исторически условия (Fed дефиниция).
      T10Y2Y — 0 = плоска крива; <0 = инверсия (класически предупредителен сигнал).
  • Band-овете ОКОЛО котвите са документирани КОНВЕНЦИИ (flicker-guard / watch нива),
      не статистики: ±0.10 dead-band около 0; 2s10s watch <0.50; recession 20/50.
  • DTWEXBGS е индексно ниво без естествена 0 → robust_z (стегнат силен долар = стрес).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.barometer import _robust_z, _zone_z, _trend_4w

# (key, показвано име, FRED id, механика, посока на стрес, десетични, бележка)
MACRO_SERIES = [
    {"key": "stlfsi", "name": "Fin. Stress", "fred_id": "STLFSI4",
     "kind": "zero", "stress_dir": "high", "decimals": 2,
     "note": "0 = средни условия; >0 над нормата", "source": "FRED STLFSI4"},
    {"key": "nfci", "name": "Fin. Conditions", "fred_id": "NFCI",
     "kind": "zero", "stress_dir": "high", "decimals": 2,
     "note": "0 = средни; >0 по-стегнати", "source": "FRED NFCI"},
    {"key": "usd", "name": "USD (Broad)", "fred_id": "DTWEXBGS",
     "kind": "robust_z", "stress_dir": "high", "decimals": 2,
     "note": "стегнат силен долар = глобално затягане", "source": "FRED DTWEXBGS"},
    {"key": "curve_2s10s", "name": "Крива 2s10s", "fred_id": "T10Y2Y",
     "kind": "spread", "stress_dir": "low", "decimals": 2,
     "note": "инверсия (<0) = предупредителен сигнал", "source": "FRED T10Y2Y"},
    {"key": "recession_prob", "name": "Recession P", "fred_id": "RECPROUSM156N",
     "kind": "prob", "stress_dir": "high", "decimals": 1,
     "note": "Chauvet-Piger smoothed P(рецесия), %", "source": "FRED RECPROUSM156N"},
]

# Документирани band-конвенции (НЕ статистики):
ZERO_DEADBAND = 0.10   # ±около дефинитивната 0 за STLFSI4/NFCI (flicker guard)
CURVE_WATCH = 0.50     # 2s10s под това = сплескваща крива (watch)
REC_WATCH, REC_ALARM = 20.0, 50.0  # recession prob % band-ове


def _zone_zero(v) -> str:
    """STLFSI4 / NFCI: 0 = норма (дефинитивно); ±dead-band; >0 = над нормата."""
    if v is None or not np.isfinite(v):
        return "unknown"
    if v < -ZERO_DEADBAND:
        return "base"
    if v > ZERO_DEADBAND:
        return "alarm"
    return "gray"


def _zone_spread(v) -> str:
    """2s10s: <0 инверсия (стрес); 0..watch сплескваща; иначе норма."""
    if v is None or not np.isfinite(v):
        return "unknown"
    if v < 0.0:
        return "alarm"
    if v < CURVE_WATCH:
        return "gray"
    return "base"


def _zone_prob(v) -> str:
    """Recession probability %: 20/50 band-ове."""
    if v is None or not np.isfinite(v):
        return "unknown"
    if v >= REC_ALARM:
        return "alarm"
    if v >= REC_WATCH:
        return "gray"
    return "base"


def compute_macro_context(fred_series: "dict | None", as_of) -> dict:
    """
    fred_series — dict по key (напр. {"stlfsi": s, "curve_2s10s": s, ...}).
    Връща {"as_of", "items": [{key,name,value,zone,z,note,source,trend_4w,...}]}.
    Работи при липсваща серия (FRED надолу) → зона 'unknown'.
    """
    fred_series = fred_series or {}
    items = []
    for m in MACRO_SERIES:
        s = fred_series.get(m["key"])
        s = s.dropna() if isinstance(s, pd.Series) else pd.Series(dtype=float)
        value = float(s.iloc[-1]) if len(s) else None
        vr = round(value, m["decimals"]) if value is not None else None
        direction, change = _trend_4w(s if len(s) else None)

        z = None
        if m["kind"] == "zero":
            zone = _zone_zero(value)
        elif m["kind"] == "spread":
            zone = _zone_spread(value)
        elif m["kind"] == "prob":
            zone = _zone_prob(value)
        else:  # robust_z (USD ниво)
            zr = _robust_z(s)
            z = round(zr, 2) if zr is not None else None
            zone = _zone_z(zr, m["stress_dir"])

        items.append({
            "key": m["key"], "name": m["name"], "value": vr, "zone": zone,
            "z": z, "note": m["note"], "source": m["source"],
            "trend_4w": direction, "change_4w_pct": change,
        })

    as_of_str = as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else str(as_of)
    return {"as_of": as_of_str, "items": items}


def compute_gold_copper_item(prices_df, as_of) -> dict:
    """
    GLD/COPX (злато / медни миньори) — 'страх срещу растеж' с едно пазарно число.
    Високо съотношение = бягство към злато (страх/защита); ниско = апетит към
    цикличната мед (растеж). Price-derived (НЕ FRED), но display-only режимен фон
    в същия стрип — затова връща item със СЪЩАТА форма като FRED серите.

    Зона през robust_z (~2г, само-калибриращ — без измислен праг); stress_dir='high'
    (високо съотношение = страх = стрес). ⚠️ COPX са медни МИНЬОРИ (акции с пазарна
    бета + оперативен ливъридж), не медни фючърси — по-шумен прокси от класическото
    copper/gold; държано като документирана конвенция (и двата вече във вселената,
    keyless). Връща zone='unknown' ако някой крак липсва (GLD/COPX извън цените).
    """
    item = {
        "key": "gld_copx", "name": "GLD/COPX", "value": None, "zone": "unknown",
        "z": None, "note": "злато/мед — страх срещу растеж",
        "source": "yfinance GLD/COPX (миньори, не фючърси — конвенция)",
        "trend_4w": "flat", "change_4w_pct": None,
    }
    if prices_df is None or "GLD" not in prices_df.columns or "COPX" not in prices_df.columns:
        return item
    ratio = (prices_df["GLD"] / prices_df["COPX"])
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return item
    zr = _robust_z(ratio)
    direction, change = _trend_4w(ratio)
    item.update({
        "value": round(float(ratio.iloc[-1]), 2),
        "z": round(zr, 2) if zr is not None else None,
        "zone": _zone_z(zr, "high"),
        "trend_4w": direction, "change_4w_pct": change,
    })
    return item
