#!/usr/bin/env python3
"""
fetch_series.py - pull the macro report tables from DBIE and dump their column trees.

Uses series_lib.table_of() so every report is fetched WHOLE (pageSize=0 with a paging fallback).
Saves raw payloads under raw/, prints the leaf columns of each report, and writes raw/survey.json.

STETP: [INFO]/[WARN]/[ERROR] logs, granular try/except; a report that fails is reported, not skipped.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import traceback

# import the client from THIS directory (the repo is self-contained: dbie_client.py and series_lib.py
# ship alongside this script). The original pointed at a local checkout, which broke on any other
# machine - including CI.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dbie_client import DBieClient          # noqa: E402
from series_lib import table_of, to_series  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
log = logging.getLogger("warroom")
ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
LOCK = RAW / ".fetch.lock"

# Reports the portal serves as a PARTIAL subset (rows << totalCount) and which are therefore
# NOT used by the dashboard. Listed explicitly so the completeness gate below can still fail
# loudly on anything else that comes back short.
KNOWN_PARTIAL = {"6"}


def acquire_lock() -> None:
    """Refuse to run if another fetch is writing raw/ - two writers silently clobber each other.

    This is not theoretical: a slow fetch left running in the background finished AFTER a newer
    one and overwrote its output files with empty tables. Because every consumer reads raw/*.json
    by name, that produced a dashboard built on blank series with no error anywhere.
    """
    if LOCK.exists():
        try:
            pid = int((LOCK.read_text().strip() or "0"))
        except ValueError:
            pid = 0
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0)                       # signal 0 = liveness probe only
                alive = True
            except OSError:
                alive = False
        if alive:
            raise SystemExit(f"[ERROR] [Lock] another fetch is already running (pid {pid}); "
                             f"refusing to write raw/ concurrently")
        log.warning("[WARN] [Lock] stale lock from dead pid %s - taking it over", pid)
    LOCK.write_text(str(os.getpid()))


def release_lock() -> None:
    try:
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()
    except Exception:
        log.error("[ERROR] [Lock] could not release lock:\n%s", traceback.format_exc())

WANT = {
    "11": "Major Price Indices (CPI/WPI monthly)",
    "13": "Money Stock: Components and Sources (M3)",
    "7": "Reserve Money",
    "9": "SCBs - Business in India (deposits/credit)",
    "2": "GoI Treasury Bills Outstanding",
    "8": "Liquidity Operations by RBI (daily LAF)",
    "10": "Ratios and Rates (CRR/SLR/policy rates)",
    "12": "Average Daily Turnover, money markets",
    "39": "RBI - Liabilities and Assets",
    "4": "Certificate of Deposit",
    "5": "Commercial Paper",
    "6": "Cash Balances of SCBs with RBI",
}


def main() -> int:
    acquire_lock()
    try:
        return _main_locked()
    finally:
        release_lock()


def _main_locked() -> int:
    c = DBieClient()
    c.warm_up()
    c.mint()
    summary = {}

    for rid, why in WANT.items():
        try:
            t = table_of(c, rid)
            dates = [r[0] for r in t["rows"] if r and r[0]]
            payload = {"tab": t["tab"], "cols": t["cols"], "rows": t["rows"], "total": t["total"]}
            (RAW / f"report_{rid}.json").write_text(json.dumps(payload, ensure_ascii=False))
            complete = len(t["rows"]) == t["total"] and len(t["rows"]) > 0
            summary[rid] = {"why": why, "rows": len(t["rows"]), "cols": len(t["cols"]),
                            "total": t["total"], "complete": complete,
                            "newest": max(dates)[:10] if dates else None,
                            "oldest": min(dates)[:10] if dates else None}
            if not complete and rid not in KNOWN_PARTIAL:
                log.error("[ERROR] [Fetch] report %s is SHORT (%s of %s) and is not a known partial "
                          "- downstream series would be wrong", rid, len(t["rows"]), t["total"])
            log.info("[INFO] [Fetch] %s rows=%s cols=%s %s..%s (%s)", rid, len(t["rows"]), len(t["cols"]),
                     summary[rid]["oldest"], summary[rid]["newest"], why)
            for i, col in enumerate(t["cols"]):
                print(f"      {rid} {i:>2} {col}")
        except Exception:
            log.error("[ERROR] [Fetch] report %s failed:\n%s", rid, traceback.format_exc())
            summary[rid] = {"why": why, "error": traceback.format_exc()[-200:]}

    for name in ("dbie_getPublicationDataImpala", "dbie_fetchReportFOrDashboardGenIndex",
                 "dbie_fetchReportFOrDashboardFoodIndex", "dbie_getEcoHeader"):
        try:
            d = c.call(name, {"body": {}})
            (RAW / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False))
            log.info("[INFO] [Fetch] %s ok", name)
        except Exception:
            log.error("[ERROR] [Fetch] %s failed:\n%s", name, traceback.format_exc())

    (RAW / "survey.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, indent=1, ensure_ascii=False)[:1500])

    # COMPLETENESS GATE: every report the dashboard is allowed to use must have arrived whole.
    # A silent short file is the failure mode that matters - it produces plausible-looking series
    # built on a truncated table, with no error anywhere.
    shorts = {r: v for r, v in summary.items()
              if r not in KNOWN_PARTIAL and not v.get("complete") and "error" not in v}
    errors = {r: v for r, v in summary.items() if "error" in v}
    if errors:
        log.error("[ERROR] [Gate] %s report(s) failed outright: %s", len(errors), list(errors))
    if shorts:
        log.error("[ERROR] [Gate] %s report(s) came back SHORT: %s", len(shorts), list(shorts))
    if errors or shorts:
        log.error("[ERROR] [Gate] raw data is incomplete - do NOT build the dashboard from it")
        return 1
    log.info("[INFO] [Gate] all %s reports complete (partial-by-nature: %s)",
             len(summary), sorted(KNOWN_PARTIAL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
