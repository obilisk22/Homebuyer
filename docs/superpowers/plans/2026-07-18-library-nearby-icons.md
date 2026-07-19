# Library Nearby Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show up to five proximity icons on library card thumbnails when a home is near a freeway, rail stop, playground, grocery, or shelter/recovery facility.

**Architecture:** New `app/core/nearby_signals.py` queries OSM Overpass (highway/transit/playground; grocery/shelter if no Google key) and Google Places Nearby Search when `GOOGLE_MAPS_API_KEY` is set. Results persist as JSON on `Property` (`nearby_signals` + `nearby_signals_at`). Library cards read the cache only and render soft neo chips on the thumbnail.

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy/SQLite, requests, Overpass API, Google Places Nearby Search (optional), existing `overlay_cache`, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-library-nearby-icons-design.md`

## Global Constraints

- Library cards only — no Map markers / property Nearby panel in v1.
- Highway: OSM `motorway` + `motorway_link` only; radius **800 ft** (~244 m).
- Transit: subway **or** light_rail/tram — **not** buses; radius **0.5 mi**.
- Playground: `leisure=playground` only; radius **0.5 mi**.
- Grocery: radius **0.5 mi**; Google Places if key else OSM; exclude pure convenience when tags allow.
- Shelter: radius **0.25 mi**; strict homeless / transitional / rehab only; Google if key else OSM.
- Tooltips on all hit icons: distance + nearest name (highway in **feet**, others in **miles**).
- Soft neo chips, bottom-left on thumbnail; order: highway → transit → playground → grocery → shelter.
- Compute on add + post-geocode; stale refresh when `nearby_signals_at` missing or **> 30 days**; concurrency-capped on library load.
- Add-home must never fail because nearby lookup failed.
- No live Overpass/Places in CI — fixtures/mocks only.
- Windows: `.\.venv\Scripts\pytest.exe`.
- Do not commit unless the user asks (commit steps below are optional).
- After user-facing work: update `AGENTS.md` + `README.md` in the same turn.

## File structure

| File | Responsibility |
|------|----------------|
| `app/core/nearby_signals.py` | Thresholds, Overpass/Places fetch+parse, `compute_signals`, `refresh_for_property`, parse/tooltip helpers |
| `app/core/models.py` | `nearby_signals`, `nearby_signals_at` columns |
| `app/core/db.py` | SQLite migrate for those columns |
| `app/core/property_service.py` | Call refresh after add/geocode; library stale pass helper |
| `app/ui/theme.py` | `.hb-nearby-icons` / chip / risk / amenity CSS |
| `app/ui/pages.py` | Render chips on library thumb; trigger stale refresh |
| `tests/test_nearby_signals.py` | Unit + fixture tests |
| `AGENTS.md`, `README.md`, `docs/TODO.md` | Continuity + backlog ID |

---

### Task 1: Pure helpers (thresholds, parse, tooltips)

**Files:**
- Create: `app/core/nearby_signals.py`
- Create: `tests/test_nearby_signals.py`

**Interfaces:**
- Produces:
  - `HIGHWAY_RADIUS_FT = 800.0`
  - `TRANSIT_RADIUS_MI = 0.5`
  - `PLAYGROUND_RADIUS_MI = 0.5`
  - `GROCERY_RADIUS_MI = 0.5`
  - `SHELTER_RADIUS_MI = 0.25`
  - `SIGNAL_ORDER = ("highway", "transit", "playground", "grocery", "shelter")`
  - `ICON_BY_KEY = {"highway": "directions_car", "transit": "train", "playground": "park", "grocery": "local_grocery_store", "shelter": "health_and_safety"}`
  - `RISK_KEYS = frozenset({"highway", "shelter"})`
  - `ft_to_miles(ft: float) -> float`
  - `miles_to_ft(mi: float) -> float`
  - `haversine_miles(...)` — re-export or thin wrap of `schools_nces.haversine_miles`
  - `parse_signals_json(raw: str | None) -> dict[str, dict]`
  - `hits_in_order(payload: dict) -> list[tuple[str, dict]]`
  - `tooltip_for(key: str, entry: dict) -> str`
  - `is_stale(nearby_signals_at: str | None, *, now: datetime | None = None, max_age_days: float = 30.0) -> bool`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_nearby_signals.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.nearby_signals import (
    HIGHWAY_RADIUS_FT,
    SHELTER_RADIUS_MI,
    TRANSIT_RADIUS_MI,
    ft_to_miles,
    hits_in_order,
    is_stale,
    miles_to_ft,
    parse_signals_json,
    tooltip_for,
)


def test_radius_constants():
    assert HIGHWAY_RADIUS_FT == 800.0
    assert TRANSIT_RADIUS_MI == 0.5
    assert SHELTER_RADIUS_MI == 0.25
    assert abs(miles_to_ft(0.5) - 2640.0) < 0.01
    assert abs(ft_to_miles(800.0) - (800.0 / 5280.0)) < 1e-9


def test_parse_and_hits_order():
    raw = """
    {"shelter": {"hit": true, "distance_mi": 0.1, "name": "A"},
     "highway": {"hit": true, "distance_ft": 400, "name": "I-10"},
     "playground": {"hit": false}}
    """
    payload = parse_signals_json(raw)
    hits = hits_in_order(payload)
    assert [k for k, _ in hits] == ["highway", "shelter"]


def test_tooltip_units():
    assert tooltip_for("highway", {"hit": True, "distance_ft": 420, "name": "I-10"}) == "420 ft · I-10"
    assert tooltip_for(
        "transit", {"hit": True, "distance_mi": 0.31, "name": "Expo/Bundy"}
    ) == "0.31 mi · Expo/Bundy"


def test_is_stale():
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    assert is_stale(None, now=now) is True
    fresh = (now - timedelta(days=5)).isoformat()
    assert is_stale(fresh, now=now) is False
    old = (now - timedelta(days=31)).isoformat()
    assert is_stale(old, now=now) is True
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `.\.venv\Scripts\pytest.exe tests/test_nearby_signals.py -v`  
Expected: import error / FAIL

- [ ] **Step 3: Minimal implementation**

Create `app/core/nearby_signals.py` with constants + helpers only (no network yet):

```python
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from app.core.schools_nces import haversine_miles

HIGHWAY_RADIUS_FT = 800.0
TRANSIT_RADIUS_MI = 0.5
PLAYGROUND_RADIUS_MI = 0.5
GROCERY_RADIUS_MI = 0.5
SHELTER_RADIUS_MI = 0.25
STALE_MAX_AGE_DAYS = 30.0

SIGNAL_ORDER = ("highway", "transit", "playground", "grocery", "shelter")
ICON_BY_KEY = {
    "highway": "directions_car",
    "transit": "train",
    "playground": "park",
    "grocery": "local_grocery_store",
    "shelter": "health_and_safety",
}
RISK_KEYS = frozenset({"highway", "shelter"})


def ft_to_miles(ft: float) -> float:
    return float(ft) / 5280.0


def miles_to_ft(mi: float) -> float:
    return float(mi) * 5280.0


def parse_signals_json(raw: str | None) -> dict[str, dict[str, Any]]:
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
        if isinstance(val, dict):
            out[str(key)] = val
    return out


def hits_in_order(payload: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    hits: list[tuple[str, dict[str, Any]]] = []
    for key in SIGNAL_ORDER:
        entry = payload.get(key) or {}
        if entry.get("hit"):
            hits.append((key, entry))
    return hits


def tooltip_for(key: str, entry: dict[str, Any]) -> str:
    name = str(entry.get("name") or "Nearby").strip() or "Nearby"
    if key == "highway":
        dist = entry.get("distance_ft")
        if dist is None:
            return name
        return f"{int(round(float(dist)))} ft · {name}"
    dist = entry.get("distance_mi")
    if dist is None:
        return name
    return f"{float(dist):.2f} mi · {name}"


def is_stale(
    nearby_signals_at: str | None,
    *,
    now: datetime | None = None,
    max_age_days: float = STALE_MAX_AGE_DAYS,
) -> bool:
    if not nearby_signals_at or not str(nearby_signals_at).strip():
        return True
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(nearby_signals_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (now - ts).total_seconds() / 86400.0
    return age_days > max_age_days
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `.\.venv\Scripts\pytest.exe tests/test_nearby_signals.py -v`  
Expected: PASS

- [ ] **Step 5: Commit (optional)**

```bash
git add app/core/nearby_signals.py tests/test_nearby_signals.py
git commit -m "feat: nearby signal helpers for library icons"
```

---

### Task 2: OSM Overpass parse + nearest-hit selection

**Files:**
- Modify: `app/core/nearby_signals.py`
- Modify: `tests/test_nearby_signals.py`

**Interfaces:**
- Produces:
  - `NearestHit` TypedDict or plain dict: `{name, lat, lng, distance_mi}`
  - `parse_overpass_elements(elements: list[dict], *, pin_lat, pin_lng, radius_mi) -> list[NearestHit]`
  - `nearest_within(hits: list[NearestHit], radius_mi: float) -> NearestHit | None`
  - `signal_entry_from_hit(key: str, hit: NearestHit | None, *, error: str | None = None) -> dict`
  - `build_overpass_query(lat: float, lng: float) -> str` — single query covering highway/transit/playground/grocery/shelter OSM tags

**OSM match rules (encode in query + optional Python filter):**

| Signal | Overpass / tags |
|--------|-----------------|
| highway | `way[highway=motorway]`, `way[highway=motorway_link]` within 244 m; use `out center` (or geom) |
| transit | `node/way[railway=station][station=subway]`, `node[railway=subway_entrance]`, `node/way[railway=station][station=light_rail]`, `node[railway=tram_stop]`, `node[railway=halt][light_rail=yes]` — exclude `bus` |
| playground | `node/way[leisure=playground]` |
| grocery (OSM fallback) | `node/way[shop=supermarket]`, `node/way[shop=grocery]`; **exclude** `shop=convenience` |
| shelter (OSM fallback) | `amenity=social_facility` + (`social_facility=shelter` OR `social_facility=drug_rehabilitation` OR `social_facility:for=homeless` OR `social_facility=transitional`); also `amenity=shelter` + `shelter_type=homeless` if present |

- [ ] **Step 1: Write failing fixture tests**

```python
def test_parse_overpass_picks_nearest_playground():
    from app.core.nearby_signals import nearest_within, parse_overpass_elements

    elements = [
        {
            "type": "node",
            "id": 1,
            "lat": 34.051,
            "lon": -118.25,
            "tags": {"leisure": "playground", "name": "Far Park Play"},
        },
        {
            "type": "node",
            "id": 2,
            "lat": 34.0502,
            "lon": -118.25,
            "tags": {"leisure": "playground", "name": "Near Play"},
        },
    ]
    hits = parse_overpass_elements(
        elements, pin_lat=34.05, pin_lng=-118.25, radius_mi=0.5
    )
    # Filter to playgrounds in test by passing only playground elements
    best = nearest_within(hits, radius_mi=0.5)
    assert best is not None
    assert best["name"] == "Near Play"


def test_signal_entry_highway_uses_feet():
    from app.core.nearby_signals import signal_entry_from_hit

    hit = {"name": "I-10", "lat": 34.0, "lng": -118.0, "distance_mi": 800 / 5280}
    entry = signal_entry_from_hit("highway", hit)
    assert entry["hit"] is True
    assert abs(entry["distance_ft"] - 800) < 1.0
    assert entry["name"] == "I-10"


def test_signal_entry_miss():
    from app.core.nearby_signals import signal_entry_from_hit

    entry = signal_entry_from_hit("grocery", None)
    assert entry == {"hit": False}
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement parse helpers + `build_overpass_query`**

Use one Overpass QL body with `(around:RADIUS,lat,lng)` unions; `out center tags;` for ways/relations and nodes. Classify each element into signal buckets via tags, compute haversine, keep nearest per key.

Highway radius in query: `244` meters. Others: use max needed (**805** m for 0.5 mi) and filter in Python per signal.

`signal_entry_from_hit`:
- miss → `{"hit": False}` (+ `"error"` if provided)
- highway hit → `hit`, `distance_ft`, `name`
- other hit → `hit`, `distance_mi` (2 decimal places ok), `name`
- unnamed → fallback name like `"Freeway"`, `"Rail stop"`, `"Playground"`, `"Grocery"`, `"Shelter"`

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit (optional)**

---

### Task 3: Overpass + Places network layer (mocked in tests)

**Files:**
- Modify: `app/core/nearby_signals.py`
- Modify: `tests/test_nearby_signals.py`

**Interfaces:**
- Produces:
  - `OVERPASS_URL = "https://overpass-api.de/api/interpreter"`
  - `CACHE_NAMESPACE = "nearby"`
  - `RAW_CACHE_MAX_AGE_S = 7 * 24 * 3600`
  - `REQUEST_TIMEOUT_S = 45`
  - `fetch_overpass(lat, lng, *, session=None) -> dict` — POST query; cache via `overlay_cache.read_json` / `write_json`
  - `fetch_places_nearby(lat, lng, *, api_key: str, place_type: str, keyword: str | None, radius_m: int) -> list[dict]`
  - `parse_places_results(results: list[dict], *, pin_lat, pin_lng, radius_mi) -> list[NearestHit]`
  - `google_key() -> str` — `(os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()`
  - `compute_signals(lat: float, lng: float, *, api_key: str | None = None) -> dict[str, dict]`

**Google Places (legacy Nearby Search — matches existing `requests` style in `geocode.py`):**

```text
GET https://maps.googleapis.com/maps/api/place/nearbysearch/json
  location={lat},{lng}
  radius={meters}
  type=supermarket          # grocery
  key={api_key}

# shelter: two keyword searches (merge, nearest wins), type omitted or establishment
  keyword=homeless shelter
  keyword=drug rehabilitation|transitional housing
  radius=403   # 0.25 mi
```

Reject Places results whose `types` clearly indicate only `convenience_store` for grocery.

- [ ] **Step 1: Failing tests with monkeypatch / fixtures**

```python
def test_compute_signals_osm_only(monkeypatch):
    from app.core import nearby_signals as ns

    def fake_overpass(lat, lng, **kwargs):
        return {
            "elements": [
                {
                    "type": "way",
                    "id": 9,
                    "center": {"lat": lat, "lon": lng},
                    "tags": {"highway": "motorway", "ref": "I-10", "name": "Santa Monica Fwy"},
                },
                {
                    "type": "node",
                    "id": 10,
                    "lat": lat,
                    "lon": lng,
                    "tags": {"railway": "station", "station": "light_rail", "name": "Expo/Bundy"},
                },
            ]
        }

    monkeypatch.setattr(ns, "fetch_overpass", fake_overpass)
    monkeypatch.setattr(ns, "google_key", lambda: "")
    payload = ns.compute_signals(34.05, -118.25)
    assert payload["highway"]["hit"] is True
    assert payload["transit"]["hit"] is True
    assert payload["playground"]["hit"] is False


def test_compute_signals_uses_places_when_key(monkeypatch):
    from app.core import nearby_signals as ns

    monkeypatch.setattr(ns, "fetch_overpass", lambda *a, **k: {"elements": []})
    monkeypatch.setattr(ns, "google_key", lambda: "fake-key")

    def fake_places(lat, lng, *, api_key, place_type, keyword, radius_m):
        if place_type == "supermarket":
            return [
                {
                    "name": "Trader Joe's",
                    "geometry": {"location": {"lat": lat, "lng": lng}},
                    "types": ["supermarket", "grocery_or_supermarket", "store"],
                }
            ]
        return []

    monkeypatch.setattr(ns, "fetch_places_nearby", fake_places)
    payload = ns.compute_signals(34.05, -118.25, api_key="fake-key")
    assert payload["grocery"]["hit"] is True
    assert payload["grocery"]["name"] == "Trader Joe's"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement fetch + `compute_signals`**

Logic for `compute_signals`:

1. Always fetch Overpass (cached); classify highway/transit/playground always from OSM.
2. If `api_key` (or `google_key()`) non-empty: grocery + shelter from Places; on Places failure for a key, fall back to OSM classification for that key only.
3. If no key: grocery + shelter from OSM.
4. Never raise — wrap fetches; on total Overpass failure, all OSM-dependent keys get `hit: False` + `error`.
5. Return full five-key dict.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit (optional)**

---

### Task 4: Persist on Property + PropertyService refresh

**Files:**
- Modify: `app/core/models.py`
- Modify: `app/core/db.py` (`_migrate_sqlite` property column list)
- Modify: `app/core/nearby_signals.py` — add `refresh_property_signals(prop) -> dict` that mutates `prop.nearby_signals` / `prop.nearby_signals_at` (ISO UTC) but does **not** commit
- Modify: `app/core/property_service.py`
- Modify: `tests/test_nearby_signals.py` (mock compute; optional DB test if project has session fixtures — otherwise keep pure)

**Interfaces:**
- Produces:
  - `Property.nearby_signals: str` default `""`
  - `Property.nearby_signals_at: str` default `""`
  - `refresh_property_signals(prop: Property) -> dict` 
  - `PropertyService.refresh_nearby_signals(property_id: int) -> Property` — load, refresh, commit; swallow errors
  - `PropertyService.refresh_stale_nearby_signals(*, limit: int = 3) -> int` — refresh up to `limit` stale/missing pinned properties

**Wire calls:**
- End of `add_from_zillow` after coordinates set (try/except around refresh).
- End of `ensure_coordinates` after successful geocode.
- Library page: once per load, call `refresh_stale_nearby_signals(limit=3)` before listing (best-effort).

- [ ] **Step 1: Add model columns**

```python
# on Property
nearby_signals: Mapped[str] = mapped_column(Text, default="", nullable=False)
nearby_signals_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
```

Migrate:

```python
("nearby_signals", "ALTER TABLE properties ADD COLUMN nearby_signals TEXT NOT NULL DEFAULT ''"),
("nearby_signals_at", "ALTER TABLE properties ADD COLUMN nearby_signals_at VARCHAR(64) NOT NULL DEFAULT ''"),
```

- [ ] **Step 2: Implement `refresh_property_signals` + service methods**

```python
def refresh_property_signals(prop: Property) -> dict[str, Any]:
    if prop.latitude is None or prop.longitude is None:
        return parse_signals_json(prop.nearby_signals)
    try:
        payload = compute_signals(float(prop.latitude), float(prop.longitude))
    except Exception as exc:  # noqa: BLE001 — never break add-home
        payload = {k: {"hit": False, "error": str(exc)} for k in SIGNAL_ORDER}
    prop.nearby_signals = json.dumps(payload)
    prop.nearby_signals_at = datetime.now(timezone.utc).isoformat()
    return payload
```

`refresh_stale_nearby_signals`: query properties with lat/lng not null; in Python filter `is_stale(nearby_signals_at)`; refresh up to `limit`; commit each or batch commit once.

- [ ] **Step 3: Test refresh writes JSON (unit with simple namespace object or mock Property)**

```python
def test_refresh_property_signals_writes(monkeypatch):
    from types import SimpleNamespace
    from app.core import nearby_signals as ns

    monkeypatch.setattr(
        ns,
        "compute_signals",
        lambda lat, lng, **k: {
            "highway": {"hit": False},
            "transit": {"hit": False},
            "playground": {"hit": False},
            "grocery": {"hit": False},
            "shelter": {"hit": False},
        },
    )
    prop = SimpleNamespace(latitude=34.0, longitude=-118.0, nearby_signals="", nearby_signals_at="")
    out = ns.refresh_property_signals(prop)
    assert "highway" in out
    assert prop.nearby_signals.startswith("{")
    assert prop.nearby_signals_at
```

- [ ] **Step 4: Run full nearby tests — PASS**

- [ ] **Step 5: Commit (optional)**

---

### Task 5: Theme + library card UI

**Files:**
- Modify: `app/ui/theme.py` — after `.hb-library-thumb` rules
- Modify: `app/ui/pages.py` — thumb wrap + stale refresh

**Interfaces:**
- Consumes: `parse_signals_json`, `hits_in_order`, `tooltip_for`, `ICON_BY_KEY`, `RISK_KEYS`
- CSS classes: `.hb-library-thumb-wrap { position: relative; }`, `.hb-nearby-icons`, `.hb-nearby-chip`, `.hb-nearby-chip--risk`, `.hb-nearby-chip--amenity`

- [ ] **Step 1: Add CSS**

```css
.hb-library-thumb-wrap {
  position: relative;
  /* keep existing sizing rules */
}

.hb-nearby-icons {
  position: absolute;
  left: 6px;
  bottom: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  z-index: 2;
  pointer-events: none;
}

.hb-nearby-chip {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(12, 16, 22, 0.82);
  border: 1px solid var(--hb-border);
  box-shadow: 2px 2px 6px rgba(0, 0, 0, 0.45), inset 1px 1px 0 rgba(255, 255, 255, 0.06);
  font-size: 15px;
  line-height: 1;
}

.hb-nearby-chip--amenity {
  color: var(--hb-lime, #B8FF3C);
}

.hb-nearby-chip--risk {
  color: var(--hb-magenta, #FF2BD6);
}
```

Use Material icons via `ui.icon(ICON_BY_KEY[key], size="xs")` inside a `ui.element("div")` with the chip classes. Set `title=tooltip_for(...)` on the chip element (pointer-events: none is ok for native title on parent — if title doesn't show, set `pointer-events: auto` on chips only and stop click propagation).

- [ ] **Step 2: Library render**

In `card_rows` build, include `"nearby": prop.nearby_signals or ""`.

Inside thumb wrap (both image and empty):

```python
from app.core.nearby_signals import (
    ICON_BY_KEY,
    RISK_KEYS,
    hits_in_order,
    parse_signals_json,
    tooltip_for,
)

hits = hits_in_order(parse_signals_json(row.get("nearby") or ""))
if hits:
    with ui.element("div").classes("hb-nearby-icons"):
        for key, entry in hits:
            kind = "risk" if key in RISK_KEYS else "amenity"
            chip = ui.element("div").classes(
                f"hb-nearby-chip hb-nearby-chip--{kind}"
            )
            chip.props(f'title="{tooltip_for(key, entry)}"')  # prefer .tooltip or style title attr safely
            with chip:
                ui.icon(ICON_BY_KEY[key], size="xs")
```

Prefer setting HTML title via:

```python
chip = ui.element("div").classes(...).style("pointer-events: auto")
chip._props["title"] = tooltip_for(key, entry)  # or ui.tooltip if available
```

Safer: `ui.icon(...).tooltip(tooltip_for(key, entry))` if NiceGUI supports it on icon — check existing codebase patterns; otherwise native `title` attribute via `.props()`.

At start of library `refresh()` (after service available):

```python
try:
    service.refresh_stale_nearby_signals(limit=3)
except Exception:
    pass
```

- [ ] **Step 3: Manual smoke** — restart `.\.venv\Scripts\python.exe -m app.main`, open library; for a geocoded home, after refresh, icons appear when signals hit.

- [ ] **Step 4: Commit (optional)**

---

### Task 6: Docs + backlog

**Files:**
- Modify: `AGENTS.md` — What’s done bullet; product decision; library checklist; key files table row for `nearby_signals.py`
- Modify: `README.md` — short mention of library proximity icons + OSM/Google sources
- Modify: `docs/TODO.md` — add `TODO-025` Done (or Open→Done) for library nearby icons
- Modify: `docs/RESEARCH.md` — brief note under overlays/bonus: Overpass + Places for library badges

- [ ] **Step 1: Update docs to match shipped behavior**
- [ ] **Step 2: Run** `.\.venv\Scripts\pytest.exe tests/test_nearby_signals.py -q` **and** `.\.venv\Scripts\pytest.exe -q` (full suite)
- [ ] **Step 3: Commit (optional)** — only if user asks

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Five signals + radii/colors | 1–2, 5 |
| OSM Overpass for highway/transit/playground | 2–3 |
| Google Places grocery/shelter + OSM fallback | 3 |
| Cached JSON on Property | 4 |
| Add + geocode + 30d stale refresh | 4–5 |
| Neo chips bottom-left + tooltips | 5 |
| Errors never break add | 3–4 |
| Fixture tests, no live net in CI | 1–3 |
| AGENTS/README update | 6 |
| No Map/property panel v1 | — (non-goal, omitted) |

## Self-review notes

- No TBD placeholders.
- Icon names locked to Material ids from the spec.
- `compute_signals` always returns all five keys.
- Highway distance stored/displayed in feet; others in miles.
- Commit steps optional per Homebuy convention.
