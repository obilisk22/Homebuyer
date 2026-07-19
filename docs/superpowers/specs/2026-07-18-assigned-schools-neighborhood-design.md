# Assigned schools (Neighborhood) — Design Spec

**Date:** 2026-07-18  
**Status:** Approved (pending implementation)  
**Product:** Homebuy Neighborhood tab  

> **Update (2026-07-18, same day):** the quality layer described below (§ Goal 2, "Quality: SchoolDigger API") was **replaced** before/shortly after shipping. SchoolDigger is a paid API, and SchoolScope (considered as a free alternative) has no publicly usable API (403 / "coming soon"). The shipped quality layer is instead **free and keyless**: a California School Dashboard performance-level color badge (Blue/Green/Yellow/Orange/Red) looked up by CDS code from the free CDE Academic Indicator downloadable data, plus a **Niche** parent-review deep link and a CA Dashboard report-page deep link. See `app/core/school_quality.py` and `docs/RESEARCH.md` for the implementation that superseded every "SchoolDigger" reference in this document.

## Problem

The Map tab’s **Nearby schools** panel lists NCES public schools within ~4 mi. That is proximity, not **attendance assignment**. Buyers care which Elementary / Middle / High the home is **zoned for**, plus a quality signal (prefer parent reviews) and a deep link — without cluttering the map.

## Goals

1. Show the **assigned** Elementary, Middle, and High school for the home’s pin when SoCal attendance GIS covers that location (LAUSD first).
2. Enrich each assigned school with **SchoolDigger** star rating, parent review summary (avg + count, optional short quote), and a profile link.
3. Present this on the **Neighborhood** tab as three cards with **level placeholder** visuals (no campus photos — neither SchoolDigger nor CA Dashboard provide them).
4. Be honest when zones or ratings are unavailable (no nearest-as-zoned heuristic).

## Non-goals (v1)

- Map overlay / marker / boundary changes for this feature  
- Real campus photos (Street View or otherwise)  
- National attendance-zone coverage or paid zone APIs  
- Private / charter / magnet choice assignment beyond residence catchment  
- GreatSchools API as primary quality source  
- CA School Dashboard colors as the primary badge (SchoolDigger chosen instead)  
- Scraping Niche / GreatSchools / SchoolDigger HTML for images  

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Placement | Neighborhood tab — **Assigned schools** section after name block, before Gemini overview |
| Geography | Greater LA / SoCal first via district attendance GIS |
| Day-1 GIS | LAUSD GeoHub `LAUSD_Schools` layers 4 / 5 / 6 (E / M / H) |
| LAUSD name resolve | Attendance polygons expose keys only (`KEY_` / `EKEY_5` etc.); resolve **name + CDS** by finding layer-0 school points (`MAP_TYPE` ES/MS/HS) that fall **inside** the returned attendance polygon |
| Quality | SchoolDigger API (stars + parent reviews) |
| Photos | Level placeholders only |
| Map | No map work; remove Map **Nearby schools** panel when this ships; leave Schools layer toggle as-is |
| Outside coverage | Explicit unavailable message — never invent zones from nearest NCES |
| Missing API keys | Still show zoned names when GIS hits; caption that ratings need keys |
| Architecture | Approach 1: district GIS point-in-polygon + SchoolDigger enrich |

## Data flow

```
Property lat/lng
    → school_zones.resolve_assigned(lat, lng)
        → registry of ArcGIS attendance layers (LAUSD E/M/H first)
        → point-in-polygon per level → attendance polygon (+ keys)
        → resolve school name: LAUSD Schools points (layer 0) of matching
          MAP_TYPE (ES/MS/HS) whose coordinates fall inside that polygon
        → { elementary?, middle?, high? } with name, city, cds_code, keys
    → schooldigger.enrich(school) per hit
        → match by name + CA + city (SchoolDigger search); detail for reviews
        → rating, review avg/count, optional parent quote, profile URL
    → Neighborhood UI: three cards + source caption
```

Cache both GIS and SchoolDigger responses under `data/cache/` (~7 days), same pattern as other area helpers.

## Components

| Unit | Responsibility |
|------|----------------|
| `app/core/school_zones.py` | Attendance registry + point-in-polygon → assigned E/M/H |
| `app/core/schooldigger.py` | API client, match, normalize rating/reviews, profile URL, cache |
| `app/modules/neighborhood_reviews.py` | **Assigned schools** section UI |
| `app/modules/map_view.py` | Remove **Nearby schools** panel only |
| `.env.example` | `SCHOOLDIGGER_APP_ID`, `SCHOOLDIGGER_APP_KEY` |
| Tests | Fixture GIS parse + SchoolDigger normalize (no live net) |

Keep `schools_nces.py` for the existing Map Schools layer; do not repurpose it as “zoned.”

## UI

- Section title: **Assigned schools** (Creato `.hb-section-title`, same chrome as Gemini / things-to-do).
- Three cards (stack on narrow widths): level placeholder · school name · SchoolDigger ★ · parent review count · truncated parent quote when present · **SchoolDigger** link button.
- Caption: zone source (e.g. `LAUSD attendance`) + `ratings via SchoolDigger`.
- **Auto-load** on Neighborhood tab when pin exists; non-blocking if slow/fails.
- Partial results: show found levels; empty slot for missing level with a quiet dash / “Not found.”

### Coverage detection

v1 treats a pin as **in registry** when any registered attendance layer returns a hit, **or** when the pin falls inside a registered district outline (LAUSD district polygon) even if a level miss occurs. Pins outside all registered district outlines → “not available for this district yet.” Pins inside a registered district with zero school hits → rare boundary-gap message.

### Error / empty states

| Case | UI |
|------|-----|
| No lat/lng | Needs a map pin — geocode this home first |
| Outside GIS registry | Assigned schools not available for this district yet (SoCal GIS) |
| Inside registered district, no school hit | No attendance match for this pin (rare boundary gap) |
| No SchoolDigger keys | Zoned names still shown; caption that ratings need `SCHOOLDIGGER_*` |
| SchoolDigger miss / error | Name + zone caption; rating area shows “—” |
| Network / GIS failure | One status line; rest of Neighborhood unchanged |

## Config

Optional env (document in `.env.example` + README / AGENTS):

- `SCHOOLDIGGER_APP_ID`
- `SCHOOLDIGGER_APP_KEY`

Free SchoolDigger DEV/TEST tier is enough for personal use; rate-limit awareness via cache.

## Testing

- Unit: LAUSD-style ArcGIS/JSON fixtures → correct school names per level for a known interior point; exterior point → no assignment.
- Unit: SchoolDigger JSON fixture → normalized stars, review count, quote, URL.
- No live network in default pytest; do not require keys for CI.

## Continuity docs (on ship)

Update `AGENTS.md`, `README.md`, `docs/RESEARCH.md` (attendance now in scope for SoCal), and `docs/TODO.md` as appropriate. Note product decision: assigned schools live on Neighborhood, not Map.

## Future (explicitly later)

- Additional SoCal district attendance layers in the registry  
- Optional CA Dashboard badge alongside SchoolDigger  
- GreatSchools as fallback when SchoolDigger miss  
- Map highlight of assigned schools (out of scope for this spec)  
