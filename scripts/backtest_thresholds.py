"""
S16 — READ-ONLY backtest harness for the three "verdict-flipper" thresholds.

NIE PIPE pipeline-а. Чете data/ranks_history.parquet + FRED parquet кешовете,
тегли ~5г цени за барометър-тикърите (кешира в scripts/.bt_cache/), и МЕРИ
base-rate-овете на трите прага. Нищо не се записва в pipeline данните.

Трите обръщача:
  1. Quadrant 80/25         (rank_history.py: HIGH/LOW_BASE_THRESHOLD; LOW=25 от S16)
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

# ─────────────────────────────────────────────────────────────────────────────
# DRIFT-GATE (S20c) — полугодишна самопроверка на трите обръщача.
#
# Скелетът горе ПЕЧАТА base-rate-овете. Драйф-портата ги СРАВНЯВА с baseline-а
# от S16 (числата, калибрирани на 2026-06-19) и с owner-sourced диапазоните,
# които Цветослав записа дословно в S16 TODO. Изход: trust-map OK/🚩 + exit-code.
#
# ЖЕЛЯЗНО ПРАВИЛО (S16): портата НЕ пипа праговете — само флагва за човешки
# sign-off. Остава read-only за pipeline данните.
# ─────────────────────────────────────────────────────────────────────────────
BASELINE_DATE = "2026-06-19"
# Измерени в S16 (trailing-2г прозорец). Реферетни точки; драйфът = колко се е
# отместил ТЕКУЩИЯТ 2г прозорец спрямо тях. (Информативни — флагът пали на BANDS.)
BASELINE = {
    "quad_hi_occ": 20.6,   # % base_rank_6m ≥ HIGH(80)
    "quad_lo_occ": 17.1,   # % base_rank_6m ≤ LOW(25)
    "alarm2_rate": 4.95,   # % седмици с raw alarm_count ≥ 2 (пост-VUG→2.5 калибр. състояние; raw предкалибр. беше 6.9)
    "rz_xle_spy": 2.2,     # XLE/SPY alarm-дял @W=504
    "rz_iwm_spy": 8.0,     # IWM/SPY
    "rz_vug_vtv": 4.98,    # VUG/VTV @z_alarm=2.5
}
# Owner-sourced флаг-диапазони (S16 TODO, дословно: "XLE/SPY > 10%, VUG/VTV пак
# > 8%, quadrant трепка > 15%"). Едностранни горни граници — флаг при measured > band.
BANDS = {
    "quad_flip_max": 15.0,    # гранична трепка (flip-rate на live прага) > 15%
    "alarm2_max": 10.0,       # raw alarm_count≥2 fitka > 10%
    "rz_xle_spy_max": 10.0,   # XLE/SPY alarm > 10%
    "rz_vug_vtv_max": 8.0,    # VUG/VTV alarm > 8%
    "rz_generic_max": 15.0,   # sanity: всеки ДРУГ robust_z индикатор > 15%
}


def evaluate_drift(measured: dict) -> "tuple[list, bool]":
    """
    ЧИСТА функция (тестваема без мрежа). Взема измерените base-rate-ове, връща
    (rows, any_flag). Всеки row = dict {name, measured, baseline, band, status}.
    status = "OK" | "FLAG". Флаг пали при measured > band (owner-sourced граница).
    """
    rows = []
    any_flag = False

    def add(name, val, baseline, band):
        nonlocal any_flag
        flag = val is not None and band is not None and val > band
        any_flag = any_flag or flag
        rows.append({
            "name": name,
            "measured": None if val is None else round(float(val), 2),
            "baseline": baseline,
            "band": band,
            "status": "FLAG" if flag else "OK",
        })

    # Quadrant — трепка (по-важна от occupancy: окупацията S16 нарочно изравни).
    add("quadrant HI flip-rate", measured.get("quad_hi_flip"), None, BANDS["quad_flip_max"])
    add("quadrant LO flip-rate", measured.get("quad_lo_flip"), None, BANDS["quad_flip_max"])
    # Окупация — информативна (baseline за справка, без band → никога не флагва сама).
    add("quadrant HI occ (≥80)", measured.get("quad_hi_occ"), BASELINE["quad_hi_occ"], None)
    add("quadrant LO occ (≤25)", measured.get("quad_lo_occ"), BASELINE["quad_lo_occ"], None)
    # Барометър — raw alarm_count≥2 fitka.
    add("alarm_count≥2 rate", measured.get("alarm2_rate"), BASELINE["alarm2_rate"], BANDS["alarm2_max"])
    # robust_z — двата с явни owner-граници + sanity за останалите.
    rz = measured.get("rz", {})
    add("robust_z XLE/SPY", rz.get("XLE/SPY"), BASELINE["rz_xle_spy"], BANDS["rz_xle_spy_max"])
    add("robust_z VUG/VTV", rz.get("VUG/VTV"), BASELINE["rz_vug_vtv"], BANDS["rz_vug_vtv_max"])
    for name, val in rz.items():
        if name in ("XLE/SPY", "VUG/VTV"):
            continue
        add(f"robust_z {name}", val, None, BANDS["rz_generic_max"])

    return rows, any_flag

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
    _hr("BT1 · QUADRANT 80/25  (rank_history.py)")
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
        return {}

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

    # Headline метрики за драйф-портата (на ЖИВИТЕ прагове HIGH/LOW).
    c_live = crossings(HIGH_BASE_THRESHOLD, LOW_BASE_THRESHOLD)
    hi_flip = (c_live["hi_border_flip"] / c_live["hi_border"] * 100) if c_live["hi_border"] else 0.0
    lo_flip = (c_live["lo_border_flip"] / c_live["lo_border"] * 100) if c_live["lo_border"] else 0.0
    return {
        "quad_hi_occ": float((b >= HIGH_BASE_THRESHOLD).mean() * 100),
        "quad_lo_occ": float((b <= LOW_BASE_THRESHOLD).mean() * 100),
        "quad_hi_flip": float(hi_flip),
        "quad_lo_flip": float(lo_flip),
    }


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

    # Headline за драйф-портата: дял седмици с raw alarm_count≥2 (живият механизъм).
    return {"alarm2_rate": float((df["alarm"] >= 2).mean() * 100)}


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
    measured_rz = {}  # {name: alarm-дял @W=504} за драйф-портата

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
                # Драйф-портата ползва ПЕР-ИНДИКАТОРНИЯ z_alarm (VUG/VTV=2.5), за
                # да съвпада с живото поведение — [a] горе ползва глобалния 2.0.
                za = ind.get("z_alarm", Z_ALARM)
                if ind["stress_dir"] == "high":
                    measured_rz[ind["name"]] = float((rz >= za).mean() * 100)
                else:
                    measured_rz[ind["name"]] = float((rz <= -za).mean() * 100)
        print(f"    {ind['name']:<12s} {ind['stress_dir']:<5s} "
              f"{row[0]:7.2f}% {row[1]:7.2f}% {row[2]:7.2f}%  "
              f"{gray504:9.1f}% {zmax504:10.2f}")

    print("\n    (base%@504 = калм-дял; gray = междинна зона; "
          "alarm+base+gray=100)")
    return {"rz": measured_rz}


def _print_trust_map(rows: list, any_flag: bool) -> None:
    _hr(f"DRIFT TRUST-MAP  (baseline {BASELINE_DATE} · owner-sourced bands)")
    print(f"    {'обръщач':<26s} {'сега':>8s} {'baseline':>9s} "
          f"{'band':>7s}  статус")
    for r in rows:
        m = "—" if r["measured"] is None else f"{r['measured']:.2f}"
        b = "—" if r["baseline"] is None else f"{r['baseline']:.2f}"
        bd = "—" if r["band"] is None else f">{r['band']:.0f}"
        mark = "🚩 FLAG" if r["status"] == "FLAG" else "✓ OK"
        print(f"    {r['name']:<26s} {m:>8s} {b:>9s} {bd:>7s}  {mark}")
    print()
    if any_flag:
        print("🚩 DRIFT ОТКРИТ — поне един обръщач излезе от owner-диапазона.")
        print("   Праговете НЕ са пипани (правило S16). Нужен е човешки sign-off:")
        print("   пусни пълния backtest, прегледай trust-map-а, реши retune ръчно.")
    else:
        print("✓ Всички обръщачи в диапазона — нищо за правене. Праговете държат.")


def drift_check(prices: pd.DataFrame, fred: dict) -> bool:
    """Пуска трите backtest-а, събира headline числата, оценява драйфа.
    Връща any_flag (True → има отклонение за човешки преглед)."""
    measured = {}
    measured.update(backtest_quadrant() or {})
    measured.update(backtest_conf_net(prices, fred) or {})
    measured.update(backtest_robust_z(prices) or {})
    rows, any_flag = evaluate_drift(measured)
    _print_trust_map(rows, any_flag)
    return any_flag


def main():
    refresh = "--refresh" in sys.argv
    drift = "--drift-check" in sys.argv
    prices = get_prices(years=5, refresh=refresh)
    print(f"Prices: {prices.shape[0]} bars × {prices.shape[1]} tickers "
          f"({prices.index[0].date()} → {prices.index[-1].date()})")
    missing = [t for t in BAROMETER_TICKERS if t not in prices.columns]
    if missing:
        print(f"  ⚠ липсват тикъри: {missing}")
    fred = load_fred()
    print(f"FRED: hy_spread {len(fred['hy_spread'])} pts, "
          f"breakeven {len(fred['breakeven_10y'])} pts")

    if drift:
        any_flag = drift_check(prices, fred)
        print("\n" + "=" * 78)
        print("DONE — read-only drift-check. Нищо не е записано в pipeline данните.")
        print("=" * 78)
        sys.exit(1 if any_flag else 0)

    backtest_quadrant()
    backtest_conf_net(prices, fred)
    backtest_robust_z(prices)
    print("\n" + "=" * 78)
    print("DONE — read-only. Нищо не е записано в pipeline данните.")
    print("=" * 78)


if __name__ == "__main__":
    main()
