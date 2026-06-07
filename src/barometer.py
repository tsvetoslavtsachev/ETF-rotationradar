"""
ELANA Барометър на поведенческите дислокации — изчислява се автоматично.

Config-driven: всеки индикатор е запис в INDICATORS със:
  kind        — "abs" (абсолютни прагове base/alarm) или "robust_z" (z спрямо
                собствената история; калм в ±Z_BASE, тревога извън ±Z_ALARM)
  stress_dir  — "high" (висока стойност = стрес) или "low" (ниска = стрес)
  src         — откъде идва серията:
                  ("fred", key)        → fred_series[key]
                  ("ratio", num, den)  → prices[num] / prices[den]
                  ("level", ticker)    → prices[ticker]

Абсолютните прагове са 1:1 от източниците на Цветослав (behavioral-tracker
шаблон + VRM canvas). Ротационните ratio-та НЯМАТ абсолютни прагове в
документите → ползват robust-z (median/MAD), за да не се измислят числа.

Зони: база (калм) / сива / тревога (стрес) / unknown.
Confluence (нетна посока): tilt към тревога/база ако |alarm−base| ≥ CONF_NET.
4-седмичен тренд = последните 4 петъчни затваряния.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── Параметри на robust-z и confluence ──────────────────────────────────────
Z_WINDOW = 504   # ~2 търговски години история за median/MAD
Z_BASE = 1.0     # |z| под това = база (калм)
Z_ALARM = 2.0    # |z| извън това (в стрес-посоката) = тревога
CONF_NET = 2     # нетна разлика alarm−base за да има confluence tilt

# ── Дефиниция на индикаторите (в реда на показване) ─────────────────────────
# Абсолютните прагове са сорснати; robust_z няма абс. праг (self-calibrating).
INDICATORS = [
    {"key": "hy_spread", "name": "HY-spread", "kind": "abs", "stress_dir": "high",
     "src": ("fred", "hy_spread"), "base": 3.00, "alarm": 3.50, "decimals": 2,
     "source": "FRED BAMLH0A0HYM2"},
    {"key": "xle_spy", "name": "XLE/SPY", "kind": "abs", "stress_dir": "high",
     "src": ("ratio", "XLE", "SPY"), "base": 0.060, "alarm": 0.070, "decimals": 4,
     "source": "yfinance XLE/SPY"},
    {"key": "gld_tlt", "name": "GLD/TLT", "kind": "abs", "stress_dir": "high",
     "src": ("ratio", "GLD", "TLT"), "base": 5.20, "alarm": 5.50, "decimals": 2,
     "source": "yfinance GLD/TLT"},
    {"key": "vix", "name": "VIX", "kind": "abs", "stress_dir": "high",
     "src": ("level", "^VIX"), "base": 20.0, "alarm": 25.0, "decimals": 2,
     "source": "yfinance ^VIX"},
    {"key": "breakeven_10y", "name": "10Y breakeven", "kind": "abs", "stress_dir": "high",
     "src": ("fred", "breakeven_10y"), "base": 2.40, "alarm": 2.60, "decimals": 2,
     "source": "FRED T10YIE"},
    {"key": "tip_ief", "name": "TIP/IEF", "kind": "robust_z", "stress_dir": "high",
     "src": ("ratio", "TIP", "IEF"), "decimals": 4,
     "source": "yfinance TIP/IEF (breakeven прокси)"},
    {"key": "move", "name": "MOVE", "kind": "robust_z", "stress_dir": "high",
     "src": ("level", "^MOVE"), "decimals": 2, "source": "yfinance ^MOVE"},
    {"key": "hyg_lqd", "name": "HYG/LQD", "kind": "robust_z", "stress_dir": "low",
     "src": ("ratio", "HYG", "LQD"), "decimals": 4, "source": "yfinance HYG/LQD"},
    {"key": "xly_xlp", "name": "XLY/XLP", "kind": "robust_z", "stress_dir": "low",
     "src": ("ratio", "XLY", "XLP"), "decimals": 4, "source": "yfinance XLY/XLP"},
    {"key": "iwm_spy", "name": "IWM/SPY", "kind": "robust_z", "stress_dir": "low",
     "src": ("ratio", "IWM", "SPY"), "decimals": 4, "source": "yfinance IWM/SPY"},
    {"key": "iwf_iwd", "name": "IWF/IWD", "kind": "robust_z", "stress_dir": "high",
     "src": ("ratio", "IWF", "IWD"), "decimals": 4, "source": "yfinance IWF/IWD (растеж/стойност)"},
    {"key": "vug_vtv", "name": "VUG/VTV", "kind": "robust_z", "stress_dir": "high",
     "src": ("ratio", "VUG", "VTV"), "decimals": 4, "source": "yfinance VUG/VTV (растеж/стойност)"},
]


def _ratio_series(prices_df: pd.DataFrame, num: str, den: str) -> pd.Series:
    if num in prices_df.columns and den in prices_df.columns:
        return (prices_df[num] / prices_df[den]).dropna()
    return pd.Series(dtype=float)


def _level_series(prices_df: pd.DataFrame, ticker: str) -> pd.Series:
    if ticker in prices_df.columns:
        return prices_df[ticker].dropna()
    return pd.Series(dtype=float)


def _series_for(ind: dict, prices_df: pd.DataFrame, fred_series: dict) -> pd.Series:
    kind, *rest = ind["src"]
    if kind == "fred":
        s = fred_series.get(rest[0])
        return s.dropna() if isinstance(s, pd.Series) else pd.Series(dtype=float)
    if kind == "ratio":
        return _ratio_series(prices_df, rest[0], rest[1])
    if kind == "level":
        return _level_series(prices_df, rest[0])
    return pd.Series(dtype=float)


def _robust_z(series: pd.Series) -> "float | None":
    """z = (last − median) / (1.4826·MAD) върху последния Z_WINDOW прозорец."""
    s = series.dropna()
    if len(s) < 30:
        return None
    s = s.iloc[-Z_WINDOW:]
    med = float(s.median())
    mad = float((s - med).abs().median())
    last = float(s.iloc[-1])
    if mad > 0:
        return (last - med) / (1.4826 * mad)
    std = float(s.std())
    return (last - med) / std if std > 0 else None


def _zone_abs(value, base, alarm, stress_dir) -> str:
    if value is None or not np.isfinite(value):
        return "unknown"
    if stress_dir == "high":
        if value < base:
            return "base"
        if value > alarm:
            return "alarm"
        return "gray"
    # stress_dir == "low": ниска стойност = стрес (base/alarm са обърнати)
    if value > base:
        return "base"
    if value < alarm:
        return "alarm"
    return "gray"


def _zone_z(z, stress_dir) -> str:
    if z is None or not np.isfinite(z):
        return "unknown"
    if stress_dir == "high":
        if z >= Z_ALARM:
            return "alarm"
        if z <= Z_BASE:
            return "base"
        return "gray"
    # stress_dir == "low": много отрицателен z = стрес
    if z <= -Z_ALARM:
        return "alarm"
    if z >= -Z_BASE:
        return "base"
    return "gray"


def _trend_4w(series: "pd.Series | None") -> "tuple[str, float | None]":
    """Връща (посока, промяна_в_%). Посока: 'up' | 'down' | 'flat'."""
    if series is None:
        return "flat", None
    s = series.dropna()
    if len(s) < 2:
        return "flat", None
    fri = s[s.index.weekday == 4]
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


def compute_barometer(prices_df: pd.DataFrame, fred_series: "dict | None", as_of) -> dict:
    """
    prices_df  — плосък Close frame, който съдържа нужните тикъри (вкл. ^VIX,
                 ^MOVE, VUG, VTV — подадени отделно и обединени преди извикване).
    fred_series — dict по indicator key, напр. {"hy_spread": s, "breakeven_10y": s}.
    Връща dict с indicators (за дашборда) + snapshot/readings/confluence (за feed-а).
    Работи и при липсваща серия (FRED надолу, тикър липсва) → зона 'unknown'.
    """
    fred_series = fred_series or {}

    indicators, snapshot, readings = [], [], []
    for ind in INDICATORS:
        series = _series_for(ind, prices_df, fred_series)
        value = float(series.iloc[-1]) if len(series) else None
        vr = round(value, ind["decimals"]) if value is not None else None
        direction, change = _trend_4w(series)

        if ind["kind"] == "abs":
            zone = _zone_abs(value, ind["base"], ind["alarm"], ind["stress_dir"])
            z = None
            base_t, alarm_t = ind["base"], ind["alarm"]
            dist_alarm = round(ind["alarm"] - value, ind["decimals"]) if value is not None else None
        else:  # robust_z
            zr = _robust_z(series)
            z = round(zr, 2) if zr is not None else None
            zone = _zone_z(zr, ind["stress_dir"])
            base_t, alarm_t, dist_alarm = None, None, None

        rec = {
            "key": ind["key"], "name": ind["name"], "source": ind["source"],
            "kind": ind["kind"], "stress_dir": ind["stress_dir"],
            "value": vr, "zone": zone,
            "base_threshold": base_t, "alarm_threshold": alarm_t,
            "dist_to_alarm": dist_alarm,
            "z": z, "z_base": Z_BASE if ind["kind"] == "robust_z" else None,
            "z_alarm": Z_ALARM if ind["kind"] == "robust_z" else None,
            "trend_4w": direction, "change_4w_pct": change,
        }
        indicators.append(rec)
        snapshot.append({
            "indicator": ind["name"], "value": vr, "kind": ind["kind"],
            "base": base_t, "alarm": alarm_t, "z": z, "zone": zone, "trend": direction,
        })
        readings.append({
            "indicator": ind["name"], "zone": zone, "kind": ind["kind"],
            "dist_to_alarm": dist_alarm, "z": z,
            "trend_4w": direction, "change_4w_pct": change,
        })

    alarm = [i["name"] for i in indicators if i["zone"] == "alarm"]
    base = [i["name"] for i in indicators if i["zone"] == "base"]
    gray = [i["name"] for i in indicators if i["zone"] == "gray"]
    unknown = [i["name"] for i in indicators if i["zone"] == "unknown"]

    # Нетна confluence: tilt само ако едната страна води с ≥ CONF_NET.
    net = len(alarm) - len(base)
    if net >= CONF_NET:
        has_conf, conf_dir = True, "alarm"
    elif -net >= CONF_NET:
        has_conf, conf_dir = True, "base"
    else:
        has_conf, conf_dir = False, None

    confluence = {
        "alarm_count": len(alarm), "base_count": len(base),
        "gray_count": len(gray), "unknown_count": len(unknown),
        "alarm": alarm, "base": base, "gray": gray,
        "net": net, "conf_net_threshold": CONF_NET,
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
