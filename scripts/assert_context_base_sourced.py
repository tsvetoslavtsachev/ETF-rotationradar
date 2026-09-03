#!/usr/bin/env python3
"""CI guard (ATL4 P10): fail RED if the market-context well silently re-split.

The P10 switch made data-core's canon the single owner of the HY OAS spread's and the 10y
breakeven's HISTORY (``mkt_hy_oas`` / ``mkt_breakeven_10y``). The barometer's own FRED pull
survives for ONE reason only: data-core's market-context collect runs WEEKLY (Saturdays) while
this radar runs daily, so the pull supplies the TAIL after the canon's last point. That is a
narrow, declared overlap, and this guard keeps it narrow.

It fails RED on three things, each of which means the well is no longer single:

  * ``fetch``    -- the canon was unreachable/empty and the OLD path served the whole history
                    alone. That is the pre-P10 world, back without anyone noticing.
  * ``conflict`` -- the canon and the fetch DISAGREE on a shared date. Both pull the same FRED
                    ticker, so a disagreement is a definition/ticker change, not noise. This is
                    the re-split the mandate asked to be caught.
  * a tail longer than the declared threshold -- the weekly collect has missed runs, so the
                    canon is no longer the history in any meaningful sense.

Run only when the read PAT is set (the workflow gates it); with the secret absent there is no
data-core checkout, the pure-fetch path is legitimate, and this is skipped. Mirrors
scripts/assert_base_sourced.py (the P6 price guard).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "data" / "context_source.json"

# Must match collectors/vrm/consumer.py BRIDGE of the same name; the expected set is anchored
# here INDEPENDENTLY of the produced payload, so a silently dropped indicator fails too.
EXPECTED = ("breakeven_10y", "hy_spread")
OK_SOURCES = ("base", "base+tail")


def main() -> int:
    if not SOURCE.exists():
        print(f"assert_context_base_sourced: {SOURCE} missing -- daily_update must run first",
              file=sys.stderr)
        return 1
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_ind = payload.get("by_indicator", {})
    detail = payload.get("detail", {})

    if not payload.get("reader_available"):
        print("assert_context_base_sourced: RED -- collectors.vrm.consumer was not importable, "
              "so the whole history came from the old direct FRED pull (the pre-P10 split is back)",
              file=sys.stderr)
        return 1

    failures = []
    for ind in EXPECTED:
        src = by_ind.get(ind)
        d = detail.get(ind, {})
        if src is None:
            failures.append(f"{ind}: absent from the provenance payload")
            continue
        if src == "conflict":
            failures.append(
                f"{ind}: RE-SPLIT -- canon and fetch disagree on {d.get('overlap_mismatches')} of "
                f"{d.get('overlap')} shared dates (worst {d.get('worst_abs_diff')})")
            continue
        if src not in OK_SOURCES:
            failures.append(
                f"{ind}: served by '{src}', not the canon -- {d.get('why') or 'no reason recorded'}")
            continue
        tail, cap = d.get("tail_bdays"), d.get("max_tail_bdays")
        if tail is not None and cap is not None and tail > cap:
            failures.append(
                f"{ind}: canon is {tail} business days behind (cap {cap}) -- the weekly "
                f"market-context collect in data-core is missing runs")

    if failures:
        print("assert_context_base_sourced: RED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    for ind in EXPECTED:
        d = detail.get(ind, {})
        print(f"assert_context_base_sourced: {ind} {by_ind.get(ind)} "
              f"(canon {d.get('base_rows')} rows to {d.get('base_last')}, tail {d.get('tail_rows')}, "
              f"overlap {d.get('overlap')} with {d.get('overlap_mismatches')} mismatches)")
    print("assert_context_base_sourced: GREEN -- one well, no re-split")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
