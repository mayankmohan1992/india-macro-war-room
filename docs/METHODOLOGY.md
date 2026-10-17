# Methodology

How every number in this repository is produced, and what it does and does not mean. The guiding rule:
**all analysis happens in the build step, in Python, and is written down here** — the dashboard and the
API only render what the build already decided.

## 1. Pipeline

```
fetch_series.py      RBI DBIE  ──►  raw/*.json          (12 tables + the key-rates snapshot)
build_dashboard.py   raw/      ──►  dashboard/warroom_data.json + dashboard/index.html
publish_api.py       payload   ──►  api/v1/**            (JSON + CSV, schemas, manifest, status)
tools/gen_docs.py    payload   ──►  docs/DATA_DICTIONARY.md, docs/DEFINITIONS.md
verify_dashboard.py  renders the built page in headless Chromium and asserts it works
tools/validate_api.py validates the API end to end
```

### Fetching

- Whole tables are pulled with `pageSize=0` and a paging fallback; **`versionRows` is a partition with
  arbitrary keys**, so every block is concatenated (reading only the first silently loses half a table).
- Tab names and region names arrive with non-breaking spaces and must be normalised before being sent
  back, or the API answers `status: success` with an empty array.
- **Completeness gate:** a table whose row count is short of its own `totalCount` fails the run. One
  report (id 6, SCB cash balances) is a known partial response and is listed explicitly as an exception
  rather than silently tolerated; it is not used by any indicator.
- **PID lockfile:** two concurrent fetches writing `raw/` would clobber each other, and because every
  consumer reads files by name, the result would be a dashboard built on blank series with no error
  anywhere. A stale lock from a dead process is detected and taken over.

### Derived maths (all in `build_dashboard.py`)

| derived figure | rule |
|---|---|
| **y-o-y growth** | `value / value_12_months_earlier − 1`, where the base is the observation closest to 12 months back within a tolerance of 20–35 days depending on the series' frequency. Never "12 rows earlier" — the calendar is the reference, not the row count. |
| **spread** | Difference between two rates **taken from the same table and the same date**, e.g. call money minus the weekly repo. Comparing a weekly table value with a mid-week announcement invents a dislocation that is pure calendar mismatch. |
| **credit-deposit ratio** | Bank credit ÷ aggregate deposits × 100, matched on the same reporting date. |
| **money multiplier** | M3 ÷ reserve money, pairing each M3 observation with the reserve-money observation within 7 days. Derived here; RBI publishes the components, not the ratio. |
| **term spread** | 10-year G-sec par yield − 91-day T-bill primary yield, both from the same weekly table so the legs share a vintage. |
| **1-month average liquidity** | Mean of the last 22 working days of daily net LFO operations. |
| **staleness** | `newest observation anywhere on the page − this series' last observation`, in days. |
| **frequency** | Median gap between consecutive observations, bucketed (≤3 daily, ≤9 weekly, ≤20 fortnightly, ≤45 monthly, ≤120 quarterly). |

### Publication calendars (why "latest data" is not one date)

| calendar | indicators | typical lag when you read the page |
|---|---|---|
| daily | liquidity operations (net LFO, SDF/MSF balances) | a few days |
| weekly | policy rates, call money, G-Sec/T-bill yields, forward premia, T-bill outstanding, turnover, RBI balance sheet, money stock | up to a week — the supplement is published weekly |
| fortnightly | SCB credit and deposits, credit-deposit ratio, CD/CP outstanding | up to two weeks |
| monthly | CPI, WPI, M3/M1/reserve money | about a month (prices are released with a one-month lag) |

The build therefore records `dataset_as_of_by_frequency` alongside the overall newest observation, the
header renders that breakdown, and each tile carries its own period. The daily refresh re-checks the
portal every morning; if a table has not been republished, the dataset hash is unchanged and nothing is
committed — which is the correct outcome, not a failure.

### Freshness policy: settings, readings, stale and dead series

RBI does not always report every line: **a nil balance is published as a blank cell**, so a column can
simply stop having observations while its table keeps publishing rows. Three rules follow, and they are
enforced by the build and asserted by the verifier:

1. **A policy setting is dated by when it took effect.** CRR, SLR and the repo rate hold one value for
   months while the weekly table repeats it in every row. `effective_from` is the date of the last
   actual change; the tile, the `?` panel, the history table and the snapshot strip all read
   *"in force since &lt;date&gt;"*, and the size of the move is reported in basis points. (Where the
   portal's own snapshot timestamp and the published series disagree — they did, by a week, for CRR and
   SLR — the published series wins.)
2. **A stale reading is labelled, not smoothed over.** Beyond ~60 days the tile shows `stale Nd` with
   its last reported date instead of a change figure — comparing an old observation with "three months
   ago" would compare it with itself. (Monthly series lag ~36 days by design and are not flagged.)
3. **A dead series is never plotted.** No observation for over ~400 days marks a series dead: it is
   dropped from any chart and the reason is stated in the caption. The Cash Management Bills line, last
   published in Aug-2020, is the live example.

### The headline is the publisher's figure; derived series are cross-checked against it

For CPI the portal publishes an inflation series directly (`cpi_yoy_official`). It is the headline because
it is the number quoted publicly and compared with the RBI's target, and because a y-o-y recomputed from
the published index differs from it by up to ~0.05pp: the index is released rounded to one decimal, so a
computed y-o-y carries a quantisation of about ±0.05pp. The derived series (`cpi_yoy`, ~150 months) is
what the chart draws, and the build publishes a `cross_checks` block with the largest gap over the
overlapping months — currently 0.05pp over 9 months, tolerance 0.1pp. A gap beyond tolerance fails the
verification gate, so a genuine derivation error cannot hide behind "rounding".

The same principle applies to freshness: the weekly table's INR–US$ row lags up to a week, while the
portal's key-rates set carries the daily FBIL rate, so the daily rate is appended to that series and the
tile shows 95.07 for 15 Oct rather than the weekly 96.61 for 9 Oct.

### Two defensible "when" dates for a policy setting

For CRR and SLR the portal's key-rates set carries RBI's own **effective** date (the setting's own stamp),
while the weekly statement is the first published row *reflecting* it. Both are reported: the tile and the
history table use the weekly-series change date, the snapshot strip carries both (`announced_from` from key
rates, `since` from the series). For CRR that is 29 Nov 2025 (effective, key rates) and 5 Dec 2025 (first
weekly statement) — a one-week difference that is a fact about publication, not a disagreement.

### Scoring bands — conventional readings, not official verdicts

Each indicator gets `good` / `watch` / `bad` from explicit thresholds. They are published on the
dashboard (*How each colour is decided*), in every tile's `?` panel, and in the API as
`scoring_rule` + `status_reason`, so a reader can disagree with a specific rule rather than with a
colour. The main bands:

| indicator | green | watch | red |
|---|---|---|---|
| CPI inflation | 2.0–4.5% | 1.5–2 / 4.5–6 | <1.5 or >6 (the RBI's 4% ±2% band) |
| WPI inflation | 0–3% | <0 or 3–6 | >6 |
| policy rate | last move was a cut | no change | last move was a hike |
| M3 growth | 9–15% | 7–9 / >15 | <7 |
| bank / non-food credit growth | 10–16% | 8–10 / 16–20 | <8 or >20 |
| aggregate deposit growth | 10–14% | 8–10 / >14 | <8 |
| credit-deposit ratio | 70–85% | 65–70 / 85–95 | <65 or >95 |
| liquidity (1-month avg net ops) | easing ≥ ₹25k cr vs a quarter ago | ±₹25k cr | draining > ₹25k cr |
| call money vs repo | \|spread\| ≤ 0.25pp | 0.25–0.75pp | >0.75pp |
| 10-year G-sec / 91-day T-bill | −20bp or better over 3 months | within ±20bp | +20bp or worse |
| net FX assets / FCA growth | >5% y-o-y | 0–5% | <0% |
| 3-month forward premia | 0–4.5% | 4.5–6% | >6% (or <0, unusual) |
| term spread | 0.5–2.5pp | 0–0.5 / >2.5 | <0 (inverted) |
| notes in circulation growth | 3–10% | <3 / 10–14% | >14% |

A negative *level* of liquidity is **not** scored as stress: since the SDF began absorbing surplus
liquidity in 2022, permanent absorption is the normal stance, so only the *direction* versus a quarter
ago is scored. The roll-up verdict counts how many of seven core indicators are off-colour — it is a
summary of the rules above, not a forecast and not an RBI judgement.

## 2. Verification gate

`verify_dashboard.py` loads the built page in headless Chromium and asserts, exiting non-zero on any
failure:

**Shell** — zero console/page errors; on desktop the window never scrolls while the two panes scroll
independently (scrolling one leaves the other and `window.scrollY` untouched); no dead space at 7
viewport widths; 2-column grids on desktop, 1 on mobile.

**Data integrity** — every tile in the DOM with a status and a value; **every tile's value and date
equal the last observation of the series it names** (this is what catches a chart plotting a different
series than the headline); sparklines, snapshot chips and rule rows all present.

**Charts** — every card draws geometry, has a dated x-axis and a labelled y-axis, a visible legend and a
visible expand control; hover reads out the date and the value for that date and tracks the cursor;
co-plotted series are date-aligned, not index-aligned; **no two text nodes in a chart overlap**;
**the newest observation is both labelled on the axis and marked with a dot**; no chart plots a series
from the dead-series list.

**Freshness** — stale tiles display their staleness; `effective_from` is a real observation; the setting
is constant in every row from that date onward; the bp move reconciles with the previous setting.

**Interaction** — clicking a card opens its history table (headers correct, newest row equal to the
card's value, close button and Esc work, clicks inside the modal do not hijack it); clicking a chart
opens the full-size modal which zooms, pans, resets and closes; the theme toggle switches palette and
chart colours and persists; the mobile hamburger drawer opens and closes over a backdrop.

`tools/validate_api.py` then validates every API document against its JSON Schema, cross-checks the
index/latest/series/CSV against the dashboard payload, and verifies the manifest hashes and the
`dataset_sha256`.

## 3. Why the numbers can still be wrong, and what is done about it

- **The publisher revises.** Weekly and fortnightly figures are provisional and get revised; a value
  today may differ from the same date a month ago. Every API document carries both `dataset_as_of` and
  `retrieved_at`, and `status.json` carries a content hash, so a consumer can detect a revision.
- **Base years change.** CPI moved from 2012=100 to 2024=100 and WPI to 2022-23; the build uses the
  current-base columns and states the base year in the caption. Publishing a stale base silently
  produced a 1.33% "headline" during development instead of the true 4.82%.
- **Column renames are fatal, not silent.** Series are mapped by item code, and a missing code raises
  instead of falling back to a default or a column index.
- **Nothing is invented.** Where a figure cannot be sourced or derived, the UI says so ("definition
  pending", "stale Nd", "no data in this window") rather than showing something plausible.

## 4. Reproducibility

The committed `raw/` tables plus the committed code reproduce the committed `api/` and `dashboard/`
byte-for-byte apart from retrieval timestamps; CI rebuilds them on every push and compares the
`dataset_sha256`, failing if they diverge. That is why the daily workflow can safely commit only when
the data changes.
