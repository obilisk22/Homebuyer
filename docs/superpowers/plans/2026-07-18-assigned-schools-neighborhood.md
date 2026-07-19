# Assigned Schools (Neighborhood) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the Elementary / Middle / High schools a home is zoned for on the Neighborhood tab, with SchoolDigger ratings + parent reviews and level placeholders — not nearby NCES points on the Map.

**Architecture:** Point-in-polygon against LAUSD attendance ArcGIS layers; resolve school names via LAUSD school points inside each zone polygon; enrich with SchoolDigger API (cached); render three cards in Neighborhood; remove the Map Nearby schools panel.

**Tech Stack:** Python 3.12, NiceGUI, `requests`, existing `overlay_cache`, SchoolDigger REST v2.4, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-assigned-schools-neighborhood-design.md`

## Global Constraints

- Placement: Neighborhood tab **Assigned schools** section after name block, **before** Gemini overview.
- Geography v1: **LAUSD only** (extendable registry); no nearest-as-zoned heuristic.
- LAUSD attendance layers 4/5/6 return keys only — names come from layer-0 points inside the zone polygon (`MAP_TYPE` ES / MS / HS).
- Quality: SchoolDigger stars + parent reviews (`SCHOOLDIGGER_APP_ID` + `SCHOOLDIGGER_APP_KEY`).
- Photos: level placeholders only (no campus images).
- Map: remove **Nearby schools** panel only; leave Schools layer toggle / NCES markers.
- Cache ~7 days under `data/cache/` via `overlay_cache`.
- No live network in default pytest; fixtures/mocks only.
- Windows: `.\.venv\Scripts\pytest.exe`.
- Do not commit unless the user asks (plan commit steps are optional).
- After ship: update `AGENTS.md`, `README.md`, `docs/RESEARCH.md`, `docs/TODO.md`.

## File structure

| File | Responsibility |
|------|----------------|
| `app/core/school_zones.py` | LAUSD attendance PIP + name resolve → assigned E/M/H |
| `app/core/schooldigger.py` | Search/detail client, review normalize, cache |
| `app/modules/neighborhood_reviews.py` | Assigned schools UI section |
| `app/modules/map_view.py` | Remove Nearby schools panel + related helpers |
| `tests/test_school_zones.py` | PIP + name resolve fixtures |
| `tests/test_schooldigger.py` | Enrich normalize fixtures |
| `.env.example` | SchoolDigger keys |
| `AGENTS.md`, `README.md`, `docs/RESEARCH.md` | Continuity |

---

### Task 1: `school_zones` — geometry helpers + LAUSD attendance parse

**Files:**
- Create: `app/core/school_zones.py`
- Create: `tests/test_school_zones.py`

**Interfaces:**
- Produces:
  - `point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool` — ray casting; ring is `[[lng, lat], ...]` (GeoJSON order)
  - `point_in_polygon(lng: float, lat: float, rings: list[list[list[float]]]) -> bool` — true if in outer ring and not in holes (first ring outer; subsequent = holes) **or** simpler v1: true if in **any** ring (LAUSD often single outer)
  - Prefer: in first ring AND not in any subsequent ring
  - `LEVELS = ("elementary", "middle", "high")`
  - `AssignedSchool` TypedDict / dataclass: `level`, `name`, `city`, `state`, `cds_code`, `map_type`, `source`, `attendance_key`
  - `parse_attendance_feature(attrs: dict, *, level: str) -> dict` — extracts `KEY_` / level key fields

- [ ] **Step 1: Write failing tests**

```python
# tests/test_school_zones.py
from app.core.school_zones import point_in_polygon, point_in_ring


def test_point_in_simple_square():
    # square around (0.5, 0.5)
    ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert point_in_ring(0.5, 0.5, ring) is True
    assert point_in_ring(1.5, 0.5, ring) is False


def test_point_in_polygon_with_hole():
    outer = [[0.0, 0.0], [3.0, 0.0], [3.0, 3.0], [0.0, 3.0], [0.0, 0.0]]
    hole = [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0], [1.0, 1.0]]
    assert point_in_polygon(0.5, 0.5, [outer, hole]) is True
    assert point_in_polygon(1.5, 1.5, [outer, hole]) is False
```

- [ ] **Step 2: Run tests — expect FAIL (import error)**

Run: `.\.venv\Scripts\pytest.exe tests/test_school_zones.py::test_point_in_simple_square tests/test_school_zones.py::test_point_in_polygon_with_hole -v`

Expected: FAIL — `ModuleNotFoundError` or import error for `school_zones`

- [ ] **Step 3: Implement geometry helpers in `app/core/school_zones.py`**

```python
"""Assigned school zones via district attendance GIS (LAUSD first)."""

from __future__ import annotations

from typing import Any

import requests

from app.core.overlay_cache import cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 30
CACHE_MAX_AGE_S = 7 * 24 * 3600
CACHE_NS = "school_zones"
CACHE_REV = "v1"

LAUSD_BASE = (
    "https://maps.lacity.org/lahub/rest/services/LAUSD_Schools/MapServer"
)
# level -> (attendance_layer_id, map_type filter for school points)
LAUSD_LEVELS: dict[str, tuple[int, str]] = {
    "elementary": (4, "ES"),
    "middle": (5, "MS"),
    "high": (6, "HS"),
}


def point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-cast; ring vertices are [lng, lat]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 0.0) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_polygon(
    lng: float, lat: float, rings: list[list[list[float]]]
) -> bool:
    if not rings:
        return False
    if not point_in_ring(lng, lat, rings[0]):
        return False
    for hole in rings[1:]:
        if point_in_ring(lng, lat, hole):
            return False
    return True
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\pytest.exe tests/test_school_zones.py::test_point_in_simple_square tests/test_school_zones.py::test_point_in_polygon_with_hole -v`

Expected: PASS

- [ ] **Step 5: Commit (optional)**

```bash
git add app/core/school_zones.py tests/test_school_zones.py
git commit -m "feat: add school zone point-in-polygon helpers"
```

---

### Task 2: `school_zones.resolve_assigned` — LAUSD query + name resolve

**Files:**
- Modify: `app/core/school_zones.py`
- Modify: `tests/test_school_zones.py`

**Interfaces:**
- Consumes: Task 1 geometry helpers; `overlay_cache`
- Produces:
  - `resolve_assigned(lat: float, lng: float) -> dict[str, Any]` with shape:

```python
{
  "status": "ok" | "outside" | "no_pin" | "error",
  "source": "LAUSD attendance",  # when applicable
  "message": str,
  "schools": {
    "elementary": AssignedSchool | None,
    "middle": AssignedSchool | None,
    "high": AssignedSchool | None,
  },
}
```

  - `AssignedSchool` keys: `level`, `name`, `city`, `state` (`"CA"`), `cds_code`, `map_type`, `attendance_key`, `source` (`"LAUSD"`)

**LAUSD algorithm (locked):**

1. For each level in `LAUSD_LEVELS`:
   - `GET {LAUSD_BASE}/{layer}/query` with `geometry={lng},{lat}`, `geometryType=esriGeometryPoint`, `inSR=4326`, `spatialRel=esriSpatialRelIntersects`, `outFields=*`, `returnGeometry=true`, `outSR=4326`, `f=json`
   - If no features → that level is `None` (continue)
   - Take first feature’s `geometry.rings` and `attributes.KEY_` (or level-specific key)
2. Resolve name: `GET {LAUSD_BASE}/0/query` with same point + `distance=3` miles + `units=esriSRUnit_StatuteMile` + `where=MAP_TYPE='ES'` (or MS/HS) + `outFields=FULLNAME,MPD_NAME,CDSCODE,CITY,MAP_TYPE,ADDRESS` + `returnGeometry=true` + `outSR=4326`
3. Keep candidates whose point is `point_in_polygon` inside the attendance rings; prefer `MAP_TYPE` exact match; if multiple, pick closest to pin (haversine — copy/adapt from `schools_nces.haversine_miles`)
4. If **any** level hit → `status=ok`, `source=LAUSD attendance`
5. If **no** level hits: check whether pin is inside LAUSD district outline — query layer **3** is a group (not queryable); instead treat “no hits on all three attendance layers” as `outside` when also a cheap bbox miss: if lat/lng outside rough LAUSD extent `(33.7–34.35, -118.7–-118.15)` → `outside`; if inside extent but zero hits → `status=ok` with all None + message rare boundary gap **or** `status=outside`. Spec: inside registered district with zero hits → boundary-gap message. Implement: if pin in rough LAUSD bbox and zero schools → `status="gap"` with message; else `status="outside"`.

- [ ] **Step 1: Write failing tests with fixtures (no network)**

```python
# append to tests/test_school_zones.py
from app.core.school_zones import (
    pick_school_in_zone,
    schools_from_attendance_payloads,
)


def test_pick_school_in_zone_prefers_inside_point():
    rings = [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]
    candidates = [
        {
            "name": "Outside ES",
            "lng": 3.0,
            "lat": 3.0,
            "map_type": "ES",
            "city": "LOS ANGELES",
            "cds_code": "1",
        },
        {
            "name": "Inside ES",
            "lng": 1.0,
            "lat": 1.0,
            "map_type": "ES",
            "city": "LOS ANGELES",
            "cds_code": "2",
        },
    ]
    picked = pick_school_in_zone(
        1.0, 1.0, rings, candidates, map_type="ES"
    )
    assert picked is not None
    assert picked["name"] == "Inside ES"


def test_schools_from_attendance_payloads_maps_levels():
    # Minimal synthetic attendance + school payloads exercised via pure helpers
    attendance = {
        "elementary": {
            "rings": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            "key": 297,
        },
        "middle": None,
        "high": None,
    }
    school_candidates = {
        "elementary": [
            {
                "name": "Test ES",
                "lng": 1.0,
                "lat": 1.0,
                "map_type": "ES",
                "city": "LOS ANGELES",
                "cds_code": "19647336018048",
            }
        ],
        "middle": [],
        "high": [],
    }
    result = schools_from_attendance_payloads(
        1.0, 1.0, attendance, school_candidates
    )
    assert result["elementary"]["name"] == "Test ES"
    assert result["elementary"]["cds_code"] == "19647336018048"
    assert result["middle"] is None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.\.venv\Scripts\pytest.exe tests/test_school_zones.py -v`

Expected: FAIL on missing `pick_school_in_zone` / `schools_from_attendance_payloads`

- [ ] **Step 3: Implement parse helpers + `resolve_assigned`**

Implement:

- `pick_school_in_zone(pin_lng, pin_lat, rings, candidates, *, map_type) -> dict | None`
- `schools_from_attendance_payloads(...)` — pure assembly for tests
- `_query_lausd_json(url, params) -> dict` — thin requests wrapper
- `_fetch_attendance(level, lat, lng) -> {rings, key} | None`
- `_fetch_school_candidates(map_type, lat, lng) -> list[dict]`
- `resolve_assigned(lat, lng) -> dict` — orchestrates + caches under `CACHE_NS` with key `cache_key(CACHE_REV, round(lat,5), round(lng,5))`

Rough LAUSD bbox constant:

```python
LAUSD_BBOX = (33.70, 34.35, -118.70, -118.15)  # min_lat, max_lat, min_lng, max_lng
```

Name field: prefer `FULLNAME`, fallback `MPD_NAME`.

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\pytest.exe tests/test_school_zones.py -v`

Expected: PASS

- [ ] **Step 5: Commit (optional)**

```bash
git add app/core/school_zones.py tests/test_school_zones.py
git commit -m "feat: resolve LAUSD assigned elementary/middle/high schools"
```

---

### Task 3: SchoolDigger client + enrich

**Files:**
- Create: `app/core/schooldigger.py`
- Create: `tests/test_schooldigger.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: assigned school dict from Task 2
- Produces:
  - `has_schooldigger_keys() -> bool`
  - `enrich_school(school: dict[str, Any]) -> dict[str, Any]` — merges rating fields onto a copy
  - `enrich_assigned(result: dict[str, Any]) -> dict[str, Any]` — enriches each non-None level in `result["schools"]`

Enriched fields added to each school:

| Key | Source |
|-----|--------|
| `rating_stars` | `rankHistory[0].rankStars` (0–5) or None |
| `rating_year` | `rankHistory[0].year` |
| `review_avg` | mean of parent `numberOfStars` (or all reviews if no parent) |
| `review_count` | count used for avg |
| `review_quote` | first parent comment truncated to ~160 chars, else first comment |
| `schooldigger_url` | `url` or `urlSchoolDigger` |
| `schooldigger_id` | `schoolid` |

**API (no paid proximity):**

1. Search: `GET https://api.schooldigger.com/v2.4/schools?st=CA&q={name}&qSearchSchoolNameOnly=true&level={Elementary|Middle|High}&appID=...&appKey=...`
2. Pick best match: normalize names (casefold, strip “School”), prefer city match to `LOS ANGELES` / assigned city
3. Detail: `GET https://api.schooldigger.com/v2.4/schools/{id}?appID=...&appKey=...` for reviews
4. If keys missing: return school unchanged (no raise)
5. Cache search+detail per `cds_code` or normalized name under `data/cache/schooldigger/` (~7d)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_schooldigger.py
from app.core.schooldigger import normalize_enrichment, pick_search_match


def test_pick_search_match_prefers_city():
    school_list = [
        {
            "schoolid": "1",
            "schoolName": "Mar Vista Elementary School",
            "address": {"city": "San Diego", "state": "CA"},
            "url": "https://example.com/a",
            "rankHistory": [{"rankStars": 2, "year": 2025}],
        },
        {
            "schoolid": "2",
            "schoolName": "Mar Vista Elementary School",
            "address": {"city": "Los Angeles", "state": "CA"},
            "url": "https://example.com/b",
            "rankHistory": [{"rankStars": 4, "year": 2025}],
        },
    ]
    picked = pick_search_match(
        school_list, name="Mar Vista Elementary School", city="LOS ANGELES"
    )
    assert picked["schoolid"] == "2"


def test_normalize_enrichment_reviews():
    detail = {
        "schoolid": "2",
        "urlSchoolDigger": "https://example.com/b",
        "rankHistory": [{"rankStars": 4, "year": 2025}],
        "reviews": [
            {
                "submitDate": "1/1/2020",
                "numberOfStars": 5,
                "comment": "Great teachers and community.",
                "submittedBy": "parent",
            },
            {
                "submitDate": "1/2/2020",
                "numberOfStars": 3,
                "comment": "ok",
                "submittedBy": "citizen",
            },
        ],
    }
    out = normalize_enrichment(detail)
    assert out["rating_stars"] == 4
    assert out["review_count"] == 1  # parent-only preferred
    assert out["review_avg"] == 5.0
    assert "Great teachers" in (out["review_quote"] or "")
    assert out["schooldigger_url"] == "https://example.com/b"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `.\.venv\Scripts\pytest.exe tests/test_schooldigger.py -v`

Expected: FAIL — missing module

- [ ] **Step 3: Implement `app/core/schooldigger.py` + `.env.example` lines**

```env
# SchoolDigger — assigned-school ratings + parent reviews (Neighborhood tab)
# Free DEV/TEST key: https://developer.schooldigger.com/
SCHOOLDIGGER_APP_ID=
SCHOOLDIGGER_APP_KEY=
```

Read keys via `os.environ` / existing dotenv load pattern used elsewhere (`GEMINI_API_KEY`).

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\pytest.exe tests/test_schooldigger.py tests/test_school_zones.py -v`

Expected: PASS

- [ ] **Step 5: Commit (optional)**

```bash
git add app/core/schooldigger.py tests/test_schooldigger.py .env.example
git commit -m "feat: SchoolDigger enrich for assigned schools"
```

---

### Task 4: Neighborhood UI — Assigned schools section

**Files:**
- Modify: `app/modules/neighborhood_reviews.py`

**Interfaces:**
- Consumes: `resolve_assigned`, `enrich_assigned`, `has_schooldigger_keys`
- Produces: UI only

**Placement:** After the name/override row + separator, **before** `Gemini neighborhood assessment`.

**UI structure:**

```python
ui.label("Assigned schools").classes("hb-section-title")
ui.label(caption).classes("hb-page-hint")  # source / keys message
cards_row = ui.row().classes("w-full gap-3 flex-wrap")
# three cards for elementary / middle / high
```

Each card (`.hb-school-card` or reuse existing quiet card patterns — match Neighborhood chrome, no new purple themes):

- Level placeholder: colored block / icon chip with label `Elementary` | `Middle` | `High` (Material `school` or level-specific)
- Name (or `—` / `Not found`)
- Stars line: `★★★★☆` or `4/5 · SchoolDigger` when present; else `—`
- Reviews: `Parent reviews: 4.5 · 12` + quote in `.hb-page-hint` if present
- Button: SchoolDigger link when URL present

**Auto-load:** On `redraw()`, if `live.latitude` and `live.longitude` set, call resolve+enrich inside try/except; set status on failure without breaking Gemini section.

**Empty states:** Match spec table (no pin / outside / gap / no keys).

Optional CSS: add minimal rules in `app/ui/theme.py` only if needed for placeholder block (keep small — e.g. `.hb-school-level-ph` with level accent borders using existing cyan/magenta/lime tokens).

- [ ] **Step 1: Insert section skeleton that calls resolve with a fake/guarded path**

Implement `_render_assigned_schools(lat, lng, container)` function in the module (or nested in `redraw`) that:

1. Clears/fills the assigned schools column
2. Calls core helpers
3. Renders three cards

- [ ] **Step 2: Manual smoke (dev)**

Run app: `.\.venv\Scripts\python.exe -m app.main`  
Open an LAUSD-pinned home → Neighborhood → confirm three cards load (names at minimum).  
With SchoolDigger keys in `.env`, confirm stars/reviews appear.

- [ ] **Step 3: Run full unit suite**

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: PASS (or only pre-existing failures unrelated to this work)

- [ ] **Step 4: Commit (optional)**

```bash
git add app/modules/neighborhood_reviews.py app/ui/theme.py
git commit -m "feat: Assigned schools section on Neighborhood tab"
```

---

### Task 5: Remove Map Nearby schools panel

**Files:**
- Modify: `app/modules/map_view.py`

**Do:**

1. Remove `schools_panel = ui.column()...`
2. Remove `_render_schools_panel` and all call sites
3. Remove unused imports: `nearest_schools_list` (keep `fetch_schools_near_pin` / `schools_to_geojson` / legend for the Schools layer toggle)
4. Leave `toggle_schools` marker behavior intact

- [ ] **Step 1: Delete panel + dead calls/imports**

- [ ] **Step 2: Confirm Map still loads Schools layer**

Manual: toggle Schools on Map — markers still appear; no Nearby expansion.

- [ ] **Step 3: Run tests**

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: PASS

- [ ] **Step 4: Commit (optional)**

```bash
git add app/modules/map_view.py
git commit -m "refactor: remove Map Nearby schools panel (moved to Neighborhood)"
```

---

### Task 6: Continuity docs

**Files:**
- Modify: `AGENTS.md`, `README.md`, `docs/RESEARCH.md`, `docs/TODO.md` (brief note)

**Updates:**

- Product decision: assigned E/M/H on Neighborhood via LAUSD GIS + SchoolDigger; Map Nearby panel removed; Schools overlay unchanged
- Env: `SCHOOLDIGGER_APP_ID` / `SCHOOLDIGGER_APP_KEY`
- RESEARCH Schools section: attendance now in scope for LAUSD; name resolve via school points in polygon
- What’s done checklist entry
- Quick verify: Neighborhood shows Assigned schools for LAUSD pin

- [ ] **Step 1: Edit docs to match shipped behavior**

- [ ] **Step 2: Commit (optional)**

```bash
git add AGENTS.md README.md docs/RESEARCH.md docs/TODO.md
git commit -m "docs: assigned schools on Neighborhood (LAUSD + SchoolDigger)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Neighborhood placement before Gemini | Task 4 |
| LAUSD E/M/H zones | Tasks 1–2 |
| SchoolDigger stars + parent reviews + link | Task 3–4 |
| Level placeholders | Task 4 |
| Honest outside / no-pin / no-keys states | Tasks 2, 4 |
| Remove Map Nearby panel; leave Schools layer | Task 5 |
| Cache ~7d | Tasks 2–3 |
| `.env.example` + continuity docs | Tasks 3, 6 |
| Unit tests without live net | Tasks 1–3 |
| No campus photos / no national zones | Non-goals honored |

**LAUSD discovery locked into Tasks 1–2:** attendance attributes lack school names; resolve via layer-0 points inside returned polygon.
