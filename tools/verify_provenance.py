#!/usr/bin/env python3
"""verify_provenance.py - independent checks that the published numbers are right.

WHY THIS EXISTS
    Every other gate in this repo compares the documents to each other: index.json to
    latest.json, the CSV to the series, the tile to its own points. They all pass if the
    build is consistently wrong, because none of them looks at the source table.

    This tool re-reads raw/ (the committed RBI tables) and checks the numbers against an
    INDEPENDENT property - never against another published copy of itself.

THREE TIERS (all from RBI data only, no external source)
    identity   the same total is published two ways inside one table (accounting identity).
               A misread or shifted column breaks the identity immediately.
    cross-feed the same fact appears in two different RBI feeds (weekly WSS table and the
               portal's key-rates snapshot).
    derived    a published growth figure is compared with one recomputed from the index.
               (CPI's is already asserted in build_dashboard; repeated here for the file.)

WHAT IT DELIBERATELY DOES NOT DO
    Some indicators have exactly one cell in one table and no second witness. Those are
    REPORTED AS "single-source" rather than given a fake check. Naming the gap is the point;
    an indicator that says "unverified" is more useful than one that pretends.

COLUMN RESOLUTION IS INDEPENDENT
    This module resolves columns itself from the report headers instead of importing
    build_dashboard, so a bug in the build's column map cannot hide in both places. The one
    trap it must respect (learned the hard way): report 9 ships a non-data "Version" column
    in its header, so the header list is longer than the row. Non-data columns are pruned
    here exactly once, and the row length is then ASSERTED against the header - a mismatch
    is a hard error, not a silent offset.

Exit code: 0 if every check passes, 1 otherwise. Writes api/v1/verification.json.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
API = ROOT / "api" / "v1"

# Rounding tolerance. RBI publishes these in Rs lakh; the identities reconcile to +-1 in the
# last printed unit, which is ~1e-6 relative at these magnitudes. 0.01% is a wide margin that
# still fails on any real transcription error (the smallest real error is a whole column).
TOL_PCT = 0.01


# ---------------------------------------------------------------- plumbing
def load(rid: str) -> dict:
    p = RAW / f"report_{rid}.json"
    if not p.exists():
        raise SystemExit(f"[ERROR] [Verity] missing source table {p} - run fetch_series.py")
    return json.loads(p.read_text())


def names_of(rep: dict) -> list[str]:
    """Data column names, with non-data columns removed (report 9 ships a 'Version' column)."""
    return [c for c in rep["cols"] if not c.strip().lower().startswith("version")]


def row(rep: dict, which: int = 0) -> tuple[list[str], list]:
    names = names_of(rep)
    r = rep["rows"][which]
    if len(r) != len(names):
        # THE trap: silently trusting positions here is how a column shift ships.
        raise SystemExit(f"[ERROR] [Verity] {len(names)} header columns but {len(r)} row values "
                         f"- refusing to compare on a misaligned table")
    return names, r


def col(names: list[str], code: str) -> int:
    tag = f"[{code}]"
    for i, n in enumerate(names):
        if n.endswith(tag):
            return i
    raise SystemExit(f"[ERROR] [Verity] column code {code!r} not found; have: {names}")


def get(names: list[str], r: list, code: str) -> float | None:
    v = r[col(names, code)]
    return None if v in (None, "") else float(v)


def compare(got: float | None, want: float | None) -> tuple[bool, float, str]:
    """(ok, residual_pct, detail). A missing component makes the check unprovable, not passed."""
    if got is None or want is None:
        return False, float("nan"), "a component is blank in the source table (nil published as blank)"
    if want == 0:
        return abs(got) < 1e-9, 0.0 if abs(got) < 1e-9 else float("nan"), "denominator is zero"
    resid = abs(got - want) / abs(want) * 100.0
    return resid <= TOL_PCT, resid, f"{got:,.0f} vs {want:,.0f}"


# ---------------------------------------------------------------- tier 1: identities
def chk_m3_components():
    rep = load("13"); n, r = row(rep)
    total = get(n, r, "MSO38")
    parts = [get(n, r, c) for c in ("MSO30", "MSO31", "MSO37", "MSO32")]
    got = sum(p for p in parts if p is not None)
    return compare(got, total)


def chk_m3_sources():
    rep = load("13"); n, r = row(rep)
    total = get(n, r, "MSO38")
    plus = [get(n, r, c) for c in ("SOMS1", "SOMS10", "SOMS16", "SOMS21")]
    minus = get(n, r, "SOMS22")
    got = sum(p for p in plus if p is not None) - (minus or 0.0)
    return compare(got, total)


def chk_m1_against_m3():
    """M1 is computed here (currency with public + demand deposits + other deposits with RBI).
    M1 + time deposits must equal the published M3 - so the computed tile is pinned to M3."""
    rep = load("13"); n, r = row(rep)
    m1 = sum(p for p in (get(n, r, "MSO30"), get(n, r, "MSO31"), get(n, r, "MSO32"))
             if p is not None)
    got = m1 + (get(n, r, "MSO37") or 0.0)
    return compare(got, get(n, r, "MSO38"))


def chk_rm_components():
    rep = load("7"); n, r = row(rep)
    total = get(n, r, "RMC5")
    got = sum(p for p in (get(n, r, "RMC1"), get(n, r, "RMC4"), get(n, r, "RMC3"))
              if p is not None)
    return compare(got, total)


def chk_rm_sources():
    rep = load("7"); n, r = row(rep)
    plus = [get(n, r, c) for c in ("RMC7", "RMC9", "RMC14", "RMC15")]
    got = sum(p for p in plus if p is not None) - (get(n, r, "RMC16") or 0.0)
    return compare(got, get(n, r, "RMC5"))


def chk_scb_food_nonfood():
    rep = load("9"); n, r = row(rep)
    got = sum(p for p in (get(n, r, "255"), get(n, r, "NONFC")) if p is not None)
    return compare(got, get(n, r, "0250"))


def chk_scb_deposits():
    rep = load("9"); n, r = row(rep)
    got = sum(p for p in (get(n, r, "0070"), get(n, r, "0080")) if p is not None)
    return compare(got, get(n, r, "0060"))


def chk_scb_investments():
    rep = load("9"); n, r = row(rep)
    got = sum(p for p in (get(n, r, "0230"), get(n, r, "0240")) if p is not None)
    return compare(got, get(n, r, "0220"))


def chk_notes_split():
    rep = load("39"); n, r = row(rep)
    got = sum(p for p in (get(n, r, "101"), get(n, r, "102")) if p is not None)
    return compare(got, get(n, r, "138"))


def chk_rbi_balance_sheet():
    """Double entry: liabilities and assets must both equal the published total. One check
    that validates seven published columns at once."""
    rep = load("39"); n, r = row(rep)
    total = get(n, r, "103")
    liab = sum(p for p in (get(n, r, "138"), get(n, r, "108"), get(n, r, "117"))
               if p is not None)
    assets = sum(p for p in (get(n, r, c) for c in
                             ("140", "104", "135", "121", "139", "136", "137"))
                 if p is not None)
    ok_l, res_l, det_l = compare(liab, total)
    ok_a, res_a, det_a = compare(assets, total)
    worst = max(x for x in (res_l, res_a) if x == x) if (res_l == res_l or res_a == res_a) else float("nan")
    return (ok_l and ok_a), worst, f"liabilities {det_l}; assets {det_a}"


def chk_tbill_tenors():
    rep = load("2"); n, r = row(rep)
    results = []
    for label, holders, total in (
            ("91d", ("3_2", "3_5", "3_3", "3_4"), "3_6"),
            ("182d", ("4_2", "4_5", "4_3", "4_4"), "4_6"),
            ("364d", ("5_2", "5_5", "5_3", "5_4"), "5_6")):
        got = sum(p for p in (get(n, r, c) for c in holders) if p is not None)
        ok, res, det = compare(got, get(n, r, total))
        results.append((label, ok, res, det))
    if not results:
        return False, float("nan"), "no tenor rows"
    ok = all(x[1] for x in results)
    worst = max((x[2] for x in results if x[2] == x[2]), default=float("nan"))
    return ok, worst, "; ".join(f"{l}: {d}" for l, _, _, d in results)


# ---------------------------------------------------------------- tier 2: two RBI feeds
def _key_rates() -> dict:
    d = json.loads((RAW / "key_rates.json").read_text())
    return {(k["name"] or "").replace("\xa0", " ").strip(): k for k in d["body"]["result"]}


def _wss_latest(code: str) -> float | None:
    rep = load("10"); n, r = row(rep)
    return get(n, r, code)


def _cross(name: str, code: str):
    kr = _key_rates().get(name)
    if not kr:
        return False, float("nan"), f"key-rates snapshot has no {name!r}"
    return compare(_wss_latest(code), float(kr["rate"]))


def chk_repo_cross():
    return _cross("Policy Repo Rate", "27")


def chk_crr_cross():
    return _cross("Cash Reserve Ratio", "19")


def chk_slr_cross():
    return _cross("Statutory Liquidity Ratio", "20")


def chk_usdinr_cross():
    """The two feeds are different observation dates (weekly row vs daily FBIL), so equality is
    only asserted when the dates actually match; otherwise the difference is reported, not failed."""
    import datetime as dt
    kr = _key_rates().get("Exchange Rate")
    if not kr:
        return False, float("nan"), "key-rates snapshot has no Exchange Rate"
    rep = load("10"); n, r = row(rep)
    wss = get(n, r, "40")
    kr_date = dt.datetime.fromtimestamp(kr["timeDate"] / 1000,
                                        dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    wss_date = str(r[0])[:10]
    if kr_date != wss_date:
        diff = abs(float(kr["rate"]) - (wss or 0)) / (wss or 1) * 100
        if diff <= 1.0:
            return True, diff, (f"different observation dates ({wss_date} weekly vs {kr_date} daily) "
                                f"- values {wss:,.4f} vs {float(kr['rate']):,.4f}, consistent")
        return False, diff, f"{wss:,.4f} ({wss_date}) vs {float(kr['rate']):,.4f} ({kr_date})"
    return compare(wss, float(kr["rate"]))


# ---------------------------------------------------------------- tier 3: published vs derived
def chk_cpi_published_vs_derived():
    named = json.loads((RAW / "named_series.json").read_text())
    off = (named.get("cpi_inflation_combined") or {}).get("points") or []
    if not off:
        return False, float("nan"), "published CPI inflation series absent"
    pub_date, pub_val = off[-1][0], float(off[-1][1])

    rep = load("11"); n, _ = row(rep)
    ci = col(n, "CPI2024_33")
    series = []
    for r in rep["rows"]:
        if r and r[0] and r[ci] is not None:
            series.append((str(r[0])[:10], float(r[ci])))
    series.sort()
    by_date = {d: v for d, v in series}
    d = pub_date[:10]
    if d not in by_date:
        return False, float("nan"), f"no index value on the published month {d}"
    prev = f"{int(d[:4]) - 1}{d[4:]}"
    if prev not in by_date:
        return False, float("nan"), f"no index value for {prev}"
    derived = (by_date[d] / by_date[prev] - 1.0) * 100.0
    resid = abs(derived - pub_val)
    # absolute pp tolerance: the index is published to one decimal, so a computed y-o-y carries
    # about +-0.05pp of quantisation. 0.1pp matches the tolerance build_dashboard asserts.
    return resid <= 0.1, resid, (f"published {pub_val:.2f}% vs index-derived {derived:.2f}% "
                                 f"for {d} ({resid:.3f}pp)")


# ---------------------------------------------------------------- registry
CHECKS = [
    # (id, tier, indicators covered, description, fn)
    ("m3_components", "identity", ["m3"],
     "currency with public + demand + time + other deposits = M3", chk_m3_components),
    ("m3_sources", "identity", ["m3", "fxa"],
     "net bank credit to govt + credit to commercial sector + net FX assets + govt currency "
     "liability - non-monetary liabilities = M3", chk_m3_sources),
    ("m1_against_m3", "identity", ["m1"],
     "(currency with public + demand deposits + other deposits with RBI) + time deposits = M3",
     chk_m1_against_m3),
    ("rm_components", "identity", ["rm", "bankdep"],
     "currency in circulation + bankers' deposits + other deposits = reserve money",
     chk_rm_components),
    ("rm_sources", "identity", ["rm"],
     "net RBI credit to govt + RBI credit to banks & commercial sector + net FX assets + "
     "govt currency liabilities - non-monetary liabilities = reserve money", chk_rm_sources),
    ("scb_food_nonfood", "identity", ["credit", "food", "nonfood"],
     "food credit + non-food credit = bank credit", chk_scb_food_nonfood),
    ("scb_deposits", "identity", ["deposit"],
     "demand deposits + time deposits = aggregate deposits", chk_scb_deposits),
    ("scb_investments", "identity", ["invest"],
     "government securities + other approved securities = investments", chk_scb_investments),
    ("notes_split", "identity", ["notes"],
     "notes in circulation + notes held in the banking department = notes issued", chk_notes_split),
    ("rbi_balance_sheet", "identity", ["fca", "gold", "rupeesec", "notes"],
     "double entry: liabilities total and assets total both equal the published total",
     chk_rbi_balance_sheet),
    ("tbill_tenors", "identity", ["tbill"],
     "each tenor total = banks + primary dealers + state govts + others", chk_tbill_tenors),
    ("repo_cross_feed", "cross-feed", ["repo"],
     "weekly WSS policy repo rate = key-rates snapshot", chk_repo_cross),
    ("crr_cross_feed", "cross-feed", ["crr"],
     "weekly WSS cash reserve ratio = key-rates snapshot", chk_crr_cross),
    ("slr_cross_feed", "cross-feed", ["slr"],
     "weekly WSS statutory liquidity ratio = key-rates snapshot", chk_slr_cross),
    ("usdinr_cross_feed", "cross-feed", ["usdinr"],
     "weekly WSS INR/US$ = portal daily FBIL reference rate", chk_usdinr_cross),
    ("cpi_published_vs_derived", "derived", ["cpi"],
     "RBI's published CPI inflation = the figure recomputed from the CPI index",
     chk_cpi_published_vs_derived),
]

# Indicators with no second witness in the RBI tables we fetch. Declared, not faked.
SINGLE_SOURCE = {
    "callmoney": "one cell in the weekly WSS table (weighted-average call rate)",
    "gsec": "one cell in the weekly WSS table (10-year par yield)",
    "yld91": "one cell in the weekly WSS table (91-day T-bill primary yield)",
    "fwd3m": "one cell in the weekly WSS table (3-month forward premia)",
    "cdout": "one cell in the CD table (amount outstanding)",
    "cpout": "one cell in the CP table (amount outstanding)",
    "turnover": "sum of five columns in the money-market turnover table; no second witness",
    "wpi": "computed from the WPI index; no published growth series in the tables we fetch",
    "wpifuel": "computed from a WPI component index; component weights are published outside DBIE",
    "wpimanu": "computed from a WPI component index; component weights are published outside DBIE",
    "wpiprim": "computed from a WPI component index; component weights are published outside DBIE",
    "cpirural": "computed from the CPI rural index; weights are published outside DBIE",
    "cpiurban": "computed from the CPI urban index; weights are published outside DBIE",
    "cdr": "ratio of credit to deposits; both inputs are identity-verified, the division is not",
    "moneymult": "M3 / reserve money; both inputs are identity-verified, the division is not",
    "termspread": "10y G-sec minus 91-day T-bill; both inputs are single-source",
    "liquidity": "22-working-day mean of net LAF; the mean is arithmetic, the input is single-source",
    "rbicredit": "net RBI credit to the Centre - a sub-line of a verified parent, not verified itself",
}


def main() -> int:
    API.mkdir(parents=True, exist_ok=True)
    results, failed = [], 0
    print("provenance checks (RBI data only):")
    for cid, tier, covers, desc, fn in CHECKS:
        try:
            ok, resid, detail = fn()
        except SystemExit:
            raise
        except Exception as exc:                                   # noqa: BLE001
            ok, resid, detail = False, float("nan"), f"check crashed: {type(exc).__name__}: {exc}"
        if not ok:
            failed += 1
        results.append({"id": cid, "tier": tier, "covers": covers, "description": desc,
                        "status": "pass" if ok else "fail",
                        "residual": None if resid != resid else round(resid, 6),
                        "detail": detail})
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {cid:28} {tier:11} {detail}")

    # map every indicator to the checks that cover it, or declare it single-source
    covered: dict[str, list[str]] = {}
    for res in results:
        if res["status"] == "pass":
            for iid in res["covers"]:
                covered.setdefault(iid, []).append(res["id"])

    index = json.loads((API / "index.json").read_text())["indicators"]
    indicators = {}
    for ind in index:
        iid = ind["id"]
        if iid in covered:
            tiers = sorted({r["tier"] for r in results if r["id"] in covered[iid]})
            indicators[iid] = {"status": "verified", "checks": covered[iid],
                               "tier": tiers[0] if len(tiers) == 1 else "+".join(tiers)}
        elif iid in SINGLE_SOURCE:
            indicators[iid] = {"status": "single-source", "checks": [],
                               "tier": "single-source", "note": SINGLE_SOURCE[iid]}
        else:
            indicators[iid] = {"status": "unverified", "checks": [], "tier": "unverified",
                               "note": "no check declared for this indicator"}

    n_verified = sum(1 for v in indicators.values() if v["status"] == "verified")
    n_single = sum(1 for v in indicators.values() if v["status"] == "single-source")
    n_unver = sum(1 for v in indicators.values() if v["status"] == "unverified")

    # The reporting date is the newest observation in the sources, never the wall clock: this file
    # is part of the dataset hash, so a timestamp would make every build look like new data.
    as_of = str(json.loads((RAW / "report_10.json").read_text())["rows"][0][0])[:10]

    out = {
        "as_of": as_of,
        "tolerance_pct": TOL_PCT,
        "summary": {"checks": len(results), "passed": len(results) - failed, "failed": failed,
                    "indicators_verified": n_verified, "indicators_single_source": n_single,
                    "indicators_unverified": n_unver, "indicators_total": len(indicators)},
        "source": "Reserve Bank of India, Database on Indian Economy (DBIE) - raw/ tables only",
        "note": ("Checks compare RBC-published totals against each other (accounting identities), "
                 "against a second RBI feed, or a published figure against one recomputed from the "
                 "index. An indicator marked single-source has one cell in one table and no second "
                 "witness; that is stated rather than dressed up as a check."),
        "checks": results,
        "indicators": indicators,
    }
    (API / "verification.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"\n  {len(results) - failed}/{len(results)} checks passed; "
          f"indicators: {n_verified} verified, {n_single} single-source, {n_unver} unverified")
    print(f"  wrote {API / 'verification.json'}")
    if n_unver:
        print(f"  [WARN] {n_unver} indicator(s) have no declared check")
    if failed:
        print(f"\nFAIL - {failed} provenance check(s) failed. The published numbers do not "
              f"reconcile; do not deploy.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
