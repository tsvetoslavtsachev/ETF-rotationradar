"""
ETF fund-flow — нетни creation/redemption потоци за МАЩАБ и ПОСОКА.

S15 v2 (основен път): БРОИМ ДЯЛОВЕТЕ.
    est_flow ≈ цена_сега × (дялове_сега − дялове_преди)

Дяловете (shares outstanding) се менят САМО при creation/redemption — нямат
ценова компонента. Затова потокът е чист: умножаваме промяната на дяловете по
текущата цена и получаваме реалния долар, който е влязъл/излязъл. Това лекува
одитната находка „flows = чист ценови ефект" от корен (price×Δshares не носи
никаква ценова информация — Δцена не мести броя дялове).

S15 v1 (резервен/крос-чек път): AUM прокси.
    est_flow ≈ AUM_сега − AUM_преди × (1 + пазарна_доходност)

Изважда пазарната част от промяната на активите. Алгебрично е същото като
v2 (AUM = дялове × цена), НО `totalAssets` от yfinance е стар, седмично-репортван
номер при чужд NAV → остатъкът е замърсен от basis несъответствие. Пазим го за
крос-чек докато v2 узрее.

Честни ограничения (общи за двата пътя):
  • Няма backfill — yfinance не дава историческо shares outstanding
    (`get_shares_full` връща празно). Пълни се НАПРЕД, по един snapshot на ден
    (data/shares_history.parquet). Потоци се появяват щом историята покрие
    прозореца → колоната е "—" първите няколко седмици.
  • И дяловете идват от `.info` (7-дневен кеш като AUM) → реалната резолюция е
    ~седмична, не дневна. Но за разлика от AUM-проксито тук НЯМА ценово
    замърсяване — броят дялове е независим от цената.
  • Точност: порядък и посока, не до цент.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AUM_HISTORY_COLUMNS = ["date", "ticker", "aum"]
SHARES_HISTORY_COLUMNS = ["date", "ticker", "shares"]
DEFAULT_WINDOW_DAYS = 21   # целеви прозорец (~1 търговски месец)
MIN_WINDOW_DAYS = 3        # под това не докладваме (твърде шумно)

FLOW_COLUMNS = ["ticker", "est_flow", "est_flow_pct", "flow_window_days", "flow_dir"]


# ---------------------------------------------------------------------------
# Snapshot история (forward-accumulate; общ механизъм за дялове и AUM)
# ---------------------------------------------------------------------------

def _append_snapshot(history_path: Path, value_map: dict, as_of, value_col: str) -> None:
    """
    Записва днешния snapshot. value_map = {ticker: float}.
    Dedup по (date, ticker) — повторен run за същия ден не дублира.
    """
    as_of = pd.Timestamp(as_of).normalize()
    rows = [
        {"date": as_of, "ticker": t, value_col: float(v)}
        for t, v in value_map.items()
        if v is not None and np.isfinite(float(v)) and float(v) > 0
    ]
    if not rows:
        print(f"Flows: няма валиден {value_col} за snapshot (пропускам).")
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


def _load_history(history_path: Path, columns: list) -> pd.DataFrame:
    history_path = Path(history_path)
    if not history_path.exists():
        return pd.DataFrame(columns=columns)
    df = pd.read_parquet(history_path)
    df["date"] = pd.to_datetime(df["date"])
    return df


def append_shares_snapshot(history_path: Path, shares_map: dict, as_of) -> None:
    """Записва днешния shares-outstanding snapshot (v2 основен път)."""
    _append_snapshot(history_path, shares_map, as_of, "shares")


def load_shares_history(history_path: Path) -> pd.DataFrame:
    return _load_history(history_path, SHARES_HISTORY_COLUMNS)


def append_aum_snapshot(history_path: Path, aum_map: dict, as_of) -> None:
    """Записва днешния AUM snapshot (v1 прокси / крос-чек)."""
    _append_snapshot(history_path, aum_map, as_of, "aum")


def load_aum_history(history_path: Path) -> pd.DataFrame:
    return _load_history(history_path, AUM_HISTORY_COLUMNS)


# ---------------------------------------------------------------------------
# Изчисление на потоци
# ---------------------------------------------------------------------------

def _price_on_or_before(price_series: pd.Series, date: pd.Timestamp) -> "float | None":
    s = price_series.dropna()
    s = s[s.index <= date]
    return float(s.iloc[-1]) if len(s) else None


def _flows_core(
    history: pd.DataFrame,
    value_col: str,
    prices_df: pd.DataFrame,
    as_of,
    window_days: int,
    basis: str,
) -> pd.DataFrame:
    """
    Общ двигател за двата базиса.
      basis="shares": est_flow = цена_сега × (дялове_сега − дялове_преди)
                      prior_aum = дялове_преди × цена_преди
      basis="aum":    est_flow = AUM_сега − AUM_преди × (1 + доходност)
                      prior_aum = AUM_преди
    Празен/липсващ ред, където историята/цените не стигат за прозореца.
    """
    if history.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)

    as_of = pd.Timestamp(as_of).normalize()

    if isinstance(prices_df.columns, pd.MultiIndex):
        prices_df = prices_df.copy()
        prices_df.columns = prices_df.columns.get_level_values(-1)

    target_prior = as_of - pd.tseries.offsets.BusinessDay(window_days)
    rows = []
    for ticker, g in history.groupby("ticker"):
        g = g.sort_values("date")

        now_rows = g[g["date"] <= as_of]
        if now_rows.empty:
            continue
        val_now = float(now_rows[value_col].iloc[-1])
        date_now = now_rows["date"].iloc[-1]

        # Най-близкият snapshot на/преди целевия прозорец; ако няма толкова стар —
        # ползваме най-стария наличен (докато историята още се пълни).
        prior_rows = g[g["date"] <= target_prior]
        prior_row = prior_rows.iloc[-1] if not prior_rows.empty else g.iloc[0]
        val_prior = float(prior_row[value_col])
        date_prior = prior_row["date"]

        wdays = (date_now - date_prior).days
        if date_now == date_prior or wdays < MIN_WINDOW_DAYS or val_prior <= 0:
            continue

        if ticker not in prices_df.columns:
            continue
        p_now = _price_on_or_before(prices_df[ticker], date_now)
        p_prior = _price_on_or_before(prices_df[ticker], date_prior)
        if not p_now or not p_prior or p_prior <= 0:
            continue

        if basis == "shares":
            est_flow = p_now * (val_now - val_prior)
            prior_aum = val_prior * p_prior
        else:  # aum
            ret = p_now / p_prior - 1.0
            est_flow = val_now - val_prior * (1.0 + ret)
            prior_aum = val_prior

        if prior_aum <= 0:
            continue

        rows.append({
            "ticker": ticker,
            "est_flow": round(est_flow, 0),
            "est_flow_pct": round(est_flow / prior_aum * 100.0, 2),
            "flow_window_days": int(wdays),
            "flow_dir": "in" if est_flow > 0 else "out" if est_flow < 0 else "flat",
        })

    if not rows:
        return pd.DataFrame(columns=FLOW_COLUMNS)
    return pd.DataFrame(rows)


def compute_flows(
    shares_history: pd.DataFrame,
    prices_df: pd.DataFrame,
    as_of,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.DataFrame:
    """v2 основен път — реален поток от промяната на дяловете (price × Δshares)."""
    return _flows_core(shares_history, "shares", prices_df, as_of, window_days, "shares")


def compute_flows_aum(
    aum_history: pd.DataFrame,
    prices_df: pd.DataFrame,
    as_of,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> pd.DataFrame:
    """v1 прокси / крос-чек — AUM-делта минус пазарното движение."""
    return _flows_core(aum_history, "aum", prices_df, as_of, window_days, "aum")
