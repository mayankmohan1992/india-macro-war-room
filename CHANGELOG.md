# Changelog

All notable changes to the pipeline, dataset and dashboard.
The dataset itself changes daily (see `api/v1/status.json` for the current as-of date); this file
records changes to the *project*.

## [1.0.5] — 2026-10-24

An audit-and-fix release. Most of the 33 defects were in the **gates** rather than the numbers, and
several were latent: they would have fired on the next real policy move, the next RBI outage, or the next
CI run that mattered. Each is now fixed and asserted.

### Fixed — published data

- **A policy move erased its own effective date.** When appending the fresher key-rates row, the build
  replaced the series dict instead of updating it, dropping the `step` (the change in force). For the few
  days after any real move — exactly when that branch fires — the tile lost `effective_from`/`bp` and
  dated the setting from the first row of the table: a fresh 25bp hike read "unchanged since 2011-04-01",
  scored **watch**, with no in-force date.
- **The policy-rate chip mixed two vintages.** After a mid-week announcement the strip took `value` from
  key rates but `since`/`prev`/`bp` from the older weekly statement, so it claimed a rate had been in
  force three days *before* it was announced, with `prev` equal to its own value and the previous move's
  basis points. An announcement newer than the weekly row is now dated by the announcement, with
  `prev` = the superseded weekly value and `bp` = the new move.
- **The "weekly" calendar date came from a daily observation.** `usdinr` appends the portal's daily FBIL
  rate to a weekly table; that point was reported as the newest *weekly* observation, so the header
  claimed weekly data six days fresher than any weekly statement — and fresher than daily. Each calendar
  now reports its own source table's vintage, and the header states the overall newest date explicitly
  instead of relying on a bucket happening to equal it.
- **`latest.change` contradicted the series' own history.** `rbicredit` published `change: 0.0` beside a
  `points` step and `history[0].change` of −₹6,882 cr, because the "3 months ago" lookup found nothing
  and fell back to the current value. `change` is now the actual step between the last two observations.
- **A null date became the literal string `"None"`.** `series()` stringified the date before the `except`
  could reject it, so report 6's empty leading date column produced points dated `"None"`.

### Fixed — dashboard

- **The `?` panel found the tile by definition key.** It matched a `definitions.json` key against tile
  ids, which only works where the two names coincide: 22 of 38 tiles lost their "On this dashboard"
  block, and the WPI chart opened **CPI's** value, colour and scoring rule. The clicked element
  (`.tile[data-id]` / `.card[data-chart]`) is resolved instead.
- **Definition source URLs were interpolated into `innerHTML` unescaped**, so a URL containing `&reg=48`
  rendered and copied as `&reg;=48` → `®`. Definition text and links are escaped.

### Fixed — publishing (`publish_api.py`)

- **`--check` verified nothing and overwrote what it was checking.** It built into `api/v1/` and then
  re-read the file it had just written, so the hashes always matched; there was no failing exit either.
  It now builds into a temporary directory and fails on any difference (verified both ways: passes when
  consistent, exits 1 on payload drift, and no longer touches the committed files).
- **Stale series files were never pruned**, so a dropped indicator kept being served, hashed, manifest-
  listed and CDN-cached forever — and any stray file became part of the dataset hash.
- **The dataset hash filtered on the absolute path** for a `schema` component, so checking out the repo
  under any directory named `schema` hashed *nothing* — which the daily workflow reads as "no change".
- `latest.schema.json` now requires the fields each indicator object actually carries, instead of
  accepting any object.

### Fixed — fetching (`fetch_series.py`, `dbie_client.py`, `series_lib.py`)

- **A short table overwrote the previous good one.** Each report was written to `raw/` *before* the
  completeness gate ran, so its verdict was only an exit code while the file already looked valid; a
  caller that ignored the code built a dashboard from a truncated series. Tables are now buffered, gated,
  and only then written atomically (`os.replace`), so `raw/` is untouched on any failure.
- **The fetch lock was check-then-act**, and an empty (half-written) lockfile was read as "stale pid 0":
  two simultaneous fetches both proceeded in 82% of measured trials. Acquisition is now atomic
  (`os.link` of a fully-written pid file), zombies are treated as dead, and EPERM (a live process owned by
  someone else) as alive rather than clobbering it.
- **An empty named series passed the gate.** A gateway error produced a 0-point CPI series, the gate said
  "all complete", and the published CPI figure silently vanished downstream. Zero usable points is now a
  failure that keeps the last good `named_series.json`.
- **A gateway `status: "error"` was returned as a successful result**, so transient failures burned no
  retry and callers built 0-row tables/0-point series from it. It now raises and is retried; a persistent
  4311 reports the real cause instead of "unknown call failure".
- If the portal omits `totalCount`, the table is no longer compared against itself (which made any
  truncation "complete"). `to_series()` no longer swallows `IndexError`, so a vanished column is loud.

### Fixed — gates and CI

- **`scripts/refresh.sh` always exited 1 after a successful run.** It grepped the verifier's log for
  `render OK|PROBLEMS`, but the verifier prints `PASS —`/`FAIL —`; under `set -o pipefail` the no-match
  killed the script, so cron and `&&` chains treated a good refresh as failed.
- **`scripts/refresh.sh` could never run.** It was a byte-identical copy of the root script, whose
  `cd "$(dirname "$0")"` lands in `scripts/`, where the pipeline does not exist. It is now a thin wrapper
  around the root script.
- **`refresh.sh` never published the API**, leaving a new `dashboard/` beside an `api/v1/` describing the
  previous data — the exact "site and API disagree" failure `daily.yml` was fixed for. It now runs
  `publish_api.py`, `tools/gen_docs.py` and `tools/validate_api.py` before verifying.
- **The verification gate hardcoded CRR's effective date** (`2025-12-05`). The next real CRR move would
  have failed the gate that blocks commit+deploy, with a message pointing at the strip. Every date is
  derived from the payload now.
- **The gate compared a float repr to formatted page text** (`previous setting 3.0` vs `3%`), so any
  whole-number predecessor would false-fail.
- **The chart-column count was measured and never asserted**, so a single-column desktop — the shell's
  headline claim — passed at every width.
- **The font check used `document.fonts.check()`**, which returns `true` for a family with no `@font-face`
  at all; renaming the embedded family still passed. It now requires a genuinely `loaded` face.
- **The responsive sweep wired no console/pageerror capture**, so a script error thrown in the 980px band
  — where the shell's `@media` block lives — went unnoticed.
- **The history table's newest row was compared to the tile value with a fixed `0.011` tolerance**, so
  any figure the page rounds for display — a ₹-crore value of −247,136.818 rendered as −2,47,137 — read
  as a mismatch and blocked the deploy on the next data refresh. The tolerance now follows the displayed
  precision (half of the last printed digit).
- **An unknown or renamed `data-status` made the worst-first assertion vacuous** (`indexOf` returns −1,
  which sorts first). The attribute's values are asserted before the ordering is checked.
- **CI never compared the committed dashboard to a rebuild.** Only the API hash was checked, so a broken
  `dashboard/index.html` could ship green. The rebuild must now match `HEAD`'s page byte-for-byte, build
  stamp aside.
- **`daily.yml` granted `pages: write` and `id-token: write` to the job that runs `pip install` and repo
  code.** Permissions are now per-job at least privilege.

### Fixed — validation (`tools/validate_api.py`, `tools/gen_docs.py`)

- **`settings.json`, `snapshot.json` and `dataset.json` were published but never validated.** A settings
  document could contradict the series about when a rate took effect — the disagreement class this project
  has been bitten by twice — and the suite still said PASS. All three are now cross-checked.
- **`unit`, `label` and `status` were compared in no document**, so a wrong status flipped the
  consumer-facing verdict silently. All three are now compared, in `index.json` and `latest.json`.
- **`status.json`'s own counts, verdict and point total were unchecked** (the file is excluded from its
  own hash). They are now reconciled against the payload and the files on disk.
- **Points were untyped and only the first 50 elements of a document were schema-checked.** Every point
  is now checked for shape, numeric value and an ISO date.
- **The CSV was compared only at its last row**, so a truncated series document beside an intact CSV
  passed. Every row is compared against the published points.
- **`DATA_DICTIONARY.md` rounded to 2dp** while the API published 4: USD/INR read `95.07` in the docs and
  `95.0691` in the API and CSV, breaking its own "must never drift" contract.

### Added

- **`status.json` carries `project_version`**, so a deployment can be identified at runtime
  (`curl .../status.json | jq .project_version`) without diffing hashes. It is excluded from
  `dataset_sha256`, so a version bump is not mistaken for a data change.

## [1.0.4] — 2026-10-17

### Fixed
- **Portal timestamps were being read in UTC.** They are midnight **IST**, so every date taken from a
  portal timestamp was one day early: the October policy announcement read 2026-10-06 instead of
  **2026-10-07**, CRR 2025-11-28 instead of 2025-11-29, the monthly CPI series 2026-09-29 instead of
  2026-09-30. All conversions now use IST, and the gate asserts a monthly point lands on a month end.
- **The CPI headline was a figure derived here (5.59%) rather than the publisher's own (5.54%).** The
  portal's indicator route (`dbie_getWSSReport`, `reportName: RBIB18`, `level3Code: ["Inflation"]`) publishes
  the official inflation series; the headline now uses it, the derived index-based series stays as the
  chart's long history, and the build publishes a `cross_checks` block (largest gap 0.05pp over 9 months,
  tolerance 0.1pp) which the gate enforces.

### Added
- **The portal's named-series route** is now a source (`fetch_series.py` → `raw/named_series.json`),
  documented in `docs/SOURCES.md` including the two traps: the response nests as `body.Result` (the report
  gateway uses `body.response.Result`), and portal timestamps are midnight IST.
- **A fresher USD/INR**: the daily FBIL rate from the portal's key-rates set (95.07 on 15 Oct) is appended
  to the weekly series, replacing the week-old 96.61 as the headline.
- **Both "when" dates for CRR/SLR** are now reported: RBI's effective date (key rates) and the first weekly
  statement reflecting it.

## [1.0.3] — 2026-10-17

### Changed
- **The header now states the newest observation per publication calendar** (`latest data: daily
  2026-10-11 · weekly 2026-10-09 · fortnightly 2026-09-30 · monthly 2026-09-30`) instead of a single
  maximum date. One bare date made the page look a week stale when it was just the fastest table's last
  row: the weekly statement for the week ended 9 Oct was published on 16 Oct, so 9 Oct *was* the newest
  weekly figure in existence. The same breakdown is exposed as `dataset_as_of_by_frequency` in every API
  document, documented in the methodology, and asserted by the verification gate.

## [1.0.2] — 2026-10-17

### Changed
- **The dashboard now defaults to the light theme on every machine**, instead of following the operating
  system. A visitor on a dark-mode laptop meets the same default as everyone else (the design is specified
  in light), Dark remains one click away, and an explicit choice is still stored and restored before first
  paint. The operating-system listener was removed, so a mid-session OS switch cannot change the page.

## [1.0.1] — 2026-10-17

### Fixed
- **API:** `latest.json` took `change` from the raw tile, so a policy *setting* published a week-on-week
  number (the repo rate showed `+0.25`) while `index.json` published `null` for the same field. Both
  documents now take it from the indicator document, and `tools/validate_api.py` asserts that a setting
  reports `change: null` in both.
- **Deployment:** the Pages artifact was assembled in a separate job, which checks out the SHA of the
  triggering event — i.e. the commit from *before* the run committed its refresh. The deployed dashboard
  therefore kept the previous as-of date while the repository's API already carried the new data. The
  artifact is now assembled and uploaded by the refresh job itself, and the live site and API are
  asserted to agree.

## [1.0.0] — 2026-10-17

Initial public release.

### Added
- **Pipeline** — `fetch_series.py` pulls 12 RBI DBIE tables with a completeness gate (a table that
  comes back short fails the run rather than shipping a partial series), plus the portal's key-rates
  snapshot. A PID lockfile prevents two concurrent fetches from overwriting each other.
- **38 indicators** across prices, policy, money, liquidity, credit, markets, external and fiscal
  sectors, each with a rule-based good/watch/bad read, a sparkline and its own period.
- **26 charts** with dated axes, hover readouts, latest-point markers, click-to-expand zoom/pan and
  a "which value prevailed when" table on every card.
- **Static API (`api/v1/`)** — catalogue, latest values, per-indicator series (JSON + CSV), policy
  settings with effective dates, definitions, JSON Schemas, a checksummed manifest and a status
  document for change detection.
- **Dashboard** — fixed-viewport console with independently scrolling panes, 2/3 density levels,
  light/dark theme toggle, worst-first sorting and sourced `?` definition panels.
- **Automation** — `daily.yml` refreshes, verifies and redeploys at 06:00 UTC; `ci.yml` proves the
  committed artefacts reproduce from the committed raw tables and re-runs the render gate.
- **Verification gate** — `verify_dashboard.py` renders the built page in headless Chromium and
  asserts layout, data integrity, tile-vs-series agreement, axis labels, freshness, modals and
  mobile behaviour; `tools/validate_api.py` validates the API end to end.

### Notes
- Derived figures (y-o-y, spreads, ratios, moving averages, the money multiplier) are computed at
  build time in Python rather than in the browser, so the methods are auditable and testable.
- Definitions are never written from memory: each is quoted from RBI / MoSPI / DPIIT / FBIL and
  carries its source URL.
