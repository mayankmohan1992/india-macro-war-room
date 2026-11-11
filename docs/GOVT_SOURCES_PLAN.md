# Government primary sources — the real-activity layer

Replaces the CMIE idea (`CMIE_LAYER_PLAN.md`). Nothing here is licensed, nothing is scraped behind
a wall: every figure below is published by the ministry or agency that owns it.

Recon date 2026-11-11. **Status column is what was actually observed**, not what the site claims.

> **Status: v1 shipped 2026-11-11.** PLFS (monthly), IIP (monthly) and NAS total GVA (quarterly) are
> live on the dashboard, in `api/v1/`, and in the daily workflow. Two things changed on the way:
> **ISP was dropped** (its API has no overall index row — `type_code=1` is documented as "no data at
> present"), and the no-PDF rule removed every physical-volume source below. What remains of this file
> is the recon record and the revival conditions for the sources that were cut.

### Correction — the API layer (checked after the first draft)

The first pass found `api.mospi.gov.in`'s root page and its **CPI-only** user manual, and concluded
"documented API = CPI only". That was wrong. The eSankhyiki portal runs a second, newer API layer
(`portal v2.0`, Data Informatics & Innovation Division) that is **open, guest-accessible, paginated
and documented per product**. 15 products carry a real OpenAPI 3.0 spec:

| product | endpoint | product | endpoint |
|---|---|---|---|
| PLFS | `/api/plfs/getData` | HCES | `/api/hces/getHcesRecords` |
| CPI | `/api/cpi/getCPIData` | Energy Statistics | `/api/energy/getEnergyRecords` |
| WPI | `/api/wpi/getWpiRecords` | AISHE | `/api/aishe/getAisheRecords` |
| IIP | `/api/iip/getIIPData` | UDISE | `/api/udise/getUdiseRecords` |
| NAS | `/api/nas/getNASData` | Gender Statistics | `/api/gender/getGenderRecords` |
| ASI | `/api/asi/getASIData` | NFHS | `/api/nfhs/getNfhsRecords` |
| ISP (services output) | `/api/isp/getISPRecords` | TUS | `/api/tus/getTusRecords` |
| ASUSE | `/api/asuse/getAsuseRecords` | RBI statistics | `/api/rbi/getRbiRecords` |

No spec (SPA fallback): environment, economic census, NSS rounds.

Verified live: `GET api.mospi.gov.in/api/plfs/getData?indicator_code=3&frequency_code=3&year=2026&month_code=9`
returned **200, 27 records over 2 pages**, each already labelled — `{"indicator":"UR (Unemployment
Rate)","year":"2026","month":"September","state":"All India","AgeGroup":"15 years and above",
"gender":"male","sector":"rural","value":"4.4","unit":"%"}` — with `meta_data
{page,totalRecords,totalPages,recordPerPage:20}`.

This supersedes the XLSX route for every MoSPI product: **JSON with labels, server-side filtering,
pagination, no token, no header-guessing.** The XLSX path in §3 stays as the offline fallback.

### Decision — API or XLSX only, no PDF parsing

PDF is the most brittle surface there is: layout shifts silently, tables split across pages, and the
parser keeps returning numbers after the format changes. So the rule is now **JSON API or XLSX only**,
and every figure must arrive with the reference period its publisher states.

That cuts the portfolio hard. Dropped:

| Source | Why it fails the rule | Could return if |
|---|---|---|
| Petroleum (PPAC) | Flash Report + ICR are PDFs | PPAC ships the consumption table as XLSX |
| Coal, Steel | monthly pages are HTML + PDF | ministry publishes a data file |
| Power (CEA / Grid-India) | PDF; the National Power Portal exposes map configs, no data API | NPP publishes a JSON endpoint |
| Ports (IPA) | host is DNS-dead; successor serves weekly PDFs | monthly cargo table in XLSX |
| Reservoirs (CWC) | PDF bulletins; the live-table host no longer resolves | CWC restores RSMS |
| Telecom (TRAI) | QPIR and subscription reports are PDFs | TRAI ships XLSX |
| Trade (DGCIS) | HTML, login for downloads | — |
| GST collections | revenue lives in a PIB press release (HTML/PDF), no file | GSTN publishes a revenue dataset |
| UPI (NPCI) | HTML table, no download control, no API | NPCI publishes a file or feed |
| MGNREGA | HTML dashboard / MIS screens | MIS roster export as XLSX |
| CGA fiscal | dashboard file stale by 9 months | file catches up (and DBIE covers fiscal anyway) |

What survives is narrower but cleaner — **the whole MoSPI statistical system, by API**:

| Product | Endpoint | Cadence | Why it matters here |
|---|---|---|---|
| PLFS | `/api/plfs/getData` | monthly / quarterly / annual | labour — the gap with no substitute |
| IIP | `/api/iip/getIIPData` | monthly | industrial output, by sector and use |
| ISP | `/api/isp/getISPRecords` | monthly | services output — nothing else covers it |
| NAS | `/api/nas/getNASData` | quarterly | GDP, GVA, consumption, investment |
| ASI | `/api/asi/getASIData` | annual | factory sector: output, employment, wages |
| HCES | `/api/hces/getHcesRecords` | periodic | household consumption, inequality |
| Energy | `/api/energy/getEnergyRecords` | annual | energy production and consumption |
| ASUSE | `/api/asuse/getAsuseRecords` | annual | unincorporated enterprises / MSME |
| TUS | `/api/tus/getTusRecords` | periodic | time use — unpaid work |
| Gender, NFHS, AISHE, UDISE | respective endpoints | periodic | social layer, later |

**The cost of the rule, stated plainly:** the physical-volume story (coal dug, fuel burnt, power
generated, cargo moved, UPI transacted) is almost entirely PDF- or HTML-only, so dropping it means the
real-activity layer rests on *official indices* rather than physical units. That is a real loss of
granularity — but an index from an API that never breaks beats a volume series that silently rots.
CPI, WPI and the RBI statistics endpoints are excluded on overlap, not on format: DBIE owns those.

### The date rule, and the disclaimer it requires

Every stored observation carries three separate fields, and the page displays the first:

1. `ref_period` — the period the publisher states for that observation (e.g. `Sep 2026`).
2. `release_date` — when the publisher loaded it into its database, taken from the catalogue, never inferred.
3. `fetched_at` — when this project pulled it.

The distinction matters because a ministry can announce a number on one date and publish it to its
database on a later one. The dashboard footer now carries that as a standing note (added 2026-11-11,
rendered at the end of the page under a dotted rule):

> **Dates, and how a figure reaches this page.** Every series here is an official publication of the
> body named beside it (Reserve Bank of India, MoSPI/NSO, and others), reproduced without alteration,
> and carries the reference period that publisher states — not the date this page was built. Government
> bodies routinely announce a figure on one date and load it into their database on a later one,
> following their own update cadence; where that happens, this page shows the value as it appears in the
> publisher's database, with its stated period. A figure announced but not yet published to the database
> is not shown here, and no date on this page should be read as the announcement date. Where a publisher
> revises history, this page carries the current vintage, not the vintage originally published — so a
> value can differ from the one reported in the press on the day it was announced.

---

## 1. Why this shape

The war room today is a **financial-conditions** dashboard: prices, money, credit, rates, liquidity,
FX, RBI's balance sheet. Every one of its 66 series is a price, a rate or a balance.

What it cannot see is **physical activity** — how much power was generated, coal dug, fuel burnt,
cargo moved, GST collected, UPI transacted, water stored, people employed. That is the layer where
recessions and recoveries actually show up first, and it is exactly the layer DBIE does not carry.

So the split is clean by construction:

- DBIE → money, credit, rates, prices, reserves (already there).
- Ministries → volumes, counts, physical flows (new, and no overlap by definition).

The joint product is a divergence panel: *credit growth says expansion while coal offtake, power
demand and e-way bills say deceleration* is a warning you cannot see from either layer alone.

## 2. What is verified live and current

*Record of the recon. Only the API/XLSX rows are eligible under the no-PDF decision below — the PDF
rows are kept here as evidence of what exists and why it was cut, not as candidates.*

| Source (owner) | Cadence | Latest observed | Format | Machine-readable | Status |
|---|---|---|---|---|---|
| **PLFS monthly** — MoSPI/NSO | monthly, 15th | **Sep 2026** (released 15 Oct 2026) | XLSX per indicator per month | **Yes** — `api.mospi.gov.in/api/esankhyiki/file/download/datacatalogue/PLFS/Monthly/2026/UR_September_2026.xlsx` | **Proven end-to-end** (§3) |
| **esankhyiki catalogue** — MoSPI | continuous | 577 PLFS catalogue rows, each with release date + table no. | JSON-ish HTML catalogue, XLSX payloads | Yes | **Verified**, NDSAP/GSDD metadata |
| **UPI statistics** — NPCI | monthly | **Oct 2026**: 758 banks, 25,466.70 mn txn, ₹31,52,929 cr | HTML table + download | Yes (table scrape, `Download` control) | **Verified** values read |
| **Petroleum** — PPAC (MoPNG) | monthly | Flash Report **Oct 2026**, ICR **Sep 2026**, crude basket 31-10-2026 | PDF | No (PDF) | **Verified** |
| **Coal** — Ministry of Coal | monthly | **Sep 2026** at-a-glance | HTML + PDF | Partial | **Verified** |
| **Steel** — Ministry of Steel | monthly | **Oct/Nov 2026** | HTML + PDF | Partial | **Verified** |
| **Telecom** — TRAI | monthly/quarterly | QPIR **12-10-2026**, subscription reports | PDF | No | **Verified** |
| **GST** — GSTN | monthly news + revenue on 1st | news **04-11-2026** | HTML | Partial | **Verified** (revenue figure lives in the PIB release) |
| **MGNREGA** — MoRD | continuous, FY2026-27 live | 10.99 Cr active workers, 9.11 Cr person-days | HTML dashboard + MIS reports | Partial | **Verified** live |
| **Trade** — DGCIS/commerce | monthly | site live, Apr 2026 refs | HTML, login for some downloads | Partial | Reachable, unverified depth |
| **Fiscal monthly** — CGA | monthly accounts | homepage shows Nov 2026 | **dashboard file stale — "upto February 2026"** | — | **Reject**: DBIE already covers fiscal, and this file is 9 months behind |

## 3. Proof: PLFS ingest actually works (XLSX fallback path)

Kept because it is the offline route if the API ever rate-limits: three monthly files pulled and
parsed today (no key, no login, ₹0):

```
UR_September_2026.xlsx  17,486 B
UR_August_2026.xlsx     17,661 B
UR_July_2026.xlsx       16,901 B
LFPR_September_2026.xlsx 17,840 B
```

Parsed: **164 rows × 18 months, 2025-04 → 2026-09**, long format. The file is **self-superseding** —
each new month's file carries the entire history, so a backfill is one download and the newest file
is always authoritative.

Spot-check against the published bulletin: all-India UR, Sep 2026 = **5.0%**, rural 4.2%, urban 6.9%,
male 4.9%, female 5.2% — all reproduced from the XLSX.

**The file has no header.** It is bare integer codes, discovered by matching values to the bulletin:

| column | meaning | codes |
|---|---|---|
| date | Excel serial (1899-12-30 epoch) | 46266 = 2026-09-01 |
| col 2 | region | 7 = rural, 11 = urban, 12 = all-India |
| col 3 | sex | 8 = male, 9 = female, 10 = person |
| cols 4-6 | age groups | three bands, 15+ first |

Getting this wrong produces a plausible-looking series with rural and urban swapped. Encode the
mapping in the adapter with these assertions, not in a comment.

## 4. Overlap rules against DBIE

Hard rule: **a series has exactly one owner.** If the same number is on DBIE, DBIE keeps it.

| Take from ministries | Do **not** take (already DBIE, or duplicative) |
|---|---|
| IIP, core industries, PLFS, MGNREGA | CPI, WPI, money stock, credit, deposits |
| Power generation/demand, coal, steel, petroleum | repo, call, T-bill, G-sec, forwards |
| Ports cargo, e-way bills, GST collections, UPI | LAF, CD/CP outstanding, turnover |
| Reservoir storage, mandi prices, rainfall | FCA, gold, notes in circulation, GoI liabilities |
| Monthly commodity trade (DGCIS) | BoP (DBIE), state finances (RBI + DBIE) |

MoSPI publishes CPI **and** PLFS from the same portal. Taking CPI from MoSPI because it is
convenient is how a dashboard ends up with two CPI series that differ in the second decimal and
nobody knows which is which. PLFS only; CPI stays on DBIE.

## 5. Scope

### v1 — four adapters, all JSON API, all free (≈3-4 days)
1. **PLFS** UR / LFPR / WPR, monthly × sector × gender × age — `/api/plfs/getData`. Labour, the gap
   with no substitute in DBIE.
2. **IIP** monthly, sector and use-based — `/api/iip/getIIPData`. Nothing in the war room covers
   industrial output today.
3. **ISP** services production, monthly — `/api/isp/getISPRecords`. The services side is entirely
   unrepresented.
4. **NAS** GDP / GVA / consumption / investment, quarterly — `/api/nas/getNASData`. The war room has
   *no* national accounts at all.

Four endpoints, one host, one adapter shape, ~20 series. No scraper, no PDF, no key.

### v2 — same API, lower frequency (≈1 week)
**ASI** (factory output, employment, wages), **HCES** (household consumption, inequality), **Energy**,
**ASUSE** (MSME/informal). All are already on the same API surface; they are deferred only because
annual/periodic series add little to a monthly read and a lot to the tile count.

### v3 — only if a source changes its publishing format
Mandi prices via the **data.gov.in JSON API** (`9ef84268-d588-465a-a308-a864a43d0070`, free key,
currently `{"error":"Authorization field missing"}` without one). It is an API, not a parse, so it
passes the rule — it is deferred only because it needs a key and a daily crawl for a weekly-useful
number.

### Permanently dropped
Everything in the "Dropped" table above — petroleum, coal, steel, power, ports, reservoirs, telecom,
trade, GST collections, UPI, MGNREGA, CGA. Each is PDF-first or a bare HTML table. None is coming back
unless the publisher ships a file or an endpoint; that is the revival condition, and it is worth
re-checking once a year rather than re-probing monthly.

## 6. Point-in-time: the quiet win

DBIE has **no release dates** — which is why `macro-signal-studio` models publication lags and
carries "lags are modelled, not observed" as a standing caveat. esankhyiki solves this for free: every
catalogue entry carries `Release Date` and a table number (e.g. PLFS Sep 2026 → 15 Oct 2026,
`PLFSFY26003SEP`, released under GSDD/NDSAP).

So any series adopted through esankhyiki gets an **observed** `pub_date` instead of a guessed one.
That is strictly better than what the existing DBIE pipeline can do, and it should be stored per
observation (`fetched_at`, `release_date`, `table_no`) — a schema change the war room needs anyway.

## 7. Traps found (each cost a probe)

| Trap | Effect | Handling |
|---|---|---|
| `api.mospi.gov.in` requires **unsafe legacy TLS renegotiation** | `curl` fails with `SSL routines::unsafe legacy renegotiation disabled`; looks like the file is gone | Fetch via browser context (returns 200, 17,486 B) or a TLS-relaxed client. Never conclude "download unavailable" from the curl error. |
| esankhyiki XLSX has **no header row** | rural/urban or male/female silently swapped | Hard-coded code map + assertion against the published bulletin |
| Each monthly file **supersedes** history | naive append duplicates 18 months every run | Replace-by-month, keyed on (indicator, ref_month) |
| `ipa.nic.in`, `old.cwc.gov.in` **do not resolve** | dead links in the ministry's own nav | Treat DNS failure as source-retired; find the successor, do not retry |
| CGA dashboard file **9 months stale** while the homepage is current | publishing an old fiscal number as if new | Freshness gate on the *file's* period, never the page's |
| `cga.nic.in`, `vahan.parivahan.gov.in`, `npci.org.in` → **403** to curl | false "blocked" verdicts | Browser UA + browser context for these hosts |
| NPCI, GST, shipmin are **HTML tables/PDFs**, not feeds | brittle parsing | Prefer the `Download` control where offered; pin the table schema and fail loudly on change |
| data.gov.in is **key-gated but free** | `{"error":"Authorization field missing"}` | Register a key; do not scrape Agmarknet's broken endpoint instead |

## 8. Cost, effort, rollback

- **Cost: ₹0.** No licences, no subscriptions, no redistribution problem — these are government
  publications, and the war room may cite and reproduce them with attribution (as it already does for
  DBIE).
- **Effort:** v1 ≈ 3-4 days (four endpoints, one host, one adapter shape); v2 ≈ 1 week.
- **Maintenance:** four adapters in v1, all on one API, so one client and one failure mode. The real
  burden is *publish-lag variance* — PLFS on the 15th, IIP near month-end, NAS quarterly — so each
  series needs its own freshness threshold, or one late release turns the whole dashboard yellow.
- **Rollback:** purely additive — a new `act_*` namespace alongside the existing 66 series. Nothing
  in the current payload changes, so deleting the new adapters restores today's dashboard exactly.
- **Second-order:** the payload grows, so the "what changed" panel must distinguish *new month* from
  *late publisher*, or it will cry wolf every month-end. The footer disclaimer exists for the reader's
  side of the same problem.

## 9. Order of work

1. PLFS adapter — the gap with no substitute.
2. IIP — the standard monthly activity read.
3. ISP — services, entirely absent today.
4. NAS — quarterly national accounts; slowest cadence, largest context win.
5. ASI, HCES, Energy, ASUSE — same API, when the monthly panel is settled.
6. data.gov.in mandi prices — only if a key is registered anyway.
