"""
П4 — Forward-return ВАЛИДАЦИОНЕН ХАРНЕС за Барометъра (READ-ONLY).

╔══════════════════════════════════════════════════════════════════════════════╗
║ МОЩНОСТЕН ЕТИКЕТ (чети ПРЕДИ всяко число оттук):                              ║
║   Извадката е ЕДИН РЕЖИМ — бичи 2021-26 + ЧАСТИЧНА мечка 2022. Forward        ║
║   прозорците се препокриват (t-статистиките са НАДУТИ от автокорелация).      ║
║   Независимите стрес-епизоди са ~7. => ВСИЧКО е descriptive, нищо predictive. ║
║   Присъдите за индикатор/confluence остават НАБЛЮДЕНИЯ до натрупване на данни. ║
╚══════════════════════════════════════════════════════════════════════════════╝

ЗАЩО СЕГА (не чака мечка): харнесът се строи РАНО и ТРУПА. С `--refresh` дърпа свежи
барометър-цени в scripts/.bt_cache/ и презаписва панела; всеки run включва цялата
налична история. Когато истинска мечка ВЛЕЗЕ в извадката, СЪЩИЯТ скрипт ще я хване
автоматично — тогава descriptive присъдите ще станат проверяеми. НЕ пипа pipeline данни.

Мери (всичко върху point-in-time reconstruction чрез живия compute_barometer):
  1. Пер-индикатор forward IC (Spearman) на стрес-ориентирания сигнал vs SPY +1/4/12сед.
  2. Групова confluence (П2): forward профил на alarm/base/single — hit-rate, false-positive.
  3. Кривата 2s10s (П3, контекстен ред): forward returns по състояние (инверт./плоска/стръмна).
Изход: доклад stdout + CSV панел (scripts/.bt_cache/barometer_forward_panel.csv, натрупва).

Пусни:  py scripts/barometer_forward_test.py [--refresh]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.barometer import (
    compute_barometer, INDICATORS, FACTOR_GROUPS, GROUP_CONF,
)
from scripts.backtest_thresholds import get_prices, load_fred, CACHE, DATA

STRESS_LOW = -0.05   # "стрес" дефиниран като forward SPY 4-сед < −5%
PANEL_CSV = CACHE / "barometer_forward_panel.csv"


def _load_t10y2y() -> "pd.Series | None":
    try:
        d = pd.read_parquet(DATA / "fred_T10Y2Y.parquet")
        return pd.Series(d["value"].values, index=pd.to_datetime(d["date"])).dropna()
    except Exception:
        return None


def build_panel(prices: pd.DataFrame, fred: dict) -> pd.DataFrame:
    """Sweep всички петъци: point-in-time compute_barometer + forward SPY доходности."""
    spy = prices["SPY"].dropna()
    idx = prices.index
    # старт = първата дата с жив HY (за да са 10-те индикатора реални); ако липсва → началото
    hy = fred.get("hy_spread")
    start = hy.dropna().index.min() if isinstance(hy, pd.Series) and len(hy.dropna()) else idx[0]
    fridays = [d for d in idx if d >= start and d.weekday() == 4]

    def fret(t, nbars):
        pos = spy.index.get_indexer([t], method="ffill")[0]
        if pos < 0 or pos + nbars >= len(spy):
            return np.nan
        return float(spy.iloc[pos + nbars] / spy.iloc[pos] - 1.0)

    rows = []
    for t in fridays:
        p_t = prices.loc[:t]
        f_t = {k: (s[s.index <= t] if isinstance(s, pd.Series) else s) for k, s in fred.items()}
        bar = compute_barometer(p_t, f_t, t)
        c = bar["confluence"]
        rec = {
            "date": t,
            "alarm_group_count": c.get("alarm_group_count"),
            "direction_grouped": c.get("direction_grouped"),
            "alarm_groups": ",".join(c.get("alarm_groups", [])),
            "curve_zone": c.get("context_rows", {}).get("t10y2y", {}).get("zone"),
            "curve_label": c.get("context_rows", {}).get("t10y2y", {}).get("label"),
            "fwd1w": fret(t, 5), "fwd4w": fret(t, 20), "fwd12w": fret(t, 60),
        }
        # стрес-ориентиран сигнал на всеки индикатор (по-високо = повече стрес)
        for ind in bar["indicators"]:
            raw = ind["z"] if ind["kind"] == "robust_z" else ind["value"]
            if raw is None:
                rec[f"sig_{ind['key']}"] = np.nan
            else:
                rec[f"sig_{ind['key']}"] = raw if ind["stress_dir"] == "high" else -raw
        rows.append(rec)
    return pd.DataFrame(rows)


def _spearman_t(x: pd.Series, y: pd.Series):
    m = x.notna() & y.notna()
    x, y = x[m], y[m]
    n = len(x)
    if n < 20:
        return np.nan, np.nan, n
    ic = x.rank().corr(y.rank())
    t = ic * np.sqrt((n - 2) / max(1e-9, 1 - ic * ic)) if abs(ic) < 1 else np.nan
    return ic, t, n


def report_indicator_ic(panel: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("1 · ПЕР-ИНДИКАТОР forward IC (стрес-сигнал vs SPY +4сед; neg = работи като стрес)")
    print("=" * 78)
    print(f"  {'индикатор':<14s} {'dir':<5s} {'IC(fwd4w)':>10s} {'t~':>7s} {'n':>5s}")
    res = []
    for ind in INDICATORS:
        col = f"sig_{ind['key']}"
        if col not in panel:
            continue
        ic, t, n = _spearman_t(panel[col], panel["fwd4w"])
        res.append((ind["name"], ind["stress_dir"], ic, t, n))
    for name, d, ic, t, n in sorted(res, key=lambda r: -(abs(r[2]) if np.isfinite(r[2]) else 0)):
        print(f"  {name:<14s} {d:<5s} {ic:>+10.3f} {t:>+7.2f} {n:>5d}")
    print("  (t~ = наивен; overlapping прозорци го надуват — ИНДИКАТИВЕН, не тест)")


def report_confluence(panel: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print(f"2 · ГРУПОВА CONFLUENCE forward профил (стрес = fwd4w < {STRESS_LOW:+.0%})")
    print("=" * 78)
    n = len(panel)
    base_rate = (panel["fwd4w"] < STRESS_LOW).mean()
    print(f"  безусловно: n={n}  P(стрес)={base_rate*100:.1f}%  "
          f"fwd1/4/12w = {panel['fwd1w'].mean()*100:+.2f}/"
          f"{panel['fwd4w'].mean()*100:+.2f}/{panel['fwd12w'].mean()*100:+.2f}%")
    for label, mask in [
        (f"ALARM-tilt (≥{GROUP_CONF} семейства)", panel["direction_grouped"] == "alarm"),
        ("SINGLE (1 семейство)", panel["direction_grouped"] == "single"),
        ("BASE-tilt (0 семейства)", panel["direction_grouped"] == "base"),
    ]:
        sub = panel[mask]
        if sub.empty:
            print(f"  {label:<28s}: (никога)")
            continue
        hit = (sub["fwd4w"] < STRESS_LOW).mean()
        print(f"  {label:<28s}: n={len(sub):3d} ({len(sub)/n*100:4.1f}%)  "
              f"P(стрес)={hit*100:5.1f}%  FP={(1-hit)*100:4.0f}%  "
              f"fwd4w={sub['fwd4w'].mean()*100:+.2f}%  fwd12w={sub['fwd12w'].mean()*100:+.2f}%")
    print("  Наблюдение: alarm hit-rate ≈ или под безусловната база → СЪВПАДАЩ/контрариан,")
    print("  не изпреварващ. Descriptive до натрупване на мечи епизоди.")


def report_curve(panel: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("3 · КРИВАТА 2s10s (контекстен ред) — forward SPY по състояние")
    print("=" * 78)
    if panel["curve_zone"].notna().sum() == 0:
        print("  (кривата липсва в панела — подай T10Y2Y кеша)")
        return
    for lab in ["инвертирана", "плоска", "стръмна"]:
        sub = panel[panel["curve_label"] == lab]
        if sub.empty:
            print(f"  {lab:<12s}: (няма седмици в извадката)")
            continue
        print(f"  {lab:<12s}: n={len(sub):3d}  fwd4w={sub['fwd4w'].mean()*100:+.2f}%  "
              f"fwd12w={sub['fwd12w'].mean()*100:+.2f}%  P(стрес)={ (sub['fwd4w']<STRESS_LOW).mean()*100:4.1f}%")
    print("  Кривата е БАВЕН лидер — стойността ѝ е контекст за прочита на клъстера,")
    print("  не самостоятелен сигнал; в тази извадка тя почти не се инвертира → ниска мощност.")


def main():
    refresh = "--refresh" in sys.argv
    print(__doc__.split("Пусни:")[0])  # печата мощностния етикет + описанието
    prices = get_prices(years=5, refresh=refresh)
    fred = load_fred()
    fred["t10y2y"] = _load_t10y2y()
    print(f"Данни: {prices.shape[0]} бара × {prices.shape[1]} тикъра "
          f"({prices.index[0].date()}→{prices.index[-1].date()}); "
          f"крива {'жива' if isinstance(fred['t10y2y'], pd.Series) else 'липсва'}")

    panel = build_panel(prices, fred)
    panel.to_csv(PANEL_CSV, index=False)
    print(f"Панел: {len(panel)} петъка → {PANEL_CSV.name} (натрупва при всеки run)")

    report_indicator_ic(panel)
    report_confluence(panel)
    report_curve(panel)

    print("\n" + "=" * 78)
    print("DONE — READ-ONLY. Всичко descriptive (1 режим). Пусни пак с --refresh при нови данни.")
    print("=" * 78)


if __name__ == "__main__":
    main()
