# Contributing

Thanks for considering a contribution. This project exists to make an official dataset easier to use
**without making it easier to misread**, so the bar for a change is: does it keep the data honest and
the claims checkable?

## The two rules

1. **Never write a definition from memory.** A definition is quoted from the publishing agency (RBI,
   MoSPI/NSO, DPIIT, FBIL) and carries a source URL in `definitions.json`. A term without sourced
   wording must render "definition pending" in the UI — that is the documented behaviour, not a bug.
2. **Never add or change a series without the verification gate covering it.** `verify_dashboard.py`
   must assert whatever property makes the series trustworthy (its value equals its series, its axis is
   labelled, its freshness handled), and the gate must fail if that property breaks.

## Workflow

```bash
git clone https://github.com/mayankmohan1992/india-macro-war-room && cd india-macro-war-room
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python -m playwright install chromium

python build_dashboard.py && python publish_api.py && python tools/gen_docs.py
python verify_dashboard.py && python tools/validate_api.py     # both must pass
```

Only `fetch_series.py` needs the network; everything else runs from the committed `raw/` tables, which is
also how CI proves reproducibility.

## Adding an indicator

1. Find the table and the exact item code in [docs/SOURCES.md](docs/SOURCES.md) (or probe the portal
   with `dbie_client.py`). Never map a column by position — a missing code must raise, not fall back.
2. Add the series in `build_dashboard.py` (`build()`), naming the derivation in a comment, then a tile in
   `tiles()` with an explicit rule and bands.
3. Register the definition key in `DEF_KEYS`, and make sure the term exists in `definitions.json` with a
   real source URL (otherwise it must show as pending).
4. If it deserves a chart, add it to the `CHARTS` registry in `template.html` — a chart needs a dated
   x-axis, a unit-labelled y-axis, a hover readout and a legend; the gate asserts all four.
5. Run the pipeline and both gates, and check the dead-space sweep output at every width.

## Reporting a wrong number

The most valuable issue you can file. Please include the indicator id, the value and date shown, the
value you believe is correct, and **a link to the RBI page that shows it**. Numbers get revised by the
publisher, so "the RBI says X" with a link usually settles it.

## Style

- Python: standard library where possible, `logging` with `[LEVEL] [Component]` prefixes, granular
  try/except, no bare `except: pass`, and comments that explain *why* a line exists (what breaks
  otherwise) rather than restating it.
- Generated files (`api/`, `dashboard/`, `docs/DATA_DICTIONARY.md`, `docs/DEFINITIONS.md`) are never
  hand-edited — regenerate them by running the pipeline.
- Keep the dashboard dependency-free: one self-contained HTML file, no CDN, no build step, works over
  `file://`.

## Licence

By contributing you agree that code contributions are licensed under [MIT](LICENSE), and that data
compiled from RBI publications remains attributed to the source.
