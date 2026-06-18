"""
ETF fund-flow прокси (S15) — груба оценка на нетни потоци за МАЩАБ и ПОСОКА,
не за прецизност.

Идея: промяната в активите (AUM) идва от ДВЕ неща — пазарът мърда цената, и
инвеститори влизат/излизат (creation/redemption). Изваждаме пазарната част:

    est_flow ≈ AUM_сега − AUM_преди × (1 + пазарна_доходност_за_периода)

Остатъкът е нетното creation/redemption (приблизително).

Честни ограничения:
  • Няма backfill — yfinance не дава историческо AUM. Пълни се НАПРЕД, по един
    snapshot на ден (data/aum_history.parquet). Потоци се появяват щом историята
    покрие прозореца → колоната е "—" първите няколко седмици. Това е по
    договорка (S15: "почва празно и се пълни напред").
  • Зависи колко често Yahoo опреснява totalAssets. Fundamentals кешът е 7-дневен,
    т.е. AUM реално мърда ~седмично. Затова целевият прозорец е ~21 търговски дни
    (месец) — улавя няколко реални AUM точки, не дневен кеш-шум.
  • Точност: порядък и посока, не до цент. Ако се окаже твърде шумно → fallback
    към issuer CSV (shares-out × цена) за флагманите.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AUM_HISTORY_COLUMNS = ["date", "ticker", "aum"]
DEFAULT_WINDOW_DAYS = 21   # целеви прозорец (~1 търговски месец)
MIN_WINDOW_DAYS = 3        # под това не докладваме (твърде шумно)

FLOW_COLUMNS = ["ticker", "est_flow", "est_flow_pct", "flow_window_days", "flow_dir"]


def append_aum_snapshot(history_path: Path, aum_map: dict, as_of) -> None:
    """
    Записва днешния AUM snapshot. aum_map = {ticker: aum_float}.
    Dedup по (date, ticker) — повторен run за същия ден не дублира.
    """
    as_of = pd.Timestamp(as_of).normalize()
    rows = [
        {"date": as_of, "ticker": t, "aum": float(a)}
        for t, a in aum_map.items()
        if a is not None and np.isfinite(float(a)) and float(a) > 0
    ]
    if not rows:
        print("Flows: няма валиден AUM за snapshot (пропускам).")
        return
    snap = pd.DataFrame(rows)

    history_path = Path(history_path)
    if history_path.exists():
        existing = pd.read_parquet(history_path)
        existing["date"] = pd.to_datetime(existing["date"])
        keys = set(zip(snap["date"], snap["ticker"]))
        mask = [(d, t) not in keys for d, t in zip(existing["date"], existing["ticker"])]
        combined = pd.concat([existing.loc[mask], snap], ignore_index=True)
    else:
        combined = snap

    combined = combined.sort_values(["date", "ticker"]).reset_index(drop=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(history_path, index=False)


def load_aum_history(history_path: Path) -> pd.DataFrame:
    history_path = Path(history_path)
    if not history_path.exists():
        return pd.DataFrame(columns=AUM_HISTORY_COLUMNS)
    df = pd.read_parquet(history_path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _price_on_or_before(price_series: pd.Series, date: pd.Timestamp) -> "float | None":
    s = price_series.dropna()
    s = s[s.index <= date]
    return float(s.iloc[-1]) if len(s) else None


def compute_flows(
    aum_history: pd.DataFrame,
    prices_df: pd.DataFrame,
    as_of,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Връща DataFrame с FLOW_COLUMNS. Празен/липсващ ред, където историята или
    цените не стигат за прозореца (по-малко от MIN_WINDOW_DAYS реални дни).
    """
    if aum_history.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)

    as_of = pd.Timestamp(as_of).normalize()

    # Сплескай цени до тикър-колони, ако са MultiIndex.
    if isinstance(prices_df.columns, pd.MultiIndex):
        prices_df = prices_df.copy()
        prices_df.columns = prices_df.columns.get_level_values(-1)

    target_prior = as_of - pd.tseries.offsets.BusinessDay(window_days)
    rows = []
    for ticker, g in aum_history.groupby("ticker"):
        g = g.sort_values("date")

        now_rows = g[g["date"] <= as_of]
        if now_rows.empty:
            continue
        aum_now = float(now_rows["aum"].iloc[-1])
        date_now = now_rows["date"].iloc[-1]

        # Най-близкият snapshot на/преди целевия прозорец; ако няма толкова стар —
        # ползваме най-стария наличен (докато историята още се пълни).
        prior_rows = g[g["date"] <= target_prior]
        prior_row = prior_rows.iloc[-1] if not prior_rows.empty else g.iloc[0]
        aum_prior = float(prior_row["aum"])
        date_prior = prior_row["date"]

        wdays = (date_now - date_prior).days
        if date_now == date_prior or wdays < MIN_WINDOW_DAYS or aum_prior <= 0:
            continue

        if ticker not in prices_df.columns:
            continue
        p_now = _price_on_or_before(prices_df[ticker], date_now)
        p_prior = _price_on_or_before(prices_df[ticker], date_prior)
        if not p_now or not p_prior or p_prior <= 0:
            continue

        ret = p_now / p_prior - 1.0
        est_flow = aum_now - aum_prior * (1.0 + ret)
        rows.append({
            "ticker": ticker,
            "est_flow": round(est_flow, 0),
            "est_flow_pct": round(est_flow / aum_prior * 100.0, 2),
            "flow_window_days": int(wdays),
            "flow_dir": "in" if est_flow > 0 else "out" if est_flow < 0 else "flat",
        })

    if not rows:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    return pd.DataFrame(rows)
