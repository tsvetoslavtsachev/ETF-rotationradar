"""
ELANA Барометър на поведенческите дислокации — изчислява се автоматично.

Трите индикатора и прагове идват 1:1 от `behavioral-tracker` skill (стабилни,
от шаблона members_template.md — не се менят без explicit request):

  HY-spread (FRED BAMLH0A0HYM2): база <3.00 · тревога >3.50
  XLE/SPY съотношение:          база <0.060 · тревога >0.070
  GLD/TLT съотношение:          база <5.20 · тревога >5.50

Между база и тревога = СИВА зона (не се действа без съвпадение).
Съвпадение (confluence) = ≥2 индикатора в една и съща посока (тревога или база).
4-седмичен тренд = последните 4 петъчни затваряния (↗ ако последните 2 > предходните 2,
↘ ако обратно, без посока ако |промяна| < 2%).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# key -> прагове и метаданни. base = долен праг, alarm = горен праг.
THRESHOLDS = {
    "hy_spread": {"name": "HY-spread", "source": "FRED BAMLH0A0HYM2", "base": 3.00, "alarm": 3.50, "decimals": 2},
    "xle_spy":   {"name": "XLE/SPY",   "source": "yfinance XLE/SPY",  "base": 0.060, "alarm": 0.070, "decimals": 4},
    "gld_tlt":   {"name": "GLD/TLT",   "source": "yfinance GLD/TLT",  "base": 5.20, "alarm": 5.50, "decimals": 2},
}
ORDER = ["hy_spread", "xle_spy", "gld_tlt"]


def _zone(key: str, value) -> str:
    """база / сива / тревога / unknown спрямо праговете."""
    if value is None or not np.isfinite(value):
        return "unknown"
    t = THRESHOLDS[key]
    if value < t["base"]:
        return "base"
    if value > t["alarm"]:
        return "alarm"
    return "gray"


def _trend_4w(series: "pd.Series | None") -> tuple[str, float | None]:
    """Връща (посока, промяна_в_%). Посока: 'up' | 'down' | 'flat'."""
    if series is None:
        return "flat", None
    s = series.dropna()
    if len(s) < 2:
        return "flat", None
    fri = s[s.index.weekday == 4]            # петъчни затваряния
    pts = fri.iloc[-4:] if len(fri) >= 4 else s.iloc[-4:]
    if len(pts) >= 4:
        recent = float(pts.iloc[-2:].mean())
        prior = float(pts.iloc[:2].mean())
        change = (recent / prior - 1.0) * 100.0 if prior else None
    else:
        first = float(pts.iloc[0])
        change = (float(pts.iloc[-1]) / first - 1.0) * 100.0 if first else None
    if change is None or not np.isfinite(change):
        return "flat", None
    if change > 2.0:
        return "up", round(change, 2)
    if change < -2.0:
        return "down", round(change, 2)
    return "flat", round(change, 2)


def _ratio_series(prices_df: pd.DataFrame, num: str, den: str) -> pd.Series:
    if num in prices_df.columns and den in prices_df.columns:
        return (prices_df[num] / prices_df[den]).dropna()
    return pd.Series(dtype=float)


def compute_barometer(prices_df: pd.DataFrame, hy_series: "pd.Series | None", as_of) -> dict:
    """
    Връща dict с indicators (за дашборда), snapshot + readings + confluence
    (за behavioral-tracker / vrm-tier-writer feed).
    Работи и при липсващ HY (FRED надолу) — само го маркира 'unknown'.
    """
    xle_spy = _ratio_series(prices_df, "XLE", "SPY")
    gld_tlt = _ratio_series(prices_df, "GLD", "TLT")

    src = {"hy_spread": hy_series, "xle_spy": xle_spy, "gld_tlt": gld_tlt}
    raw = {
        "hy_spread": float(hy_series.dropna().iloc[-1]) if (hy_series is not None and len(hy_series.dropna())) else None,
        "xle_spy": float(xle_spy.iloc[-1]) if len(xle_spy) else None,
        "gld_tlt": float(gld_tlt.iloc[-1]) if len(gld_tlt) else None,
    }

    indicators, snapshot, readings = [], [], []
    for key in ORDER:
        t = THRESHOLDS[key]
        v = raw[key]
        zone = _zone(key, v)
        direction, change = _trend_4w(src[key])
        vr = round(v, t["decimals"]) if v is not None else None
        dist_alarm = round(t["alarm"] - v, t["decimals"]) if v is not None else None

        ind = {
            "key": key, "name": t["name"], "source": t["source"],
            "value": vr, "zone": zone,
            "base_threshold": t["base"], "alarm_threshold": t["alarm"],
            "dist_to_alarm": dist_alarm,
            "trend_4w": direction, "change_4w_pct": change,
        }
        indicators.append(ind)
        snapshot.append({
            "indicator": t["name"], "value": vr,
            "base": t["base"], "alarm": t["alarm"], "zone": zone, "trend": direction,
        })
        readings.append({
            "indicator": t["name"], "zone": zone,
            "dist_to_alarm": dist_alarm, "trend_4w": direction, "change_4w_pct": change,
        })

    alarm = [i["name"] for i in indicators if i["zone"] == "alarm"]
    base = [i["name"] for i in indicators if i["zone"] == "base"]
    gray = [i["name"] for i in indicators if i["zone"] == "gray"]
    if len(alarm) >= 2:
        has_conf, conf_dir = True, "alarm"
    elif len(base) >= 2:
        has_conf, conf_dir = True, "base"
    else:
        has_conf, conf_dir = False, None

    confluence = {
        "alarm_count": len(alarm), "base_count": len(base), "gray_count": len(gray),
        "alarm": alarm, "base": base, "gray": gray,
        "has_confluence": has_conf, "direction": conf_dir,
    }

    as_of_str = as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else str(as_of)
    return {
        "as_of": as_of_str,
        "indicators": indicators,
        "snapshot": snapshot,
        "readings": readings,
        "confluence": confluence,
    }
