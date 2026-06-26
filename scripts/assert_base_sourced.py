#!/usr/bin/env python3
"""CI guard (INIT-22 P6): fail RED if any ETF price silently fell back to yfinance.

The P6 strangler sources every ETF's daily bars FROM the canonical price-archive (the guarded,
survivorship-clean base) via collectors/price/consumer.py. That reader is base-first with a
CLOSED yfinance fallback that keeps the radar alive if the archive checkout/wiring is
unavailable -- but a silent fallback would quietly republish ranks off un-audited fetch data
instead of the canon.

This guard makes that failure LOUD. It anchors on the EXPECTED UNIVERSE read INDEPENDENTLY of
the produced payload -- the radar's own src/universe.py (mirroring the A1 template, which anchors
on data/manifest.json, not on the shrinkable produced file). Every expected ticker must be
present in data/price_source.json AND carry source == "base". A dropped/dead ETF (absent from
the payload) or a fetch-sourced one fails the build. Without the independent anchor a silent
universe-shrink would pass green (daily_update's only health check is prices_df.empty, which a
PARTIAL universe does not trip).

Run only when the read PAT is set (the workflow gates it); with the secret absent the yfinance
fallback is legitimate and this is skipped. Mirrors
dashboards/cot-monitor/scripts/assert_base_sourced.py (A1 cot_source guard).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "data" / "price_source.json"
sys.path.insert(0, str(REPO))  # so the expected-universe anchor (src/universe.py) imports

from src.universe import get_universe_tickers, get_benchmark_tickers  # noqa: E402


def main() -> int:
    if not SOURCE.exists():
        print(f"assert_base_sourced: {SOURCE} missing -- daily_update must run first",
              file=sys.stderr)
        return 1
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_symbol = payload.get("by_symbol", {})

    # Independent anchor: the universe the radar is DEFINED over (not the produced payload).
    expected = sorted(set(get_universe_tickers()) | set(get_benchmark_tickers()))
    if not expected:
        print("assert_base_sourced: empty expected universe -- src/universe.py broken",
              file=sys.stderr)
        return 1

    offenders = []
    for t in expected:
        src = by_symbol.get(t)
        if src is None:
            offenders.append(f"{t} (MISSING from price_source -- dropped/dead; universe shrank)")
        elif src != "base":
            offenders.append(f"{t} (source={src!r})")

    total = len(expected)
    if offenders:
        print(f"FAIL: {len(offenders)}/{total} expected ETFs did NOT source from the price-archive "
              f"base (the read PAT is set, so base sourcing was expected):", file=sys.stderr)
        for o in offenders:
            print(f"  - {o}", file=sys.stderr)
        print("The strangler silently reverted to the yfinance fallback (un-audited fetch) or the "
              "published universe shrank. Check the data-core/price-archive checkout + PYTHONPATH "
              "+ DATACORE_ROOT, and any per-symbol archive gap (config.yaml daily-window limit).",
              file=sys.stderr)
        return 1

    print(f"OK: all {total} expected ETFs sourced from the price-archive base (source=base).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
