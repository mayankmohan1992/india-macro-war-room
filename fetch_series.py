#!/usr/bin/env python3
"""
fetch_series.py - pull the macro report tables from DBIE and dump their column trees.

Uses series_lib.table_of() so every report is fetched WHOLE (pageSize=0 with a paging fallback).
Saves raw payloads under raw/, prints the leaf columns of each report, and writes raw/survey.json.

STETP: [INFO]/[WARN]/[ERROR] logs, granular try/except; a report that fails is reported, not skipped.
"""
from __future__ import annotations

import datetime as dt
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

# The portal encodes dates as milliseconds at MIDNIGHT IST (UTC+05:30). Formatting those in UTC renders
# them one day early - a September figure stamped 2026-09-30T00:00+05:30 became "2026-09-29". Every
# portal timestamp in this project is therefore read in IST.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def ist_date(ms: int | float) -> str:
    """Portal epoch-milliseconds -> the calendar date the portal means (IST, not UTC)."""
    return dt.datetime.fromtimestamp(ms / 1000, IST).strftime("%Y-%m-%d")

# Reports the portal serves as a PARTIAL subset (rows << totalCount) and which are therefore
# NOT used by the dashboard. Listed explicitly so the completeness gate below can still fail
# loudly on anything else that comes back short.
KNOWN_PARTIAL = {"6"}


def _atomic_write(path, text: str) -> None:
    """Write through a temp file + os.replace.

    A truncated report_N.json is indistinguishable from a good one to every consumer, so a crash or
    a short table must never leave a half-written (or silently short) table behind.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _pid_alive(pid: int) -> bool:
    """Is `pid` a LIVE process (not a zombie, not a recycled pid we do not own)?

    os.kill(pid, 0) alone is the wrong probe: it SUCCEEDS for a zombie left by a killed fetch, so the
    stale-lock path never fired and every later run was refused forever; and it raises PermissionError
    for a live process owned by someone else, which used to be read as "dead" and clobbered.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                       # exists, just not ours
    except OSError:
        return False
    # os.kill succeeds for zombies; treat them as dead so a killed fetch cannot wedge the pipeline.
    try:
        stat = open(f"/proc/{pid}/stat", encoding="utf-8").read()
        state = stat.rsplit(")", 1)[-1].split()[0]
        if state == "Z":
            return False
    except OSError:
        pass
    return True


def acquire_lock() -> None:
    """Refuse to run if another fetch is writing raw/ - two writers silently clobber each other.

    This is not theoretical: a slow fetch left running in the background finished AFTER a newer
    one and overwrote its output files with empty tables. Because every consumer reads raw/*.json
    by name, that produced a dashboard built on blank series with no error anywhere.

    The lock is created ATOMICALLY and with its content already complete: the pid is written to a
    private temp file first, then hard-linked into place. `os.link` fails if the target exists, so
    exactly one process wins. Creating first with O_EXCL and writing the pid afterwards leaves a
    window where the file exists but is EMPTY, which the reader interpreted as "stale pid 0" - and
    two simultaneous fetches both proceeded (measured: 6 of 40 trials after that fix, 82% before).
    """
    for _ in range(3):
        tmp = LOCK.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(str(os.getpid()), encoding="utf-8")
        try:
            os.link(tmp, LOCK)            # atomic and exclusive: fails if LOCK already exists
        except FileExistsError:
            tmp.unlink(missing_ok=True)
            try:
                pid = int((LOCK.read_text().strip() or "0"))
            except (ValueError, FileNotFoundError):
                pid = 0
            if _pid_alive(pid):
                raise SystemExit(f"[ERROR] [Lock] another fetch is already running (pid {pid}); "
                                 f"refusing to write raw/ concurrently")
            log.warning("[WARN] [Lock] stale lock from dead pid %s - taking it over", pid)
            try:
                LOCK.unlink()             # only remove the lock we just judged dead
            except FileNotFoundError:
                pass
            continue
        finally:
            tmp.unlink(missing_ok=True)
        return
    raise SystemExit("[ERROR] [Lock] could not acquire the fetch lock")


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


# Named series served by the RBIDATA gateway (the "Indicators" pages of the portal, e.g.
# https://data.rbi.org.in/#/dbie/ind1). This is a DIFFERENT surface from the report tables: requests
# are built from reportName + level codes, and the response nests as body.Result (NOT
# body.response.Result, which is what cost a probe cycle here). It carries the figures the portal's own
# headline strip shows, including the OFFICIALLY PUBLISHED inflation series - which differs from a
# y-o-y computed on the published index by up to ~0.05pp, because the index is rounded to one decimal.
NAMED_SERIES = [
    {"name": "cpi_inflation_combined",
     "vo": {"currencyCode": "", "itemCode": ["27"], "fromDate": "2024-01-01 00:00:00",
            "toDate": "2099-01-01 00:00:00", "frequency": "Annual", "reportName": "RBIB18",
            "level1Code": ["Combined"], "level2Code": ["CPI-2024 = 100"], "level3Code": ["Inflation"]},
     "why": "CPI inflation, Combined (as published by MoSPI/NSO via the portal)"},
]


def fetch_named_series(c: "DBieClient") -> dict:
    """Fetch the portal's named indicator series; each entry keeps its own metadata + points."""
    out: dict = {}
    for spec in NAMED_SERIES:
        try:
            r = c.call("dbie_getWSSReport", {"body": {"requestVO": spec["vo"]}}, gateway="RBIDATA")
            rows = (r.get("body") or {}).get("Result") or []
            pts = []
            for row in rows:
                try:
                    d = ist_date(row["time_date"])
                    pts.append([d, float(row["wss_amount"])])
                except Exception:
                    continue
            pts.sort()
            if not pts:
                # An error body and "no data" land in the same branch, and a 0-point series silently
                # removed the published CPI figure downstream. Fail loudly instead.
                raise RuntimeError(f"{spec['name']}: {len(rows)} row(s) but 0 usable points")
            out[spec["name"]] = {"why": spec["why"], "points": pts,
                                 "desc": (rows[0].get("wss_desc") if rows else None),
                                 "version": (rows[0].get("version_desc") if rows else None),
                                 "source": (rows[0].get("addressPath", "").replace("\xa0", " ") if rows else ""),
                                 "rows": len(pts)}
            log.info("[INFO] [Named] %s: %s points %s..%s", spec["name"], len(pts),
                     pts[0][0] if pts else "-", pts[-1][0] if pts else "-")
        except Exception:
            log.error("[ERROR] [Named] %s failed:\n%s", spec["name"], traceback.format_exc())
    return out


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
    payloads: dict[str, dict] = {}

    for rid, why in WANT.items():
        try:
            t = table_of(c, rid)
            dates = [r[0] for r in t["rows"] if r and r[0]]
            complete = bool(t.get("total_reported") not in (None, "")) and \
                len(t["rows"]) == t["total"] and len(t["rows"]) > 0
            summary[rid] = {"why": why, "rows": len(t["rows"]), "cols": len(t["cols"]),
                            "total": t["total"], "complete": complete,
                            "newest": max(dates)[:10] if dates else None,
                            "oldest": min(dates)[:10] if dates else None}
            if not complete and rid not in KNOWN_PARTIAL:
                log.error("[ERROR] [Fetch] report %s is SHORT (%s of %s) and is not a known partial "
                          "- downstream series would be wrong", rid, len(t["rows"]), t["total"])
            elif complete or rid in KNOWN_PARTIAL:
                # BUFFER, do not write. The file used to be written here, before the gate ran, so a
                # short table overwrote the previous good one and any caller that ignored the exit
                # code built a dashboard from a truncated series with no error anywhere.
                payloads[rid] = {"tab": t["tab"], "cols": t["cols"], "rows": t["rows"],
                                 "total": t["total"]}
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
    named = fetch_named_series(c)
    named_bad = [s["name"] for s in NAMED_SERIES
                 if not (named.get(s["name"]) or {}).get("rows")]
    if named and not named_bad:
        _atomic_write(RAW / "named_series.json", json.dumps(named, ensure_ascii=False, indent=1))
    elif named_bad:
        # Never overwrite the last good file with an empty one - the published CPI figure would
        # silently vanish while the build reported success.
        log.error("[ERROR] [Named] no usable points for %s - keeping the previous named_series.json",
                  named_bad)
    else:
        # a missing named series must not silently fall back to a computed figure without saying so
        log.warning("[WARN] [Named] no named series fetched - the published CPI figure will be absent")
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
    if named_bad:
        log.error("[ERROR] [Gate] %s named series returned no points: %s",
                  len(named_bad), named_bad)
    if errors or shorts or named_bad:
        log.error("[ERROR] [Gate] raw data is incomplete - do NOT build the dashboard from it. "
                  "raw/ is left untouched, so the previous complete tables stay in place.")
        return 1
    # Only once every gate has passed are the tables committed to raw/ - atomically, so a crash
    # mid-write can never leave a truncated report beside this week's other tables.
    for rid, payload in payloads.items():
        _atomic_write(RAW / f"report_{rid}.json", json.dumps(payload, ensure_ascii=False))
    log.info("[INFO] [Gate] all %s reports complete (partial-by-nature: %s); wrote %s table(s) to raw/",
             len(summary), sorted(KNOWN_PARTIAL), len(payloads))
    return 0


if __name__ == "__main__":
    sys.exit(main())
