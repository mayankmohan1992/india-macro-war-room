## What this changes

<!-- one or two sentences -->

## Checks

- [ ] `python build_dashboard.py && python publish_api.py && python tools/gen_docs.py` run and committed
- [ ] `python verify_dashboard.py` passes (render gate)
- [ ] `python tools/validate_api.py` passes (API gate)
- [ ] If a series was added or changed: the gate asserts whatever makes it trustworthy
- [ ] If a definition was added: it is quoted from the publisher **with a source URL**
- [ ] No hand-edits to generated files (`api/`, `dashboard/`, `docs/DATA_DICTIONARY.md`, `docs/DEFINITIONS.md`)

## Notes for the reviewer

<!-- anything needing judgement: a new threshold, a revised band, a source that disagrees -->
