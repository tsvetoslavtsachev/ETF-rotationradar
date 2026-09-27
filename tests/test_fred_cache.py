# -*- coding: utf-8 -*-
"""27.09.2026 -- барометърните FRED серии се теглят всеки пуск (max_age_days=None).
С 1-дневния TTL всеки втори дневен пуск тихо ползваше вчерашното теглене и HY
изоставаше с 2-3 сесии. Кешът остава резерва при провал."""
import pandas as pd
import pytest

from src import fred


def _cache(path, last="2026-09-22"):
    idx = pd.bdate_range(end=last, periods=5)
    df = pd.DataFrame({"date": idx, "value": [2.7, 2.71, 2.72, 2.73, 2.74]})
    df["fetched_at"] = pd.Timestamp.now().normalize()  # „свеж“ кеш от днес
    df.to_parquet(path, index=False)


class _Remote(list):
    fail = False


@pytest.fixture
def remote(monkeypatch):
    calls = _Remote()
    fresh = pd.Series([2.75, 2.8], index=pd.to_datetime(["2026-09-23", "2026-09-24"]))

    def fake(series_id):
        calls.append(series_id)
        if calls.fail:
            raise RuntimeError("FRED down")
        return fresh
    monkeypatch.setattr(fred, "_fetch_remote", fake)
    monkeypatch.setattr(fred.time, "sleep", lambda s: None)
    return calls


def test_default_ttl_still_returns_fresh_cache_without_fetch(tmp_path, remote):
    p = tmp_path / "hy.parquet"
    _cache(p)
    s = fred.fetch_fred_series("BAMLH0A0HYM2", cache_path=p)
    assert remote == [] and s.index.max() == pd.Timestamp("2026-09-22")


def test_none_always_fetches_even_with_fresh_cache(tmp_path, remote):
    p = tmp_path / "hy.parquet"
    _cache(p)
    s = fred.fetch_fred_series("BAMLH0A0HYM2", cache_path=p, max_age_days=None)
    assert remote == ["BAMLH0A0HYM2"] and s.index.max() == pd.Timestamp("2026-09-24")
    assert pd.to_datetime(pd.read_parquet(p)["date"]).max() == pd.Timestamp("2026-09-24")


def test_none_falls_back_to_cache_when_fetch_fails(tmp_path, remote):
    p = tmp_path / "hy.parquet"
    _cache(p)
    remote.fail = True
    s = fred.fetch_fred_series("BAMLH0A0HYM2", cache_path=p, max_age_days=None)
    assert len(remote) == 3 and s.index.max() == pd.Timestamp("2026-09-22")
