# Cleanup Sweep #2 (Moderate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove post–TODO-006 dead code, cut clear Gemini/DB waste without changing features, and sync living docs.

**Architecture:** Three batches — (1) mechanical dead-code deletes + test fixes, (2) behavior-preserving efficiency (`force=False`, light peer query, deduped financial sync), (3) AGENTS/README/.env.example continuity. No lazy tabs; no fingerprint product change.

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy + SQLite, pytest, Gemini via `google-genai`

**Spec:** `docs/superpowers/specs/2026-07-18-cleanup-sweep-2-design.md`

## Global Constraints

- No feature removals or UX redesigns.
- Do not defer Map / Neighborhood / Financials tab mounting until first click.
- Do not change financial Gemini fingerprint to subject-URL-only.
- Do not unify money/bbox/address helpers in this pass.
- Do not commit unless the user asks.
- After continuity edits: update `AGENTS.md` and `README.md` in the same turn.
- Verify with `.\.venv\Scripts\pytest.exe -q` before claiming done.
- Work from: `C:\Users\hheaf\Projects\homebuy`

---

## File map

| File | Role |
|------|------|
| `app/core/property_service.py` | Drop dead imports/methods; light `_library_zillow_refs`; refresh/add sync dedupe |
| `app/core/gemini_financial.py` | Drop fin_v3 shims |
| `app/ui/pages.py` | Drop `_listing_meta_bits`; header insights `force=False` |
| `app/modules/financial.py` | Ask `force=False`; Regenerate `force=True` |
| `app/core/census_acs.py` | Drop dead income wrappers / `county_fips_for`; optional `median_income` geojson field |
| `tests/test_map_overlays.py` | Retarget income color tests |
| `tests/` (new or existing) | Cover light peer query + insights force=False if practical |
| `AGENTS.md`, `README.md`, `.env.example`, optionally `app/static/fonts/README.md` | Docs sync |

---

### Task 1: Dead code removal

**Files:**
- Modify: `app/core/property_service.py`
- Modify: `app/core/gemini_financial.py`
- Modify: `app/ui/pages.py`
- Modify: `app/core/census_acs.py`
- Modify: `tests/test_map_overlays.py`

**Interfaces:**
- Consumes: none new
- Produces: same public APIs minus deleted private helpers; map still uses `build_acs_geojson` / `fill_color_for_breaks`

- [ ] **Step 1: Confirm dead symbols still unreferenced**

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\python.exe -c "
from pathlib import Path
names = ['_listing_meta_bits','_financial_assumption_dict','_library_comps_for_financial','LibraryCompSnapshot','library_comps_digest','format_buy_vs_rent_notes','income_fill_color','build_income_geojson','county_fips_for']
root = Path('app')
for n in names:
  hits = [str(p) for p in root.rglob('*.py') if n in p.read_text(encoding='utf-8', errors='ignore')]
  print(n, '->', hits)
"
```

Expected: each name only in its definition file (plus possibly tests for `income_fill_color`).

- [ ] **Step 2: Clean `property_service.py` imports and dead methods**

Remove from imports if unused:
- `summarize` from `app.core.finance` (keep `blend_appreciation_rates` if still used)
- `zillow_urls_digest` from `app.core.gemini_financial`

Delete methods:
- `_financial_assumption_dict` (entire method)
- `_library_comps_for_financial` (entire method; keep `_library_zillow_refs`)

- [ ] **Step 3: Clean `gemini_financial.py` shims**

Delete the back-compat block at end of file (~`LibraryCompSnapshot`, `library_comps_digest`, `format_buy_vs_rent_notes`). Keep `ZillowListingRef`, `build_financial_fingerprint`, `generate_financial_commentary`, etc.

If `build_financial_fingerprint` still has `**_ignored` only for legacy, leave it unless nothing passes extra kwargs (grep first).

- [ ] **Step 4: Delete `_listing_meta_bits` from `pages.py`**

Remove the whole function (~lines 70–96). Confirm no remaining callers (library uses chip helpers).

- [ ] **Step 5: Clean ACS wrappers**

In `census_acs.py`:
- Delete `income_fill_color`
- Delete `county_fips_for` (callers already use `_fcc_fips`)
- Delete `build_income_geojson` if it only wraps the generic path and has no app callers
- If geojson properties include unused `median_income`, stop writing it (keep `fillColor` / `popup`)

In `tests/test_map_overlays.py`, replace:

```python
def test_income_fill_color_breaks():
    assert income_fill_color(None) == "#2A3340"
    ...
```

with calls to `fill_color_for_breaks(value, INCOME_BREAKS)` (import those symbols). Keep the same expected colors.

- [ ] **Step 6: Run focused tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_map_overlays.py tests/test_gemini_financial.py tests/test_core.py -q
```

Expected: PASS

- [ ] **Step 7: Commit only if user asked** — skip by default

---

### Task 2: Gemini force=False + lightweight peers

**Files:**
- Modify: `app/ui/pages.py` (`run_gemini_insights`)
- Modify: `app/modules/financial.py` (`refresh_gemini_panel` Ask button)
- Modify: `app/core/property_service.py` (`_library_zillow_refs`)
- Test: add or extend a unit test for peer query / insights caching if fixtures exist

**Interfaces:**
- Consumes: `ensure_gemini_insights(property_id, *, force: bool = False) -> dict[str, str]`
- Produces: same status keys (`ok` / `cached` / error); peer list still `list[ZillowListingRef]` max 19

- [ ] **Step 1: Header insights use cache**

In `pages.py` `run_gemini_insights`, change:

```python
results = PropertyService(session).ensure_gemini_insights(prop_id, force=False)
```

Keep toast logic that treats `ok` and `cached` as success. Optionally refine message when all three are `cached` (e.g. “Gemini insights already up to date”) — nice-to-have, not required.

- [ ] **Step 2: Financials Ask vs Regenerate**

Mirror Neighborhood:

```python
# When text exists and not stale — Regenerate only:
on_click=lambda: run_gemini(force=True)

# Ask (no text) or stale — Ask/Regenerate label with force=False for Ask path:
# Prefer:
ui.button("Ask Gemini", on_click=lambda: run_gemini(force=False), ...)
ui.button("Regenerate", on_click=lambda: run_gemini(force=True), ...)  # when text present
```

Concrete pattern (match neighborhood_reviews):
- Always show Ask (or primary CTA) with `force=False` when empty or stale needs fill via ensure’s own stale logic
- Show separate Regenerate with `force=True` when text exists

Minimal change that satisfies the spec: change the Ask/empty-state button from `force=True` to `force=False`; leave the Regenerate button at `force=True`.

Current code uses one button that always `force=True`. Split or:

```python
if text and not stale:
    ui.button("Regenerate", on_click=lambda: run_gemini(force=True), ...)
else:
    label = "Regenerate" if text else "Ask Gemini"
    ui.button(label, on_click=lambda: run_gemini(force=False), ...)  # was force=True
```

When stale, `force=False` still regenerates because fingerprint mismatch inside `ensure_gemini_financial`. When empty, generates. When warm cache and user somehow hits Ask — cached. For Regenerate-only UI when warm, keep `force=True`.

- [ ] **Step 3: Lightweight `_library_zillow_refs`**

Replace `list_properties()` loop with a lean select:

```python
def _library_zillow_refs(self, exclude_property_id: int) -> list[ZillowListingRef]:
    rows = self.session.execute(
        select(Property.id, Property.zillow_url, Property.address)
        .where(Property.id != exclude_property_id)
        .order_by(Property.id.asc())
    ).all()
    refs: list[ZillowListingRef] = []
    for pid, zurl, address in rows:
        url = (zurl or "").strip()
        if not url:
            continue
        refs.append(
            ZillowListingRef(
                property_id=int(pid),
                zillow_url=url,
                label=(address or "").strip(),
            )
        )
        if len(refs) >= 19:
            break
    return refs
```

Preserve max 19 peers and URL-required filter. Order by `id` for stable fingerprints (previous order was `list_properties` default — check `list_properties` order and match it).

- [ ] **Step 4: Tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_gemini_financial.py tests/test_gemini_neighborhood.py -q
```

If easy: assert `_library_zillow_refs` returns peers without needing photos. Skip heavy UI tests.

- [ ] **Step 5: Commit only if user asked**

---

### Task 3: Dedupe `_sync_financial_from_listing`

**Files:**
- Modify: `app/core/property_service.py` (`_apply_listing_details`, `refresh_listing_details`, `add_from_zillow`)

**Interfaces:**
- Produces: `_apply_listing_details(prop, details, *, sync_financial: bool = True) -> None`

- [ ] **Step 1: Optional sync flag on apply**

```python
def _apply_listing_details(
    self, prop: Property, details: ListingDetails, *, sync_financial: bool = True
) -> None:
    # ... field copies unchanged ...
    if sync_financial:
        self._sync_financial_from_listing(prop, details)
```

- [ ] **Step 2: Fix `refresh_listing_details`**

Before apply/geocode, capture:

```python
had_coords = prop.latitude is not None and prop.longitude is not None
```

Flow:
1. `details = fetch...` / `_apply_listing_details(prop, details)` (syncs once; includes ACS if `had_coords`)
2. `_fill_location_from_address`
3. If missing coords → `ensure_coordinates`
4. Second sync **only if** `details is not None` and coords exist **and** `not had_coords` (ACS path newly available)

```python
if details is not None:
    now_coords = prop.latitude is not None and prop.longitude is not None
    if now_coords and not had_coords:
        self._sync_financial_from_listing(prop, details)
```

- [ ] **Step 3: Fix `add_from_zillow` double FHFA/PMMS**

```python
self._apply_listing_details(prop, details_for_sync, sync_financial=False)
...
# After geocode success OR geocode failure — exactly one sync:
if details_for_sync is not None:
    self._sync_financial_from_listing(prop, details_for_sync)
```

Place the single sync after the geocode try/except so ACS runs when coords landed, and listing/HOA/PMMS still run when geocode failed.

Remove the inner “re-sync now that coordinates exist” block that duplicated apply’s sync.

- [ ] **Step 4: Run financial/listing tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_financial_sync.py tests/test_core.py tests/test_listing_filters.py -q
```

Expected: PASS (create/adapt tests if sync coverage is thin — do not invent network calls).

- [ ] **Step 5: Commit only if user asked**

---

### Task 4: Docs sync

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `app/static/fonts/README.md` (if Akira/Creato still wrong)

- [ ] **Step 1: AGENTS.md**

- Overlay “What’s done” / map bullet: Zoning + full ACS set + LA County (LAPD + Santa Monica CKAN) + Seattle hex crime — match product decision #7.
- Property model list: include `thumbnail_locked`.
- Fonts: Creato for body/prices; Akira for street/brand (not “Akira for prices”).
- Gemini: Neighborhood default `gemini-3.1-flash-lite`; Financials `GEMINI_FINANCIAL_MODEL` else `GEMINI_MODEL` else `gemini-2.5-flash-lite`.
- Note cleanup sweep #2 in What’s done / last-updated line.
- Slim in-progress table to truly open items only.

- [ ] **Step 2: README.md + `.env.example`**

- Census comment: map ACS layers **and** rent-growth (`B25064`) + tax fallback.
- Uncomment in `.env.example`:

```env
GEMINI_FINANCIAL_MODEL=gemini-2.5-flash-lite
```

- README Financials/Neighborhood model lines match.

- [ ] **Step 3: Fonts README** if stale

- [ ] **Step 4: No commit unless asked**

---

### Task 5: Full verification

- [ ] **Step 1: Full suite**

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\pytest.exe -q
```

Expected: all PASS

- [ ] **Step 2: Manual smoke (if app running)**

1. Property page → header Ask Gemini with warm caches → should be fast / “cached”, not 3 fresh API calls  
2. Financials Ask with existing take → no re-call; Regenerate forces  
3. Refresh listing → financial autofill still works  
4. Library + Map overlays still load  

- [ ] **Step 3: Use `verification-before-completion`** before claiming done — cite pytest output.

---

## Self-review

**Spec coverage:** Dead code → T1; force=False + peers → T2; sync dedupe → T3; docs → T4; verify → T5. Out-of-scope items explicitly excluded.

**Placeholders:** None.

**Consistency:** `_apply_listing_details(..., sync_financial=)` used by T3; `_library_zillow_refs` signature unchanged for financial module.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-18-cleanup-sweep-2.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh agent per task, review between tasks  
2. **Inline Execution** — do tasks in this chat with checkpoints  

Which approach?
