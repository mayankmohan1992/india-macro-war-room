# Deployment

The whole project runs on GitHub's free tier: **GitHub Actions** for the daily refresh and
**GitHub Pages** for hosting. There are no servers, no secrets and no paid services.

## What runs where

| piece | host | refreshed by |
|---|---|---|
| Dashboard (`/`) | GitHub Pages | `daily.yml` → `actions/upload-pages-artifact` + `actions/deploy-pages` |
| API (`/api/v1/`) | GitHub Pages (mirror) and `raw.githubusercontent.com` (primary, CORS-enabled) | committed by `daily.yml` |
| Dataset (`raw/`, `api/`) | the repository itself | committed by `daily.yml` |

The API is committed rather than only deployed, because `raw.githubusercontent.com` serves repository
files with `access-control-allow-origin: *` — that is what makes the API usable directly from a browser
with no server of your own.

## First-time setup

1. **Push this repository** (it already contains the workflow files, the seed `raw/` data, and a built
   `dashboard/` + `api/` set).
2. **Settings → Pages → Source: GitHub Actions.** Nothing else; no branch to pick, no Jekyll config.
   `scripts/build-public.sh` assembles the artifact: the dashboard at `/`, the API at `/api/v1/`, plus
   a `.nojekyll` marker so Pages serves the tree verbatim.
3. **Actions → Daily data refresh → Run workflow** once, to confirm the fetch works from GitHub's
   runners and to publish the site for the first time.
4. Optional: protect `main` and require the CI workflow to pass, so a hand-edit cannot publish a
   dataset that no longer reproduces.

No repository secrets are required. The DBIE client uses only public constants (see
[SOURCES.md](SOURCES.md)); nothing here is a credential.

## The daily workflow

```yaml
on:
  schedule: [{ cron: "0 6 * * *" }]   # 06:00 UTC = 11:30 IST, daily
  workflow_dispatch:                   # manual trigger
```

Order of operations: fetch → build → publish API → regenerate docs → verify (headless Chromium) →
validate API → **commit only if the data changed** → assemble the Pages artifact → deploy.

- **Correncies:** the job runs under `concurrency: daily-refresh` with `cancel-in-progress: false`, so a
  slow run is never killed mid-commit by the next one.
- **No commit noise:** the job compares the freshly computed `api/v1/status.json` `dataset_sha256` with
  the committed one. If RBI has published nothing new, it discards the rebuild (which differs only in
  the retrieval timestamp) and skips the commit entirely.
- **Fails loudly, ships nothing:** if a fetch comes back short, the completeness gate raises, the
  verification gate fails, or the API validator objects — the workflow stops **before** the commit, so
  the last good dataset stays published.
- **Permissions:** `contents: write` (commit), `pages: write` + `id-token: write` (deploy). Nothing else.
- **Timing caveat:** GitHub's cron is UTC, is best-effort, and can be delayed under load; runs are
  idempotent, so a late run is harmless. Scheduled workflows are disabled after 60 days without
  repository activity — the daily commit itself counts as activity, but if the data ever stops changing
  for two months, trigger a manual run.
- **Playwright:** the verification gate installs Chromium (`playwright install --with-deps chromium`);
  the browser download is cached on `requirements.txt`'s hash.

## CI workflow

`ci.yml` runs on every push and pull request (and skips docs-only changes):

1. **Reproducibility** — rebuild the dataset from the committed `raw/` tables, re-publish to a temp
   directory, and fail if the resulting `dataset_sha256` differs from the committed `api/v1/status.json`.
   This is the check that stops a hand-edited artefact from being published.
2. **Render gate** — `verify_dashboard.py` in headless Chromium.
3. **API gate** — `tools/validate_api.py` (schemas, cross-document consistency, manifest hashes).
4. **Artifact gate** — `scripts/build-public.sh` must assemble and contain `index.html` and
   `api/v1/latest.json`.
5. **Workflow lint** — the YAML files must parse.

## Forking / self-hosting

```bash
git clone https://github.com/<you>/india-macro-war-room && cd india-macro-war-room
pip install -r requirements.txt
python build_dashboard.py && python publish_api.py   # works offline from the committed raw/
python verify_dashboard.py                            # after: playwright install chromium
```

Then in your fork: update the URLs in `README.md` (badges, API base) and `CITATION.cff`, enable Pages
with the GitHub Actions source, and run the daily workflow once. If you want a different cadence, edit
the `cron` line; if you only want the API and not the site, delete the `build-site`/`deploy` jobs.

## Troubleshooting

| symptom | cause and fix |
|---|---|
| `fetch_series.py` fails with `another fetch is already running` | a stale `raw/.fetch.lock` from a killed process: the client takes it over automatically when the pid is dead, otherwise delete the file |
| a table comes back empty with `status: success` | a non-breaking space in a tab or region name — `series_lib.report_page` normalises it; if a *new* report shows this, normalise before sending it back |
| decryption errors on some fields | the portal's field-crypto constants live in its own JS bundle and can rotate on redeploy; re-derive them from a fresh bundle (see [SOURCES.md](SOURCES.md)) |
| HTTP 418 on `/download/*` endpoints | those export routes sit behind the CIMS WAF; this project does not depend on them |
| the site 404s but the workflow succeeded | Settings → Pages → Source must be **GitHub Actions**, and the deploy job must have run (check the `github-pages` environment) |
| the dashboard shows a "refresh is due" note | the newest observation is over six weeks old — check the daily workflow's recent runs |
| CI fails "committed API is not reproducible" | the artefacts were edited by hand or the pipeline changed without re-running it: run build → publish → gen_docs locally and commit the result |
