"""
Category-Rotation Heat-Strip (Tier 3 UX, последното парче на роудмапа).

Топлинна карта „кои сектори бяха горещи/студени през последния половин година":
~9 категории × 26 седмици, всяка клетка = медианният АБСОЛЮТЕН momentum-перцентил
на категорията за тази седмица.

Решения на Цветослав (S20, 2026-06-19) — всички sign-off-нати, anti-illusion verified:
  • Метрика = `unadj_percentile` (ГЛОБАЛЕН ранг по абсолютен 12-1 momentum,
    signal_engine.py:81), НЕ `percentile_rank`. Причина (изчислена, не догадка):
    `percentile_rank` е ранг ВЪТРЕ в категорията → медианата му е структурно ~50
    за всяка категория всяка седмица (измерено: 9 кат × 26 седм. се събират в
    51.6–62.5) → плосък безполезен heat-strip. `unadj_percentile` дава реален
    контраст (медианите 10.3–92.7, p10=17 / p90=80) → истинско „горещо/студено".
  • Цветова скала = ДИВЕРЖЕНТНА, центрирана на 50 (frontend). 50 = медианният ETF
    (дефиниция на перцентил), 0/100 = краищата (дефиниция) → нула измислени прагове.
  • 26 седмици (полугодие).

⚠️ Каденца: ranks_history е W-FRI седмична, НО CI ботът append-ва snapshot всеки
делник от ~9 юни. Затова resample-ваме W-FRI (вземаме ПОСЛЕДНАТА снимка на всяка
седмица), иначе скорошните седмици тежат 5× повече от старите.

Нула нови вызови — чете готовата `ranks_history.parquet`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

METRIC = "unadj_percentile"
N_WEEKS = 26


def compute_heatstrip(
    history: pd.DataFrame,
    category_map: dict | None = None,
    n_weeks: int = N_WEEKS,
    metric: str = METRIC,
) -> dict:
    """
    Връща display-ready dict:
      available   — False (празно) ако историята е твърде къса.
      metric      — "unadj_percentile".
      n_weeks     — брой колони.
      weeks       — списък крайни дати на седмиците (W-FRI, "YYYY-MM-DD"), хронологично.
      categories  — подредени по ПОСЛЕДНАТА седмица низходящо (най-горещият сектор отгоре).
      cells       — {category: [v0..v_{n-1}]} медианен momentum-перцентил per седмица
                    (закръглен; None ако категорията няма данни за тази седмица).
    """
    category_map = category_map or {}
    empty = {
        "available": False, "metric": metric, "n_weeks": n_weeks,
        "weeks": [], "categories": [], "cells": {},
    }
    if history is None or history.empty or metric not in history.columns:
        return empty

    df = history.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "category" not in df.columns:
        df["category"] = df["ticker"].map(category_map)
    df = df.dropna(subset=["category", metric])
    if df.empty:
        return empty

    # W-FRI resample: за всяка седмица пазим ПОСЛЕДНАТА налична снимка (лекува
    # дневните CI append-и — скорошните седмици иначе тежат 5×).
    df["wk"] = df["date"].dt.to_period("W-FRI")
    last_date_per_week = df.groupby("wk")["date"].max()
    week_periods = sorted(last_date_per_week.index)[-n_weeks:]
    if not week_periods:
        return empty

    # пазим САМО редовете на последната дата от всяка избрана седмица (иначе
    # медианата би смесила всички дневни snapshot-и в седмицата → каденца-капан)
    keep_dates = {last_date_per_week[w] for w in week_periods}
    sub = df[df["date"].isin(keep_dates) & df["wk"].isin(set(week_periods))]
    # медианен absolute-momentum перцентил per (категория, седмица)
    piv = (
        sub.groupby(["category", "wk"])[metric]
        .median()
        .unstack()
        .reindex(columns=week_periods)
    )

    weeks = [pd.Timestamp(last_date_per_week[w]).strftime("%Y-%m-%d") for w in week_periods]

    # подредба: най-горещ сектор (по последната седмица) отгоре; None → най-долу
    last_col = piv[week_periods[-1]]
    order = last_col.sort_values(ascending=False, na_position="last").index.tolist()

    cells: dict[str, list] = {}
    for cat in order:
        row = piv.loc[cat, week_periods]
        cells[cat] = [
            None if pd.isna(v) else round(float(v), 1) for v in row.tolist()
        ]

    return {
        "available": True,
        "metric": metric,
        "n_weeks": len(weeks),
        "weeks": weeks,
        "categories": order,
        "cells": cells,
    }
