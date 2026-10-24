#!/usr/bin/env python3
"""
series_lib.py - shared helpers for pulling a whole DBIE report table.

WHY A LIBRARY: the "pageSize=0 means whole table" trick only works for SOME reports
(11, 13, 9, 2, 8, 39, 4, 5 answer fully) while others (7, 10, 12) return an EMPTY table for it.
So: try pageSize=0, and if that yields nothing, page with pageSize=100 until `totalCount` is met.

Traps encoded here (all measured live):
  * tabName comes back with NBSP (`Report\xa01`) and must be normalised - dbie_client.report_page does it.
  * `versionRows` is a PARTITION of the table with arbitrary keys -> concatenate every block.
  * an empty page mid-stream (while totalCount says more exists) is an ERROR, not an end.
STETP: [INFO]/[WARN]/[ERROR] logging on stderr, granular try/except, never return a silent short table.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

log = logging.getLogger("series")


def flatten_versions(version_rows: Any) -> list[list[Any]]:
    """Concatenate every versionRows block (keys vary per report: 'Final', '2025-26', ...)."""
    if not isinstance(version_rows, dict):
        return []
    return [row for block in version_rows.values() if isinstance(block, list) for row in block]


def body_rows(body: Any) -> list[list[Any]]:
    """Rows out of a REPORTS_getWSSReport response body, whichever shape it uses.

    TWO SHAPES EXIST (both seen live):
      * `versionRows` = dict of partitions  -> report 11, 13, 9, 2, 8, 39, 4, 5, 12
      * `rows`        = flat list of rows   -> report 7 (Reserve Money), 6 (Cash Balances)
    Reading only `versionRows` silently yields an empty table for the second group.
    """
    if not isinstance(body, dict):
        return []
    rows = flatten_versions(body.get("versionRows"))
    if rows:
        return rows
    flat = body.get("rows")
    if isinstance(flat, list):
        # The flat list is a list of row-arrays; guard against a list of dicts just in case.
        return [r for r in flat if isinstance(r, (list, tuple))]
    return []


def leaf_columns(headers: Any) -> list[str]:
    """Depth-first leaf labels of a report's `headers` tree = the value columns of each row."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for it in node:
                walk(it)
        elif isinstance(node, dict):
            kids = node.get("children") or []
            if kids:
                walk(kids)
            else:
                lab = str(node.get("label") or node.get("name") or "").strip()
                code = str(node.get("itemCode") or "").strip()
                out.append(f"{lab} [{code}]" if code else lab)

    walk(headers)
    return out


def table_of(client, report_id: str) -> dict:
    """Return {"rows", "cols", "total", "tab"} for one reportId's first tab, fetched WHOLE.

    Short responses are paged up to `totalCount` - a partial table must never look final
    (report 6 reports totalCount=7379 but hands back 524 rows for pageSize=0).
    """
    try:
        tabs = client.report_tabs(report_id)
        tabnames = [t.get("tabName") for t in ((tabs.get("body") or {}).get("response") or [])
                    if t.get("tabName")]
        if not tabnames:
            raise RuntimeError(f"report {report_id} exposes no tabs")
        tab = tabnames[0]

        first = client.report_page(report_id, tab, page_size=0, page_number=0)   # whole-table attempt
        body = (first.get("body") or {}).get("response") or {}
        rows = body_rows(body)
        # If the portal omits totalCount, do NOT fall back to len(rows): that makes the completeness
        # gate compare the table with itself and call any truncation "complete". Record what the
        # portal actually reported and let the caller judge.
        raw_total = body.get("totalCount")
        total = int(raw_total) if raw_total not in (None, "") else len(rows)
        cols = leaf_columns(body.get("headers"))

        if not rows or len(rows) < total:                                       # page the remainder
            log.info("[INFO] [Table] report %s: pageSize=0 gave %s of %s -> paging",
                     report_id, len(rows), total)
            rows = []
            page, prev_short = 1, False
            while len(rows) < total:
                nxt = client.report_page(report_id, tab, page_size=100, page_number=page)
                body_n = (nxt.get("body") or {}).get("response") or {}
                got = body_rows(body_n)
                if not got:
                    if prev_short or page > 1:
                        break
                    raise RuntimeError(f"report {report_id} page {page} empty at {len(rows)}/{total}")
                rows.extend(got)
                cols = leaf_columns(body_n.get("headers")) or cols
                total = int(body_n.get("totalCount") or total)
                prev_short = len(got) < 100
                page += 1
                if page > 600:
                    raise RuntimeError(f"report {report_id}: page guard tripped")

        if len(rows) != total:
            log.warning("[WARN] [Table] report %s: got %s rows but totalCount=%s", report_id, len(rows), total)
        log.info("[INFO] [Table] report %s rows=%s cols=%s", report_id, len(rows), len(cols))
        return {"tab": tab, "rows": rows, "cols": cols, "total": total,
                "total_reported": raw_total}
    except Exception:
        log.error("[ERROR] [Table] report %s failed:\n%s", report_id, traceback.format_exc())
        raise


def to_series(rows: list[list[Any]], idx: int) -> list[tuple[str, float]]:
    """Extract column `idx` as [(YYYY-MM-DD, value)] pairs, newest-first rows preserved."""
    out: list[tuple[str, float]] = []
    for r in rows:
        try:
            if not r[0]:
                continue                                        # a null date is skipped, not stringified
            d = str(r[0])[:10]
            v = float(r[idx])
        except (TypeError, ValueError):
            continue                                            # nulls/non-numerics are skipped by design
        # IndexError deliberately NOT caught: a vanished column is a bug in the caller's column map,
        # and swallowing it returned a silently empty series.
        out.append((d, v))
    return out
