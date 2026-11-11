# CMIE as a second data layer — what is usable, what overlaps DBIE

Status: **plan, not implemented.** Recon date 2026-11-11. Nothing here has been wired into the
pipeline, and the recommendation is that most of it should not be.

---

## 1. The verdict first

**CMIE publishes no open or public datasets.** Every substantive series sits behind a paid
subscription; the public surface is a marketing catalogue, teaser headlines and a news feed.
Checked and observed:

| Surface | Observed behaviour |
|---|---|
| `www.cmie.com`, `economicoutlook`, `consumerpyramids`, `capex`, `prowess` `robots.txt` | `User-agent: * / Disallow: /` — crawler access is refused, Googlebot excepted. Automation needs written permission, not a clever header. |
| Insight articles (`kall=warticle`) | First paragraph only, then *"To read the whole article subscribe now!"* |
| Series/report links inside announcements (`kall=wshreport`, `kall=wreport`) | Redirect to the subscription landing page — no table is served to an anonymous session |
| "Sample data" link on the Unemployment product page (`kall=wlstind&file=ue&type=data`) | Redirects back to the product page; no file is served |
| Mobile app *India Economic Outlook* | Free to install, but *"Only for subscribers to CMIE's Economic Outlook"* — login gated |
| Free data actually rendered | Four homepage tiles: 10-y G-sec 7.17 (09 Nov 2026), INR/USD 93.86 (09 Nov 2026), CPI y-o-y 5.54 (Sep 2026), **unemployment rate 4.70 (Oct 2026)**; on `consumerpyramidsdx` a 30-day moving average (unemployment 4.4, LPR 41.6, as of 23 Sep 2026). Latest point only, no history, no download. |

So "what can we use for free" has a thin answer: the announcement feed, plus headline tiles that
are copyrighted output rather than a dataset. Everything worth analysing is a licence.

## 2. What CMIE publishes regularly

| Product | Cadence | Content | CMIE-original? |
|---|---|---|---|
| **Consumer Pyramids Household Survey (CPHS)** | 3 waves/yr over 354k households; monthly labour tabulations | unemployment, LPR, employment by industry/state/gender/age/education, wages; household income, ~20 expense heads, assets, borrowing, savings | **Yes** — in-house panel since 2014 |
| **CapEx** | continuous; quarterly aggregates | life-cycle tracking of investment projects (announcement → implementation → completion) across mining, manufacturing, utilities, infrastructure, services; public/private/foreign | **Yes** — their own project tracking |
| **Economic Outlook (EO)** | daily/weekly/monthly | 4.2m series — CPI, WPI, PPI, IIP, PMI, GST, trade, BoP, fiscal, RBI surveys (IOS, OBICUS, CCS, IES), plus CMIE's own CPHS and sentiment data; 5-year forecasts | **Mostly no** — a cleaned mirror of official releases |
| **Industry Outlook** | quarterly, per industry | aggregate results of ~100 industries (capacity, production, margins, project commissioning) | Partly (from Prowess) |
| **Prowess / Prowess dx** | daily | company financials 1989-90 →, listed + unlisted | Partly (from annual reports) |
| **States of India** | fast-frequency + annual | 46 states/UTs, 1,097 districts: rainfall, agri, farm prices, vehicle sales, employment, sentiments, state finance | Partly |
| **Beliefs & Behaviour** | periodic | attitudinal survey data | Yes |

## 3. Overlap against what the war room already publishes

The public payload carries 66 series, all from DBIE: prices (CPI/WPI and components), money
(M0/M1/M3, multipliers), banking (credit, deposits, CD ratio, investments, food/non-food),
rates (repo, SDF, MSF, CRR, SLR, call, T-bill 91/182/364, 10-y G-sec, term spread, forwards),
FX (INR/USD, INR/EUR), liquidity (LAF net), market instruments (CD/CP, turnover), RBI balance
sheet (FCA, gold, notes, rupee securities, loans to Centre), GoI T-bill outstanding.

| CMIE content | Relationship to the war room | Decision |
|---|---|---|
| CPI, WPI, money, credit, rates, FX, reserves, fiscal | **Direct duplicate.** Same underlying official releases, re-cleaned. | Never source from CMIE. A second vendor for the same number only creates reconciliation debt. |
| IIP, PMI, GST, trade, ports, electricity, rainfall | Not in the war room, but **free from the primary publisher** (MoSPI, S&P/HSBC, GSTN, DGCIS, IPA, CEA, IMD) | Source from the publisher, not from CMIE. |
| RBI surveys (IOS, OBICUS, CCS, IES), state finances | Absent from the war room; free from RBI | If wanted, extend the DBIE client — not a CMIE subscription. |
| **CPHS labour** (unemployment, LPR, employment by industry/state/gender) | **Absent.** Zero labour series in the payload. | Genuine gap — but the *substance* is free from PLFS at a longer lag (see §5). |
| **CapEx project pipeline** | **Absent.** No investment-pipeline, order-book or capacity-formation series anywhere. | Biggest genuine gap; no free equivalent at project granularity. |
| **Household balance sheet** (income, expenses, debt, savings, assets by state/income class) | Absent; war room is entirely institutional/monetary | Genuinely new, and the only lens that connects credit growth to household demand. Expensive. |
| Prowess corporate financials | Absent, and out of scope — that is `macro-signal-studio`/NSE territory | Skip. |
| Consumer Sentiments index | Absent; nearest free analogue is RBI's CCS | Skip unless licensed. |

Rule that falls out of this: **CMIE's value to this project is exactly the four rows it
originates — labour, capex, households, sentiment. Everything else on their catalogue is a
re-publication of numbers we already hold or can fetch free, and paying ₹2.7 lakh a year for a
second copy of DBIE would be the single worst use of the budget.**

## 4. If we buy: the menu at real prices

Public 2027 list (effective 1 Jan 2027, per annum, from the price announcement article):

| Product | Price | Hit cap | What it buys us |
|---|---|---|---|
| Economic Outlook | ₹270,000 | 7,000 | 4.2m series, ~90% duplicate of free sources; includes CPHS tabulations and sentiment |
| **CapEx** | **₹220,000** | 7,000 | project-level pipeline, quarterly aggregates |
| Prowess | ₹270,000 | 7,000 | company financials — out of scope |
| States of India | ₹270,000 | 7,000 | district-level layer — could later feed `india-admin-atlas` |
| Industry Outlook | ₹325,000 | 7,000 | industry aggregates |
| Consumer Pyramids dx (commercial) | ₹3,000,000 / USD 18,500 | 200,000 | household microdata — prohibitive for this project |
| Prowess dx / CapEx dx | USD 4,500 / USD 3,000 | 50,000 | bulk extraction licences |
| Academic IP-based EO / CapEx | ₹405,000 / ₹330,000 | 15,000 | only for educational/research institutions |

Note the hit caps: 7,000 "hits" is roughly 20 a day — fine for a monthly dashboard refresh, fatal
for a backtest that walks 15 years of series. Any licensed feed must be cached locally on first
pull and never re-queried.

## 5. Recommended plan

### Phase 0 — no licence, do this regardless (≈1 week)
Close the labour gap for free, from the primary publisher:

- **PLFS** monthly bulletin (MoSPI) → unemployment rate, LPR, WPR, employment by broad sector,
  monthly since 2024 with a ~45-day lag; quarterly detailed tables.
- Wire it as `plfs_*` series into the existing DBIE-shaped pipeline, with `pub_date` taken from the
  bulletin's own release date (MoSPI publishes a release calendar — this is better than DBIE, which
  has no release dates at all and forces modelled lags, the known weak point in
  `macro-signal-studio`).
- Add three tiles: unemployment rate, LPR, employment growth. These are the only genuinely new
  headline numbers the plan produces, and they cost nothing.

### Phase 1 — the free-usable fragment (small, no scraping)
CMIE's Economic Outlook **announcements feed** is free full text and is the only thing on the site
that is both free and non-overlapping: it is a dated record of *when each Indian dataset actually
landed* (PLFS quarter, PMI, GST collections, port traffic, e-way bills, NBFC credit deployment,
reservoir levels, electricity generation, petroleum consumption). That is publication-timestamp
evidence, which DBIE cannot give.

Constraint, and it is decisive: `robots.txt` disallows all non-Googlebot agents on every CMIE host,
and the usage agreement grants a non-exclusive **non-commercial** access right. Therefore:

- **Do not build a scraper.** Read the feed manually at the weekly review, or get written
  permission first.
- **Do not republish CMIE-derived values** anywhere in `dashboard/`, `api/v1/` or the Pages site.
- Treat it as a reading aid for the human, not as a data source for the pipeline.

### Phase 2 — licensed layer, only if Phase 0 leaves a real signal gap (2-3 weeks)
If investment-cycle visibility is judged worth ₹220k/yr, buy **CapEx** (not EO):

- Ingest quarterly aggregates: new project announcements (₹ crore, count, by sector/state),
  completions, under-implementation stock, and the announced-to-commissioned ratio.
- Presents as the leading edge of the credit cycle: credit growth (DBIE, coincident) against
  announced capex (CMIE, leading) — the two are complementary, not duplicative.
- Gated behind a build flag; series live in `private/cmie/`, excluded from `publish_api.py`.

### Explicitly not recommended
- **Economic Outlook** — paying ₹270k for a mirror of free releases, with the unique content
  (CPHS aggregates) obtainable only if the licence explicitly grants redistribution-limited
  display rights. Verify at quote stage; the product page does not say.
- **Prowess** — corporate fundamentals, already covered by the NSE archives in `macro-signal-studio`.
- **CPHS dx** — ₹30 lakh for microdata is out of proportion to a one-person dashboard.

## 6. Architecture constraint (the part that must not be got wrong)

The war room publishes `dashboard/warroom_data.json` and `api/v1/*` to GitHub Pages — public,
permanent, indexed. CMIE's agreement grants non-commercial access and retains all rights; CMIE
figures posted publicly in a derivative dashboard are a redistribution, not a citation. So:

1. Licensed series go to `private/` (git-ignored), consumed only by a local build.
2. `publish_api.py` gains a source allowlist — a hard assertion that no series whose `source`
   contains `CMIE` reaches the public payload. A test asserts the guard fires, in the same spirit
   as the existing completeness gate.
3. Any public mention of a CMIE figure is a dated quotation in prose, never a chart or a series.
4. Rollback: deleting `private/` and rebuilding restores the current dashboard exactly — no schema
   change, no migration. That is the reason for keeping CMIE out of `warroom_data.json` rather
   than beside it.

## 7. Failure modes to accept before committing

- **Vendor lock with no API.** There is no documented REST/JSON feed for EO or CapEx; access is
  browser/desktop/`dx` extraction. A pipeline built on it is a pipeline built on a scrape, with a
  rebuild date. `dx` (USD 3,000) is the only honest programmatic route.
- **Hits, not bytes.** 7,000 hits/yr means a licence is for a refresh loop, never a backfill.
- **Two copies of the same number.** If any CMIE series mirrors an official one, the dashboard must
  pick one owner. Pick the publisher.
- **Reputational asymmetry.** If a CMIE-derived chart leaks into the public payload, the downside is
  a takedown on a public portfolio repo. The upside was one extra chart. Guard it at build time.
- **Their figures move.** CPHS is a panel with waves and sampling error; CMIE re-estimates. Any
  derived signal needs the vintage captured, which means storing `fetched_at` per observation —
  the war room does not currently do this for DBIE either, and should.

## 8. Sequence and cost summary

| Step | Effort | Cost | Output |
|---|---|---|---|
| Phase 0 — PLFS labour layer | ~1 week | ₹0 | 3 new headline series, free release-date PIT |
| Phase 1 — announcements as reading aid | hours | ₹0 | weekly release diary, human-read |
| Phase 2 — CapEx annexe | 2-3 weeks | ₹220,000/yr | investment pipeline vs credit growth |
| Guard: publish allowlist + test | 1 day | ₹0 | licensed data cannot leak |

Do Phase 0 and the guard first; they are cheap, permanent, and make any later licence decision
safe rather than urgent.
