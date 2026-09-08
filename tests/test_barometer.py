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


def test_other_indicators_have_no_value_date():
    df = _frame()
    feed = compute_barometer(df, {}, df.index[-2])
    xle_row = _snap(feed, "XLE/SPY")
    assert "value_date" not in xle_row


def test_value_date_matches_as_of_when_series_aligned():
    df = _frame(vix_extra_day=False)
    as_of = df.index[-1]
    feed = compute_barometer(df, {}, as_of)
    vix_row = _snap(feed, "VIX")
    assert vix_row["value_date"] == feed["as_of"]
