#!/usr/bin/env python3
"""
fetch_mospi.py - pull the real-economy layer from MoSPI's eSankhyiki API.

WHY THIS EXISTS: RBI's DBIE (fetch_series.py) carries prices, money, credit, rates and the RBI balance
sheet. It carries no labour, no industrial output and no national accounts. MoSPI publishes all three,
free, as JSON - so this script adds the *activity* half of the picture without a single PDF or scrape.

RULES THIS SCRIPT ENFORCES (decided 2026-11-11):
  * official API or XLSX only - no PDF parsing anywhere in this project;
  * every observation keeps the reference period its publisher STATES (e.g. "Sep 2026"), never a date
    this script inferred;
  * the publication date is NOT modelled here. MoSPI's catalogue publishes release dates, but only in a
    browser-rendered page; the API does not expose them. Rather than invent a lag, `release_date` is
    left null and the payload says so.

WHY NOT ISP: the services-production API has no overall index row (`type_code=1` is documented as
"no data at present"), so an all-services figure could only be produced by summing weighted sub-sectors
we do not have weights for. Not published, not attempted.

STETP: [INFO]/[WARN]/[ERROR] on stderr, per-product try/except, and a completeness gate that refuses to
write a short dataset.

TLS TRAP (cost a probe cycle): api.mospi.gov.in negotiates with UNSAFE LEGACY RENEGOTIATION. OpenSSL 3
refuses it by default, so a plain requests/curl call dies with
    SSLError: unsafe legacy renegotiation disabled
which reads like "the endpoint is gone". The server is fine; Python just needs
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import re
import ssl
import sys
import time
import traceback

import requests
from requests.adapters import HTTPAdapter

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
log = logging.getLogger("mospi")

ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
OUT = RAW / "mospi.json"

BASE = "https://api.mospi.gov.in"
UA = "Mozilla/5.0 (X11; Linux x86_64) warroom-mospi/1.0"
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}

# The monthly PLFS bulletin series starts April 2025 (it is the first month published with monthly
# estimates under the revised methodology). Earlier monthly requests return an empty envelope.
PLFS_FIRST = dt.date(2025, 4, 1)

# The API spells the all-India row "rural + urban"; normalise to a spacing-insensitive map. Returning
# the MAP KEY instead of this value (as the first version did) filed the headline series under
# "act_ur_rural + urban", so the 6-series gate below found no act_ur at all.
SECTOR_KEY = {"rural": "rural", "urban": "urban", "rural + urban": "both"}

# Minimum points per series before raw/mospi.json is accepted. A monthly series needs half a year of
# history to be worth a tile; the quarterly one needs three quarters. Tested in tests/test_mospi.py.
REQUIRED = {"act_ur": 6, "act_lfpr": 6, "act_wpr": 6, "act_iip": 6, "act_gva": 3,
            "act_oppi": 6, "act_iip_capital": 6}


def _session() -> requests.Session:
    """A session that can actually talk to api.mospi.gov.in (see the TLS note in the docstring)."""
    ctx = ssl.create_default_context()
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT

    class LegacyAdapter(HTTPAdapter):
        def init_poolmanager(self, *a, **kw):
            kw["ssl_context"] = ctx
            return super().init_poolmanager(*a, **kw)

        def proxy_manager_for(self, *a, **kw):
            kw["ssl_context"] = ctx
            return super().proxy_manager_for(*a, **kw)

    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.mount("https://", LegacyAdapter())
    return s


SESSION = _session()


def get(path: str, *, _tries: int = 4, **params) -> dict:
    """GET one API page as JSON, retrying transient failures.

    A 200 with `statusCode: true` and an empty `data` list is a VALID empty answer here (a month the
    publisher has not released yet), not an error - see plfs_month(). Any other failure raises, because
    a silently-missing month would hole the series while every number that remains looks plausible.
    """
    last = None
    for attempt in range(1, _tries + 1):
        try:
            r = SESSION.get(BASE + path, params=params, timeout=45)
            if r.status_code == 429:            # the host answers 429 + Retry-After after ~10 rapid calls
                wait = int(r.headers.get("Retry-After") or 5)
                log.warning("[WARN] [API] rate-limited on %s - waiting %ss", path, wait)
                time.sleep(wait)
                raise RuntimeError("HTTP 429 rate limited")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
            return r.json()
        except Exception as e:                     # noqa: BLE001 - retried, then re-raised
            last = e
            if attempt < _tries:
                wait = 2 ** attempt
                log.warning("[WARN] [API] %s %s failed (%s) - retry %s/%s in %ss",
                            path, params, type(e).__name__, attempt, _tries - 1, wait)
                time.sleep(wait)
    raise RuntimeError(f"{path} failed after {_tries} attempts: {last}")


def paged(path: str, **params) -> list[dict]:
    """Every record for a query, walking `meta_data.totalPages` rather than trusting page 1.

    recordPerPage is 10-20 depending on the product, so a single call is never the whole answer.
    """
    rows: list[dict] = []
    page, pages = 1, 1
    while page <= pages:
        j = get(path, page=page, **params)
        meta = j.get("meta_data") or j.get("metaData") or {}
        pages = int(meta.get("totalPages") or 1)
        rows.extend(j.get("data") or [])
        if pages > 60:                             # guard against a runaway loop
            raise RuntimeError(f"{path}: {pages} pages - refusing to walk that far")
        page += 1
    return rows


CATALOGUE = "/api/esankhyiki/cms/golden-sheet/list"


def _iso_of(datestr: str) -> str | None:
    """'15 Oct 2026' -> '2026-10-15'. The catalogue states dates in this form; anything else is null."""
    try:
        return dt.datetime.strptime(datestr.strip(), "%d %b %Y").date().isoformat()
    except (AttributeError, ValueError):
        return None


def _canon_period(ref: str) -> str:
    """Normalise a catalogue ref_period so it can be matched against our own labels.

    The catalogue writes the same month several ways across tables ("Sep 2026", "Sept 2026",
    "September 2026") because each table is maintained by a different division. Left unnormalised, the
    lookup silently misses and every release date reads as absent.
    """
    s = " ".join((ref or "").split())
    m = re.match(r"^([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$", s)
    if m:
        mon = m.group(1).title()
        mon = "Sep" if mon == "Sep" else mon
        return f"{mon} {m.group(2)}"
    return s


def catalogue_releases(product: str, patterns: list[str]) -> dict[str, str]:
    """ref_period -> release_date, straight from MoSPI's own catalogue.

    WHY: the data API returns values but no publication date, and this project refuses to MODEL a lag
    (that is how a backtest manufactures edge). The catalogue behind e-Sankhyiki does publish one per
    table, and its CMS endpoint is queryable - so the release date is OBSERVED, not guessed.

    `patterns` narrows to the tables we actually read (the catalogue carries hundreds of tables per
    product, published on different days within the same period). Where several match, the EARLIEST
    release for a period wins: that is when the period's figures first became public.

    Best-effort by design: an empty result leaves release dates absent and the build still works.
    """
    out: dict[str, str] = {}
    page, pages = 1, 1
    while page <= pages:
        try:
            j = get(CATALOGUE, product=product, page=page, limit=200)
        except Exception:
            log.warning("[WARN] [Catalogue] %s page %s unavailable - release dates will be absent",
                        product, page)
            return out
        meta = j.get("meta_data") or {}
        pages = int(meta.get("totalPages") or 1)
        for row in j.get("data") or []:
            name = (row.get("table_name") or "")
            if patterns and not any(p.lower() in name.lower() for p in patterns):
                continue
            rp, rd = row.get("ref_period"), row.get("release_date")
            iso = _iso_of(rd) if rd else None
            if not rp or not iso:
                continue
            key = _canon_period(rp)
            prev = out.get(key)
            out[key] = iso if prev is None else min(prev, iso)
        page += 1
        if pages > 60:                     # guard against a runaway walk
            break
        time.sleep(0.6)                    # the host 429s after ~10 rapid calls; measured here
    return out


def month_start(y: int, m: int) -> str:
    return dt.date(y, m, 1).isoformat()


def month_label(y: int, m: int) -> str:
    return dt.date(y, m, 1).strftime("%b %Y")


# --------------------------------------------------------------------------- #
# PLFS - labour, monthly, all-India
# --------------------------------------------------------------------------- #
def plfs_month(year: int, month: int, indicator_code: int) -> list[dict]:
    """One month of one indicator, split by sector (rural / urban / both) for persons 15+."""
    j = get("/api/plfs/getData", indicator_code=indicator_code, frequency_code=3,
            year=str(year), month_code=str(month),
            sector_code="1,2,3", gender_code=3, age_code=1)
    return j.get("data") or []


def fetch_plfs() -> dict:
    """UR / LFPR / WPR, monthly, all-India, 15+, by sector. Returns series keyed act_*."""
    today = dt.date.today()
    end = dt.date(today.year, today.month, 1) - dt.timedelta(days=1)   # previous month
    series: dict[str, dict] = {}
    spec = {"ur": (3, "Unemployment rate (15+, CWS)"), "lfpr": (1, "Labour force participation rate"),
            "wpr": (2, "Worker population ratio")}
    sectors = {"rural": "1", "urban": "2", "both": "3"}
    got_months: set[str] = set()

    d = PLFS_FIRST
    while d <= end:
        for short, (code, _lbl) in spec.items():
            try:
                rows = plfs_month(d.year, d.month, code)
            except Exception:
                log.error("[ERROR] [PLFS] %s %s failed:\n%s", short, d, traceback.format_exc())
                raise
            if not rows:
                continue
            for row in rows:
                sec = " ".join((row.get("sector") or "").split()).lower()
                key = SECTOR_KEY.get(sec)
                if key is None:
                    continue
                try:
                    val = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                skey = f"act_{short}" if key == "both" else f"act_{short}_{key}"
                s = series.setdefault(skey, {"label": "", "unit": "%", "freq": "monthly",
                                             "source": f"MoSPI PLFS monthly (CWS), {key}",
                                             "endpoint": "/api/plfs/getData",
                                             "points": [], "periods": {}})
                date = month_start(d.year, d.month)
                s["points"].append([date, val])
                s["periods"][date] = month_label(d.year, d.month)
                got_months.add(date)
        d = (d.replace(day=28) + dt.timedelta(days=5)).replace(day=1)   # next month, safely

    labels = {"act_ur": "Unemployment rate, 15+ (all-India)",
              "act_ur_rural": "Unemployment rate, 15+ (rural)",
              "act_ur_urban": "Unemployment rate, 15+ (urban)",
              "act_lfpr": "Labour force participation rate, 15+",
              "act_lfpr_rural": "Labour force participation rate (rural)",
              "act_lfpr_urban": "Labour force participation rate (urban)",
              "act_wpr": "Worker population ratio, 15+",
              "act_wpr_rural": "Worker population ratio (rural)",
              "act_wpr_urban": "Worker population ratio (urban)"}
    rel = catalogue_releases("PLFS", ["Unemployment Rate (UR)", "Labour Force Participation Rate (LFPR)",
                                      "Worker Population Ratio (WPR)"])
    for k, s in series.items():
        s["label"] = labels.get(k, k)
        s["points"].sort()
        s["unit"] = "%"
        s["releases"] = rel          # ref_period -> observed release date (may be {})
    log.info("[INFO] [PLFS] %s series over %s months (%s..%s)", len(series), len(got_months),
             min(got_months) if got_months else "-", max(got_months) if got_months else "-")
    return series


# --------------------------------------------------------------------------- #
# IIP - industry, monthly (base 2022-23, General index)
# --------------------------------------------------------------------------- #
def fetch_iip() -> dict:
    """General IIP index + the publisher's own y-o-y growth. One call per calendar year."""
    rows: list[dict] = []
    for year in (2025, 2026, 2027):                # 2027 is a no-op until it arrives
        try:
            j = get("/api/iip/getIIPData", frequency="Monthly", base_year="2022-23",
                    year=str(year), type="General", category_code="4")
        except Exception:
            log.error("[ERROR] [IIP] year %s failed:\n%s", year, traceback.format_exc())
            raise
        got = j.get("data") or []
        rows.extend(got)
        log.info("[INFO] [IIP] %s: %s month(s)", year, len(got))
    idx, grow, periods = [], [], {}
    for r in rows:
        m = MONTHS.get((r.get("month") or "").strip())
        y = r.get("year")
        if not m or not y:
            continue
        date = month_start(int(y), m)
        try:
            idx.append([date, float(r["index"])])
        except (KeyError, TypeError, ValueError):
            pass
        try:
            grow.append([date, float(r["growth_rate"])])
        except (KeyError, TypeError, ValueError):
            pass
        periods[date] = month_label(int(y), m)
    out = {}
    if idx:
        out["act_iip"] = {"label": "Index of Industrial Production (General, 2022-23=100)",
                          "unit": "index", "freq": "monthly", "source": "MoSPI IIP monthly",
                          "endpoint": "/api/iip/getIIPData",
                          "points": sorted(idx), "periods": dict(sorted(periods.items()))}
    if grow:
        out["act_iip_growth"] = {"label": "IIP growth, y-o-y (as published)",
                                 "unit": "%", "freq": "monthly", "source": "MoSPI IIP monthly",
                                 "endpoint": "/api/iip/getIIPData",
                                 "points": sorted(grow), "periods": dict(sorted(periods.items()))}
    # No table-name filter: IIP tables are titled by NIC digit depth, not by type, and all of them for
    # a month publish on the same day (the 28th, generally) - the earliest is that month's release.
    rel = catalogue_releases("IIP", [])
    for s in out.values():
        s["releases"] = rel
    log.info("[INFO] [IIP] %s series, %s points", len(out), len(idx))
    return out


# --------------------------------------------------------------------------- #
# NAS - national accounts, quarterly (GVA at constant prices)
# --------------------------------------------------------------------------- #
Q_START = {1: 4, 2: 7, 3: 10, 4: 1}               # Indian FY: Q1 = Apr-Jun ... Q4 = Jan-Mar


def quarter_date(fy: str, quarter: str) -> tuple[str, str] | None:
    """'2026-27','Q1' -> ('2026-04-01','Q1 FY2026-27').

    Q4 crosses the calendar year: FY2026-27 runs Apr 2026 - Mar 2027, so Q4 STARTS in Jan 2027. Getting
    this wrong dates every Q4 a year early and quietly shifts the whole y-o-y series.
    """
    if not fy or not quarter or not str(quarter).startswith("Q"):
        return None
    try:
        qi = int(str(quarter)[1])
        y0 = int(str(fy).split("-")[0])
    except (ValueError, IndexError):
        return None
    if qi not in Q_START:
        return None
    year = y0 if qi != 4 else y0 + 1
    return month_start(year, Q_START[qi]), f"Q{qi} FY{fy}"


def fetch_nas() -> dict:
    """Total GVA at constant prices, quarterly, plus a y-o-y computed from the published levels.

    The API carries a "Total Gross Value Added" row, so nothing is summed here. The y-o-y is computed
    (4 quarters back) and labelled as computed - the published growth rate is not on this endpoint.
    """
    rows: list[dict] = []
    for fy in ("2023-24", "2024-25", "2025-26", "2026-27"):
        try:
            got = paged("/api/nas/getNASData", indicator_code="1", base_year="2022-23",
                        series="Current", frequency_code="2", year=fy)
        except Exception:
            log.error("[ERROR] [NAS] %s failed:\n%s", fy, traceback.format_exc())
            raise
        rows.extend(got)
        log.info("[INFO] [NAS] FY%s: %s row(s)", fy, len(got))

    lvl, periods = [], {}
    for r in rows:
        if (r.get("industry") or "").strip().lower() != "total gross value added":
            continue
        qd = quarter_date(r.get("year") or "", r.get("quarter") or "")
        if not qd:
            continue
        date, label = qd
        try:
            lvl.append([date, float(r["constant_price"])])
        except (KeyError, TypeError, ValueError):
            continue
        periods[date] = label
    lvl.sort()

    out = {}
    if lvl:
        out["act_gva"] = {"label": "Gross value added, constant prices (total)",
                          "unit": "₹ crore", "freq": "quarterly",
                          "source": "MoSPI NAS quarterly (2022-23 base)",
                          "endpoint": "/api/nas/getNASData",
                          "points": lvl, "periods": dict(sorted(periods.items()))}
        by_date = {d: v for d, v in lvl}
        yoy = []
        for d, v in lvl:
            y, m = int(d[:4]), int(d[5:7])
            prev = by_date.get(dt.date(y - 1, m, 1).isoformat())
            if prev:
                yoy.append([d, round((v / prev - 1) * 100, 2)])
        if yoy:
            out["act_gva_yoyt"] = {"label": "Gross value added, y-o-y (computed)",
                                   "unit": "%", "freq": "quarterly",
                                   "source": "MoSPI NAS quarterly (computed from published levels)",
                                   "endpoint": "/api/nas/getNASData",
                                   "points": yoy,
                                   "periods": {d: periods[d] for d, _ in yoy if d in periods}}
    rel = catalogue_releases("NAS", ["Gross Value Added"])
    for s in out.values():
        s["releases"] = rel
    log.info("[INFO] [NAS] %s quarters, %s series", len(lvl), len(out))
    return out



# --------------------------------------------------------------------------- #
# OPPI - producer prices, monthly (all commodities)
# --------------------------------------------------------------------------- #
def fetch_oppi() -> dict:
    """Producer price index, all commodities, monthly + a y-o-y computed from the levels.

    OPPI needs `base_year` or it answers 400 "base year is required" - unlike every other product here,
    where base_year is optional. `limit=200` is honoured on this endpoint (161 rows a month, one page),
    which is why this walks month by month rather than paging.
    """
    rows = []
    for year in (2025, 2026):
        for m in range(1, 13):
            try:
                j = get("/api/oppi/getOppiRecords", base_year="2022-23", frequency="Monthly",
                        year=str(year), month_code=str(m), limit="200")
            except Exception:
                log.warning("[WARN] [OPPI] %s-%02d unavailable", year, m)
                continue
            rows.extend(j.get("data") or [])
    lvl, periods = [], {}
    for r in rows:
        if (r.get("major_group") or "").strip().lower() != "all commodities":
            continue
        m = MONTHS.get((r.get("month") or "").strip())
        if not m or not r.get("year"):
            continue
        d = month_start(int(r["year"]), m)
        try:
            lvl.append([d, float(r["index_value"])])
        except (KeyError, TypeError, ValueError):
            continue
        periods[d] = month_label(int(r["year"]), m)
    lvl = sorted({d: v for d, v in lvl}.items())
    out: dict[str, dict] = {}
    if lvl:
        out["act_oppi"] = {"label": "Producer price index (OPPI), all commodities",
                           "unit": "index", "freq": "monthly",
                           "source": "MoSPI OPPI monthly (2022-23=100)",
                           "endpoint": "/api/oppi/getOppiRecords",
                           "points": [[d, v] for d, v in lvl],
                           "periods": {d: periods[d] for d, _ in lvl if d in periods}}
        by_date = {d: v for d, v in lvl}
        yoy = []
        for d, v in lvl:
            prev = by_date.get(f"{int(d[:4]) - 1}-{d[5:7]}-01")
            if prev:
                yoy.append([d, round((v / prev - 1) * 100, 2)])
        if yoy:
            out["act_oppi_yoy"] = {"label": "Producer price inflation, y-o-y (computed)",
                                   "unit": "%", "freq": "monthly",
                                   "source": "MoSPI OPPI monthly (computed from published levels)",
                                   "endpoint": "/api/oppi/getOppiRecords",
                                   "points": yoy,
                                   "periods": {d: periods[d] for d, _ in yoy if d in periods}}
    log.info("[INFO] [OPPI] %s months, %s series", len(lvl), len(out))
    return out


# --------------------------------------------------------------------------- #
# IIP use-based categories - capital goods vs consumer durables
# --------------------------------------------------------------------------- #
USE_KEYS = {"capital goods": "capital", "consumer durables": "consdur", "primary goods": "primary",
            "intermediate goods": "intermediate",
            "infrastructure/construction goods": "infra",
            "consumer non-durables": "consnon"}


def fetch_iip_usebased() -> dict:
    """IIP growth by use-based category, monthly.

    The General index says industry grew; the split says whether that growth was investment (capital
    goods) or consumption (durables) - which is the question a macro reader actually asks.
    """
    rows = []
    for year in (2025, 2026):
        for m in range(1, 13):
            try:
                j = get("/api/iip/getIIPData", frequency="Monthly", base_year="2022-23",
                        year=str(year), month_code=str(m), type="Use-based category")
            except Exception:
                continue
            rows.extend(j.get("data") or [])
    out: dict[str, dict] = {}
    for r in rows:
        k = USE_KEYS.get((r.get("category") or "").strip().lower())
        m = MONTHS.get((r.get("month") or "").strip())
        if not k or not m or not r.get("year"):
            continue
        try:
            val = float(r["growth_rate"])
        except (KeyError, TypeError, ValueError):
            continue
        d = month_start(int(r["year"]), m)
        s = out.setdefault(f"act_iip_{k}", {
            "label": "", "unit": "%", "freq": "monthly",
            "source": f"MoSPI IIP monthly, use-based: {r['category']}",
            "endpoint": "/api/iip/getIIPData", "points": [], "periods": {}})
        s["points"].append([d, val])
        s["periods"][d] = month_label(int(r["year"]), m)
    rel = catalogue_releases("IIP", [])       # same catalogue rows as the General index
    names = {"capital": "Capital goods", "consdur": "Consumer durables",
             "primary": "Primary goods", "intermediate": "Intermediate goods",
             "infra": "Infrastructure/construction goods", "consnon": "Consumer non-durables"}
    for k, s in out.items():
        s["points"].sort()
        s["label"] = f"IIP {names[k.split('_')[-1]].lower()}, y-o-y"
        s["releases"] = rel
    log.info("[INFO] [IIP] use-based: %s categories, %s points", len(out),
             sum(len(s["points"]) for s in out.values()))
    return out


def _atomic_write(path: pathlib.Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    log.info("[INFO] [MoSPI] fetching PLFS / IIP / NAS from %s", BASE)
    series: dict[str, dict] = {}
    failures: list[str] = []

    for name, fn in (("PLFS", fetch_plfs), ("IIP", fetch_iip), ("IIP-use", fetch_iip_usebased),
                     ("NAS", fetch_nas), ("OPPI", fetch_oppi)):
        try:
            got = fn()
            if not got:
                raise RuntimeError("returned no series")
            series.update(got)
        except Exception:
            failures.append(name)
            log.error("[ERROR] [MoSPI] %s failed - the real-economy layer is incomplete", name)

    # COMPLETENESS GATE. A short series is worse than a missing one: it plots, it colours a tile, and
    # nothing says the history stops early. Each required series needs real history before we accept it.
    short = {k: len(series.get(k, {}).get("points", [])) for k, n in REQUIRED.items()
             if len(series.get(k, {}).get("points", [])) < n}
    if failures or short:
        log.error("[ERROR] [Gate] refusing to write raw/mospi.json - products failed: %s; "
                  "series short: %s", failures or "none", short or "none")
        return 1

    payload = {
        "fetched_at": started,
        "publisher": "Ministry of Statistics and Programme Implementation (MoSPI), Government of India",
        "api": BASE,
        "release_date": None,
        "release_date_note": ("Release dates are OBSERVED from MoSPI's catalogue "
                              "(/api/esankhyiki/cms/golden-sheet/list), which states one per table; no lag "
                              "is modelled. Where a period has no catalogue row, its release date is absent "
                              "rather than guessed."),
        "series": series,
    }
    _atomic_write(OUT, json.dumps(payload, ensure_ascii=False, indent=1))
    log.info("[INFO] [Gate] wrote raw/mospi.json: %s series, %s points",
             len(series), sum(len(s["points"]) for s in series.values()))
    for k in sorted(series):
        pts = series[k]["points"]
        print(f"   {k:18s} {len(pts):>3} pts  {series[k]['unit']:>8s}  "
              f"{pts[0][0]}..{pts[-1][0]}  last={pts[-1][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
