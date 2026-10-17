#!/usr/bin/env python3
"""
build_dashboard.py - turn the raw DBIE report tables into a self-contained war-room dashboard.

PHILOSOPHY (matches the brief): every bit of number-crunching happens HERE, at build time -
YoY/growth maths, spreads, moving averages, and the good/watch/bad verdict per indicator.
The HTML that comes out only draws the trends and the colours; it does no analysis.

WHAT IT DOES
  1. reads raw/*.json (fetched by fetch_series.py)
  2. maps explicit indicator COLUMN CODES -> normalised series (raises if a code is missing,
     so a silent DBIE column rename can never quietly produce an empty dashboard)
  3. computes derived series (YoY %, ratios, spreads, 30-day averages)
  4. scores each tile with an explicit, printed rule (thresholds are conventional market/RBI
     heuristics - the rule text is embedded in the tile so the user can always see WHY)
  5. renders dashboard/index.html from template.html with the data inlined (works offline, file://)

STETP: [INFO]/[WARN]/[ERROR] logs, granular try/except per report, non-zero exit if a REQUIRED
series is missing or too short to chart.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import sys
import traceback
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
log = logging.getLogger("build")

# Portal timestamps are midnight IST; reading them as UTC dates them one day early (2026-09-30 IST
# midnight is 2026-09-29T18:30Z). Every portal timestamp here is read in IST.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "dashboard"
OUT.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def load(report_id: str) -> dict:
    """Read one saved report payload, failing loudly if it is absent."""
    p = RAW / f"report_{report_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"raw/report_{report_id}.json missing - run fetch_series.py first")
    return json.loads(p.read_text())


def data_columns(rep: dict) -> list[str]:
    """Column list ALIGNED with the row arrays.

    TRAP (measured on report 9): the `headers` tree declares 32 leaves but each row carries 31
    values - the non-numeric `Version` column is present in the header and absent from the data.
    Mapping by raw leaf index therefore shifts every indicator one column to the left and reads
    the WRONG series with no error. Drop non-data columns when the row is exactly one shorter.
    """
    cols, rows = rep["cols"], rep["rows"]
    if not rows:
        return cols
    n = len(rows[0])
    if n == len(cols):
        return cols
    pruned = [c for c in cols if not c.strip().lower().startswith("version")]
    if len(pruned) == n:
        log.info("[INFO] [Columns] report has a non-data 'Version' column; pruned to align rows")
        return pruned
    raise ValueError(f"cannot align {len(cols)} columns to {n} row values (period/label columns?)")


def col_index(cols: list[str], code: str) -> int:
    """Index of a column identified by itemCode (the [XXX] suffix), e.g. 'CPI2012_33'."""
    tag = f"[{code}]"
    for i, c in enumerate(cols):
        if c.endswith(tag):
            return i
    raise KeyError(f"column code {code!r} not found; available: {cols}")


def series(rep: dict, code: str, scale: float = 1.0, date_idx: int = 0) -> list[list[Any]]:
    """[(ISO date, float)] ascending for one column code; blanks are dropped predictably.

    `date_idx` exists because a report can carry a leading label column that is empty
    (report 6: col0 'Fortnight End Date' is null, the real date is col1 'Date [TIME_DATE]').
    """
    cols = data_columns(rep)
    idx = col_index(cols, code)
    pts: list[list[Any]] = []
    for row in rep["rows"]:
        try:
            d, v = str(row[date_idx])[:10], float(row[idx])
        except (TypeError, ValueError, IndexError):
            continue
        pts.append([d, v * scale])
    pts.sort(key=lambda x: x[0])
    if not pts:
        raise ValueError(f"column {code!r} produced no numeric points")
    return pts


def sum_columns(rep: dict, codes: list[str], date_idx: int = 0) -> list[list[Any]]:
    """Row-wise sum of several columns (skipping blanks) - e.g. total T-bill outstanding."""
    cols = data_columns(rep)
    idxs = [col_index(cols, c) for c in codes]
    out: list[list[Any]] = []
    for row in rep["rows"]:
        try:
            d = str(row[date_idx])[:10]
            vals = [float(row[i]) for i in idxs if row[i] not in (None, "")]
        except (TypeError, ValueError, IndexError):
            continue
        if vals:
            out.append([d, round(sum(vals), 2)])
    out.sort(key=lambda x: x[0])
    if not out:
        raise ValueError(f"no usable rows for codes {codes}")
    return out


def as_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def value_near(pts: list[list[Any]], months_back: int, tolerance_days: int = 25) -> float | None:
    """Value closest to `months_back` months before the latest point, within a tolerance window."""
    if not pts:
        return None
    last = as_date(pts[-1][0])
    target = last - dt.timedelta(days=int(30.4 * months_back))
    best, best_gap = None, None
    for d, v in pts:
        gap = abs((as_date(d) - target).days)
        if gap <= tolerance_days and (best_gap is None or gap < best_gap):
            best, best_gap = v, gap
    return best


def yoy(pts: list[list[Any]], months_back: int = 12, tolerance_days: int = 25) -> list[list[Any]]:
    """Year-on-year % growth series built from a level series."""
    out: list[list[Any]] = []
    for i, (d, v) in enumerate(pts):
        base = value_near(pts[:i + 1], months_back, tolerance_days)
        if base in (None, 0):
            continue
        out.append([d, round((v / base - 1) * 100, 2)])
    return out


def delta(pts: list[list[Any]], n: int = 1) -> float | None:
    """Change vs the value n observations back."""
    if len(pts) <= n:
        return None
    return round(pts[-1][1] - pts[-1 - n][1], 3)


def stat(pts: list[list[Any]], n: int) -> float | None:
    """Mean of the last n observations."""
    vals = [v for _d, v in pts[-n:]]
    return round(sum(vals) / len(vals), 3) if vals else None


def last(pts: list[list[Any]]) -> tuple[str, float]:
    return pts[-1][0], pts[-1][1]


def trim(pts: list[list[Any]], n: int) -> list[list[Any]]:
    """Last n points - what the charts actually draw."""
    return pts[-n:]


def spark(pts: list[list[Any]], n: int = 36) -> list[float]:
    return [round(v, 3) for _d, v in pts[-n:]]


def freq_of(points: list[list[Any]]) -> str:
    """Publication frequency from the median gap between observations (daily .. quarterly).

    WHY: tables publish on different calendars (daily operations, weekly statements, fortnightly SCB
    returns, monthly prices). A single "latest data" date therefore reads as stale when it is simply
    the newest observation of whatever table is fastest, so the dashboard and the API report the
    newest date per class as well as the overall maximum.
    """
    try:
        ds = sorted(dt.date.fromisoformat(p[0]) for p in points)
        if len(ds) < 3:
            return "unknown"
        gaps = sorted((ds[i + 1] - ds[i]).days for i in range(len(ds) - 1))
        med = gaps[len(gaps) // 2]
        return ("daily" if med <= 3 else "weekly" if med <= 9 else "fortnightly" if med <= 20
                else "monthly" if med <= 45 else "quarterly" if med <= 120 else "irregular")
    except Exception:
        log.warning("[WARN] [Freq] could not derive a frequency:\n%s", traceback.format_exc())
        return "unknown"


def step_info(pts: list[list[Any]]) -> dict | None:
    """For a policy-setting STEP series: when the value in force took effect, from what, how big.

    WHY THIS EXISTS: CRR/SLR/the repo rate are not readings, they are settings. Dating them by the
    newest row of the weekly table that repeats them ("latest reading 3.00% for 2026-10-02") is
    misleading - nothing has happened to CRR since 2025-12-05. The UI shows "in force since <date>"
    instead, which is what the number actually means.
    """
    if len(pts) < 2:
        return None
    last_v = pts[-1][1]
    i = next((j for j in range(len(pts) - 1, 0, -1) if pts[j][1] != pts[j - 1][1]), None)
    if i is None:
        return {"effective_from": pts[0][0], "prev": None, "bp": None, "rows": len(pts),
                "value": last_v, "first": pts[0][0]}
    prev = pts[i - 1][1]
    return {"effective_from": pts[i][0], "prev": prev, "bp": round((last_v - prev) * 100, 2),
            "rows": len(pts) - i, "value": last_v, "first": pts[0][0]}


def band_status(v: float | None, bands: list[tuple], default: str = "watch") -> tuple[str, str]:
    """bands = [(lo, hi, status, text)] evaluated in order; first match wins."""
    if v is None:
        return default, "no data"
    for lo, hi, st, txt in bands:
        if lo <= v < hi:
            return st, txt
    return default, "outside defined bands"


# --------------------------------------------------------------------------- #
# indicator build
# --------------------------------------------------------------------------- #
def build() -> dict:
    """Assemble every series + tile. Raises on any required failure (no silent gaps)."""
    r11 = load("11")      # CPI / WPI monthly
    r13 = load("13")      # Money stock M3
    r7 = load("7")        # Reserve money
    r9 = load("9")        # SCB business (credit/deposits)
    r10 = load("10")      # Ratios and rates (policy + market rates)
    r8 = load("8")        # Liquidity operations (daily LAF)
    r2 = load("2")        # T-bills outstanding
    r4 = load("4")        # Certificate of deposit
    r5 = load("5")        # Commercial paper
    r39 = load("39")      # RBI liabilities & assets
    r12 = load("12")      # Average daily turnover, money markets

    kr = json.loads((RAW / "key_rates.json").read_text())["body"]["result"]
    named = {}
    named_path = RAW / "named_series.json"
    if named_path.exists():
        try:
            named = json.loads(named_path.read_text())
        except Exception:
            log.error("[ERROR] [Named] raw/named_series.json is unreadable:\n%s", traceback.format_exc())
    else:
        log.warning("[WARN] [Named] no raw/named_series.json - the published CPI figure will be absent")

    S: dict[str, dict] = {}

    # ---- prices ------------------------------------------------------------
    # BASE CHANGE (measured): the 2012=100 CPI column ends 2025-12 and the 2012=100 WPI column
    # ends 2026-04; the current-published series are CPI 2024=100 and WPI 2023=100. Using the old
    # columns silently published a STALE headline (CPI 1.33% dated Dec-2025 instead of ~4.8% for
    # Aug-2026). Both bases agree to ~0.15pp where they overlap, so the new-base columns are used
    # throughout (they carry back-cast history to 2013 / 2023).
    cpi = series(r11, "CPI2024_33")
    wpi = series(r11, "WPI2023_1000000000")
    cpi_iw = series(r11, "CPI2016_1")
    S["cpi_level"] = {"label": "CPI (Combined, 2024=100)", "unit": "index", "source": "RBI r11",
                      "points": trim(cpi, 240)}
    S["cpi_yoy"] = {"label": "CPI inflation, y-o-y", "unit": "%", "source": "RBI r11 (CPI 2024=100)",
                    "points": trim(yoy(cpi), 240)}
    S["wpi_yoy"] = {"label": "WPI inflation, y-o-y", "unit": "%", "source": "RBI r11 (WPI 2023=100)",
                    "points": trim(yoy(wpi), 240)}
    S["cpi_iw_yoy"] = {"label": "CPI-IW inflation, y-o-y", "unit": "%", "source": "RBI r11",
                       "points": trim(yoy(cpi_iw), 240)}
    # The OFFICIALLY PUBLISHED inflation series (portal indicator route, reportName RBIB18). A y-o-y
    # computed from the published index differs from it by up to ~0.05pp because the index is rounded to
    # one decimal - so the headline shows the published figure and the computed series is kept as an
    # auditable cross-check (see cross_checks in the payload and the assertion in verify_dashboard.py).
    cpi_off = (named.get("cpi_inflation_combined") or {}).get("points") or []
    if cpi_off:
        S["cpi_yoy_official"] = {"label": "CPI inflation, y-o-y (as published)", "unit": "%",
                                 "source": "RBI DBIE indicator series (RBIB18)",
                                 "points": trim([list(p) for p in cpi_off], 60)}
        log.info("[INFO] [Named] published CPI inflation series: %s points, newest %s = %s%%",
                 len(cpi_off), cpi_off[-1][0], cpi_off[-1][1])

    # ---- money -------------------------------------------------------------
    m3 = series(r13, "MSO38")
    S["m3_level"] = {"label": "M3 (broad money)", "unit": "₹ crore", "source": "RBI r13",
                     "points": trim(m3, 240)}
    S["m3_yoy"] = {"label": "M3 growth, y-o-y", "unit": "%", "source": "RBI r13", "points": trim(yoy(m3), 240)}
    fxa = series(r13, "SOMS16")
    S["fxa_yoy"] = {"label": "Net FX assets of the banking sector, y-o-y", "unit": "%",
                    "source": "RBI r13", "points": trim(yoy(fxa, tolerance_days=35), 200)}

    rm = series(r7, "RMC5")
    S["rm_level"] = {"label": "Reserve money", "unit": "₹ crore", "source": "RBI r7",
                     "points": trim(rm, 240)}
    S["rm_yoy"] = {"label": "Reserve money growth, y-o-y", "unit": "%", "source": "RBI r7",
                   "points": trim(yoy(rm, tolerance_days=30), 200)}
    cic = series(r7, "RMC1")
    S["cic_yoy"] = {"label": "Currency in circulation, y-o-y", "unit": "%", "source": "RBI r7",
                    "points": trim(yoy(cic, tolerance_days=30), 200)}

    # ---- banking -----------------------------------------------------------
    credit = series(r9, "0250")
    depos = series(r9, "0060")
    S["credit_level"] = {"label": "Bank credit outstanding", "unit": "₹ crore", "source": "RBI r9",
                         "points": trim(credit, 200)}
    S["credit_yoy"] = {"label": "Bank credit growth, y-o-y", "unit": "%", "source": "RBI r9",
                       "points": trim(yoy(credit, tolerance_days=30), 200)}
    S["deposit_yoy"] = {"label": "Aggregate deposit growth, y-o-y", "unit": "%", "source": "RBI r9",
                        "points": trim(yoy(depos, tolerance_days=30), 200)}
    cdr = []
    dep_by_date = {d: v for d, v in depos}
    for d, v in credit:
        dv = dep_by_date.get(d)
        if dv:
            cdr.append([d, round(v / dv * 100, 2)])
    S["cd_ratio"] = {"label": "Credit-to-deposit ratio (SCBs)", "unit": "%", "source": "RBI r9",
                     "points": trim(sorted(cdr), 200)}
    # NOTE: report 6 (SCB cash balances with RBI) is deliberately NOT used. The endpoint returns
    # only 524 of its claimed 7,379 rows, in non-chronological order, and paging past ~5 pages
    # yields empty pages - a partial, unsorted subset is not a usable series, and a tile built on
    # it would be quietly wrong. Liquidity is covered by the daily LAF table (r8), which is complete.

    # ---- rates & liquidity -------------------------------------------------
    repo = series(r10, "27")
    call = series(r10, "34")
    S["repo_wss"] = {"label": "RBI policy repo rate (weekly WSS)", "unit": "%",
                     "source": "RBI r10 (weekly WSS)", "points": trim(repo, 260)}
    S["repo"] = {"label": "RBI policy repo rate", "unit": "%", "source": "RBI r10 (weekly WSS)",
                 "points": trim(repo, 260)}
    S["call_rate"] = {"label": "Call money rate (weighted avg)", "unit": "%", "source": "RBI r10",
                      "points": trim(call, 260)}
    S["gsec10y"] = {"label": "10-year G-sec par yield", "unit": "%", "source": "RBI r10",
                    "points": trim(series(r10, "38"), 260)}

    laf = series(r8, "14")
    S["laf_net"] = {"label": "RBI liquidity ops - net injection(+)/absorption(-)", "unit": "₹ crore",
                    "source": "RBI r8", "points": trim(laf, 400)}
    laf30 = [[d, stat([[dd, vv] for dd, vv in laf if dd <= d] or laf, 22)] for d, _v in laf[-200:]]  # 22 working days ≈ 1 month
    S["laf_net_30d"] = {"label": "Net liquidity (1-month average)", "unit": "₹ crore", "source": "RBI r8",
                        "points": trim([p for p in laf30 if p[1] is not None], 200)}

    tb = sum_columns(r2, ["3_6", "4_6", "5_6", "6_6"])          # 91+182+364-day + CMB totals
    S["tbill"] = {"label": "Treasury bills outstanding (91+182+364+CMB)", "unit": "₹ crore",
                  "source": "RBI r2", "points": trim(tb, 260)}

    cd = series(r4, "TOT_AMT_OUT")
    cp = series(r5, "N_AMT_OUTSTANDING")
    S["cd_out"] = {"label": "Certificates of deposit outstanding", "unit": "₹ crore", "source": "RBI r4",
                   "points": trim(cd, 200)}
    S["cp_out"] = {"label": "Commercial paper outstanding", "unit": "₹ crore", "source": "RBI r5",
                   "points": trim(cp, 200)}
    S["notes_yoy"] = {"label": "Notes in circulation, y-o-y", "unit": "%", "source": "RBI r39",
                      "points": trim(yoy(series(r39, "101")), 240)}
    fca = series(r39, "140")
    S["fca_level"] = {"label": "RBI foreign currency assets (balance sheet)", "unit": "₹ crore",
                      "source": "RBI r39", "points": trim(fca, 240)}
    S["fca_yoy"] = {"label": "RBI foreign currency assets, y-o-y", "unit": "%", "source": "RBI r39",
                    "points": trim(yoy(fca, tolerance_days=20), 240)}
    S["gold_level"] = {"label": "RBI gold holdings (balance sheet)", "unit": "₹ crore", "source": "RBI r39",
                       "points": trim(series(r39, "104"), 200)}
    # --- short-end yields + FX from the same weekly 'Ratios and Rates' table -------------------
    # NOTE: this table publishes bank retail rates (MCLR, term deposit, savings, base rate) as
    # RANGE STRINGS like "8.40/10.00", so those columns yield no numeric series and are skipped
    # rather than silently mis-parsed. The yield and FX columns are plain numbers.
    for col, sid, label in (("35", "yld91", "91-day Treasury bill yield (primary)"),
                            ("36", "yld182", "182-day Treasury bill yield (primary)"),
                            ("37", "yld364", "364-day Treasury bill yield (primary)"),
                            ("40", "inr_usd", "INR-US$ spot rate"),
                            ("41", "inr_eur", "INR-Euro spot rate"),
                            ("42", "fwd1m", "US$ 1-month forward premia (annualised)"),
                            ("43", "fwd3m", "US$ 3-month forward premia (annualised)"),
                            ("44", "fwd6m", "US$ 6-month forward premia (annualised)")):
        S[sid] = {"label": label, "unit": "%" if sid.startswith(("yld", "fwd")) else "₹",
                  "source": "RBI r10 (weekly WSS)", "points": trim(series(r10, col), 260)}
    # The weekly table's INR-US$ row lags by up to a week; the portal's key-rates set carries the daily
    # FBIL rate. Append it to the same series (the same pattern used for the policy rate announcement)
    # so the tile shows the freshest available rate while the chart keeps the weekly history.
    kr_usd = next((k for k in kr if k["name"].replace("\xa0", " ").strip() == "Exchange Rate"), None)
    if kr_usd and kr_usd.get("rate"):
        d_usd = dt.datetime.fromtimestamp(kr_usd["timeDate"] / 1000, IST).strftime("%Y-%m-%d")
        pts = S["inr_usd"]["points"]
        if not pts or d_usd > pts[-1][0]:
            S["inr_usd"] = {"label": "USD/INR (weekly table + latest daily rate)", "unit": "₹",
                            "source": "RBI r10 (weekly) + DBIE key rates (daily)",
                            "points": pts + [[d_usd, float(kr_usd["rate"])]]}
            log.info("[INFO] [FX] appended the daily key-rates exchange rate %.4f dated %s to the weekly "
                     "INR-US$ series", float(kr_usd["rate"]), d_usd)

    # --- standing facilities (the liquidity instruments themselves) ----------------------------
    S["sdf_level"] = {"label": "Standing Deposit Facility balances (absorption)", "unit": "₹ crore",
                      "source": "RBI r8 (daily)", "points": trim(series(r8, "19"), 400)}
    S["msf_level"] = {"label": "Marginal Standing Facility (injection)", "unit": "₹ crore",
                      "source": "RBI r8 (daily)", "points": trim(series(r8, "5"), 400)}

    # --- SCB balance-sheet mix -----------------------------------------------------------------
    S["invest_yoy"] = {"label": "SCB investments (govt & approved securities) growth, y-o-y",
                       "unit": "%", "source": "RBI r9", "points": trim(yoy(series(r9, "0220"), tolerance_days=30), 200)}
    S["nonfood_yoy"] = {"label": "Non-food credit growth, y-o-y", "unit": "%", "source": "RBI r9",
                        "points": trim(yoy(series(r9, "NONFC"), tolerance_days=30), 200)}
    S["food_yoy"] = {"label": "Food credit growth, y-o-y", "unit": "%", "source": "RBI r9",
                     "points": trim(yoy(series(r9, "255"), tolerance_days=30), 200)}

    # --- T-bill outstanding by tenor (91/182/364-day + CMB) ------------------------------------
    for code, sid, label in (("3_6", "tb91", "91-day T-bills outstanding"),
                             ("4_6", "tb182", "182-day T-bills outstanding"),
                             ("5_6", "tb364", "364-day T-bills outstanding"),
                             ("6_6", "tbcmb", "Cash Management Bills outstanding")):
        # TRAP: this table returns rows NEWEST FIRST, so a hand-built series must be sorted or the
        # chart draws the series backwards (dates zig-zag on the axis).
        ci = col_index(data_columns(r2), code)
        pts = sorted([[str(r[0])[:10], float(r[ci])] for r in r2["rows"] if isinstance(r[ci], (int, float))])
        S[sid] = {"label": label, "unit": "₹ crore", "source": "RBI r2", "points": trim(pts, 260)}

    # --- RBI reserve assets, in levels ---------------------------------------------------------
    S["gold_growth"] = {"label": "RBI gold holdings, y-o-y", "unit": "%", "source": "RBI r39",
                        "points": trim(yoy(series(r39, "104"), tolerance_days=20), 240)}

    # --- CD / CP issuance rate range (min & max) ------------------------------------------------
    S["cd_rate"] = {"label": "Certificate of deposit issuance rate (max)", "unit": "%", "source": "RBI r4",
                    "points": trim(series(r4, "MAX_ROI"), 200)}
    S["cp_rate"] = {"label": "Commercial paper issuance rate (max)", "unit": "%", "source": "RBI r5",
                    "points": trim(series(r5, "N_MAX"), 200)}
    # --- price components: what is actually DRIVING the headline ---------------------------------
    # A single headline CPI/WPI number hides the story: the war-room question is always "which
    # component moved". These are the three WPI Major Groups and the CPI rural/urban split, taken
    # from the SAME table (r11) and the SAME base-year columns as the headline, so the parts always
    # add up to the whole.
    for c, sid, lab in (("WPI2023_1100000000", "wpi_primary", "WPI primary articles"),
                        ("WPI2023_1200000000", "wpi_fuel",    "WPI fuel and power"),
                        ("WPI2023_1300000000", "wpi_manu",    "WPI manufactured products"),
                        ("CPI2024_31",          "cpi_rural",   "CPI rural"),
                        ("CPI2024_32",          "cpi_urban",   "CPI urban")):
        S[sid + "_yoy"] = {"label": f"{lab}, y-o-y", "unit": "%", "source": "RBI r11",
                           "points": trim(yoy(series(r11, c)), 240)}
    S["wpi_components"] = S["wpi_fuel_yoy"]          # alias used by the chart registry

    # --- M1 (narrow money) = currency with the public + demand deposits + 'other' deposits with RBI
    # Same table and same definition as M3 (r13), so M1 and M3 share one compilation basis.
    m1 = sum_columns(r13, ["MSO30", "MSO31", "MSO32"])
    S["m1_level"] = {"label": "M1 (narrow money)", "unit": "₹ crore", "source": "RBI r13",
                     "points": trim(m1, 240)}
    S["m1_yoy"] = {"label": "M1 growth, y-o-y", "unit": "%", "source": "RBI r13",
                   "points": trim(yoy(m1, tolerance_days=35), 220)}

    # --- money multiplier = M3 / reserve money ---------------------------------------------------
    # DERIVED here, not published by RBI (RBI publishes both components, not their ratio). The two
    # tables are separate weekly series, so pair each M3 Friday with the nearest reserve-money
    # Friday within a week - never index-aligned, which would compare different weeks.
    mult = []
    rm_by_date = {d: v for d, v in rm}
    for d, v in m3:
        cand = [abs((dt.date.fromisoformat(dd) - dt.date.fromisoformat(d)).days) for dd in rm_by_date]
        if not cand or min(cand) > 7:
            continue
        dd = list(rm_by_date)[cand.index(min(cand))]
        if rm_by_date[dd]:
            mult.append([d, round(v / rm_by_date[dd], 2)])
    S["money_mult"] = {"label": "Money multiplier (M3 ÷ reserve money)", "unit": "x", "source": "derived (r13 ÷ r7)",
                       "points": trim(sorted(mult), 220)}

    # --- RBI balance sheet: how the central bank funds the government -----------------------------
    S["bankers_dep_yoy"] = {"label": "Bankers' deposits with RBI, y-o-y", "unit": "%", "source": "RBI r39",
                            "points": trim(yoy(series(r39, "112"), tolerance_days=20), 240)}
    S["rbi_govt_level"] = {"label": "RBI loans & advances to the Central Government", "unit": "₹ crore",
                           "source": "RBI r39", "points": trim(series(r39, "122"), 240)}
    S["rupeesec_yoy"] = {"label": "RBI rupee securities (incl. T-bills), y-o-y", "unit": "%",
                         "source": "RBI r39", "points": trim(yoy(series(r39, "135"), tolerance_days=20), 240)}

    # --- policy instruments in force (step series; a change here IS the policy news) -------------
    S["crr"] = {"label": "Cash Reserve Ratio", "unit": "%", "source": "RBI r10", "points": trim(series(r10, "19"), 260)}
    S["slr"] = {"label": "Statutory Liquidity Ratio", "unit": "%", "source": "RBI r10", "points": trim(series(r10, "20"), 260)}

    # --- term spread: 10-year G-sec par yield minus the 91-day T-bill primary yield ---------------
    # Same table (r10), same weekly date, so the two legs are always the same vintage. A flattening
    # or inverted curve signals tight monetary conditions / expected slowdown; a steep curve signals
    # easing expectations, heavy long-end supply or inflation risk.
    g10_by_date = {d: v for d, v in series(r10, "38")}
    ts = [[d, round(g10_by_date[d] - v, 2)] for d, v in series(r10, "35") if d in g10_by_date]
    S["term_spread"] = {"label": "Term spread (10-year G-sec − 91-day T-bill)", "unit": "pp",
                        "source": "derived (r10)", "points": trim(sorted(ts), 260)}

    turnover = sum_columns(r12, ["OVR_CALL", "TERM_NTCE", "CBLO", "MARKET_REPO", "REPO_CORPRATE_BOND"])
    S["turnover"] = {"label": "Money-market turnover (call + repo + triparty)", "unit": "₹ crore",
                     "source": "RBI r12", "points": trim(turnover, 200)}

    # Freshest policy settings come from the portal's own key-rates snapshot (dated) - the weekly
    # WSS table lags by a week, so a rate change announced mid-week is not yet in r10.
    # NBSP TRAP (again): every key-rate name is delivered with non-breaking spaces
    # ("Policy\xa0Repo\xa0Rate"), so a plain dict lookup by "Policy Repo Rate" misses silently
    # and the freshest policy rate never reaches the tile. Normalise once, here.
    for k in kr:
        k["name"] = k["name"].replace("\xa0", " ").strip()
    krate = {k["name"]: k for k in kr}
    for name, key in (("Policy Repo Rate", "repo"), ("Standing Deposit Facility (SDF) Rate", "sdf")):
        k = krate.get(name)
        if not k:
            continue
        d = dt.datetime.fromtimestamp(k["timeDate"] / 1000, IST).strftime("%Y-%m-%d")
        pts = S[key]["points"] if key in S else []
        if not pts or d > pts[-1][0]:
            pts = pts + [[d, float(k["rate"])]]
            S[key] = {"label": f"{name} (latest announcement)", "unit": "%", "source": "DBIE key rates",
                      "points": pts}
    # ---- point-in-time policy/market snapshot ---------------------------------
    # Built here, not in the browser: each value is the FRESHEST available, tagged with its own date
    # and source, so a mid-week announcement (key rates) and the weekly WSS table can sit side by side
    # without pretending to be the same vintage. Snapshot is assembled in Python because doing this in
    # JS meant matching names that arrive with NBSPs - a silent, invisible failure mode.
    def kr_of(name: str):
        k = krate.get(name)
        if not k:
            return None
        return {"value": float(k["rate"]),
                "date": dt.datetime.fromtimestamp(k["timeDate"] / 1000, IST).strftime("%Y-%m-%d"),
                "src": "key rates"}

    def wss_of(code: str, scale: float = 1.0):
        try:
            pts = series(r10, code, scale=scale)
        except Exception:
            return None
        return {"value": pts[-1][1], "date": pts[-1][0], "src": "weekly WSS"}

    # WHY THIS LOOKS FUSSY: these chips used to carry the key-rates SNAPSHOT timestamp for every entry,
    # so CRR read "3.00% dated 2025-11-28" when the rate has been in force since 2025-12-05 (the WSS
    # series says so; the portal's stamp is only the week the snapshot was taken). A rate that changes
    # occasionally must be dated by when it took effect.
    def wss_step(code: str):
        """Last observation AND the date the value in force took effect, from the weekly WSS table."""
        try:
            pts = series(r10, code)
        except Exception:
            return None
        si = step_info(pts) or {}
        return {"value": pts[-1][1], "date": pts[-1][0], "src": "weekly WSS",
                "since": si.get("effective_from"), "prev": si.get("prev"), "bp": si.get("bp")}

    snap = []
    for label, key in (("Policy repo rate", "Policy Repo Rate"),
                       ("SDF rate", "Standing Deposit Facility (SDF) Rate")):
        v = kr_of(key)
        if v:                                    # for an announcement, the announcement IS the date
            snap.append({"name": label, "unit": "%", "kind": "setting", "since": v["date"], **v})
    for label, code in (("MSF rate", "29"), ("Bank rate", "30")):
        v = wss_step(code)
        if v:
            snap.append({"name": label, "unit": "%", "kind": "setting", **v})
    for label, code in (("Call money (wtd avg)", "34"),):
        v = wss_of(code)
        if v:
            snap.append({"name": label, "unit": "%", "kind": "reading", **v})
    k_usd = kr_of("Exchange Rate")
    if k_usd:                      # daily, fresher than the weekly table's INR-US$ row
        snap.append({"name": "USD/INR", "unit": "₹/US$", "kind": "reading", **k_usd})
    # CRR/SLR: value from the portal's key-rates set, EFFECTIVE DATE from the published weekly series
    # (the two agree on the value; the series is the authority on when it took effect).
    for label, key, code in (("CRR", "Cash Reserve Ratio", "19"),
                             ("SLR", "Statutory Liquidity Ratio", "20")):
        k, w = kr_of(key), wss_step(code)
        if k and w:
            snap.append({"name": label, "unit": "%", "kind": "setting", "value": k["value"],
                         "date": w["date"], "src": "key rates + WSS setting in force",
                         "since": w["since"], "prev": w["prev"], "bp": w["bp"],
                         # two defensible notions of "when": RBI's own effective date (key rates) and
                         # the first weekly statement that reflects it
                         "announced_from": k["date"]})
        elif k:
            snap.append({"name": label, "unit": "%", "kind": "setting", **k})
    for label, key in (("CPI inflation (released)", "CPI Inflation"), ("WACR", "WACR")):
        v = kr_of(key)
        if v:
            snap.append({"name": label, "unit": "%", "kind": "reading", **v})
    S["snapshot"] = {"label": "Snapshot", "unit": "-", "source": "mixed (dated per row)",
                     "points": [], "raw": snap}
    S["kpi_key_rates"] = {"label": "Portal key-rates snapshot", "unit": "-", "source": "DBIE home",
                          "points": [], "raw": kr}
    return S


# --------------------------------------------------------------------------- #
# tiles: value + verdict
# --------------------------------------------------------------------------- #
# tile id -> definition key (the sourced wording in definitions.json uses the term-style keys)
DEF_KEYS = {
    "rm": "reserve_money", "notes": "notes_in_circulation", "cic": "currency_in_circulation",
    "credit": "bank_credit", "deposit": "aggregate_deposits", "cdr": "credit_deposit_ratio",
    "fxa": "net_fx_assets", "gsec": "gsec10y", "tbill": "treasury_bills",
    "cdout": "certificate_of_deposit", "cpout": "commercial_paper",
    "turnover": "money_market_turnover", "invest": "bank_investments",
    "nonfood": "bank_credit", "food": "food_credit", "gold": "gold",
    "yld91": "treasury_bills", "fwd3m": "forward_premia",
    # new indicators
    "wpifuel": "wpi", "wpimanu": "wpi", "wpiprim": "wpi",
    "cpirural": "cpi", "cpiurban": "cpi",
    "m1": "m1", "moneymult": "money_multiplier", "bankdep": "bankers_deposits",
    "rbicredit": "rbi_credit_to_govt", "rupeesec": "rupee_securities",
    "crr": "crr", "slr": "slr", "usdinr": "exchange_rate", "termspread": "term_spread",
}


def tiles(S: dict) -> list[dict]:
    """One tile per watched indicator: value, change, status, and the rule that decided it."""
    out: list[dict] = []

    def add(tid, label, group, key, unit, fmt, period, status, reason, rule, value=None, change=None,
            chart="spark"):
        pts = S[key]["points"] if key in S else []
        v = last(pts)[1] if pts and value is None else value
        d = last(pts)[0] if pts else ""
        if change is None and len(pts) > 1:
            change = round(pts[-1][1] - pts[-2][1], 3)   # uniform: change vs the PREVIOUS reading
        out.append({"id": tid, "def_key": DEF_KEYS.get(tid, tid), "series_key": key,   # lets the
                    "label": label, "group": group, "value": v,                        # verifier prove
                                                                                      # tile == series
                    "unit": unit, "fmt": fmt,
                    "period": d or period, "status": status, "reason": reason, "rule": rule,
                    "change": change, "spark": spark(pts), "chart": chart})

    # inflation ------------------------------------------------------------
    # HEADLINE = the figure the publisher actually prints (MoSPI/NSO via the portal's indicator route),
    # not a number this project derived, because that is the one quoted in the news and compared against
    # the RBI's target. The index-derived series remains the long history on the chart, and the two are
    # reconciled in cross_checks (tolerance 0.1pp).
    cpi_tile_key = "cpi_yoy_official" if "cpi_yoy_official" in S else "cpi_yoy"
    cy = S[cpi_tile_key]["points"]; cv = cy[-1][1]
    st, why = band_status(cv, [
        (-99, 1.5, "bad", "below the 2% floor - deflation risk"),
        (1.5, 2.0, "watch", "under target floor"),
        (2.0, 4.5, "good", "inside the 2-6% tolerance band, near the 4% target"),
        (4.5, 6.0, "watch", "inside the band but above target"),
        (6.0, 99, "bad", "above the 6% upper tolerance limit")])
    gap = ""
    if "cpi_yoy_official" in S:
        comp = dict(S["cpi_yoy"]["points"]).get(cy[-1][0])
        if comp is not None:
            gap = (f" (an index-derived y-o-y for the same month gives {comp:.2f}%; the two differ because "
                   f"the published index is rounded to one decimal)")
    add("cpi", "CPI inflation", "Prices", cpi_tile_key, "%", "pct", "y-o-y",
        st, f"{cv:.2f}% - {why}{gap}",
        ("The figure the publisher prints (MoSPI/NSO, via the portal's indicator series), not a figure "
         "derived here. RBI flexible target 4% +/- 2% (2-6%). Green 2-4.5, watch 1.5-2 / 4.5-6, "
         "red <1.5 or >6. The chart draws the longer index-derived history, reconciled against this "
         "series to within 0.1pp (see cross_checks)."),
        change=delta(cy))

    wy = S["wpi_yoy"]["points"]; wv = wy[-1][1]
    st, why = band_status(wv, [
        (-99, 0.0, "watch", "wholesale deflation"),
        (0.0, 3.0, "good", "mild wholesale inflation"),
        (3.0, 6.0, "watch", "elevated wholesale prices"),
        (6.0, 99, "bad", "high wholesale inflation")])
    add("wpi", "WPI inflation", "Prices", "wpi_yoy", "%", "pct", "y-o-y",
        st, f"{wv:.2f}% - {why}. Caveat: the series carries an unusual +4% month-on-month step in "
            f"Apr-2026 (both index bases show it), so treat the level as provisional.",
        "No formal target. Green 0-3, watch <0 or 3-6, red >6.",
        change=delta(wy))

    # policy stance --------------------------------------------------------
    rp = S["repo"]["points"]; rv = rp[-1][1]
    # find the most recent actual change in the policy rate
    move_i = next((i for i in range(len(rp) - 1, 0, -1) if rp[i][1] != rp[i - 1][1]), None)
    if move_i:
        bp = (rp[move_i][1] - rp[move_i - 1][1]) * 100
        st = "good" if bp < -1 else ("bad" if bp > 1 else "watch")
        why = (f"{'cut' if bp < 0 else 'hiked'} {abs(bp):.0f} bp on {rp[move_i][0]} "
               f"({'supportive' if bp < 0 else 'tightening'})")
    else:
        st, why = "watch", f"unchanged since {rp[0][0]}"
    add("repo", "Policy repo rate", "Policy", "repo", "%", "pct", "level", st,
        f"{rv:.2f}% - {why}", "Direction read: a cut is supportive (green), no change is neutral (watch), a hike is tightening (red). Value is the latest announced rate.")
    si = step_info(rp)
    if si and si["bp"]:
        mv = ("hike" if si["bp"] > 0 else "cut")
        out[-1].update({"step": True, "effective_from": si["effective_from"], "prev": si["prev"],
                        "bp": si["bp"],
                        "reason": f"a {abs(si['bp']):.0f}bp {mv} on {si['effective_from']} took it from "
                                  f"{si['prev']:.2f}% to {si['value']:.2f}%; the weekly table has not "
                                  f"published a newer week yet"})

    # money ---------------------------------------------------------------
    my = S["m3_yoy"]["points"]; mv = my[-1][1]
    st, why = band_status(mv, [
        (-99, 7.0, "bad", "broad money barely growing - demand weakness"),
        (7.0, 9.0, "watch", "below the usual 10-12% norm"),
        (9.0, 15.0, "good", "healthy nominal expansion"),
        (15.0, 99, "watch", "very fast money growth - inflation risk")])
    add("m3", "M3 (broad money) growth", "Money", "m3_yoy", "%", "pct", "y-o-y",
        st, f"{mv:.1f}% - {why}", "Green 9-15%, watch 7-9 / >15, red <7 (no developed band exists; these are the customary read).",
        change=delta(my))

    ry = S["rm_yoy"]["points"]; rmv = ry[-1][1]
    st, why = band_status(rmv, [
        (-99, 5.0, "bad", "reserve money contracting or flat"),
        (5.0, 8.0, "watch", "slow reserve money growth"),
        (8.0, 14.0, "good", "ample base-money expansion"),
        (14.0, 99, "watch", "very fast base-money growth")])
    add("rm", "Reserve money growth", "Money", "rm_yoy", "%", "pct", "y-o-y",
        st, f"{rmv:.1f}% - {why}", "Green 8-14%, watch 5-8 / >14, red <5.")

    # banking -------------------------------------------------------------
    cg = S["credit_yoy"]["points"]; cgv = cg[-1][1]
    st, why = band_status(cgv, [
        (-99, 8.0, "bad", "credit growth too weak to support activity"),
        (8.0, 10.0, "watch", "credit growth below trend"),
        (10.0, 16.0, "good", "credit expanding in the healthy zone"),
        (16.0, 20.0, "watch", "very fast credit growth"),
        (20.0, 99, "bad", "credit boom - systemic risk")])
    add("credit", "Bank credit growth", "Credit", "credit_yoy", "%", "pct", "y-o-y",
        st, f"{cgv:.1f}% - {why}", "Green 10-16%, watch 8-10 / 16-20, red <8 or >20.", change=delta(cg))

    dg = S["deposit_yoy"]["points"]; dgv = dg[-1][1]
    st, why = band_status(dgv, [
        (-99, 8.0, "bad", "deposit growth lagging credit - funding stress"),
        (8.0, 10.0, "watch", "modest deposit growth"),
        (10.0, 14.0, "good", "deposits keeping pace"),
        (14.0, 99, "watch", "deposit surge - could signal risk aversion")])
    add("deposit", "Aggregate deposit growth", "Credit", "deposit_yoy", "%", "pct", "y-o-y",
        st, f"{dgv:.1f}% - {why}", "Green 10-14%, watch 8-10 / >14, red <8.", change=delta(dg))

    cr = S["cd_ratio"]["points"]; crv = cr[-1][1]
    st, why = band_status(crv, [
        (-99, 65.0, "bad", "banks barely lending against deposits"),
        (65.0, 70.0, "watch", "low credit deployment"),
        (70.0, 85.0, "good", "credit deployment in the usual range"),
        (85.0, 95.0, "watch", "stretched credit-deposit ratio"),
        (95.0, 999, "bad", "lending outrunning deposit base")])
    add("cdr", "Credit-to-deposit ratio", "Credit", "cd_ratio", "%", "pct", "level", st,
        f"{crv:.1f}% - {why}", "Green 70-85%, watch 65-70 / 85-95, red <65 or >95.", change=delta(cr))

    # liquidity -----------------------------------------------------------
    # READ THE TREND, NOT THE SIGN. Since the SDF was introduced in 2022 the RBI's normal stance is
    # to ABSORB surplus liquidity, so a permanently negative net-injection number is not "stress" by
    # itself - what matters is whether the 1-month average is draining or easing versus a quarter ago.
    ln = S["laf_net_30d"]["points"]; lnv = ln[-1][1]
    ln_3m = value_near(ln, 3) or lnv
    ln_chg = lnv - ln_3m
    cr_lakh = lnv / 100000
    st, why = band_status(ln_chg, [
        (-99999999, -25000, "bad", "liquidity draining - the 1-month average absorbed over "
                                   "₹25k cr more than a quarter ago"),
        (-25000, 25000, "watch", "roughly steady versus a quarter ago"),
        (25000, 99999999, "good", "liquidity easing - the 1-month average is over ₹25k cr less "
                                  "absorbed than a quarter ago")])
    add("liquidity", "Liquidity (1-month avg net ops)", "Liquidity", "laf_net_30d", "₹ crore", "crore",
        "1-month avg", st, f"{lnv:+,.0f} cr ({cr_lakh:+.1f} lakh cr), {ln_chg:+,.0f} cr vs 3 months ago - {why}",
        "Direction read: improving > +₹25k cr = green, within +/-₹25k cr = watch, deteriorating "
        "> ₹25k cr = red. A negative level alone is not scored as stress (SDF-era absorption is normal).")

    # rates & markets ------------------------------------------------------
    cl = S["call_rate"]["points"]; clv = cl[-1][1]
    # VINTAGE TRAP: the headline repo now carries the 2026-10-06 announcement while call money comes
    # from the 2026-10-02 weekly table. Comparing them invents a ~0.25pp "dislocation" that is pure
    # calendar mismatch, so the spread uses the weekly repo of the SAME table.
    repo_wss_v = S["repo_wss"]["points"][-1][1]
    spread = clv - repo_wss_v
    st, why = band_status(abs(spread), [
        (0, 0.25, "good", "anchored to the repo rate"),
        (0.25, 0.75, "watch", "drifting away from the policy rate"),
        (0.75, 99, "bad", "money market dislocated from the policy rate")])
    add("callmoney", "Call money rate", "Policy", "call_rate", "%", "pct", "level", st,
        f"{clv:.2f}% vs the same week's repo {repo_wss_v:.2f}% (spread {spread:+.2f}pp) - {why}",
        "Green |spread| <= 0.25pp, watch 0.25-0.75pp, red > 0.75pp.")

    if "gsec10y" in S:
        gs = S["gsec10y"]["points"]; gsv = gs[-1][1]
        g3 = value_near(gs, 3) or gsv
        chg = (gsv - g3) * 100
        st = "good" if chg < -20 else ("bad" if chg > 20 else "watch")
        add("gsec", "10-year G-sec yield", "Markets", "gsec10y", "%", "pct", "level", st,
            f"{gsv:.2f}% ({chg:+.0f} bp over 3m) - {'yields falling, easing conditions' if chg < -20 else ('yields rising, tightening conditions' if chg > 20 else 'yields broadly flat')}",
            "Direction read: -20bp or better in 3 months = green, +20bp or worse = red, else watch.")

    # external & fiscal ----------------------------------------------------
    fx = S["fxa_yoy"]["points"]; fxv = fx[-1][1]
    st, why = band_status(fxv, [
        (-99, 0.0, "bad", "net FX assets shrinking - external squeeze"),
        (0.0, 5.0, "watch", "net FX assets barely growing"),
        (5.0, 99, "good", "net FX assets building")])
    add("fxa", "Net FX assets (banking sector)", "External", "fxa_yoy", "%", "pct", "y-o-y", st,
        f"{fxv:.1f}% - {why}", "Green >5% y-o-y, watch 0-5%, red <0%.")

    fc = S["fca_yoy"]["points"]; fcv = fc[-1][1]
    st, why = band_status(fcv, [
        (-99, 0.0, "bad", "RBI's foreign currency assets shrinking"),
        (0.0, 5.0, "watch", "foreign currency assets barely growing"),
        (5.0, 99, "good", "foreign currency assets building")])
    add("fca", "RBI foreign currency assets", "External", "fca_yoy", "%", "pct", "y-o-y", st,
        f"{fcv:.1f}% - {why}", "Green >5% y-o-y, watch 0-5%, red <0%.", change=delta(fc))

    tb = S["tbill"]["points"]; tbv = tb[-1][1]
    t3 = value_near(tb, 3) or tbv
    tchg = (tbv / t3 - 1) * 100 if t3 else None
    st, why = band_status(tchg, [
        (-99, -5, "good", "government short-term borrowing easing"),
        (-5, 10, "watch", "stable short-term borrowing"),
        (10, 999, "watch", "fast build-up of short-term government paper")])
    add("tbill", "T-bill outstanding", "Fiscal", "tbill", "₹ crore", "crore", "level", st,
        f"{tbv:,.0f} cr ({tchg:+.1f}% over 3m) - {why}",
        "Green if 3-month change <= -5%, watch -5%..+10%, watch/red above +10% (more short-term borrowing).")

    # money-market instruments --------------------------------------------
    cd = S["cd_out"]["points"]; cp = S["cp_out"]["points"]
    cdc = (cd[-1][1] / (value_near(cd, 12) or cd[-1][1]) - 1) * 100
    cpc = (cp[-1][1] / (value_near(cp, 12) or cp[-1][1]) - 1) * 100
    st, why = band_status(cdc, [
        (-99, -20, "watch", "CD issuance contracting"),
        (-20, 30, "good", "CD market functioning normally"),
        (30, 999, "watch", "heavy CD issuance - banks chasing deposits")])
    add("cdout", "CD outstanding", "Markets", "cd_out", "₹ crore", "crore", "level", st,
        f"{cd[-1][1]:,.0f} cr ({cdc:+.0f}% y-o-y) - {why}",
        "Green -20%..+30% y-o-y; sharp rises flag deposit competition (watch).")
    st, why = band_status(cpc, [
        (-99, -20, "watch", "CP market contracting - corporate funding stress"),
        (-20, 30, "good", "CP market functioning normally"),
        (30, 999, "watch", "surging CP issuance")])
    add("cpout", "Commercial paper outstanding", "Markets", "cp_out", "₹ crore", "crore", "level", st,
        f"{cp[-1][1]:,.0f} cr ({cpc:+.0f}% y-o-y) - {why}",
        "Green -20%..+30% y-o-y, watch outside that.")

    to = S["turnover"]["points"]; tov = to[-1][1]
    toc = (tov / (value_near(to, 12) or tov) - 1) * 100
    st, why = band_status(toc, [
        (-99, -20, "watch", "money-market activity well below a year ago"),
        (-20, 20, "good", "money-market turnover in line with last year"),
        (20, 999, "good", "money-market turnover expanding")])
    add("turnover", "Money-market turnover", "Markets", "turnover", "₹ crore", "crore", "daily avg",
        st, f"{tov:,.0f} cr/day ({toc:+.0f}% y-o-y) - {why}",
        "Green within +/-20% y-o-y or expanding; watch on a >20% contraction.")

    # markets & balance-sheet extras --------------------------------------
    y1 = S["yld91"]["points"]; y1v = y1[-1][1]
    y13 = value_near(y1, 3) or y1v
    y1c = (y1v - y13) * 100
    st = "good" if y1c < -20 else ("bad" if y1c > 20 else "watch")
    add("yld91", "91-day T-bill yield", "Markets", "yld91", "%", "pct", "level", st,
        f"{y1v:.2f}% ({y1c:+.0f} bp over 3 months) - "
        f"{'short-end yields falling, easier funding conditions' if y1c < -20 else ('short-end yields rising, tighter funding conditions' if y1c > 20 else 'short-end yields broadly flat')}",
        "Direction read: -20bp or better in 3 months = green, +20bp or worse = red, else watch.")

    fw = S["fwd3m"]["points"]; fwv = fw[-1][1]
    st, why = band_status(fwv, [
        (-99, 0.0, "watch", "negative premia - dollars at a discount, unusual for India"),
        (0.0, 4.5, "good", "premia in the customary range, no depreciation pressure priced in"),
        (4.5, 6.0, "watch", "premia elevated - hedging demand or depreciation expectations building"),
        (6.0, 99, "bad", "premia very high - market pricing sharp rupee depreciation")])
    add("fwd3m", "3-month US$ forward premia", "External", "fwd3m", "%", "pct", "annualised", st,
        f"{fwv:.2f}% - {why}", "Interpretation bands: 0-4.5% normal, 4.5-6% watch, >6% stress, <0 unusual.")

    # ---- new: price components ---------------------------------------------------------
    for tid, key, lab, why_hi in (("wpifuel", "wpi_fuel_yoy", "WPI fuel & power", 6.0),
                                  ("wpimanu", "wpi_manu_yoy", "WPI manufactured products", 5.0),
                                  ("wpiprim", "wpi_primary_yoy", "WPI primary articles", 6.0)):
        pts = S[key]["points"]; v = pts[-1][1]
        st, why = band_status(v, [(-99, 0.0, "good", "falling - easing pipeline pressure"),
                                  (0.0, 3.0, "good", "mild"),
                                  (3.0, why_hi, "watch", "elevated"),
                                  (why_hi, 999, "bad", "very high - pushes the headline up")])
        add(tid, lab, "Prices", key, "%", "pct", "y-o-y", st, f"{v:.2f}% - {why}",
            f"Component of the WPI; bands green <=3%, watch 3-{why_hi:.0f}%, red >{why_hi:.0f}%.", change=delta(pts))

    for tid, key, lab in (("cpirural", "cpi_rural_yoy", "CPI rural"), ("cpiurban", "cpi_urban_yoy", "CPI urban")):
        pts = S[key]["points"]; v = pts[-1][1]
        st, why = band_status(v, [(-99, 1.5, "bad", "below the tolerance floor"),
                                  (1.5, 2.0, "watch", "under target"),
                                  (2.0, 4.5, "good", "inside the tolerance band"),
                                  (4.5, 6.0, "watch", "above target"),
                                  (6.0, 99, "bad", "above the upper tolerance limit")])
        add(tid, lab, "Prices", key, "%", "pct", "y-o-y", st, f"{v:.2f}% - {why}",
            "Same 2-6% tolerance band as headline CPI.", change=delta(pts))

    # ---- new: money --------------------------------------------------------------------
    pts = S["m1_yoy"]["points"]; v = pts[-1][1]
    st, why = band_status(v, [(-99, 5.0, "bad", "narrow money barely growing - transactions weak"),
                              (5.0, 9.0, "watch", "below the usual range"),
                              (9.0, 16.0, "good", "healthy transactions demand"),
                              (16.0, 999, "watch", "very fast - inflation risk")])
    add("m1", "M1 (narrow money) growth", "Money", "m1_yoy", "%", "pct", "y-o-y", st, f"{v:.1f}% - {why}",
        "Green 9-16%, watch 5-9 / >16, red <5%. M1 tracks transactions demand; M3 tracks savings too.",
        change=delta(pts))

    pts = S["money_mult"]["points"]; v = pts[-1][1]
    m3m = value_near(pts, 12) or v
    chg = v - m3m
    st, why = band_status(chg, [(-99, -0.15, "watch", "multiplier falling - money creation losing efficiency"),
                                (-0.15, 0.15, "good", "multiplier stable"),
                                (0.15, 999, "watch", "multiplier rising - banks creating money faster")])
    add("moneymult", "Money multiplier", "Money", "money_mult", "x", "num", "ratio", st,
        f"{v:.2f}x ({chg:+.2f} vs a year ago) - {why}",
        "Derived as M3 ÷ reserve money. Green +/-0.15 of a year ago, watch outside that.", change=delta(pts))

    # ---- new: RBI balance sheet / government funding ------------------------------------
    pts = S["bankers_dep_yoy"]["points"]; v = pts[-1][1]
    st, why = band_status(v, [(-99, 0.0, "bad", "bank reserves with RBI shrinking"),
                              (0.0, 5.0, "watch", "broadly flat"),
                              (5.0, 999, "good", "bank reserves building - ample system liquidity")])
    add("bankdep", "Bankers' deposits with RBI", "Liquidity", "bankers_dep_yoy", "%", "pct", "y-o-y", st,
        f"{v:.1f}% - {why}", "Green >5% y-o-y, watch 0-5%, red <0%.", change=delta(pts))

    pts = S["rbi_govt_level"]["points"]; v = pts[-1][1]; v3 = value_near(pts, 3) or v
    st, why = band_status(v - v3, [(-1e12, -1000, "good", "repaid - the Centre borrowed less from RBI than a quarter ago"),
                                  (-1000, 1000, "watch", "broadly unchanged over 3 months"),
                                  (1000, 1e12, "watch", "rising - fiscal pressure building")])
    # NOTE: this line is not published every week - RBI reports a nil balance as a BLANK cell, so the
    # column stops rather than printing zero. Comparing "3 months ago" with the last observation would
    # compare it with itself, so the reason states the last reported date instead.
    add("rbicredit", "RBI credit to the Centre", "Fiscal", "rbi_govt_level", "₹ crore", "crore", "level", st,
        f"₹{v:,.0f} cr as last reported on {pts[-1][0]}; the RBI table carries no value for this line on "
        f"any later date (a nil balance is published as a blank cell)",
        "Loans and advances to the Central Government (Ways and Means Advances and overdrafts). "
        "Direction read: falling = green, rising = watch.", change=v - v3)

    pts = S["rupeesec_yoy"]["points"]; v = pts[-1][1]
    st, why = band_status(v, [(-99, 0.0, "watch", "RBI's rupee securities portfolio shrinking"),
                              (0.0, 12.0, "good", "normal growth, absorbing government paper"),
                              (12.0, 999, "watch", "fast growth - heavy government paper absorption")])
    add("rupeesec", "RBI rupee securities", "Fiscal", "rupeesec_yoy", "%", "pct", "y-o-y", st, f"{v:.1f}% - {why}",
        "RBI's holdings of government securities incl. treasury bills (balance-sheet item 3). "
        "Green 0-12% y-o-y, watch <0 or >12%.", change=delta(pts))

    # ---- new: policy instruments in force -----------------------------------------------
    for tid, key, lab in (("crr", "crr", "Cash Reserve Ratio"), ("slr", "slr", "Statutory Liquidity Ratio")):
        pts = S[key]["points"]; v = pts[-1][1]
        mv = next((i for i in range(len(pts) - 1, 0, -1) if pts[i][1] != pts[i - 1][1]), None)
        if mv:
            d = pts[mv][0]; prev = pts[mv - 1][1]
            st = "good" if v < prev else ("bad" if v > prev else "watch")
            why = f"{'cut' if v < prev else 'raised'} from {prev:.2f}% on {d}"
        else:
            st, why = "watch", f"unchanged since {pts[0][0]}"
        add(tid, lab, "Policy", key, "%", "pct", "level", st, f"{v:.2f}% - {why}",
            "A cut releases lendable funds (supportive/green); a hike absorbs them (tightening/red); "
            "unchanged is neutral/watch. Value is the rate in force.")
        # a policy SETTING is dated by when it took effect, not by the newest weekly row repeating it
        si = step_info(pts)
        if si:
            if si["bp"]:
                mv = "hike" if si["bp"] > 0 else "cut"
                reason = (f"a {abs(si['bp']):.0f}bp {mv} on {si['effective_from']} took it from "
                          f"{si['prev']:.2f}% to {si['value']:.2f}%; the rate has been unchanged in all "
                          f"{si['rows']} weekly rows published since")
            else:
                reason = f"unchanged at {si['value']:.2f}% in every weekly row since {si['first']}"
            out[-1].update({"step": True, "effective_from": si["effective_from"], "prev": si["prev"],
                            "bp": si["bp"], "reason": reason,
                            # no change inside the fetched window: effective_from is then the window's
                            # first observation, NOT a date the setting actually changed. Consumers must
                            # be able to tell those apart, so the flag travels with the value.
                            "unchanged_in_window": si["prev"] is None})

    # ---- new: external / curve ----------------------------------------------------------
    pts = S["inr_usd"]["points"]; v = pts[-1][1]; v3 = value_near(pts, 3) or v
    dep = (v / v3 - 1) * 100
    st, why = band_status(dep, [(-99, -1.0, "good", "rupee appreciating"),
                                (-1.0, 1.0, "watch", "rupee broadly stable"),
                                (1.0, 2.5, "watch", "rupee depreciating"),
                                (2.5, 999, "bad", "rupee depreciating fast - import cost pressure")])
    add("usdinr", "USD/INR", "External", "inr_usd", "₹", "num", "spot", st,
        f"{v:.2f} ({dep:+.2f}% over 3m) - {why}",
        "Direction read over 3 months: a weaker rupee (higher USD/INR) is a stress signal.")

    pts = S["term_spread"]["points"]; v = pts[-1][1]
    st, why = band_status(v, [(-99, 0.0, "bad", "inverted curve - tighter than the policy rate implies"),
                              (0.0, 0.5, "watch", "flat curve"),
                              (0.5, 2.5, "good", "normally sloped"),
                              (2.5, 999, "watch", "steep curve - inflation or supply pressure")])
    add("termspread", "Term spread (10y − 91d)", "Markets", "term_spread", "pp", "num", "level", st,
        f"{v:+.2f}pp - {why}", "Green 0.5-2.5pp, watch 0-0.5 / >2.5, red <0 (inverted).", change=delta(pts))

    gd = S["gold_growth"]["points"]; gdv = gd[-1][1]
    st, why = band_status(gdv, [
        (-99, 0.0, "bad", "RBI gold holdings shrinking"),
        (0.0, 5.0, "watch", "gold holdings broadly flat"),
        (5.0, 999, "good", "RBI building its gold reserve")])
    add("gold", "RBI gold holdings", "External", "gold_growth", "%", "pct", "y-o-y", st,
        f"{gdv:.1f}% - {why}", "Green >5% y-o-y, watch 0-5%, red <0% (valuation and purchases both feed this).")

    iv = S["invest_yoy"]["points"]; ivv = iv[-1][1]
    st, why = band_status(ivv, [
        (-99, 0.0, "bad", "banks shrinking their investment book"),
        (0.0, 6.0, "watch", "investment growth lagging nominal growth"),
        (6.0, 12.0, "good", "banks funding government borrowing at a normal pace"),
        (12.0, 999, "watch", "very fast investment growth - often a sign of weak credit demand")])
    add("invest", "SCB investments growth", "Credit", "invest_yoy", "%", "pct", "y-o-y", st,
        f"{ivv:.1f}% - {why}", "Green 6-12% y-o-y, watch 0-6% / >12%, red <0%.")

    nf = S["nonfood_yoy"]["points"]; nfv = nf[-1][1]
    st, why = band_status(nfv, [
        (-99, 8.0, "bad", "non-food credit growth too weak to support activity"),
        (8.0, 10.0, "watch", "non-food credit growth below trend"),
        (10.0, 16.0, "good", "non-food credit expanding in the healthy zone"),
        (16.0, 20.0, "watch", "very fast non-food credit growth"),
        (20.0, 999, "bad", "credit boom - systemic risk")])
    add("nonfood", "Non-food credit growth", "Credit", "nonfood_yoy", "%", "pct", "y-o-y", st,
        f"{nfv:.1f}% - {why}", "Same bands as total bank credit: green 10-16%, watch 8-10 / 16-20, red <8 or >20.")

    fd = S["food_yoy"]["points"]; fdv = fd[-1][1]
    st, why = band_status(fdv, [
        (-99, 0.0, "watch", "food credit contracting - procurement borrowing down"),
        (0.0, 20.0, "good", "food credit growing with procurement"),
        (20.0, 999, "watch", "food credit surging - heavy procurement financing")])
    add("food", "Food credit growth", "Credit", "food_yoy", "%", "pct", "y-o-y", st,
        f"{fdv:.1f}% - {why}", "Loose bands because this series is volatile and seasonal: green 0-20%, watch <0 or >20%.")

    # currency --------------------------------------------------------------
    ny = S["notes_yoy"]["points"]; nyv = ny[-1][1]
    st, why = band_status(nyv, [
        (-99, 3.0, "watch", "cash demand unusually weak"),
        (3.0, 10.0, "good", "normal structural cash demand"),
        (10.0, 14.0, "watch", "elevated cash preference"),
        (14.0, 999, "bad", "cash demand surging - outside money system")])
    add("notes", "Notes in circulation growth", "Money", "notes_yoy", "%", "pct", "y-o-y", st,
        f"{nyv:.1f}% - {why}", "Green 3-10%, watch <3% / 10-14%, red >14%.")

    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        S = build()
    except Exception:
        log.error("[ERROR] [Build] series build failed:\n%s", traceback.format_exc())
        return 1
    try:
        T = tiles(S)
    except Exception:
        log.error("[ERROR] [Build] tile scoring failed:\n%s", traceback.format_exc())
        return 1

    # ---- history tables for the per-tile modal -----------------------------------------------
    # SETTINGS (CRR, SLR, the repo rate) get their CHANGE LOG: which rate prevailed from which date.
    # READINGS get the last N observations with the step from the previous one. Computed here rather
    # than in the browser, so the page keeps drawing only what was worked out at build time.
    HIST_N = 20
    for t in T:
        pts = S[t["series_key"]]["points"]
        unit = t["unit"]
        if t.get("step"):
            rows, prev = [], None
            for i, (d, v) in enumerate(pts):
                if i == 0 or pts[i - 1][1] != v:
                    rows.append({"date": d, "value": v, "prev": prev,
                                 "change": None if prev is None else round((v - prev) * 100, 2)})
                    prev = v
            t["history_kind"] = "setting"
            t["history"] = list(reversed(rows))[:14]        # newest change first
            t["history_note"] = (f"{len(pts)} published rows in the source table; the setting changed "
                                 f"{len(rows)} time(s) in that window")
        else:
            rows, win = [], pts[-HIST_N:]
            base = len(pts) - len(win)
            for i, (d, v) in enumerate(win):
                prev = pts[base + i - 1][1] if base + i > 0 else None
                rows.append({"date": d, "value": v, "prev": prev,
                             "change": None if prev is None else round(v - prev, 3)})
            t["history_kind"] = "reading"
            t["history"] = list(reversed(rows))             # newest first
            t["history_note"] = f"last {len(rows)} published observations of {len(pts)} stored"

    # ---- cross-checks between a computed series and the publisher's own figure ------------------
    cross_checks = []
    if "cpi_yoy_official" in S:
        comp = {d: v for d, v in S["cpi_yoy"]["points"]}
        pairs = [(d, v, comp[d]) for d, v in S["cpi_yoy_official"]["points"] if d in comp]
        if pairs:
            worst = max(pairs, key=lambda p: abs(p[1] - p[2]))
            state = "within tolerance" if abs(worst[1] - worst[2]) <= 0.1 else "BEYOND TOLERANCE"
            log.info("[INFO] [CrossCheck] CPI: published vs index-derived over %s months, largest gap "
                     "%.3fpp (%s: published %.2f vs computed %.2f) - %s", len(pairs),
                     abs(worst[1] - worst[2]), worst[0], worst[1], worst[2], state)
            if abs(worst[1] - worst[2]) > 0.1:
                log.error("[ERROR] [CrossCheck] the index-derived CPI has drifted more than 0.1pp from "
                          "the published series - the derivation needs re-checking")
            cross_checks.append({
                "indicator": "cpi", "computed_series": "cpi_yoy", "published_series": "cpi_yoy_official",
                "months_compared": len(pairs), "max_abs_diff_pp": round(abs(worst[1] - worst[2]), 3),
                "worst_month": worst[0], "published": worst[1], "computed": worst[2],
                "tolerance_pp": 0.1,
                "note": ("The published figure is quoted on the headline; the index-derived series is the "
                         "long history drawn on the chart. The index is published rounded to one decimal, "
                         "so a computed y-o-y carries a quantisation of about +/-0.05pp.")})
    counts = {k: sum(1 for t in T if t["status"] == k) for k in ("good", "watch", "bad")}
    core = [t for t in T if t["id"] in ("cpi", "wpi", "m3", "credit", "liquidity", "repo", "callmoney")]
    bad_core = sum(1 for t in core if t["status"] == "bad")
    watch_core = sum(1 for t in core if t["status"] == "watch")
    verdict = ("Stress signals in core indicators" if bad_core >= 2 else
               "Mixed - some core indicators off-colour" if (bad_core or watch_core >= 3) else
               "Broadly stable")
    asof = max(t["period"] for t in T if t["period"])
    # ---- staleness audit -------------------------------------------------------------------------
    # WHY: a column can simply STOP having observations while the table keeps publishing rows (RBI
    # reports a nil balance as a blank cell). Plotting or comparing such a series as if it were
    # current is how a 6-month-old number gets read as today's. Each tile carries how old its own
    # last observation is; anything older than 60 days is surfaced in the UI, and a series with no
    # observation for over a year is marked permanently dead so no chart plots it.
    asof_d = dt.date.fromisoformat(asof)
    for t in T:
        try:
            t["stale_days"] = (asof_d - dt.date.fromisoformat(t["period"])).days
        except Exception:
            t["stale_days"] = None
        t["stale"] = bool(t["stale_days"] is not None and t["stale_days"] > 60)
    for t in T:
        t["freq"] = freq_of(S[t["series_key"]]["points"])
    by_freq: dict[str, str] = {}
    for t in T:
        if t["period"] and t["period"] > by_freq.get(t["freq"], ""):
            by_freq[t["freq"]] = t["period"]
    freq_rank = {"daily": 0, "weekly": 1, "fortnightly": 2, "monthly": 3, "quarterly": 4,
                 "irregular": 5, "unknown": 6}
    as_of_by_freq = dict(sorted(by_freq.items(), key=lambda kv: freq_rank.get(kv[0], 9)))
    dead = {}
    for k, v in S.items():
        pts = v.get("points") or []
        if not pts:
            continue
        try:
            lag = (asof_d - dt.date.fromisoformat(pts[-1][0])).days
        except Exception:
            continue
        if lag > 400:
            dead[k] = {"last": pts[-1][0], "days": lag, "label": v.get("label", k)}
            log.warning("[WARN] [Stale] series %s has no observation since %s (%s days) - must not be "
                        "plotted as current", k, pts[-1][0], lag)
    if any(t["stale"] for t in T):
        for t in T:
            if t["stale"]:
                log.warning("[WARN] [Stale] tile %s reads %s - %s days old; the UI will label it",
                            t["id"], t["period"], t["stale_days"])
    # Definitions are sourced separately (RBI / MoSPI / FBIL pages) and stored in definitions.json;
    # the build never invents them. Missing keys simply render as "definition pending" in the UI.
    defs = {}
    defs_path = ROOT / "definitions.json"
    if defs_path.exists():
        try:
            defs = json.loads(defs_path.read_text())
            log.info("[INFO] [Build] loaded %s sourced definitions", len(defs))
        except Exception:
            log.error("[ERROR] [Build] definitions.json is unreadable:\n%s", traceback.format_exc())
    else:
        log.warning("[WARN] [Build] no definitions.json - the ? panels will show 'pending'")

    payload = {
        "definitions": defs,
        "def_keys": DEF_KEYS,
        "generated": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "as_of": asof,
        "as_of_by_frequency": as_of_by_freq,
        "cross_checks": cross_checks,
        "verdict": verdict,
        "counts": counts,
        "tiles": T,
        "dead_series": dead,
        "series": {k: {"label": v["label"], "unit": v["unit"], "source": v.get("source", ""),
                       "points": v["points"]} for k, v in S.items() if k != "kpi_key_rates"},
        "key_rates": S["kpi_key_rates"]["raw"],
        "snapshot": S["snapshot"]["raw"],
        "sources": {"portal": "data.rbi.org.in (DBIE)", "reports": "WSS / RBI Bulletin tables r2,r4,r5,r6,r7,r8,r9,r10,r11,r13,r39"},
    }
    tpl = (ROOT / "template.html").read_text()
    if "/*__WARROOM_DATA__*/" not in tpl:
        log.error("[ERROR] [Build] template.html has no /*__WARROOM_DATA__*/ placeholder")
        return 1
    html = tpl.replace("/*__WARROOM_DATA__*/", json.dumps(payload, ensure_ascii=False))
    # Embed the typeface (Archivo variable, OFL, 34 KB) so the page keeps its design offline.
    # The font is fetched once into assets/ and inlined as base64 - no CDN request at view time.
    font_b64 = ROOT / "assets" / "archivo-var.b64"
    if font_b64.exists():
        html = html.replace("/*__FONT_B64__*/", font_b64.read_text().strip())
        log.info("[INFO] [Build] embedded Archivo variable font (%s KB base64)", round(font_b64.stat().st_size / 1024))
    else:
        html = html.replace("/*__FONT_B64__*/", "")
        log.warning("[WARN] [Build] assets/archivo-var.b64 missing - falling back to system fonts")
    (OUT / "index.html").write_text(html)
    (OUT / "warroom_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    log.info("[INFO] [Build] %s tiles (%s good / %s watch / %s bad) -> dashboard/index.html (%.0f KB)",
             len(T), counts["good"], counts["watch"], counts["bad"], len(html) / 1024)
    print(json.dumps({"tiles": len(T), "counts": counts, "verdict": verdict, "as_of": asof}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
