"""
S16 — READ-ONLY backtest harness for the three "verdict-flipper" thresholds.

NIE PIPE pipeline-а. Чете data/ranks_history.parquet + FRED parquet кешовете,
тегли ~5г цени за барометър-тикърите (кешира в scripts/.bt_cache/), и МЕРИ
base-rate-овете на трите прага. Нищо не се записва в pipeline данните.

Трите обръщача:
  1. Quadrant 80/20         (rank_history.py: HIGH/LOW_BASE_THRESHOLD)
  2. CONF_NET = 2           (barometer.py)
  3. robust_z 1.0/2.0/504   (barometer.py: Z_BASE/Z_ALARM/Z_WINDOW)

Целта е TRUST-MAP, не retune. Праговете НЕ се пипат тук.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.prices import download_prices
from src.rank_history import (
    load_history, compute_delta_metrics,
    HIGH_BASE_THRESHOLD, LOW_BASE_THRESHOLD,
)
from src.barometer import (
    INDICATORS, compute_barometer, _series_for, _robust_z, _zone_z,
    Z_BASE, Z_ALARM, Z_WINDOW, CONF_NET,
)

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
CACHE = Path(__file__).parent / ".bt_cache"
CACHE.mkdir(exist_ok=True)

BAROMETER_TICKERS = ["SPY", "XLE", "GLD", "TLT", "^VIX", "^MOVE",
                     "HYG", "LQD", "XLY", "XLP", "IWM", "VUG", "VTV"]


def _hr(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def get_prices(years: int = 5, refresh: bool = False) -> pd.DataFrame:
    """~5г цени за барометъра. Кешира в scratch (НЕ pipeline data)."""
    cache_file = CACHE / f"barometer_prices_{years}y.parquet"
    if cache_file.exists() and not refresh:
        df = pd.read_parquet(cache_file)
        df.index = pd.to_datetime(df.index)
        return df
    print(f"Fetching {years}y prices for {len(BAROMETER_TICKERS)} barometer tickers...")
    df = download_prices(BAROMETER_TICKERS, period=f"{years}y")
    df.to_parquet(cache_file)
    return df


def load_fred() -> dict:
    hy = pd.read_parquet(DATA / "fred_BAMLH0A0HYM2.parquet")
    be = pd.read_parquet(DATA / "fred_T10YIE.parquet")
    hy_s = pd.Series(hy["value"].values, index=pd.to_datetime(hy["date"])).dropna()
    be_s = pd.Series(be["value"].values, index=pd.to_datetime(be["date"])).dropna()
    return {"hy_spread": hy_s, "breakeven_10y": be_s}


# ─────────────────────────────────────────────────────────────────────────────
# BT1 — Quadrant 80/20
# ─────────────────────────────────────────────────────────────────────────────
def backtest_quadrant() -> None:
    _hr("BT1 · QUADRANT 80/20  (rank_history.py)")
    print(f"Live thresholds: HIGH={HIGH_BASE_THRESHOLD}  LOW={LOW_BASE_THRESHOLD}")

    history = load_history(DATA / "ranks_history.parquet")
    dates = sorted(history["date"].unique())
    print(f"History: {len(history)} rows · {len(dates)} dates · "
          f"{history['ticker'].nunique()} tickers · "
          f"{pd.Timestamp(dates[0]).date()} → {pd.Timestamp(dates[-1]).date()}")

    # Sweep compute_delta_metrics across all history dates (LIVE code).
    rows = []
    for d in dates:
        dm = compute_delta_metrics(history, as_of=d)
        if dm.empty:
            continue
        if "ticker" not in dm.columns and "index" in dm.columns:
            # На дата без никаква история index-name се губи → "index".
            dm = dm.rename(columns={"index": "ticker"})
        dm = dm[np.isfinite(dm["base_rank_6m"])].copy()
        dm["date"] = pd.Timestamp(d)
        rows.append(dm[["date", "ticker", "base_rank_6m", "delta_1m",
                        "quadrant_1m", "quadrant_3m"]])
    panel = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if panel.empty:
        print("No finite base_rank_6m observations — abort BT1.")
        return

    usable_dates = sorted(panel["date"].unique())
    print(f"Usable (finite base_rank_6m): {len(panel)} obs across "
          f"{len(usable_dates)} dates "
          f"({pd.Timestamp(usable_dates[0]).date()} → "
          f"{pd.Timestamp(usable_dates[-1]).date()})")

    # (a) base_rank_6m distribution
    b = panel["base_rank_6m"]
    print("\n[a] base_rank_6m разпределение (всички date×ticker):")
    for q in [0, 5, 10, 20, 25, 50, 75, 80, 90, 95, 100]:
        print(f"    p{q:<3d} = {np.percentile(b, q):6.2f}")
    print(f"    ≥80 : {(b >= 80).mean()*100:5.2f}%   "
          f"≤20 : {(b <= 20).mean()*100:5.2f}%   "
          f"middle(20,80): {((b > 20) & (b < 80)).mean()*100:5.2f}%")

    # (b) quadrant occupancy (1m)
    print("\n[b] Quadrant occupancy (quadrant_1m, всички обс.):")
    occ = panel["quadrant_1m"].value_counts(normalize=True) * 100
    for k, v in occ.items():
        print(f"    {k:<15s} {v:5.2f}%")

    # (c) flicker across the boundary, week-to-week
    def crossings(threshold_hi: float, threshold_lo: float):
        """Брой смени на 'квалифициран ли е' статус седмица за седмица."""
        hi_cross = lo_cross = 0
        hi_border = lo_border = 0          # ticker-weeks within ±5 of boundary
        hi_border_flip = lo_border_flip = 0
        for tk, g in panel.sort_values("date").groupby("ticker"):
            bb = g["base_rank_6m"].values
            hi = (bb >= threshold_hi).astype(int)
            lo = (bb <= threshold_lo).astype(int)
            hi_cross += int(np.abs(np.diff(hi)).sum())
            lo_cross += int(np.abs(np.diff(lo)).sum())
            for i in range(len(bb) - 1):
                if abs(bb[i] - threshold_hi) <= 5:
                    hi_border += 1
                    if hi[i] != hi[i + 1]:
                        hi_border_flip += 1
                if abs(bb[i] - threshold_lo) <= 5:
                    lo_border += 1
                    if lo[i] != lo[i + 1]:
                        lo_border_flip += 1
        return dict(hi_cross=hi_cross, lo_cross=lo_cross,
                    hi_border=hi_border, hi_border_flip=hi_border_flip,
                    lo_border=lo_border, lo_border_flip=lo_border_flip)

    print("\n[c] Flicker (смени на квалификация седмица-за-седмица), "
          "по различни прагове:")
    n_ticker_weeks = len(panel) - panel["ticker"].nunique()  # approx transitions
    print(f"    (≈{n_ticker_weeks} ticker-week прехода общо)")
    for hi, lo in [(80, 20), (85, 15), (75, 25)]:
        c = crossings(hi, lo)
        hi_bf = (c["hi_border_flip"] / c["hi_border"] * 100) if c["hi_border"] else 0
        lo_bf = (c["lo_border_flip"] / c["lo_border"] * 100) if c["lo_border"] else 0
        print(f"    {hi}/{lo}: HI-crossings={c['hi_cross']:3d}  "
              f"LO-crossings={c['lo_cross']:3d}  | "
              f"граница±5 flip-rate: HI {hi_bf:4.1f}% (n={c['hi_border']})  "
              f"LO {lo_bf:4.1f}% (n={c['lo_border']})")

    # (d) membership stability: of tickers EVER ≥80, how many weeks do they hold?
    print("\n[d] Постоянство на HI-членството (base≥80):")
    ever_hi = panel[panel["base_rank_6m"] >= 80]["ticker"].unique()
    holds = []
    for tk in ever_hi:
        g = panel[panel["ticker"] == tk].sort_values("date")
        holds.append((g["base_rank_6m"] >= 80).mean() * 100)
    if holds:
        print(f"    {len(ever_hi)} тикъра някога ≥80; от техните седмици — "
              f"медиана {np.median(holds):.0f}% държат ≥80 "
              f"(p25={np.percentile(holds,25):.0f}%, "
              f"p75={np.percentile(holds,75):.0f}%)")


# ─────────────────────────────────────────────────────────────────────────────
# BT2 — CONF_NET
# ─────────────────────────────────────────────────────────────────────────────
def backtest_conf_net(prices: pd.DataFrame, fred: dict) -> None:
    _hr("BT2 · CONF_NET  (barometer.py)")
    print(f"Live threshold: CONF_NET = {CONF_NET}  (tilt ако |alarm−base| ≥ {CONF_NET})")

    idx = prices.index
    cutoff = idx[-1] - pd.Timedelta(days=365 * 2)
    fridays = [d for d in idx if d >= cutoff and d.weekday() == 4]
    print(f"Sample: {len(fridays)} петъчни дати "
          f"({fridays[0].date()} → {fridays[-1].date()})")

    recs = []
    for t in fridays:
        p_t = prices.loc[:t]
        f_t = {k: s[s.index <= t] for k, s in fred.items()}
        bar = compute_barometer(p_t, f_t, t)
        c = bar["confluence"]
        recs.append({"date": t, "net": c["net"],
                     "alarm": c["alarm_count"], "base": c["base_count"],
                     "gray": c["gray_count"], "unknown": c["unknown_count"],
                     "conf": c["has_confluence"], "dir": c["direction"],
                     "alarm_names": ",".join(c["alarm"])})
    df = pd.DataFrame(recs)

    print("\n[a] net (=alarm−base) разпределение:")
    for q in [0, 10, 25, 50, 75, 90, 100]:
        print(f"    p{q:<3d} = {np.percentile(df['net'], q):5.1f}")
    print(f"    среден alarm_count={df['alarm'].mean():.2f}  "
          f"base_count={df['base'].mean():.2f}  "
          f"gray={df['gray'].mean():.2f}  unknown={df['unknown'].mean():.2f}")

    print("\n[b] Колко често пали confluence (по различни CONF_NET):")
    n = len(df)
    for thr in [2, 3, 4]:
        a = (df["net"] >= thr).sum()
        bse = (df["net"] <= -thr).sum()
        print(f"    CONF_NET={thr}: ALARM-tilt {a:3d}/{n} ({a/n*100:4.1f}%)  "
              f"BASE-tilt {bse:3d}/{n} ({bse/n*100:4.1f}%)  "
              f"no-tilt {n-a-bse:3d} ({(n-a-bse)/n*100:4.1f}%)")

    print("\n[c] АЛТЕРНАТИВА — raw alarm_count праг (вместо net):")
    print("    Колко често ≥k индикатора са едновременно в alarm:")
    for k in [1, 2, 3]:
        hit = (df["alarm"] >= k).sum()
        print(f"    alarm_count≥{k}: {hit:3d}/{n} ({hit/n*100:4.1f}%)")

    print("\n[d] Седмици с raw alarm_count≥2 — дата + КОИ индикатори "
          "(стрес-епизод проверка):")
    multi = df[df["alarm"] >= 2].sort_values("date")
    if multi.empty:
        print("    (никога ≥2 едновременни alarm-а)")
    else:
        for _, r in multi.iterrows():
            print(f"    {r['date'].date()}  alarm={int(r['alarm'])} "
                  f"base={int(r['base'])} net={int(r['net'])}  "
                  f"[{r['alarm_names']}]")


# ─────────────────────────────────────────────────────────────────────────────
# BT3 — robust_z per indicator (window sensitivity)
# ─────────────────────────────────────────────────────────────────────────────
def _rz_series(series: pd.Series, window: int) -> pd.Series:
    """Rolling robust-z, репликира src.barometer._robust_z точно (median/1.4826·MAD)."""
    s = series.dropna()
    out = {}
    for i in range(len(s)):
        if i < 29:  # _robust_z иска len>=30
            continue
        w = s.iloc[max(0, i - window + 1): i + 1]
        med = float(w.median())
        mad = float((w - med).abs().median())
        last = float(w.iloc[-1])
        if mad > 0:
            z = (last - med) / (1.4826 * mad)
        else:
            std = float(w.std())
            z = (last - med) / std if std > 0 else np.nan
        out[s.index[i]] = z
    return pd.Series(out)


def backtest_robust_z(prices: pd.DataFrame) -> None:
    _hr("BT3 · robust_z  Z_BASE/Z_ALARM/Z_WINDOW = "
        f"{Z_BASE}/{Z_ALARM}/{Z_WINDOW}  (barometer.py)")

    rz_inds = [i for i in INDICATORS if i["kind"] == "robust_z"]
    print(f"{len(rz_inds)} robust_z индикатора: "
          f"{', '.join(i['name'] for i in rz_inds)}")

    # guard: репликацията съвпада с live _robust_z @504 на последния бар
    sample = _series_for(rz_inds[0], prices, {})
    mine = _rz_series(sample, Z_WINDOW).iloc[-1]
    live = _robust_z(sample)
    print(f"\n[guard] репликация vs live _robust_z @{Z_WINDOW} "
          f"({rz_inds[0]['name']}): mine={mine:.4f} live={live:.4f} "
          f"Δ={abs(mine-live):.2e}")

    last = prices.index[-1]
    cutoff = last - pd.Timedelta(days=365 * 2)

    print(f"\n[a] Дял alarm (|z| в стрес-посоката ≥ {Z_ALARM}) — "
          f"оценено върху trailing 2г, по прозорец:")
    print(f"    {'indicator':<12s} {'dir':<5s} "
          f"{'W=252':>8s} {'W=504':>8s} {'W=756':>8s}  "
          f"{'gray%@504':>10s} {'|z|max@504':>11s}")
    for ind in rz_inds:
        s = _series_for(ind, prices, {})
        row = []
        gray504 = zmax504 = None
        for w in [252, 504, 756]:
            rz = _rz_series(s, w)
            rz = rz[rz.index >= cutoff].dropna()
            if rz.empty:
                row.append(np.nan); continue
            if ind["stress_dir"] == "high":
                alarm = (rz >= Z_ALARM).mean()
                base = (rz <= Z_BASE).mean()
            else:
                alarm = (rz <= -Z_ALARM).mean()
                base = (rz >= -Z_BASE).mean()
            row.append(alarm * 100)
            if w == 504:
                gray504 = (1 - alarm - base) * 100
                zmax504 = rz.abs().max()
        print(f"    {ind['name']:<12s} {ind['stress_dir']:<5s} "
              f"{row[0]:7.2f}% {row[1]:7.2f}% {row[2]:7.2f}%  "
              f"{gray504:9.1f}% {zmax504:10.2f}")

    print("\n    (base%@504 = калм-дял; gray = междинна зона; "
          "alarm+base+gray=100)")


def main():
    refresh = "--refresh" in sys.argv
    prices = get_prices(years=5, refresh=refresh)
    print(f"Prices: {prices.shape[0]} bars × {prices.shape[1]} tickers "
          f"({prices.index[0].date()} → {prices.index[-1].date()})")
    missing = [t for t in BAROMETER_TICKERS if t not in prices.columns]
    if missing:
        print(f"  ⚠ липсват тикъри: {missing}")
    fred = load_fred()
    print(f"FRED: hy_spread {len(fred['hy_spread'])} pts, "
          f"breakeven {len(fred['breakeven_10y'])} pts")

    backtest_quadrant()
    backtest_conf_net(prices, fred)
    backtest_robust_z(prices)
    print("\n" + "=" * 78)
    print("DONE — read-only. Нищо не е записано в pipeline данните.")
    print("=" * 78)


if __name__ == "__main__":
    main()
