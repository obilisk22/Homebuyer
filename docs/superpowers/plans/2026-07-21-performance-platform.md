# Performance Platform + Hot-Path Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a shared cache platform (disk + process memo + singleflight + SWR + GeoJSON quantize), split oversized modules, then port ranked hot paths so Homebuy feels faster without changing product semantics.

**Architecture:** Platform-first (Approach 2). Introduce `app/core/cache/` with compatibility re-exports from `overlay_cache.py`. Extract `listing_ingest` / `area_signals` / `financial_sync` behind a thin `PropertyService` façade and split `pages.py` into library/property modules. Then port geocode → Redfin → library query → stale refresh → lazy tabs → zoning/ACS quantize → add-home parallel → photo thumbs.

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy + SQLite, existing `overlay_cache` callers, Pillow (photos), pytest.

**Spec:** [`docs/superpowers/specs/2026-07-21-performance-platform-design.md`](../specs/2026-07-21-performance-platform-design.md)

## Global Constraints

- Everything must keep working: library, add-home, map overlays, financials, neighborhood, photos, packaging — no product-behavior regressions.
- Same chips, layers, labels, Financials math, Gemini prompt semantics, cyberpunk theme (scheduling/structure only).
- Long UI I/O via `await run.io_bound(...)` + `app/core/ui_jobs.py` (own `get_session()`; never pass ORM/UI across threads).
- Prefer bisectable steps: pytest green after each task; quick verify for the touched surface.
- Update `AGENTS.md` + `README.md` when user-facing / continuity behavior changes (fold into the task that ships the change).
- Do not commit unless the user asks (or the task step explicitly says commit and the user approved plan execution with commits).
- Windows: run tests with `.\.venv\Scripts\pytest.exe …` from repo root.

---

## File map

| Path | Responsibility |
|------|----------------|
| `app/core/cache/__init__.py` | Public exports |
| `app/core/cache/disk.py` | JSON(/gzip) disk store, TTL, prune helper |
| `app/core/cache/memo.py` | Process-local TTL memo |
| `app/core/cache/singleflight.py` | Coalesce concurrent identical keys |
| `app/core/cache/swr.py` | Stale-while-revalidate helper |
| `app/core/cache/geojson_quantize.py` | Coord round + ring simplify |
| `app/core/overlay_cache.py` | Thin re-export / wrapper for existing imports |
| `app/core/listing_ingest.py` | Add/refresh Zillow listing + photos orchestration |
| `app/core/area_signals.py` | Nearby/permits/broadband/market + coalesced stale refresh |
| `app/core/financial_sync.py` | Listing → `FinancialAssumptions` sync helpers |
| `app/core/property_service.py` | Thin façade delegating to the above |
| `app/ui/chip_helpers.py` | Nearby + risk/market chip render helpers |
| `app/ui/library_page.py` | `/` library route |
| `app/ui/property_page.py` | `/property/{id}` route + lazy tabs |
| `app/ui/pages.py` | Re-export routes / shared `page_header` only |
| `tests/test_cache_platform.py` | Disk/memo/singleflight/SWR/quantize |
| `tests/test_geocode.py` | Extend for address cache |
| `tests/test_market_activity.py` / Redfin tests | Memo + singleflight |
| `tests/test_listing_filters.py` | Library query slim-down |
| `tests/test_zillow_photos.py` | Thumb sidecar |

---

### Task 1: Cache platform — disk, memo, singleflight, quantize

**Files:**
- Create: `app/core/cache/__init__.py`
- Create: `app/core/cache/disk.py`
- Create: `app/core/cache/memo.py`
- Create: `app/core/cache/singleflight.py`
- Create: `app/core/cache/swr.py`
- Create: `app/core/cache/geojson_quantize.py`
- Create: `tests/test_cache_platform.py`
- Modify: `app/core/overlay_cache.py` (re-export new disk API; keep signatures)

**Interfaces:**
- Produces:
  - `cache_dir(*parts: str) -> Path`
  - `cache_key(*parts: str) -> str`
  - `read_json(namespace: str, key: str, *, max_age_s: float | None = None) -> Any | None`
  - `write_json(namespace: str, key: str, payload: Any, *, gzip: bool = False, max_bytes: int | None = None) -> Path`
  - `prune_namespace(namespace: str, *, max_age_s: float) -> int`
  - `memo_get(ns: str, key: str) -> Any | None` / `memo_set(ns: str, key: str, value: Any, *, ttl_s: float) -> None` / `memo_clear(ns: str | None = None) -> None`
  - `singleflight(ns: str, key: str, factory: Callable[[], T]) -> T`
  - `swr_get(ns: str, key: str, *, max_age_s: float, soft_age_s: float, factory: Callable[[], Any]) -> Any | None` — return stale if within soft, refresh when past soft but within max (sync factory for unit tests; callers wrap refresh in threads later)
  - `quantize_geojson(fc: dict, *, precision: int = 5, min_ring_points: int = 4) -> dict`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cache_platform.py`:

```python
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.core.cache import (
    cache_dir,
    cache_key,
    memo_clear,
    memo_get,
    memo_set,
    prune_namespace,
    quantize_geojson,
    read_json,
    singleflight,
    write_json,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    # paths.DATA_DIR is resolved at import in some modules — re-bind cache root if needed
    from app.core import paths
    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    memo_clear()
    yield
    memo_clear()


def test_disk_roundtrip_and_ttl(tmp_path):
    write_json("t", "k1", {"a": 1})
    assert read_json("t", "k1", max_age_s=60) == {"a": 1}
    path = cache_dir("t") / "k1.json"
    # expire by rewriting mtime
    older = time.time() - 120
    import os
    os.utime(path, (older, older))
    assert read_json("t", "k1", max_age_s=60) is None


def test_gzip_roundtrip():
    write_json("t", "gz", {"n": list(range(50))}, gzip=True)
    assert (cache_dir("t") / "gz.json.gz").is_file()
    assert read_json("t", "gz", max_age_s=60)["n"][0] == 0


def test_memo_ttl():
    memo_set("m", "x", 42, ttl_s=0.2)
    assert memo_get("m", "x") == 42
    time.sleep(0.25)
    assert memo_get("m", "x") is None


def test_singleflight_coalesces():
    calls = {"n": 0}
    barrier = threading.Barrier(3)

    def factory():
        calls["n"] += 1
        time.sleep(0.1)
        return "ok"

    results = []

    def worker():
        barrier.wait()
        results.append(singleflight("sf", "one", factory))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["ok", "ok", "ok"]
    assert calls["n"] == 1


def test_quantize_geojson_shrinks_coords():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"zone_code": "R1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-118.123456789, 34.123456789],
                            [-118.123456780, 34.123456780],
                            [-118.12, 34.12],
                            [-118.123456789, 34.123456789],
                        ]
                    ],
                },
            }
        ],
    }
    out = quantize_geojson(fc, precision=5)
    ring = out["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.12346, 34.12346]
    assert json.dumps(out) != json.dumps(fc)


def test_cache_key_stable():
    assert cache_key("a", "b") == cache_key("a", "b")
    assert cache_key("a", "b") != cache_key("a", "c")


def test_prune_namespace_removes_old():
    write_json("oldns", "a", {"x": 1})
    path = cache_dir("oldns") / "a.json"
    older = time.time() - 9999
    import os
    os.utime(path, (older, older))
    assert prune_namespace("oldns", max_age_s=60) >= 1
    assert read_json("oldns", "a") is None
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `.\.venv\Scripts\pytest.exe tests/test_cache_platform.py -v`  
Expected: import errors / missing `app.core.cache`

- [ ] **Step 3: Implement package**

`app/core/cache/disk.py` — move logic from today’s `overlay_cache.py`; add gzip via `gzip.open` writing `key.json.gz` and reading either `.json` or `.json.gz`; on `max_bytes` log a warning (use `logging.getLogger(__name__).warning`) but still write unless `refuse_oversize=True` (default False per spec soft guard).

`app/core/cache/memo.py` — dict keyed by `(ns, key)` → `(expires_at, value)` with lock.

`app/core/cache/singleflight.py` — `threading.Lock` + in-flight `Future`/`Event` map; on exception, propagate to waiters.

`app/core/cache/swr.py` — thin helper using disk mtime: if age ≤ soft return payload; if soft < age ≤ max return payload (caller may refresh); if age > max treat as miss. Keep API simple for Task 8.

`app/core/cache/geojson_quantize.py` — recursively round floats in coordinate arrays; drop consecutive duplicates after round; ensure polygon rings keep ≥ `min_ring_points` (if collapse would break ring, keep original ring).

`app/core/cache/__init__.py` — export all public names.

`app/core/overlay_cache.py` — become:

```python
"""Compatibility wrappers — prefer app.core.cache."""
from app.core.cache import cache_dir, cache_key, read_json, write_json

__all__ = ["cache_dir", "cache_key", "read_json", "write_json"]
```

Ensure `HOMEBUY_DATA_DIR` / `paths.DATA_DIR` still backs `cache_dir` (same as today).

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\pytest.exe tests/test_cache_platform.py -v`  
Also: `.\.venv\Scripts\pytest.exe tests/test_zoning_gis.py tests/test_map_overlays.py tests/test_area_overlays.py -q` (overlay_cache import compatibility)

- [ ] **Step 5: Commit** (if user asked for commits during execution)

```bash
git add app/core/cache app/core/overlay_cache.py tests/test_cache_platform.py
git commit -m "Add shared cache platform with memo, singleflight, and GeoJSON quantize."
```

---

### Task 2: Structural split — PropertyService façade

**Files:**
- Create: `app/core/area_signals.py`
- Create: `app/core/listing_ingest.py`
- Create: `app/core/financial_sync.py`
- Modify: `app/core/property_service.py`
- Modify: `app/core/ui_jobs.py` (imports only if needed)
- Test: existing `tests/test_financial_sync.py`, `tests/test_nearby_signals.py`, `tests/test_core.py`, `tests/test_permits_nearby.py`, `tests/test_fcc_broadband.py`, `tests/test_market_activity.py`

**Interfaces:**
- Consumes: existing methods currently on `PropertyService`
- Produces:
  - `area_signals.refresh_property_all(prop) -> None` (best-effort each signal)
  - `area_signals.refresh_stale_area_signals(session, *, limit: int = 3) -> dict[str, int]` counts refreshed per kind
  - `listing_ingest.add_from_zillow(session, url, *, import_photos: bool) -> tuple[Property, int]`
  - `financial_sync.sync_financial_from_listing(session, prop, details) -> None`
  - `PropertyService` methods remain as thin delegates (same signatures)

- [ ] **Step 1: Move without behavior change**

Extract methods by cut-paste:

1. Nearby/permits/broadband/market refresh + four `refresh_stale_*` → `area_signals.py` (functions taking `session` or operating on attached `Property`).
2. `_sync_financial_from_listing` + helpers only used by it → `financial_sync.py`.
3. `add_from_zillow` / `refresh_listing_details` / photo import orchestration → `listing_ingest.py`.

Keep `PropertyService.add_from_zillow` as:

```python
def add_from_zillow(self, zillow_url: str, *, import_photos: bool = True):
    return listing_ingest.add_from_zillow(
        self.session, zillow_url, import_photos=import_photos
    )
```

Same pattern for stale refresh methods (delegate to `area_signals`).

- [ ] **Step 2: Run regression suite**

Run: `.\.venv\Scripts\pytest.exe tests/test_financial_sync.py tests/test_nearby_signals.py tests/test_permits_nearby.py tests/test_fcc_broadband.py tests/test_market_activity.py tests/test_core.py -q`  
Expected: PASS

- [ ] **Step 3: Commit** (if approved)

```bash
git add app/core/area_signals.py app/core/listing_ingest.py app/core/financial_sync.py app/core/property_service.py app/core/ui_jobs.py
git commit -m "Split PropertyService into listing, area signals, and financial sync modules."
```

---

### Task 3: Structural split — library / property pages

**Files:**
- Create: `app/ui/chip_helpers.py`
- Create: `app/ui/library_page.py`
- Create: `app/ui/property_page.py`
- Modify: `app/ui/pages.py` — keep `page_header`, API keys dialog, re-import/register pages
- Modify: `app/main.py` only if it imports page symbols by path
- Test: `tests/test_library_iteration2.py`, `tests/test_library_street_display.py`, `tests/test_assigned_schools_ui.py`, `tests/test_visual_foundation.py`

**Interfaces:**
- Produces: `@ui.page("/")` in `library_page.py`, `@ui.page("/property/{property_id}")` in `property_page.py`
- `pages.py` re-exports: `from app.ui.library_page import library_page` / `from app.ui.property_page import property_page` so existing imports keep working
- Chip helpers: `_render_nearby_signal_chips`, `_extra_signal_chips`, street/format helpers used by both pages

- [ ] **Step 1: Move code**

Move helpers + `library_page` / `property_page` bodies without changing logic. Ensure NiceGUI still registers routes (import side effects from `app.main` / `pages` load path unchanged).

- [ ] **Step 2: Verify imports**

Run: `.\.venv\Scripts\pytest.exe tests/test_library_iteration2.py tests/test_library_street_display.py tests/test_assigned_schools_ui.py tests/test_visual_foundation.py -q`  
Plus: `.\.venv\Scripts\python.exe -c "from app.ui import pages; from app.ui.library_page import library_page; from app.ui.property_page import property_page"`

- [ ] **Step 3: Commit** (if approved)

```bash
git add app/ui/chip_helpers.py app/ui/library_page.py app/ui/property_page.py app/ui/pages.py
git commit -m "Split library and property pages out of pages.py."
```

---

### Task 4: Geocode disk + process memo

**Files:**
- Modify: `app/core/geocode.py`
- Modify: `tests/test_geocode.py`

**Interfaces:**
- Consumes: `cache.read_json` / `write_json` / `memo_get` / `memo_set` / `cache_key`
- Produces: `geocode_address` checks cache first; key = `cache_key("v1", normalized_query)` where normalized = first candidate or `strip_unit_designator` + casefold collapse whitespace; payload `{"lat": float, "lng": float}`; disk TTL `30 * 24 * 3600`; memo TTL same or 1h (use 1h memo / 30d disk)

- [ ] **Step 1: Write failing test**

```python
@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_uses_disk_cache_on_second_call(mock_get, tmp_path, monkeypatch):
    from pathlib import Path
    from app.core import paths
    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = [{"lat": "34.0", "lon": "-118.0"}]
    mock_get.return_value = response

    a1 = geocode_address("123 Main St Santa Monica CA 90401")
    a2 = geocode_address("123 Main St Santa Monica CA 90401")
    assert a1 == a2
    assert mock_get.call_count == 1
```

- [ ] **Step 2: Run — expect FAIL** (call_count == 2)

- [ ] **Step 3: Implement**

At start of `geocode_address`, after building candidates, for each candidate check memo then disk; on network success write memo+disk for the successful query string. Do not cache failures.

- [ ] **Step 4: Run `tests/test_geocode.py -v` — PASS**

- [ ] **Step 5: Commit** (if approved)

```bash
git commit -am "Cache geocode results on disk and in process memory."
```

---

### Task 5: Redfin ZIP map — memo + singleflight + optional gzip

**Files:**
- Modify: `app/core/redfin_sales.py`
- Modify: `tests/test_market_activity.py` (or add `tests/test_redfin_cache.py`)

**Interfaces:**
- Consumes: `singleflight`, `memo_get`/`memo_set`, `write_json(..., gzip=True)`, `read_json`
- Produces: `_stream_redfin_zip_medians` / `load_zip_market_bundle` go through `singleflight("redfin", _ZIP_MARKET_CACHE_KEY, _load_bundle_uncached)` and memoize the returned dict for `CACHE_MAX_AGE_S` (or shorter process TTL e.g. 1h)

- [ ] **Step 1: Failing test — singleflight**

```python
def test_load_zip_market_bundle_singleflight(monkeypatch):
    calls = {"n": 0}
    def fake_stream():
        calls["n"] += 1
        time.sleep(0.05)
        return {"90210": {"median_sale_price": 1.0, "homes_sold": 10}}
    monkeypatch.setattr("app.core.redfin_sales._stream_redfin_zip_medians", fake_stream)
    # Also bypass disk read inside bundle if needed
    from app.core.redfin_sales import load_zip_market_bundle
    import threading
    out = []
    def w():
        out.append(load_zip_market_bundle())
    threads = [threading.Thread(target=w) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert calls["n"] == 1
```

Adjust monkeypatch target to whatever uncached loader you introduce (e.g. `_load_zip_medians_uncached`).

- [ ] **Step 2: Implement** — wrap ingest; write gzip disk payload when rewriting cache; `read_json` must accept `.json.gz`.

- [ ] **Step 3: pytest market + map overlay redfin tests — PASS**

- [ ] **Step 4: Commit** (if approved)

```bash
git commit -am "Memoize and singleflight Redfin ZIP market ingest."
```

---

### Task 6: Library query slim-down

**Files:**
- Modify: `app/core/property_service.py` (`list_properties`) and/or `area_signals` if list moved
- Modify: `app/ui/library_page.py` (thumbnail resolution)
- Modify: `app/core/thumbnail.py` if needed
- Test: `tests/test_listing_filters.py`, `tests/test_library_iteration2.py`

**Interfaces:**
- Produces: `list_properties` uses `joinedload(Property.financial)` and does **not** `joinedload(Property.photos)`. Load thumbnail via separate query or `selectinload` only when needed — preferred: query `Photo` for `thumbnail_photo_id` / first exterior path helper that takes property ids and returns `dict[int, Photo]`.
- Push simple filters to SQL where cheap: `Property.beds >= min_beds`, price range on `list_price`, `ilike` search on address/city when dialect supports (SQLite `like`).

- [ ] **Step 1: Failing test**

```python
def test_list_properties_does_not_eager_load_all_photos(session_with_home_and_many_photos):
    # After list_properties, photos collection should not be loaded for every prop
    props = PropertyService(session).list_properties()
    from sqlalchemy import inspect as sa_inspect
    for p in props:
        assert not sa_inspect(p).unloaded  # better:
        state = sa_inspect(p)
        assert "photos" in state.unloaded or "photos" not in state.attrs
```

Use SQLAlchemy `sa_inspect(p).attrs.photos.loaded_value` — assert photos not loaded; assert `financial` is loaded when present.

- [ ] **Step 2: Implement query + library thumb batch fetch**

- [ ] **Step 3: pytest listing filters + library iteration — PASS**

- [ ] **Step 4: Commit** (if approved)

```bash
git commit -am "Slim library listing query: financial join, no full photo graphs."
```

---

### Task 7: Coalesced stale refresh + card patch

**Files:**
- Modify: `app/core/area_signals.py`
- Modify: `app/core/ui_jobs.py` — add `refresh_stale_area_signals_job`
- Modify: `app/ui/library_page.py` — one timer job; patch chip row instead of full `refresh()`
- Deprecate individual stale jobs (keep thin wrappers calling coalesced for compatibility)

**Interfaces:**
- Produces: `refresh_stale_area_signals(*, limit: int = 3) -> dict[str, int]`
- `refresh_stale_area_signals_job(*, limit: int = 3) -> dict[str, int]`
- Library: after paint, `await run.io_bound(refresh_stale_area_signals_job, limit=3)`; if any counts > 0, update only chip containers (shared render helper from `chip_helpers`) keyed by `property_id`

- [ ] **Step 1: Unit test coalesced function refreshes up to limit across kinds without requiring four separate DB full scans** (can assert one query pattern or simply that wrappers call shared implementation).

- [ ] **Step 2: Implement + wire library_page**

Remove the 1.25s sleep between homes if present in nearby refresh loop, or parallelize with a small semaphore (max 2) while staying polite to Overpass — prefer sequential but **no** artificial 1.25s unless required by provider; if kept, document why in code comment.

- [ ] **Step 3: Manual quick verify** — library loads, chips appear, after stale job chips update without flash of empty list.

- [ ] **Step 4: pytest nearby/permits/broadband/market — PASS**

- [ ] **Step 5: Commit** (if approved)

```bash
git commit -am "Coalesce library stale area-signal refresh and patch cards."
```

---

### Task 8: Lazy property tabs + Financials off UI thread

**Files:**
- Modify: `app/ui/property_page.py`
- Modify: `app/modules/financial.py`
- Modify: `app/core/ui_jobs.py` — `ensure_financial_job(property_id: int) -> None`
- Test: add `tests/test_lazy_tabs.py` (light: assert render not called for all modules — may need injectable hook); or document manual verify if NiceGUI hard to unit test

**Interfaces:**
- Produces: each `tab_panel` starts empty; on first `tabs` value change / panel show, call `mod.render(prop, panel)` once (track `mounted: set[str]`).
- Default selected tab (Photos) mounts immediately; others wait.
- `financial.render` calls `await run.io_bound(ensure_financial_job, property_id)` then reloads assumptions for UI (make `render` async if needed — NiceGUI supports async handlers; if `render` must stay sync, kick `io_bound` via `ui.timer(0, ...)` then build form).

Preferred pattern:

```python
mounted: set[str] = set()

async def ensure_tab(mod_id: str) -> None:
    if mod_id in mounted:
        return
    mounted.add(mod_id)
    panel = panels[mod_id]
    panel.clear()
    with panel:
        mod_by_id[mod_id].render(prop, panel)

# bind tabs.on_value_change → ensure_tab
# also ensure default tab once at end
```

For Financials PMMS: move `ensure_financial` into `ensure_financial_job` so network is off the event loop.

- [ ] **Step 1: Implement lazy mount**

- [ ] **Step 2: Implement `ensure_financial_job`**

- [ ] **Step 3: Quick verify** — open property: Map Leaflet not created until Map tab; Financials Ask still works; Neighborhood schools load when that tab opens; Map auto-geocode still runs when Map mounts

- [ ] **Step 4: pytest assigned schools UI + financial defaults — PASS**

- [ ] **Step 5: Update AGENTS.md** — note lazy tab mounting

- [ ] **Step 6: Commit** (if approved)

```bash
git commit -am "Lazy-mount property tabs; run ensure_financial via io_bound."
```

---

### Task 9: Zoning + ACS GeoJSON quantization

**Files:**
- Modify: `app/core/zoning_gis.py` — bump `CACHE_REV` to `v7`; apply `quantize_geojson` before `write_json` / on read miss path
- Modify: `app/core/census_acs.py` — quantize styled FeatureCollection; process memo key per layer+bbox
- Modify: `tests/test_zoning_gis.py`, `tests/test_map_overlays.py`
- Optional: lower `main.py` WS buffer only if measured payloads stay under previous need — **do not break** large layers; keep 32 MiB until verified smaller

**Interfaces:**
- Consumes: `quantize_geojson`, `memo_get`/`memo_set`, `singleflight` for identical overlay keys
- On simplify failure / invalid geometry: return pre-quantize payload

- [ ] **Step 1: Test fixture shrink**

```python
def test_zoning_result_is_quantized(monkeypatch):
    # build_zoning_geojson path writes quantized coords at precision 5
    ...
```

- [ ] **Step 2: Implement + CACHE_REV bump**

- [ ] **Step 3: pytest zoning + map overlays — PASS**

- [ ] **Step 4: Manual** — Map Zoning + Income toggles still paint for an LA pin

- [ ] **Step 5: Commit** (if approved)

```bash
git commit -am "Quantize zoning and ACS GeoJSON payloads for smaller map toggles."
```

---

### Task 10: Add-home parallelization

**Files:**
- Modify: `app/core/listing_ingest.py` (`add_from_zillow`)
- Test: extend `tests/test_core.py` or add `tests/test_add_home_parallel.py` with mocked downloaders

**Interfaces:**
- After pin + financial sync: run photo downloads and area-signal refreshes concurrently via `concurrent.futures.ThreadPoolExecutor` (max_workers=4). Serialize DB commits on the owning session — workers return plain dicts/paths; main thread writes ORM rows.
- Market activity may wait on Redfin warm path (Task 5). Signal failures still swallowed.

- [x] **Step 1: Refactor download + signals to pure functions returning data**

- [x] **Step 2: Parallel schedule in `add_from_zillow`**

- [x] **Step 3: pytest add/import paths — PASS**

- [x] **Step 4: Commit** (if approved)

```bash
git commit -am "Parallelize add-home photo import and area signal lookups."
```

---

### Task 11: Photo derivatives (sidecar thumbs)

**Files:**
- Modify: `app/core/zillow_photos.py` / import path in `listing_ingest.py`
- Modify: `app/core/thumbnail.py` — resolve `stem_thumb.webp` beside `Photo.path`
- Modify: `app/ui/library_page.py` / `property_page.py` thumb URLs
- Modify: `tests/test_zillow_photos.py`, `tests/test_thumbnail.py`

**Interfaces:**
- Produces: after saving image `foo.jpg`, write `foo_thumb.webp` (long edge ~400px, WebP quality ~80). `Photo.path` remains the mid/full file (cap long edge ~1600 on download if easy).
- `resolve_library_thumbnail_url(photo) -> str` prefers thumb sidecar if present.

- [x] **Step 1: Failing test — sidecar created**

```python
def test_import_writes_thumb_sidecar(tmp_path, monkeypatch):
    ...
    assert (uploads / "x_thumb.webp").is_file()
```

- [x] **Step 2: Implement with Pillow**

- [x] **Step 3: pytest photos + thumbnail — PASS**

- [x] **Step 4: Update README/AGENTS** — library uses derivative thumbs when present

- [x] **Step 5: Commit** (if approved)

```bash
git commit -am "Write WebP thumbnail sidecars for library and header cards."
```

---

### Task 12: Final verification + docs sweep

**Files:**
- Modify: `AGENTS.md`, `README.md` — cache platform, lazy tabs, coalesced refresh, photo thumbs, module split paths in Key files table

- [ ] **Step 1: Full test suite**

Run: `.\.venv\Scripts\pytest.exe -q`  
Expected: all PASS

- [ ] **Step 2: Quick verify checklist** (from AGENTS.md) — library, add-home, map toggles, financials, neighborhood, photos

- [ ] **Step 3: Docs sync**

- [ ] **Step 4: Commit** (if approved)

```bash
git commit -am "Document performance platform and responsiveness changes."
```

---

## Plan self-review

| Spec requirement | Task |
|------------------|------|
| Cache platform disk/memo/singleflight/SWR/quantize | 1 |
| overlay_cache compatibility | 1 |
| Split property_service / pages | 2–3 |
| Geocode cache | 4 |
| Redfin memo/singleflight/gzip | 5 |
| Library query slim-down | 6 |
| Coalesced stale + card patch | 7 |
| Lazy tabs + ensure_financial io_bound | 8 |
| Zoning/ACS quantize | 9 |
| Add-home parallel | 10 |
| Photo sidecars | 11 |
| Docs + full verify | 12 |
| Errors/resilience (miss on corrupt, singleflight errors, fallback quantize) | 1, 9, 10 |
| Non-goals respected | Global constraints |

No TBD placeholders. Interfaces named consistently (`refresh_stale_area_signals_job`, `ensure_financial_job`, `quantize_geojson`).
