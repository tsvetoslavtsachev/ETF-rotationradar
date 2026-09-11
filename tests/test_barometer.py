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
