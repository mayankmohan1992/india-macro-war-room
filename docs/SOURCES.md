# Data sources

Everything here comes from the **Reserve Bank of India's public Database on Indian Economy (DBIE)** and
the statistical releases it mirrors. This page documents exactly which tables are used, how they are
reachable, and which traps the client encodes — so the data path can be audited rather than trusted.

- Portal: <https://data.rbi.org.in/>
- The figures are the same as RBI's Weekly Statistical Supplement / Monthly Bulletin tables.
- Definitions are quoted from RBI (and, where the index is not RBI's, from MoSPI/NSO, DPIIT or FBIL) —
  see [DEFINITIONS.md](DEFINITIONS.md).

## Tables fetched

| id | table | used for |
|---|---|---|
| **11** | Major Price Indices | CPI (combined, rural, urban, 2024=100) and WPI (all commodities + the three major groups, 2022-23 base) |
| **13** | Money Stock: Components and Sources | M3, M1 components (currency with the public, demand deposits, other deposits with the RBI), net FX assets of the banking sector |
| **7** | Reserve Money | reserve money (M0) and currency in circulation |
| **9** | SCBs — Business in India | bank credit, non-food and food credit, aggregate deposits, SCB investments; the credit-deposit ratio is derived from it |
| **10** | Ratios and Rates | policy repo rate, CRR, SLR, call money (weighted average), 91/182/364-day T-bill yields, 10-year G-sec par yield, INR–US$ and INR–Euro spot rates, US$ forward premia (1/3/6-month) |
| **2** | GoI Treasury Bills Outstanding | T-bill outstanding by tenor (91/182/364-day) and Cash Management Bills |
| **8** | Liquidity Operations by RBI | daily LAF/standing-facility operations and the net injection(+)/absorption(−) column |
| **12** | Average Daily Turnover, money markets | call, notice/term, triparty repo, market repo, corporate-bond repo turnover |
| **39** | RBI — Liabilities and Assets | notes in circulation, bankers' deposits, rupee securities, foreign currency assets, gold, loans and advances to the Centre |
| **4** | Certificate of Deposit | CD outstanding, amount issued, issuance-rate range |
| **5** | Commercial Paper | CP outstanding, amount issued, issuance-rate range |
| **6** | Cash Balances of SCBs with RBI | *fetched but not used* — the endpoint returns a partial, non-chronological subset (≈524 of 7,379 rows). Listed as a known exception so the completeness gate still fails loudly on anything else |
| **—** | key-rates snapshot | the portal's own policy-rate set (repo, SDF, CRR, SLR, bank rate, WACR, latest CPI release), used for the freshest announced values and the snapshot strip |

## The portal's indicator route (a second data surface)

The `#/dbie/indN` pages ("Indicators" in the portal menu) are **not** served by the report tables above.
They call `dbie_getWSSReport` on the **RBIDATA** gateway with a request built from named-series codes:

```json
{"body": {"requestVO": {
  "currencyCode": "", "itemCode": ["27"], "fromDate": "2024-01-01 00:00:00",
  "toDate": "2099-01-01 00:00:00", "frequency": "Annual", "reportName": "RBIB18",
  "level1Code": ["Combined"], "level2Code": ["CPI-2024 = 100"], "level3Code": ["Inflation"]}}}
```

Two things about this route cost a probe cycle and are worth recording:

* the response nests as **`body.Result`** — *not* `body.response.Result`, which is the shape the report
  gateway uses;
* it carries the **officially published** series, e.g. CPI inflation, Combined, as printed in
  "Home > Publication > Time-Series Publications > Monthly RBI Bulletin > Prices and Production >
  19 Consumer Price Index". That published figure is the one quoted in the press and compared with the
  RBI's target, so it is the headline here (`cpi_yoy_official`), while the series derived from the
  published index remains the long history on the chart.

**Timestamp encoding:** every date the portal stores is midnight **IST** (UTC+05:30). Read as UTC, each
such date lands one day early — a September observation stamped `2026-09-30T00:00+05:30` became
`2026-09-29`, and the October policy announcement became 6 Oct instead of 7 Oct. The pipeline converts
every portal timestamp in IST (`ist_date()` in `fetch_series.py`), and the verification gate asserts that
a monthly point lands on a month end.

## How the portal is read

The portal is an Angular application over six gateways on `data.rbi.org.in`; the client speaks to them
directly rather than driving a browser:

- **Gateways** — `CIMS_Gateway_{DBIE,LOGIN,REPORTS,RBIDATA,SAARC,FRBS}/GATEWAY/SERVICES` on the same host.
  The indicator tables come from `REPORTS` (`REPORTS_getReportTabs` → `REPORTS_getWSSReport`).
- **Session** — `GET /` for the WAF cookie, then `security_generateSessionToken` with the portal's own
  public `channelkey`; the token comes back in the **response header**, not the body.
- **Field crypto** — some response fields are AES-encrypted with a key derived from the session
  (`PBKDF2(password=token, salt=hex(status), 1000 iterations, SHA1, 256-bit)`), with the IV from the
  response. The constants involved are published inside the portal's own JavaScript and are an
  obfuscation layer, not a credential.
- **No secrets are needed to run this project**, locally or in CI: nothing here is an API key, and the
  workflows carry no repository secrets.

### Traps encoded in the client (each one measured, each one a silent-failure source)

| trap | effect if ignored |
|---|---|
| `versionRows` is a **partition** with arbitrary keys (`Final`, `2025-26`, …) | reading one block loses half the table (456 of 1,163 rows in one measured case) |
| tab names and region names contain **non-breaking spaces** | the gateway answers `status: success` with an empty array |
| Solr responses are **NBSP-padded** | `json.loads` fails, or fields silently don't match |
| some reports return `rows`, others `versionRows` | a whole table reads as empty |
| one report's rows are **newest-first** | a hand-built series draws backwards while every value is right |
| a report declares one more header leaf than its rows carry (a non-data `Version` column) | every column shifts by one and the dashboard publishes a nonsense figure (a 2.6% credit-deposit ratio) |
| `pageSize=0` works for some reports and returns an empty table for others | paging fallback is mandatory |
| index bases change (CPI 2012=100 → 2024=100, WPI → 2022-23) | a stale base silently publishes an outdated headline |
| a **nil balance is published as a blank cell** | a series can be years out of date with nothing to indicate it |

## Publishing and reuse

The RBI publishes these figures for public consumption, and this project reproduces them with
attribution and without modification of the underlying values. It is **not** an RBI product and is not
endorsed by the RBI; the derived figures and colour verdicts are this project's own and are documented
in [METHODOLOGY.md](METHODOLOGY.md).

When reusing the data, credit *Reserve Bank of India — Database on Indian Economy*, and verify anything
that matters at the source. Definitions quoted in `api/v1/definitions.json` remain the words of their
publishers (RBI, MoSPI/NSO, DPIIT, FBIL) and are reproduced for identification.
