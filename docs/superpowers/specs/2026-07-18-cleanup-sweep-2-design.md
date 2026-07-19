# Cleanup Sweep #2 (Moderate) — Design

**Date:** 2026-07-18  
**Status:** Approved for planning  
**Related:** Post–TODO-006 janitor pass; does not reopen TODO-006 checklist items already shipped.

## Goal

Remove dead leftovers from post–TODO-006 feature work, cut clear efficiency waste (especially Gemini RPD), and sync living docs — **without removing or changing product features**.

## Constraints

- No feature removals or UX redesigns.
- Do **not** defer Map / Neighborhood / Financials tab mounting until first click (lazy tabs = out of scope).
- Do **not** change financial Gemini fingerprint to subject-URL-only (product nuance about peer-library staleness = out of scope).
- Do **not** unify money/bbox/address helpers in this pass (drift risk; defer).
- Prefer small, reviewable changes; run `.\.venv\Scripts\pytest.exe -q` before claiming done.
- Do not commit unless the user asks.
- After user-facing / continuity doc changes: update `AGENTS.md` and `README.md` in the same turn.

## In scope

### A. Dead code removal

| Item | Location | Action |
|------|----------|--------|
| Unused imports `summarize`, `zillow_urls_digest` | `app/core/property_service.py` | Drop from imports |
| `_financial_assumption_dict` | `property_service.py` | Delete method |
| `_library_comps_for_financial` | `property_service.py` | Delete alias (callers use `_library_zillow_refs`) |
| fin_v3 shims (`LibraryCompSnapshot`, `library_comps_digest`, `format_buy_vs_rent_notes`) | `app/core/gemini_financial.py` | Delete unused block |
| `_listing_meta_bits` | `app/ui/pages.py` | Delete unused helper |
| ACS `income_fill_color` / `build_income_geojson` wrappers; unused `county_fips_for` | `app/core/census_acs.py` | Delete; adjust tests to use `fill_color_for_breaks` / `INCOME_BREAKS` |
| Optional: stop writing unused `median_income` geojson prop | `census_acs.py` | Only if map JS never reads it (confirmed in audit) |

### B. Efficiency (behavior-preserving)

| Change | Detail | Expected effect |
|--------|--------|-----------------|
| Header Gemini insights | `ensure_gemini_insights(prop_id, force=False)` in `pages.py` | Warm cache → `cached` statuses, **0** Gemini calls; empty/stale still generate |
| Financials Ask button | `run_gemini(force=False)` for Ask; Regenerate stays `force=True` | Matches Neighborhood tab pattern; avoids needless RPD if Ask clicked with valid cache |
| Lightweight peer refs | `_library_zillow_refs` queries `id`, `zillow_url`, `address` only — **no** `joinedload(photos)` / full `list_properties()` | Same peer list for Gemini; less SQLite work on every Financials paint |
| Dedupe financial sync | `refresh_listing_details`: drop second `_sync_financial_from_listing` when `_apply_listing_details` already synced; on `add_from_zillow`, avoid redundant FHFA/PMMS double-pass where end state stays identical | Same autofilled rates/tax/HOA; less network/disk on refresh/add |

### C. Docs sync

- `AGENTS.md`: overlay “What’s done” bullet matches decision #7 (Zoning + full ACS set + LA County crime); add `thumbnail_locked` to Property model blurb; font note Creato vs Akira; slim Done noise from in-progress if any; Financials Gemini model wording matches code (`GEMINI_FINANCIAL_MODEL` → else `GEMINI_MODEL` → else 2.5 default).
- `README.md` / `.env.example`: Census key covers map ACS layers + rent-growth; Financials model override documented honestly (uncomment `GEMINI_FINANCIAL_MODEL=gemini-2.5-flash-lite` in example **or** document fallback).
- Optional: `app/static/fonts/README.md` Akira/Creato roles if still stale.

## Out of scope

- Lazy property-tab render
- Subject-only financial fingerprint / peer-staleness product change
- Shared `format_usd` / `bbox_around` / address-parser unify
- Broad `except Exception` narrowing
- Startup lazy-import of FHFA/openpyxl/curl_cffi beyond existing Plotly laziness
- Rewriting historical `docs/RESEARCH.md` recommendation sections

## Success criteria

1. `.\.venv\Scripts\pytest.exe -q` passes.
2. Header Ask Gemini with warm caches does not call the Gemini API (statuses `cached`).
3. Financials Ask with warm cache does not re-call Gemini; Regenerate still forces.
4. Peer list for Gemini still max 19 other homes with URLs.
5. Listing refresh / add still autofill financial fields as today.
6. Living docs agree on overlays, Census usage, and Gemini model env vars.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Dropping second sync on refresh misses a post-geocode ACS path | Only skip when apply already ran sync **and** coords were already present before refresh; if refresh geocodes mid-flight, keep one post-coord sync |
| Ask `force=False` surprises users who expected always-fresh | UI still has Regenerate; toast can show cached vs generated via existing status keys |
| ACS test breakage | Point tests at `fill_color_for_breaks` |

## Implementation note

After this design is approved as a written spec, implement via `writing-plans` → subagent-driven or inline execution. Prefer one focused cleanup pass (or small task batches: dead code → efficiency → docs → verify).
