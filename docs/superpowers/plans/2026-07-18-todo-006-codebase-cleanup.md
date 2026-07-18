# TODO-006 Codebase Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Janitor pass that removes dead code, deduplicates wasteful work, and aligns docs — without changing product features or user-visible behavior.

**Architecture:** Safe deletions first, then behavior-preserving efficiency fixes (single Zillow HTML fetch, batched photo commits, fewer redundant SQLite loads), then doc/status sync. Prefer mechanical cleanups over refactors that merge overlapping address parsers or money formatters (those stay for a later pass — higher behavior-drift risk).

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy + SQLite, pytest, existing `app/core/*` helpers

## Global Constraints

- Do **not** remove or change any features or how they work (user lock).
- Do **not** defer Map / Street View rendering until tab focus (would change when pin/SV appear).
- Do **not** rewrite `docs/RESEARCH.md` research recommendations — only fix factual “Implemented” crime coverage wording.
- Do **not** delete historical `docs/superpowers/specs/*` or BUG-001.
- Do **not** commit unless the user asks.
- After meaningful fixes: update `AGENTS.md` + `README.md` + mark TODO-006 Done in `docs/TODO.md`.
- Verify with `.\.venv\Scripts\pytest.exe -q` before claiming done.
- Prefer Windows venv interpreter: `.\.venv\Scripts\python.exe`.

---

## File map (who touches what)

| File | Role in cleanup |
|------|-----------------|
| `app/main.py` | Drop unused `Path` import |
| `app/core/module_registry.py` | Remove unused `reset_modules_cache` |
| `app/core/neighborhood.py` | Remove dead Reddit embed helpers + `normalize_http_url` |
| `tests/test_neighborhood.py` | Drop tests for removed Reddit embed helpers |
| `app/core/property_service.py` | Remove `photo_absolute_path`; single HTML fetch on add; batch photo import |
| `app/core/zillow_photos.py` | Optional: accept pre-fetched HTML for photo URL extraction |
| `app/core/zillow_listing.py` | Already has `extract_listing_details(html)` — reuse |
| `app/ui/pages.py` | Library double-query fix; property page one-load-per-module loop |
| `app/modules/{gallery,financial,neighborhood_reviews,map_view}.py` | Stop redundant `get_property` on initial render when caller already passed `prop` |
| `app/modules/street_view.py` | Avoid second ensure/geocode when coords already present on passed prop |
| `app/core/overlay_cache.py` | Delete expired cache files on miss |
| `app/modules/financial.py` | Lazy-import plotly inside chart redraw |
| `AGENTS.md`, `README.md`, `docs/TODO.md`, `.env.example`, `docs/BUGS.md`, `docs/RESEARCH.md` | Status + crime wording sync |

**Out of scope this pass (documented for later):** unifying `_format_price` / `_money` helpers; merging `parse_address_parts` vs `_split_us_address`; shared `bbox_around`; overview cache key versioning (belongs with TODO-009 prompt change); broad `except Exception` narrowing (log-only is optional hygiene in Task 7 notes).

---

### Task 1: Dead code and unused imports (safe)

**Files:**
- Modify: `app/main.py`
- Modify: `app/core/module_registry.py`
- Modify: `app/core/neighborhood.py`
- Modify: `app/core/property_service.py`
- Modify: `tests/test_neighborhood.py`

**Interfaces:**
- Consumes: none
- Produces: removed symbols — nothing else may call them (verified unused)

- [ ] **Step 1: Confirm symbols are unreferenced**

Run from repo root:

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\python.exe -c "import pathlib,re; root=pathlib.Path('.'); names=['normalize_http_url','reset_modules_cache','photo_absolute_path','parse_reddit_post_url','reddit_embed_url','is_valid_reddit_post_url'];
for n in names:
  hits=[str(p) for p in root.rglob('*.py') if n in p.read_text(encoding='utf-8', errors='ignore')]
  print(n, '->', hits)"
```

Expected: each name only appears in its definition file and (for Reddit helpers) `tests/test_neighborhood.py`.

- [ ] **Step 2: Remove unused `Path` import from `main.py`**

In `app/main.py`, delete:

```python
from pathlib import Path
```

Leave `DATA_DIR.mkdir` usage unchanged (`DATA_DIR` already imported from `app.core.db`).

- [ ] **Step 3: Remove `reset_modules_cache` from `module_registry.py`**

Delete the entire function:

```python
def reset_modules_cache() -> None:
    global _MODULES
    _MODULES = None
```

Keep `discover_modules` / `get_modules` / `_MODULES` cache as-is.

- [ ] **Step 4: Remove `photo_absolute_path` from `PropertyService`**

In `app/core/property_service.py`, delete:

```python
    def photo_absolute_path(self, photo: Photo) -> Path:
        return UPLOADS_DIR / photo.path
```

If `Path` becomes unused in that file after removal, drop the unused import only if nothing else needs it (file still uses `Path` for other paths — keep import).

- [ ] **Step 5: Remove dead URL helpers from `neighborhood.py`**

Delete `parse_reddit_post_url`, `reddit_embed_url`, `is_valid_reddit_post_url`, and `normalize_http_url` (entire functions through end of each).

Also remove now-unused pieces only if nothing remaining needs them:
- `_REDDIT_POST_RE` if only used by `parse_reddit_post_url`
- `quote` from `urllib.parse` if only used by `reddit_embed_url`
- `urlparse` if only used by `normalize_http_url`

Keep all deep-link builders (`reddit_search_url`, Niche/City-Data helpers, `build_review_links`, etc.) untouched.

- [ ] **Step 6: Trim Reddit embed tests**

In `tests/test_neighborhood.py`:
- Remove imports of `is_valid_reddit_post_url`, `parse_reddit_post_url`, `reddit_embed_url`
- Remove `test_reddit_embed_url_valid` and any sibling tests that only cover those helpers
- Keep tests for deep-link URL builders and neighborhood resolution

- [ ] **Step 7: Run neighborhood + smoke tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_neighborhood.py tests/test_core.py -q
```

Expected: PASS

- [ ] **Step 8: Commit (only if user asked)**

```powershell
git add app/main.py app/core/module_registry.py app/core/neighborhood.py app/core/property_service.py tests/test_neighborhood.py
git commit -m "$(cat <<'EOF'
Remove unused imports and dead neighborhood embed helpers.

EOF
)"
```

---

### Task 2: Single Zillow HTML fetch on add-home

**Files:**
- Modify: `app/core/property_service.py` (`add_property_from_zillow` ~262–289, `import_zillow_photos` ~674+)
- Modify: `app/core/zillow_photos.py` (`fetch_listing_photo_urls`)
- Test: `tests/test_zillow_photos.py`, `tests/test_listing_filters.py` (no behavior change expected)

**Interfaces:**
- Consumes: `fetch_listing_html`, `extract_listing_details`, `extract_photo_urls` (already exist)
- Produces: `fetch_listing_photo_urls(zillow_url, *, html: str | None = None) -> FetchedListingPhotos`
- Produces: `import_zillow_photos(..., *, html: str | None = None)` optional kwarg for reuse

- [ ] **Step 1: Allow photo fetch to reuse HTML**

In `app/core/zillow_photos.py`, change:

```python
def fetch_listing_photo_urls(
    zillow_url: str,
    *,
    html: str | None = None,
) -> FetchedListingPhotos:
    page = html if html is not None else fetch_listing_html(zillow_url)
    urls = extract_photo_urls(page, zillow_url=zillow_url)
    if not urls:
        raise ValueError(
            "No listing photos found on that Zillow page. "
            "The link may be invalid, blocked, or not a home details page."
        )
    return FetchedListingPhotos(urls=urls, raw_html_bytes=len(page))
```

Default `html=None` keeps every existing caller identical.

- [ ] **Step 2: Thread HTML through `import_zillow_photos`**

In `property_service.py`:

```python
def import_zillow_photos(
    self,
    property_id: int,
    *,
    replace: bool = False,
    html: str | None = None,
) -> int:
    ...
    fetched = fetch_listing_photo_urls(prop.zillow_url, html=html)
    ...
```

Gallery “Re-import (replace)” continues to call with no `html` (second network fetch OK).

- [ ] **Step 3: Fetch once in `add_property_from_zillow`**

Replace the separate `fetch_listing_details` + `import_zillow_photos` pair with one HTML fetch:

```python
        html: str | None = None
        try:
            html = fetch_listing_html(prop.zillow_url)
            details = extract_listing_details(html)
            self._apply_listing_details(prop, details)
            self._fill_location_from_address(prop)
            self.session.commit()
            self.session.refresh(prop)
        except Exception:
            # Keep the home even if listing scrape fails; user can refresh/edit later.
            html = None

        try:
            lat, lng = geocode_address(prop.address)
            prop.latitude = lat
            prop.longitude = lng
            self.session.commit()
            self.session.refresh(prop)
        except ValueError:
            pass

        imported = 0
        if import_photos:
            try:
                imported = self.import_zillow_photos(prop.id, html=html)
            except Exception:
                imported = 0
        return prop, imported
```

Add imports at top of `property_service.py` if not present:

```python
from app.core.zillow_listing import extract_listing_details, fetch_listing_details
from app.core.zillow_photos import fetch_listing_html  # or via existing photo imports
```

Keep `fetch_listing_details` for Refresh listing / `ensure_neighborhood` paths — do not delete those call sites.

**UX identity checklist:** On scrape failure, home still saved; photos still optional; geocode failure still ignored — same as today.

- [ ] **Step 4: Run photo + listing tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_zillow_photos.py tests/test_listing_filters.py -q
```

Expected: PASS

- [ ] **Step 5: Commit (only if user asked)**

```powershell
git add app/core/property_service.py app/core/zillow_photos.py
git commit -m "$(cat <<'EOF'
Reuse one Zillow HTML fetch when adding a home.

EOF
)"
```

---

### Task 3: Batch photo DB writes during Zillow import

**Files:**
- Modify: `app/core/property_service.py` (`import_zillow_photos`, possibly a private `_write_photo_bytes_no_commit` helper)
- Test: existing photo tests; add a focused unit test if none covers import batching

**Interfaces:**
- Consumes: `download_image`, `extension_for`, `select_thumbnail`, `delete_photo` (unchanged signatures for callers)
- Produces: same `import_zillow_photos(...) -> int` return value (count imported)

- [ ] **Step 1: Write a failing test for one-commit import**

Add to `tests/test_zillow_photos.py` or `tests/test_core.py` a test that mocks `fetch_listing_photo_urls` + `download_image` and asserts multiple photos land with a single commit path — simplest approach: monkeypatch downloads to return tiny JPEG bytes and assert `len(prop.photos)` and `imported` count. Do **not** hit the network.

Example shape (adapt to existing fixtures):

```python
def test_import_zillow_photos_batches_commits(monkeypatch, tmp_path, session):
    # arrange property with zillow_url; monkeypatch UPLOADS_DIR if tests already do
    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_photo_urls",
        lambda url, html=None: FetchedListingPhotos(urls=["https://example.com/a.jpg", "https://example.com/b.jpg"], raw_html_bytes=1),
    )
    monkeypatch.setattr(
        "app.core.property_service.download_image",
        lambda url: (b"fake-bytes", "image/jpeg"),
    )
    svc = PropertyService(session)
    n = svc.import_zillow_photos(prop.id)
    assert n == 2
    session.refresh(prop)
    assert len(prop.photos) == 2
```

If the test suite has no easy session fixture, implement the batching and rely on existing tests + manual import smoke — do not invent a heavy new fixture framework.

- [ ] **Step 2: Implement batched import**

Refactor `import_zillow_photos` loop so that for each URL it:
1. downloads bytes (same skip-on-`ValueError` as today)
2. writes file to disk (same collision `stem_i` rules as `add_photo_bytes`)
3. `session.add(Photo(...))` with increasing `sort_order`
4. does **not** call `get_property` per photo

After the loop: **one** `session.commit()`, then `select_thumbnail(property_id)` once (same as calling `add_photo_bytes` N times then selecting thumb — today each add commits but thumb is selected only via later paths; match current end behavior: after import, `select_thumbnail` runs once in `import_zillow_photos` if that already exists at end — read current end of function and preserve).

Failure surface note: mid-batch download skip still continues (same); disk write failure mid-loop should still fail the import (acceptable — rare). Do not soften exception handling vs today beyond batching commits.

- [ ] **Step 3: Run tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_zillow_photos.py tests/test_core.py -q
```

Expected: PASS

- [ ] **Step 4: Commit (only if user asked)**

```powershell
git add app/core/property_service.py tests/
git commit -m "$(cat <<'EOF'
Batch photo rows into one DB commit during Zillow import.

EOF
)"
```

---

### Task 4: Fewer redundant property loads (pages + modules)

**Files:**
- Modify: `app/ui/pages.py` (library `refresh`, property tab loop)
- Modify: `app/modules/gallery.py`, `financial.py`, `neighborhood_reviews.py`, `map_view.py`
- Modify: `app/modules/street_view.py` only if needed for double-ensure

**Interfaces:**
- Consumes: `ModuleSpec.render(prop, container)` — keep signature
- Produces: modules use the passed `prop` for initial paint; re-`get_property` only after mutations

- [ ] **Step 1: Fix library double `list_properties`**

In `pages.py` `refresh()`:

```python
        def refresh() -> None:
            list_box.clear()
            search = search_input.value or ""
            min_price = _parse_filter_float(min_price_input.value)
            max_price = _parse_filter_float(max_price_input.value)
            min_beds = _parse_filter_float(min_beds_input.value)
            with get_session() as session:
                svc = PropertyService(session)
                props = svc.list_properties(
                    search=search,
                    min_price=min_price,
                    max_price=max_price,
                    min_beds=min_beds,
                )
                if props:
                    has_any = True
                elif not search and min_price is None and max_price is None and min_beds is None:
                    has_any = False
                else:
                    # Any home exists? cheap count without filters
                    has_any = bool(svc.list_properties())
```

Better (preferred): add a tiny `PropertyService.has_any_properties() -> bool` using `session.query(Property.id).limit(1).first() is not None` or SQLAlchemy 2.0 `session.scalar(select(Property.id).limit(1)) is not None` — **no photos join**.

```python
    def has_any_properties(self) -> bool:
        return self.session.scalar(select(Property.id).limit(1)) is not None
```

Then:

```python
                props = svc.list_properties(...)
                has_any = True if props else svc.has_any_properties()
```

Empty-state copy must stay identical:
- no homes at all → `"No homes yet — paste a Zillow link above."`
- filters match none → `"No homes match these filters."`

- [ ] **Step 2: Property page — load once per tab panel setup**

Today each module opens a new session + `get_property`. Change to one load for the page chrome, then either:
- **Option A (preferred, safest UX):** keep per-module session but pass `prop_id` and let modules load once — wait, that does not reduce N loads.

Preferred concrete approach:

```python
        with get_session() as session:
            live = PropertyService(session).get_property(prop_id)
            if live is None:
                ui.label("Not found")
                return
            # build header using live ...
            for mod in modules:
                with ui.tab_panel(...):
                    panel = ui.column().classes("w-full")
                    # Detached instance is OK for read-only initial render of attributes already loaded
                    mod.render(live, panel)
```

**Critical:** expire/detach issues — if `live` is used outside the session block, access to lazy relationships can fail. Today `get_property` uses `joinedload` for photos + financial — verify and keep that. Render only using already-loaded attributes during the open session **or** `session.expunge(live)` after loading needed relationships.

Safest pattern matching current code structure:

```python
        with get_session() as session:
            live = PropertyService(session).get_property(prop_id)
            if live is None:
                ...
                return
            # touch relationships so they are loaded
            _ = list(live.photos)
            _ = live.financial
            session.expunge(live)

        # header + tabs use detached `live`
        for mod in modules:
            with ui.tab_panel(...):
                mod.render(live, panel)
```

Modules that mutate must open a **new** session and `get_property` again (they already do after saves).

- [ ] **Step 3: Modules — skip initial re-fetch when `prop.id` matches**

In each module `render(prop, container)`:
- Use the passed `prop` for first paint instead of immediately calling `get_property(prop.id)` when the only goal is reading fields.
- Keep internal `reload()` helpers that re-fetch after Ask Gemini / geocode / import / save.

For `map_view.redraw` / Street View: if `prop.latitude` and `prop.longitude` are set, do not call `ensure_coordinates` again on first paint. `auto_geocode_if_needed` stays for missing pins.

- [ ] **Step 4: Run UI-adjacent tests**

```powershell
.\.venv\Scripts\pytest.exe -q
```

Expected: PASS (no UI browser tests — unit suite green is the gate)

- [ ] **Step 5: Commit (only if user asked)**

```powershell
git add app/ui/pages.py app/core/property_service.py app/modules/
git commit -m "$(cat <<'EOF'
Cut redundant property loads on library and property pages.

EOF
)"
```

---

### Task 5: Overlay cache prune + lazy Plotly import

**Files:**
- Modify: `app/core/overlay_cache.py`
- Modify: `app/modules/financial.py`
- Test: `tests/test_map_overlays.py` (still pass); optionally add tiny cache expiry unit test

**Interfaces:**
- Consumes: `read_json` / `write_json` call sites unchanged
- Produces: same return values; expired files deleted on read miss

- [ ] **Step 1: Delete expired cache file on TTL miss**

In `overlay_cache.read_json`:

```python
def read_json(namespace: str, key: str, *, max_age_s: float | None = None) -> Any | None:
    path = cache_dir(namespace) / f"{key}.json"
    if not path.is_file():
        return None
    if max_age_s is not None:
        age = time.time() - path.stat().st_mtime
        if age > max_age_s:
            path.unlink(missing_ok=True)
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
```

- [ ] **Step 2: Lazy-import Plotly in financial module**

Move `import plotly...` from module top-level into the function that builds figures (e.g. inside `redraw` / chart builders). Keep chart appearance and data identical. Module discovery must still succeed without Plotly import error unless Plotly missing entirely (it is a project dep).

- [ ] **Step 3: Run tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_map_overlays.py tests/test_gemini_financial.py -q
```

Expected: PASS

- [ ] **Step 4: Commit (only if user asked)**

```powershell
git add app/core/overlay_cache.py app/modules/financial.py
git commit -m "$(cat <<'EOF'
Prune expired overlay cache files and lazy-load Plotly.

EOF
)"
```

---

### Task 6: Docs and backlog status sync

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/TODO.md`
- Modify: `.env.example`
- Modify: `docs/BUGS.md`
- Modify: `docs/RESEARCH.md` (Implemented bullet only)

- [ ] **Step 1: Crime coverage wording**

Align user-facing blurbs to: **LA County (LAPD Socrata + Santa Monica CKAN) + Seattle**, hex density — matching AGENTS product decision #7.

Update stale “LA/Seattle SODA only” lines in:
- `docs/TODO.md` TODO-002 notes
- `README.md` Map row
- `.env.example` SOCRATA comment
- `docs/RESEARCH.md` “Implemented” slice only

- [ ] **Step 2: Mark TODO-006 Done**

In `docs/TODO.md` and `AGENTS.md` in-progress table: status **Done** with date 2026-07-18; summarize: dead helpers removed, single HTML fetch on add, batched photo import, fewer DB loads, overlay cache prune, lazy Plotly, docs sync. Features unchanged.

- [ ] **Step 3: Slim AGENTS “In progress / next”**

Keep only truly open rows (`TODO-009`, partial `TODO-002` / `map-overlays-impl`). Move completed rows out or leave under “What’s done”. Bump “Last updated” line.

- [ ] **Step 4: Archive BUG-002**

In `docs/BUGS.md`, move BUG-002 under a `## Fixed` heading (or keep status `fixed` and add note “archived — no action”). Leave BUG-001 open.

- [ ] **Step 5: Commit (only if user asked)**

```powershell
git add AGENTS.md README.md docs/TODO.md docs/BUGS.md docs/RESEARCH.md .env.example
git commit -m "$(cat <<'EOF'
Document TODO-006 cleanup and fix stale crime coverage notes.

EOF
)"
```

---

### Task 7: Full verification gate

**Files:** none (run only)

- [ ] **Step 1: Full test suite**

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\pytest.exe -q
```

Expected: all tests PASS

- [ ] **Step 2: Manual smoke (if app not already running)**

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Quick checklist (behavior must match pre-cleanup):
1. Library list + Filter empty states
2. Add home from Zillow still gets details + photos (faster is OK)
3. Map pin + flood/income/crime toggles + Street View below
4. Financials charts + Gemini ask still work
5. Neighborhood deep links + Gemini sections still work

- [ ] **Step 3: Required skill** Use `verification-before-completion` before claiming done — cite pytest output and any smoke notes.

---

## Self-review

**1. Spec coverage (TODO-006):**
- Dead code / unused imports → Task 1
- Duplicate wasteful work / efficiency → Tasks 2–5
- Stale docs → Task 6
- Don’t change product behavior → Global Constraints + UX identity checks
- Thin modules vs fat core / naming cleanup → deferred (higher risk); not required for moderate pass

**2. Placeholder scan:** No TBD steps; concrete code and commands included.

**3. Type consistency:** `fetch_listing_photo_urls(..., html=None)` and `import_zillow_photos(..., html=None)` optional kwargs are consistent across Tasks 2–3.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-18-todo-006-codebase-cleanup.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
