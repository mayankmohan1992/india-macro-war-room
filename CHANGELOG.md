# Changelog

All notable changes to the pipeline, dataset and dashboard.
The dataset itself changes daily (see `api/v1/status.json` for the current as-of date); this file
records changes to the *project*.

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
