# Performance Platform + Hot-Path Port — Design

**Date:** 2026-07-21  
**Status:** Approved for planning  

**Approach:** Platform first, then port hot paths (Approach 2)  
**Aggressiveness:** Structural splits + perf/UX responsiveness wins allowed  
**Constraint:** Nothing sacred for optimization targets, but **everything must keep working** (no behavior regressions for library, add-home, map overlays, financials, neighborhood, photos, packaging).

**Related:** Perf/caching audit (session 2026-07-21); builds on existing `overlay_cache.py`, `ui_jobs.py` / `run.io_bound`, and per-feature disk TTLs.

## Goal

Make Homebuy **faster and more responsive** by:

1. Introducing a shared **cache platform** (disk + process memo + singleflight + SWR + GeoJSON quantize helpers).
2. **Splitting** oversized modules so ports are safe.
3. **Porting** ranked hot paths onto that platform without changing product semantics (same chips, layers, formulas, Gemini prompts, theme).

## Constraints

- Prefer regressions that are bisectable: platform lands with compatibility shims first; each port step must leave pytest green and the affected surface working.
- Long UI I/O stays on `run.io_bound` + `ui_jobs.py` (own sessions; no ORM/UI across threads).
- Do not bake secrets into the installer; paths via `app/core/paths.py` unchanged.
- After user-facing / continuity changes: update `AGENTS.md` and `README.md` in the same turn.
- Do not commit unless the user asks (repo convention).

## Architecture — cache platform

Extend today’s thin `app/core/overlay_cache.py` into `app/core/cache/` (package), with thin **re-exports / wrappers** so existing callers keep working during the port:

| Piece | Role |
|-------|------|
| **Disk store** | JSON read/write + mtime TTL delete-on-miss; optional gzip; soft max-bytes guard (log + still write, or refuse only when caller opts in); optional namespace prune helper |
| **Process memo** | In-process dict with TTL for hot payloads (Redfin ZIP map, styled GeoJSON, geocode hits) |
| **Singleflight** | Coalesce concurrent identical keys into one fetch; waiters share success/failure |
| **SWR helper** | Return stale disk/memory immediately + schedule refresh (library chips, overlay re-toggles) |
| **Quantize utils** | Shared coordinate rounding / GeoJSON simplify for zoning + ACS |

**Non-goals for the platform itself:** no new UI and no behavior change until callers are ported. Existing TTLs remain defaults; callers opt into memo / singleflight / SWR / gzip.

**Compatibility:** keep `overlay_cache.read_json` / `write_json` / `cache_key` / `cache_dir` as thin wrappers or re-exports.

## Structural splits

Carve god-modules along clear ownership so ports don’t fight one file:

| Today | Split into |
|-------|------------|
| `property_service.py` | Thin `PropertyService` façade; extract `listing_ingest.py` (add/refresh Zillow), `area_signals.py` (nearby/permits/broadband/market + stale refresh), `financial_sync.py` (listing → assumptions) |
| `pages.py` | `library_page.py` + `property_page.py` (+ small `chip_helpers.py` for nearby/risk chips) |
| `ui_jobs.py` | Stay the I/O boundary; jobs call the new modules |
| Map toggle boilerplate | Optional later helper in `map_view` only if it falls out of the overlay port |

**Rules:** same public behavior; façade methods remain so tests/call sites migrate gradually; no theme/CSS rewrite unless a tiny hook is required for lazy tabs / card patch.

## Port order (after platform + splits)

Each step: targeted tests + quick verify for that surface; full `.\.venv\Scripts\pytest.exe -q` before claiming the step done.

1. **Geocode disk + process memo** — normalize address → lat/lng; ~30d TTL.
2. **Redfin ZIP map** — process memo + singleflight + optional gzip on disk (market chip + sale choropleth share one warm load).
3. **Library query slim-down** — `joinedload(financial)`; thumb path only (not all photos); push filters/sort toward SQL where cheap.
4. **Coalesced stale refresh** — one `refresh_stale_area_signals_job`; SWR: show cached chips, refresh in background; **patch cards** instead of full library `refresh()`.
5. **Lazy property tabs** — mount Photos/Map/Neighborhood/Financials on first select; move `ensure_financial` / PMMS into `io_bound` when Financials opens.
6. **Zoning + ACS quantization** — coord precision + simplify; cache styled slim FeatureCollections; process memo on re-toggle; aim ≪ few MB over WS (same layers/labels).
7. **Add-home parallelization** — after pin: photos ‖ area signals; market waits on warm Redfin; signal failures remain best-effort (add never fails on them).
8. **Photo derivatives** — on import, write a sidecar `*_thumb.webp` next to the stored image (no required DB schema change in v1); library/header resolve thumb with fallback to full path; lightbox uses the full/mid-size file.

## Errors & resilience

- Cache corruption → treat as miss, refetch.
- Singleflight waiters get the same success/failure as the leader (no silent empty).
- SWR refresh failures leave last-good chips/overlays; no toast spam on library paint.
- Add-home / geocode: area-signal failures stay best-effort; listing + photos still commit.
- Quantized GeoJSON must still paint and toggle exclusive layers; if simplify fails, fall back to unsimplified cached payload.

## Testing

- Unit: cache TTL, gzip round-trip, singleflight coalescing, memo hit/miss.
- Unit: geocode cache key normalization; Redfin memo does not double-ingest.
- Library list: financial present without N+1; thumb query does not load full photo sets.
- Overlay quantize: fixture GeoJSON shrinks and remains a valid FeatureCollection.
- Existing pytest suite stays green after each port; add tests only where behavior is new.

## Out of scope

- New product features / new map layers / Compare revival
- Redesigning the cyberpunk theme or changing Financials math formulas
- Changing Gemini prompt semantics (only when/how work is scheduled)
- Global LRU eviction across all namespaces (optional prune helper is enough for v1)
- Vector tiles / CDN (quantize + memo first)

## Success criteria

1. `.\.venv\Scripts\pytest.exe -q` passes after platform land and after each port step.
2. Opening a property does not mount Map/Financials/Neighborhood work until the tab is selected; Financials PMMS/network is not on the UI thread at property open.
3. Library load with many homes does not `joinedload` all photos; financial captions still render; filters still work.
4. Library stale chip refresh does not require a full list rebuild when only chip JSON changed (card patch).
5. Zoning/ACS toggle payloads are materially smaller than today while layers still render correctly.
6. Cold Redfin ingest happens at most once per process for concurrent callers (singleflight); warm toggles hit process memo.
7. Repeat geocode of the same normalized address hits cache within TTL.
8. Add-home still imports listing + photos; area signals remain best-effort; perceived wait drops when parallelized.
9. Library/header thumbnails can use derivative thumbs without breaking pin/lightbox.
10. Living docs (`AGENTS.md`, `README.md`) describe the cache platform and any user-visible responsiveness changes.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Platform rewrite breaks every overlay caller | Compatibility re-exports; port one caller at a time; tests on disk API first |
| Lazy tabs miss first-paint side effects (geocode, schools) | Keep intentional auto-geocode only when Map tab mounts; Neighborhood schools job only when that tab mounts |
| Card patch drifts from full refresh | Shared card-render helper used by both full paint and patch |
| Over-simplified zoning looks wrong | Quantize/simplify with fallback to prior payload; visual spot-check LA pin |
| Photo derivatives break existing paths | Keep `Photo.path` as the full/mid-size file; sidecar thumb by naming convention; resolve with fallback to full |
| Parallel add-home races on session/ORM | One session owner for DB writes; workers return plain dicts; serialize commits |
| Structural split merge conflicts | Façade-first extract; update imports in same change as move |

## Implementation note

After this written spec is user-reviewed, implement via `writing-plans` → sequenced execution (platform → splits → ports 1–8). Prefer verification evidence before claiming any step done.
