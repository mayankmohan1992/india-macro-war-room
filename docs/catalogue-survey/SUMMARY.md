# eSankhyiki catalogue survey — 4,876 datasets, mapped

Date 2026-11-11. Four parallel surveys covered every product in MoSPI's e-Sankhyiki catalogue
(33 product tiles + an `ALL` row = **4,876 datasets**). This file merges them into the decisions that
matter for this project. Per-slice evidence (with sample records and evidence URLs) is in
`slice_catalogue_map.json`, `slice_prices_industry.json`, `slice_household.json`, `slice_social.json`
alongside this file.

**What changed because of the survey:** three things we had shipped or documented were wrong or
incomplete, and one of them was worth acting on immediately.

| Finding | Action |
|---|---|
| The catalogue is itself queryable, and its rows carry **`ref_period` + `release_date`** | **Implemented.** Release dates are now observed, not modelled — `fetch_mospi.py` reads them from the catalogue. PLFS Sep 2026 → 2026-10-15; IIP Sep 2026 → 2026-10-28. |
| **ISP is not "no data"** — the overall index row is absent, but 19 broad sub-sector series publish monthly to Aug 2026 | Corrected in the docs; a sub-sector chart is now a candidate (no headline index exists, so none is shown). |
| "15 products have an OpenAPI spec" was imprecise | Corrected: 15 spec files resolve on the API host, but only **12 of the 33 catalogue products** map to one; AISHE / UDISE / NFHS have live endpoints and zero catalogue rows. |

---

## 1. The machine-readable route into the catalogue

Undocumented, but it is the same API host and the same shape as the data endpoints:

```
GET https://api.mospi.gov.in/api/esankhyiki/cms/golden-sheet/list
    ?page=1&limit=200[&product=PLFS][&ref_period=Sep 2026][&keywords=...][&table_name=...][&unique_id=...]
→ {"data":[{catalogue_code, product, table_name, year, category, geography, frequency,
            ref_period, release_date, data_source, description, file_name, file_path, ...}],
   "meta_data":{page,totalPages,totalRecords,recordPerPage}, "msg":"Data fetched successfully", ...}
```

Sibling routes: `cms/golden-sheet/mappings` (per-product counts, including the `product=ALL` row →
4,876 = the published total), `cms/golden-sheet/distinct-products` (33 product labels, 7,526 keywords,
2,764 table names, 15 ref_periods), `cms/golden-sheet/products/<catalogue_code>`, and
`file/download/<file_path><file_name>` for the XLSX behind any row.

Rules measured, not assumed:

- `limit` is **capped at 200** (`400 Limit cannot be greater than 200`); default page size 10.
- Past the last page it answers **HTTP 200 with `data: []`** — stop on empty data, never on the status.
- Filters are **exact and case-sensitive**: `product=CPI` → 499 rows, `product=cpi` → 0.
- Filter vocabulary is mixed: `WMI`, `ESI`, `SAAHLL`, `AIDIS` return 0; the display names
  (`Women and Men in India`, `Energy Statistics India`, …) are what match.
- **Zero catalogue rows does not mean no data.** WPI, ISP, OPPI, SPPI, CPI-AL/RL and BMW list 0
  catalogue rows while serving live JSON. Read `dataset_count` as catalogue coverage only.
- The host rate-limits: **429 + `Retry-After` after ~10 rapid calls**. Fetch pacing in
  `fetch_mospi.py` is 0.6s per catalogue page, with 429 handling in `get()`.

## 2. What to adopt, ranked

| # | Product | Cadence | Why it is worth it | Overlap |
|---|---|---|---|---|
| 1 | **OPPI** (producer prices) | monthly, 161 rows/mo to Aug 2026 | The producer-price layer the page lacks; WPI is wholesale, OPPI is output-price based | None in DBIE/current layer |
| 2 | **IIP use-based + sectoral detail** | monthly | One extra parameter on the adapter already shipped: capital goods vs consumer durables is the growth read that matters | Extends IIP we already publish |
| 3 | **ISP broad sub-sectors** | monthly to Aug 2026 | 19 services series; no overall index exists, so chart 3-4 (trade, transport, telecom, IT) | None |
| 4 | **ASI** | annual, 57 indicators × 16 FY × 39 states × NIC 2/3/4-digit | Factory GVA, employment, wages, capex, physical coal/electricity consumed — the value/employment side of the IIP volume we show | None |
| 5 | **ASUSE** | annual (quarterly QBUSE exists as XLSX only) | Informal-sector establishments, workers, GVA — the missing majority of employment | Partly with PLFS employment counts |
| 6 | **AIDIS** (NSS 77) | survey round | Household debt and assets: the one real gap — no DBIE table covers it | None |
| 7 | **HCES** | two rounds (2022-23, 2023-24) | Consumption level and Gini; the standard inequality input | None |
| 8 | **WMI demographics** (narrow slice) | annual, state × rural/urban | TFR, IMR, MMR, life expectancy, sex ratio — the only API-served, annually-maintained demography | Must exclude its PLFS labour and RBI banking rows, or it becomes a second UR series that disagrees with PLFS |

Everything else is either a **single survey round** (better as a static cross-section than a live tile)
or stale: NSS 71/72/73/74/76 rounds, Children/Youth in India compendia (republished SRS/UDISE/NFHS),
Health/Education in India (2014), SCE/SCH (2017-18), DWSHHC (2018), PWDII (2018), DTI (2014-15),
CII/YII (compendia), SOA (Ayush, one round), NII and TASI (no working API), EC 4/5/6 (microdata portal),
and **RBI statistics** — a partial republication of DBIE with weaker coverage, which would create the
two-vintages problem this project already refuses for CPI.

## 3. Traps for whoever builds the next adapter

Each one was hit during the survey; each produces a plausible wrong answer rather than an error.

- **`indicator_code` is an integer on some products and the exact indicator-name string on others**
  (HCES, TUS, ASUSE, NSS 77). Passing `1` to a name-enum product returns HTTP 200,
  `statusCode: true`, `data: []` — a silent empty.
- **One endpoint serves two catalogue products.** `/api/nss-<round>/getNss<round>Records` covers
  71 = EII + HII, 73 = UNAEI + OCUAEI, 75 = SCH + SCE, 76 = PWDII + DWSHHC, 77 = AIDIS + SAAHLL,
  79 = CAMS + SOA — with no product discriminator. Split on indicator name.
- **`Format=JSON` is required** on `/api/nss-77/*`, or it 500s.
- **TUS with an integer `indicator_code` times out past 120s**; the name string returns 61,325 rows.
- **Two spec vintages disagree**: `api.mospi.gov.in` serves v1.0.11 paths (`getCPIIndex`,
  `getIIPMonthly`) while `esankhyiki.mospi.gov.in` serves v2.0.0 (`getCPIData`, `getIIPData`) with
  different field names for the same data. Pin one — this project pins the v2.0 API host.
- **Spec YAMLs return `text/html` or `application/octet-stream` unless `Accept` includes yaml**, and a
  miss is HTTP 200 with a 486-byte swagger-ui shell: test the body prefix `openapi:`, not the status.
- **ISP `month_code` is the fiscal month** (1 = April), not the calendar month.
- Unknown API paths return the SPA's HTML with **HTTP 200** — check `content-type`.

## 4. What is still deliberately absent

- **A headline services index.** ISP has no overall row (`type_code=1` documented as "no data at
  present"), so a single all-services number would have to be invented from weighted sub-sectors whose
  weights are not published through the endpoint.
- **State-level monthly labour.** PLFS monthly is all-India only; state detail is quarterly/annual.
- **Post-2011 census demographics.** The census sex-ratio series on the portal stops at 2011.
- **NAS quarterly release dates.** The catalogue states NAS rows per financial year, so its quarters
  carry no release date rather than borrowing the year's.
