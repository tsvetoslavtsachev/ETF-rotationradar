# -*- coding: utf-8 -*-
"""ЧИС3 казус 1 -- ^VIX/^MOVE носят value_date по СОБСТВЕНАТА серия в snapshot,
защото as_of на фийда следва ETF архива и в делник изостава с един ден (виж
manus-factory/prompts/observatory-atlas/CHISTKA-3.md)."""
import numpy as np
import pandas as pd

from src.barometer import compute_barometer

TICKERS = ["XLE", "SPY", "GLD", "TLT", "HYG", "LQD", "XLY", "XLP", "IWM", "VUG", "VTV"]


def _frame(n=35, vix_extra_day=True):
    idx = pd.bdate_range("2026-07-01", periods=n)
    rng = np.random.default_rng(7)
    data = {t: 100 + rng.normal(0, 1, n).cumsum() for t in TICKERS}
    df = pd.DataFrame(data, index=idx)
    vix = pd.Series(20 + rng.normal(0, 1, n).cumsum() * 0.1, index=idx)
    move = pd.Series(90 + rng.normal(0, 1, n).cumsum() * 0.1, index=idx)
    if vix_extra_day:
        # ETF колоните свършват на Т-1 (последният ред е NaN за тях),
        # ^VIX/^MOVE имат стойност през Т -> прочетени в реално време.
        df.loc[idx[-1], TICKERS] = np.nan
    df["^VIX"] = vix
    df["^MOVE"] = move
    return df


def _snap(feed, name):
    return next(r for r in feed["snapshot"] if r["indicator"] == name)


def test_vix_move_carry_value_date_ahead_of_as_of():
    df = _frame()
    as_of = df.index[-2]  # ETF архивът е с ден назад
    feed = compute_barometer(df, {}, as_of)
    assert feed["as_of"] == as_of.strftime("%Y-%m-%d")
    vix_row = _snap(feed, "VIX")
    move_row = _snap(feed, "MOVE")
    expected_value_date = df.index[-1].strftime("%Y-%m-%d")
    assert vix_row["value_date"] == expected_value_date
    assert move_row["value_date"] == expected_value_date
    assert vix_row["value_date"] != feed["as_of"]


def test_every_indicator_with_a_series_carries_its_own_value_date():
    # 11.09.2026: value_date е при всеки индикатор; ETF ratio-тата свършват на as_of,
    # ^VIX/^MOVE са ден напред, FRED серии без данни нямат поле.
    df = _frame()
    as_of = df.index[-2]
    feed = compute_barometer(df, {}, as_of)
    xle_row = _snap(feed, "XLE/SPY")
    assert xle_row["value_date"] == feed["as_of"]
    hy_row = _snap(feed, "HY-spread")
    assert "value_date" not in hy_row and hy_row["zone"] == "unknown"


def test_snapshot_carries_direction_thresholds_and_history():
    df = _frame(n=60)
    feed = compute_barometer(df, {}, df.index[-1])
    rows = {r["indicator"]: r for r in feed["snapshot"]}
    assert rows["HYG/LQD"]["stress_dir"] == "low" and rows["VIX"]["stress_dir"] == "high"
    # robust_z носи z-праговете, abs не (там z не решава зоната)
    assert rows["XLE/SPY"]["z_base"] == 1.0 and rows["XLE/SPY"]["z_alarm"] == 2.0
    assert rows["VUG/VTV"]["z_alarm"] == 2.5
    assert rows["VIX"]["z_base"] is None and rows["VIX"]["z_alarm"] is None
    # историята: седмични точки, дата + стойност, последната е текущата стойност
    hist = rows["XLE/SPY"]["history"]
    assert 0 < len(hist) <= 26
    assert all(set(p) == {"date", "value"} for p in hist)
    assert hist[-1]["value"] == rows["XLE/SPY"]["value"]
    assert hist[-1]["date"] == rows["XLE/SPY"]["value_date"]
    assert rows["HY-spread"]["history"] == []  # без серия -> празно, не измислено


def test_value_date_matches_as_of_when_series_aligned():
    df = _frame(vix_extra_day=False)
    as_of = df.index[-1]
    feed = compute_barometer(df, {}, as_of)
    vix_row = _snap(feed, "VIX")
    assert vix_row["value_date"] == feed["as_of"]


# ── 27.09.2026 · свежест на всяко число (казусът VIX W39) ────────────────────
# Моделът е data-core (digest.py: свежо / „забавя" / „залежал"; m_pulse: кохорта и кой
# изостава). Застоял VIX трябва да излезе маркиран, не пренесен като днешен.

def test_stale_vix_is_marked_stale_not_carried_as_today():
    df = _frame(vix_extra_day=False)
    df.loc[df.index[-4:], "^VIX"] = np.nan  # VIX спира 4 сесии преди останалите
    feed = compute_barometer(df, {}, df.index[-1])
    vix = _snap(feed, "VIX")
    assert vix["value_date"] == df.index[-5].strftime("%Y-%m-%d")
    assert vix["lag_sessions"] == 4
    assert vix["freshness"] == "stale" and vix["stale"] is True
    assert feed["freshness"]["stale"] == ["VIX"]
    assert feed["freshness"]["newest_cohort"] == df.index[-1].strftime("%Y-%m-%d")
    reading = next(r for r in feed["readings"] if r["indicator"] == "VIX")
    assert reading["stale"] is True and reading["value_date"] == vix["value_date"]


def test_normal_weekday_lag_marks_nothing():
    # ETF архивът с ден назад, VIX/MOVE в реално време: това е нормата, не застой.
    df = _frame()
    feed = compute_barometer(df, {}, df.index[-2])
    dated = [r for r in feed["snapshot"] if "value_date" in r]
    assert dated and all(r["freshness"] == "fresh" and r["stale"] is False for r in dated)
    assert _snap(feed, "XLE/SPY")["lag_sessions"] == 1
    assert feed["freshness"]["late"] == [] and feed["freshness"]["stale"] == []


def test_two_sessions_behind_is_late_not_stale():
    df = _frame(vix_extra_day=False)
    df.loc[df.index[-2:], "^VIX"] = np.nan
    feed = compute_barometer(df, {}, df.index[-1])
    vix = _snap(feed, "VIX")
    assert (vix["lag_sessions"], vix["freshness"], vix["stale"]) == (2, "late", False)
    assert feed["freshness"]["late"] == ["VIX"]


def test_missing_series_has_no_freshness_but_is_listed():
    feed = compute_barometer(_frame(), {}, _frame().index[-2])
    hy = _snap(feed, "HY-spread")
    assert "stale" not in hy and "freshness" not in hy
    assert "HY-spread" in feed["freshness"]["missing"]


def test_value_since_separates_coincidence_from_recycled_print():
    df = _frame(vix_extra_day=False)
    idx = df.index
    # истинско съвпадение (CBOE 21.09 = 25.09 = 14,87): стойността се движи между двете
    df.loc[idx[-5:], "^VIX"] = [14.87, 14.21, 15.18, 15.67, 14.87]
    vix = _snap(compute_barometer(df, {}, idx[-1]), "VIX")
    assert vix["value_since"] == idx[-1].strftime("%Y-%m-%d")
    # рециклиран отпечатък: същото число стои от три сесии
    df.loc[idx[-3:], "^VIX"] = 15.67
    vix = _snap(compute_barometer(df, {}, idx[-1]), "VIX")
    assert vix["value_since"] == idx[-3].strftime("%Y-%m-%d")
