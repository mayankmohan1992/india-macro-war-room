# Dashboard guide

How the interface works and why it is built this way. For the data side see
[METHODOLOGY.md](METHODOLOGY.md); for the endpoint reference see [API.md](API.md).

A single self-contained page showing the health of the Indian economy at a glance: **38 indicators and
26 charts**, each with its trend and a green / amber / red verdict from explicit published rules.
**All the number-crunching happens at build time in Python; the page only draws lines and colours.**

Open `dashboard/index.html` - it works offline over `file://`, with no server and no CDN.

```bash
scripts/refresh.sh                 # fetch -> verify provenance -> build -> publish API -> docs -> validate -> verify (~5 min)
scripts/refresh.sh --build-only    # re-render from the raw JSON already on disk
```

## What it watches

| Section | Indicators (tile = value + trend + verdict) |
|---|---|
| Inflation | CPI y-o-y, WPI y-o-y |
| Policy, money & liquidity | policy repo rate, call money rate (vs repo), RBI net liquidity operations, M3 growth, reserve money growth, notes in circulation |
| Credit & banking | bank credit growth, aggregate deposit growth, credit-to-deposit ratio, SCB investment growth, non-food credit growth, food credit growth |
| External, fiscal & markets | net FX assets of the banking sector, RBI foreign currency assets, 10-year G-sec yield, 91-day T-bill yield, 3-month US$ forward premia, RBI gold holdings, T-bill outstanding, CD outstanding, CP outstanding, money-market turnover |
| Plus | a dated policy/market snapshot strip (repo, SDF, MSF, bank rate, call money, USD/INR, CRR, SLR, released CPI, WACR) and the full rule table |

Charts (18): CPI vs the 4% target band; WPI vs CPI; policy rate + call money + 10-yr G-sec; M3 vs reserve
money; daily liquidity operations (bars) with the 1-month average; SDF vs MSF standing facilities;
reserve money vs currency in circulation; the yield curve (91/182/364-day T-bills vs the 10-year G-sec);
credit vs deposit growth; credit mix (total, non-food, food); credit vs SCB investments;
credit-to-deposit ratio; T-bill outstanding (total and by tenor); CD vs CP outstanding; CD and CP
issuance rates; US$ forward premia (1/3/6-month); RBI reserve assets (FCA and gold).

## Reading the charts

- **Axes on every chart**: dated x axis (day + month for short windows, month + year for long ones) and a
  labelled y axis carrying the unit (%, ₹ crore, ₹ per US$).
- **Hover any point** to read the exact value for that date — a crosshair snaps to the nearest
  observation and a tooltip lists every plotted series (`Sep 2024 · CPI y-o-y 4.82%`). Works on the
  cards and in the full-size view, on the bar chart too (daily value plus the 1-month average).
- **Every chart is visibly interactive.** Each card carries its own legend bar (colour swatch + series
  name, one entry per line plotted) and an explicit **⤢ EXPAND** button next to the `?`; clicking the
  button *or anywhere on the card* — title, legend or plot — opens the full-size view with zoom
  (`+`/`−`/wheel, 6 points up to the full stored history), pan (drag, arrow keys) and reset.
  The legend bar also states it: *"click chart to expand · hover for values"*.
  (Regression this fixes: the charts were only clickable on the plot area and had no visible
  affordance at all, so the page read as static line graphs. `verify_dashboard.py` now asserts a
  visible legend and a working expand control on **all 18** charts, via both routes.)
- **Click the `?`** on any tile or chart for the official RBI / Government of India definition of that
  figure, with the source page. All 25 terms are covered and stored in `definitions.json`; the build
  loads them and never writes them from memory — a term without a sourced entry renders as
  "definition pending" instead of a guess, and `verify_dashboard.py` asserts both paths.

  Sources used, each verified live before use: MoSPI/NSO PIB release (CPI base 2024=100), DPIIT/Office
  of the Economic Adviser PIB release (WPI base **2022-23**), RBI Act ss. 45ZA/45ZB and the monetary
  policy framework (policy repo rate, MPC), RBI's Handbook on the Weekly Statistical Supplement
  (bank credit = food + non-food, aggregate deposits, investments, money stock, reserve money,
  notes/currency in circulation, FCA, gold), RBI Master Directions on Certificates of Deposit (2021),
  Commercial Paper (2024) and CRR/SLR (2021), FBIL Reference Rate page and the FBIL Forward Premia
  Curve methodology, FBIL G-Sec par yield notes, and the WSS 'Ratios' table (credit-deposit and
  incremental credit-deposit ratios).

## Layout & interaction

- **No dead space.** The tile area is a fixed six-column grid and every tile carries an explicit column
  span, so each section's spans sum to a multiple of six: rows are always completely filled instead of
  leaving a hole at the end of a row (the auto-fill grid left a five-sixths-empty row when a section
  held a single tile). Charts sit in an exact two-column grid and the snapshot strip in five columns
  (ten chips = two full rows). `verify_dashboard.py` asserts a right-edge gap of 0px for every row at
  seven viewport widths from 480px to 1760px, and that nothing overflows horizontally.
- **Click any chart to open it full size.** The modal re-renders the same series at a much larger size
  with its own zoom state:
  - `+` / `−` and the mouse wheel zoom in and out (8 window sizes, from 6 points up to the full stored
    history — the readout shows e.g. `60 pts shown · 152 stored`);
  - drag sideways, or use `←`/`→`, to pan back through history (`60 pts shown · 44 back`);
  - `reset` returns to the chart's default window;
  - close with the **✕ button at the top right**, `Esc`, or a click on the backdrop. Focus returns to
    the chart you opened, and the page behind is scroll-locked while it is open.

## How the colours are decided

Every tile carries its rule, visible on hover and listed in the page's last section. The bands are
conventional market/RBI readings, **not official verdicts**, and the ones without a published
threshold are labelled as the customary read:

| Indicator | Green | Amber | Red |
|---|---|---|---|
| CPI inflation | 2–4.5% (inside the 2–6% tolerance band, near the 4% target) | 1.5–2 or 4.5–6 | <1.5 (deflation) or >6 |
| WPI inflation | 0–3% | <0 or 3–6 | >6 |
| Policy repo rate | last move was a cut | no change | last move was a hike |
| Call money spread vs repo | ≤ 0.25pp | 0.25–0.75pp | > 0.75pp |
| M3 growth | 9–15% | 7–9 or >15 | <7 |
| Reserve money growth | 8–14% | 5–8 or >14 | <5 |
| Bank credit growth | 10–16% | 8–10 or 16–20 | <8 or >20 |
| Deposit growth | 10–14% | 8–10 or >14 | <8 |
| Credit-to-deposit ratio | 70–85% | 65–70 or 85–95 | <65 or >95 |
| Liquidity (1-mth avg net ops) | easing > +₹25k cr q-o-q | ±₹25k cr | draining > ₹25k cr |
| 10-yr G-sec yield | −20bp or better in 3 months | flat | +20bp or worse |
| Net FX assets | >5% y-o-y | 0–5% | <0% |
| T-bill outstanding | 3-month change ≤ −5% | −5…+10% | > +10% (heavier short-term borrowing) |
| CD / CP outstanding | ±20–30% y-o-y band | outside | — |
| Money-market turnover | within ±20% y-o-y or expanding | >20% contraction | — |
| Notes in circulation | 3–10% y-o-y | <3 or 10–14% | >14% |

The header verdict is a roll-up of the seven core tiles (CPI, WPI, M3, credit, liquidity, repo, call money):
≥2 red → "stress signals in core indicators"; any red or ≥3 amber → "mixed"; otherwise "broadly stable".

## Data sources (all RBI, public, no login)

`https://data.rbi.org.in` — the REPORTS gateway's report tables, fetched whole and paged to `totalCount`:

Cross-checks that validate the pipeline against the central bank's own publications: the computed
credit-deposit ratio (80.98%) sits inside RBI's published WSS range for recent fortnights
(80.28/80.32/80.84%), and the fetched tables line up with the WSS handbook's own item numbering
(7 Bank Credit, 7a.1 Food Credit, 2.1 Aggregate Deposits, 6 Investments, 8 Liquidity Operations).

| id | table | used for |
|---|---|---|
| r11 | Major Price Indices | CPI (2024=100), WPI (2023=100) |
| r13 | Money Stock | M3, net FX assets of the banking sector |
| r7 | Reserve Money | reserve money, currency in circulation |
| r9 | SCBs – Business in India | bank credit, aggregate deposits, CD ratio |
| r10 | Ratios and Rates (weekly) | repo, call money, 10-yr G-sec, MSF, bank rate, USD/INR |
| r8 | Liquidity Operations (daily) | LAF net injection/absorption |
| r2 / r4 / r5 / r12 | T-bills, CD, CP, money-market turnover | fiscal & market issuance |
| r39 | RBI Liabilities and Assets | notes in circulation, foreign currency assets, gold, bankers' deposits |
| DBIE home | key-rates snapshot | latest announced repo/SDF, CRR, SLR, released CPI, WACR |

## Files

```
fetch_series.py        pulls the tables          -> raw/*.json (+ raw/survey.json)
series_lib.py          shared table fetcher (paging, column alignment, version partitions)
build_dashboard.py     analysis + scoring + rendering -> dashboard/index.html + warroom_data.json
template.html          the page (dark war-room styling, hand-rolled SVG charts, no dependencies)
verify_dashboard.py    headless-Chromium render assertions + screenshot
refresh.sh             fetch -> verify_provenance -> build -> publish_api -> gen_docs -> validate_api -> verify, logged to logs/
dashboard/index.html   THE DELIVERABLE (self-contained; data inlined)
```

## Known data caveats (found while building, all handled)

- **Base changes.** The 2012=100 CPI column stops at Dec-2025 and the 2012=100 WPI column at Apr-2026;
  using them published a stale headline. The dashboard uses the current 2024=100 CPI and 2023=100 WPI
  columns (back-cast history to 2013 / 2023); both bases agree within ~0.15pp where they overlap.
- **WPI April-2026 step.** Both WPI bases carry an unusual +4% month-on-month jump in Apr-2026, so the
  WPI tile says the level is provisional.
- **Report 6 excluded.** SCB cash balances with RBI returns only 524 of its claimed 7,379 rows, in
  non-chronological order — not usable as a series, so no tile is built on it.
- **Vintages.** Weekly and fortnightly tables lag the daily ones by a few days. The call-money spread is
  computed only within the same weekly table; the repo tile uses the newest announcement. Each tile and
  every snapshot chip shows the period it belongs to.
- **Legacy rates.** The portal's key-rate snapshot still lists a 2020-era "Reverse Repo Rate"; it is
  deliberately omitted from the snapshot strip.
- **Chart alignment.** Multi-line charts join series of different lengths and frequencies (CPI vs WPI,
  M3 vs reserve money, CD vs CP), so they are plotted against a union date axis, not by position.
  `verify_dashboard.py` asserts the series don't share a left edge — the check that caught WPI being
  drawn a decade early.
- The scoring bands are heuristics for orientation. Nothing here is investment advice.


## Layout: a fixed-viewport console (desktop) with two independent panes

The brief was "see the war room at a glance without scrolling too much", so the page is an app shell
rather than a document:

- **On desktop the window itself never scrolls** (`body{height:100dvh;overflow:hidden}`). The body is a
  grid: a **left rail of compact indicator tiles (2 per row)** and a **right pane of charts (2 per row)**,
  and *each pane scrolls independently* — scrolling the rail does not move the charts or the window.
- **Three density levels** (Comfort / Compact / Fit all) change the charts' aspect ratio so more rows fit.
  Measured, not estimated: on a 1440x900 window Comfort shows 4 charts + 11 tiles at once, Compact/Fit-all
  6 + 11; on 1920x1080 Fit-all shows **8 charts + 14 tiles**. A legible one-screen view of all 26 charts
  and 38 tiles at once is not physically possible — so the glance is served by the **Worst first** sort,
  which floats the stressed indicators to the top of the rail, and by the verdict strip in the header.
- **Mobile (<=980px)**: the rail becomes an off-canvas drawer behind a hamburger (with a backdrop),
  the charts drop to one column and the page scrolls normally.
- **Colours are read from CSS custom properties at render time**, so light/dark mode is one source of
  truth; the palette follows the reference design (see below) and includes a dark variant.

## Design language (from getartcraft.com, as requested)

Taken from that site's own stylesheet rather than approximated: paper `#f2f1ee` / raised `#faf9f7` /
sunken `#e9e8e4` / ink `#101014` (dark: `#121316`/`#101014`/`#060607`), **square corners everywhere
(`border-radius:0`)**, 1px hairline rules, a single blue accent `#2d81ff`, and its app palette for status
(green `#1f9d55`, amber `#f2a516`, red `#e8573f`) — green/amber/red are used for status only, never as
decoration. **Archivo** (the site's typeface) is embedded as a 34 KB base64 variable font so the design
survives offline; micro-labels are uppercase at `.14em`, headings at `-.02em`, big numbers at weight 300.

## Light / dark theme toggle

A **Light / Dark** switch sits at the top right of the header, next to the density control.

- **Light is the default on every machine**, regardless of the operating system's own preference: the
  dashboard's design is specified in light, so a visitor should not meet a different default just because
  their laptop is in dark mode. Dark is one click away.
- The choice is stored in `localStorage` (`warroom-theme`) and reapplied **before first paint** by a small
  inline script in `<head>`, so a returning visitor never sees their choice flash to the other theme.
- A stored Light/Dark choice always wins over the default. There is deliberately **no operating-system
  listener**, so a mid-session OS switch cannot move the page underneath the visitor.
- Exactly two token blocks exist — `:root` (light) and `:root[data-theme="dark"]` — so the palette has one
  source of truth, and the chart colours are read from those CSS properties at render time.
- Switching themes **repaints instead of re-rendering**: the palette is re-read, the legend swatches and
  header dots are re-tinted, and every chart is redrawn — the DOM is left in place, so both panes keep
  their scroll position (asserted: rail `scrollTop` 200 before and after a switch).

Verified: a system-dark machine starts dark; a system-light machine starts light; clicking Dark switches
the body background `rgb(242,241,238)` → `rgb(18,19,22)`, recolours the chart lines `#2d81ff` → `#74aaff`,
persists across a reload, and Light restores both.

## Axis and freshness rules (learned from reported defects)

- **Axis titles never share a column or baseline with tick labels.** The y-axis unit sits above the plot,
  left-aligned to the plot edge; the x-axis title has its own row below the tick labels. `verify_dashboard.py`
  asserts pairwise that **no two text nodes in any chart overlap** — 0 overlaps across all 26 charts.
- **The newest observation is always labelled and always marked.** The x axis forces the latest date into
  its tick list (dropping the neighbouring tick if they would collide), and every series gets a dot at its
  last point, so "where does this series end" is answerable without hovering. The right-edge hover
  tolerance is widened because the newest point sits exactly on the axis edge.
- **Every tile is checked against its own series.** Each tile carries the `series_key` it was built from,
  and the verifier asserts `tile.value == series[series_key].points[-1]` (value *and* date) for all 38 —
  which is what caught the policy-rate chart plotting a weekly series that omitted the latest hike.
- **Sparse reporting is audited, not assumed.** RBI reports a nil balance as a blank cell, so a column can
  stop having observations while its table keeps publishing rows. The build measures each series' lag
  against the newest observation on the page: over ~400 days it is marked **dead** and cannot be plotted
  (this removed the Cash Management Bills line, which ended in Aug-2020); over ~60 days the tile is marked
  **stale** and shows `stale Nd` with its last-reported date instead of a delta that compares a value with
  itself (this is the case for RBI credit to the Centre, last reported 2026-04-17).

## Per-card history tables

Every one of the 38 cards has a **≡ history** button (and the whole card is clickable) which opens a table
of *which value prevailed on which date*:

- **Policy settings** (CRR, SLR, the repo rate) show their **change log**: `in force from | rate | until |
  move`. CRR, for example, lists 8 changes — 4.50% from 2022-05-27, ..., 3.25% from 2025-11-07, 3.00% from
  2025-12-05 — with the size of each move in bp and "in force now" on the newest row.
- **Readings** show the last 20 published observations with the change from the previous one.
- The summary line at the top states the current value and either "since <date>" (settings) or "as at
  <date>" (readings), so the modal itself cannot be misread the way the old CRR panel was.

## Dating rules for settings vs readings (audit of every card)

- **A setting is dated by when it took effect**, everywhere: the rail tile foot, the `?` panel, the history
  table and the snapshot strip all read "in force since <date>". The strip previously carried the portal's
  key-rates *snapshot* stamp for every chip, so CRR read "3.00% dated 2025-11-28" while the weekly series
  shows the rate took effect on 2025-12-05 — the two sources disagree by a week, and the published series
  wins on effective dates. SLR likewise: 2020-04-17 (series) not 2020-04-10 (snapshot).
- **Every tile now carries a delta with one meaning**: the change vs the previous reading (or the bp move
  for a setting), so the same badge cannot mean "vs last week" on one card and "vs last month" on another.
- **A stale series never shows a delta**: RBI credit to the Centre reads `stale 172d · 2026-04-17 · last
  reported` with the reason stating that the table publishes no value for that line after that date.
