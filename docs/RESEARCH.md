# Research notes — Homebuy

Captured 2026-07-17 from research agents. **Do not re-research from scratch** unless these go stale; implement from here.

---

## Map overlays

Source: [Map overlays research v2](323317c3-1601-4d1f-8acb-0a1211070c19)

### Recommended v1 (1–2 days, free)

1. **Income choropleth** — Census ACS `B19013` (tract or ZCTA) + TIGER/cartographic boundaries  
2. **Home value choropleth** — ACS `B25077` (owner-estimated value, not sale price)  
3. **Sale-price choropleth** — Redfin Data Center ZIP median sale → join ZCTA polygons  
4. **Flood toggle** — FEMA NFHL WMS (`L.tileLayer.wms`)  
5. **Crime near pin** — LA / Seattle Socrata SODA, bbox + recent window, cluster/heat  

**Day-2 bonuses:** NCES school points; EPA National Walkability Index.

**Library nearby badges (2026-07-18, not Map overlays):** OSM Overpass around the pin for highway/transit/playground/grocery/shelter; optional Google Places Nearby Search for grocery + shelter when `GOOGLE_MAPS_API_KEY` is set. Cached per property + raw responses ~7d — see `app/core/nearby_signals.py` and TODO-025.

### Keys

| Key | Needed? |
|-----|---------|
| `CENSUS_API_KEY` | Yes for live ACS |
| `SOCRATA_APP_TOKEN` | Optional (rate limits) |
| FEMA / Redfin download / NCES / EPA | No key |

### Avoid

CrimeGrade scraping, GreatSchools paid API, FBI CDE for neighborhood maps, Zillow for overlay layers, SpotCrime/CrimeoMeter paid APIs.

### Also noted (optional later)

- **Crime Open Database (CODE)** — historical multi-city CC-BY dump; prefer live Socrata for LA/Seattle  
- **USGS seismic hazard** — useful CA bonus tiles  
- **Transitland / Walk Score** — pin enrichment, not choropleths  
- **FHFA HPI** — appreciation indexes, not dollar medians  

### Stack shorthand

**Census ACS + Redfin ZIP + FEMA WMS + city Socrata crime** → Leaflet toggles on existing map; cache server-side; never load nationwide crime into the browser.

### Implemented (2026-07-18 slice)

Shipped on Map tab toggles (no Neighborhood chips): FEMA NFHL WMS flood; **Zoning** (City of LA ZIMAS `1101`, Santa Monica via SCAG `Zoning_poly_LA`, LA County DRP unincorporated + SCAG fallback) as ACS-style GeoJSON (`zoning_gis.py`); ACS choropleths for median income / home value / age / kids / owner% / year built / rent / bachelor's+ via `census_acs.py` (`CENSUS_API_KEY`); LA County + Seattle crime as a **hex density choropleth** (`crime_density.py`). Deferred: more cities’ zoning, Redfin sales, air quality, fire risk. Cache: `data/cache/`. Street View merged into Map tab (TODO-010).

---

## Neighborhood reviews / locals’ opinions

Source: [Neighborhood reviews research v2](3a6daec2-ae9b-4383-a1e6-1caf7b562d47)

### Recommended v1 (1–2 days)

1. **Resolve neighborhood name:** Zillow HTML already fetched → Nominatim reverse (cached) → optional Google → manual override  
2. **Module UI:** show name + editable override  
3. **Deep links only** (no scrape): Reddit search `"{neighborhood}" {city}`, city housing subreddit guesses, City-Data / Niche / Google `site:reddit.com`  
4. **Optional:** paste Reddit URL → official embed iframe  
5. **User notes** textarea (first-party, always safe)  
6. OSM/Nominatim attribution + disclaimer  

### Avoid

Scraping Reddit / City-Data / Niche / AreaVibes / Nextdoor; Census tract labels as neighborhood names; bulk Reddit harvest without approved API.

### Keys

None required for v1. Optional: existing `GOOGLE_MAPS_API_KEY`, later Reddit developer app (if approved), Nextdoor partner, AreaVibes widget.

### v2 stretch

Reddit Data API (titles/permalinks only), Nextdoor partner API, city GIS neighborhood polygons, AreaVibes widget, tie-in to map overlay context.

---

## Suggested build order

1. Neighborhood Reviews module (deep links + name resolver) — faster UX win  
2. Map overlays v1 (Census + flood + crime bbox) — needs `CENSUS_API_KEY`  
3. Redfin sale choropleth + school/walkability bonuses  
