# ACS demographics overlays — Implementation Plan

> Execute from [`docs/superpowers/specs/2026-07-18-acs-demographics-overlays-design.md`](../specs/2026-07-18-acs-demographics-overlays-design.md). Zoning is out of scope.

**Goal:** Add Map toggles for median home value, median age, and avg kids/HH via generalized ACS choropleth configs.

## Tasks

1. Extend `app/core/census_acs.py` with layer configs + `build_acs_geojson`; keep `build_income_geojson` / `INCOME_LEGEND` / tax-rate helper.
2. Tests in `tests/test_map_overlays.py` (+ new parsers/fills).
3. Wire checkboxes + stacked legends in `app/modules/map_view.py`.
4. Update AGENTS.md, README.md, RESEARCH.md, TODO.md; `pytest -q`; restart app.

No commit unless asked.
