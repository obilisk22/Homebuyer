# Property tab visual chrome — Design Spec

**Date:** 2026-07-18  
**Status:** Approved — implementing  
**Product:** Property page header + Photos / Map / Neighborhood / Financials tab chrome  
**Depth:** Chrome + light module polish (option 2)

## Goal

Bring property page and module tabs in line with the library visual system: Creato page chrome, Akira street (header only), dense fields/buttons, shared empty states — without rewriting map/chart/embed internals.

## Non-goals

- Leaflet / basemap / overlay plumbing changes  
- Plotly figure internals (keep `_chart_layout`)  
- Street View `svembed` iframe HTML  
- Gallery grid layout / lightbox behavior  
- New neon systems or motion  

## Decisions

| Area | Choice |
|------|--------|
| Tokens | Reuse existing `.hb-page-*`, `.hb-empty-state`, `.hb-meta-chip*`, `.hb-library-address` / price / place |
| Property title | Street-only via `_street_address_line` + Akira; city/state muted; price quieter Creato |
| Meta | Chip rows like library (primary + secondary) |
| Fields / buttons | `dense outlined` / `dense` + primary `unelevated` where library does |
| Neighborhood | Replace ad-hoc neon inline section heads with shared classes; hood name may use `hb-page-title` |
| Map | Dense pin fields + empty-state copy only |

## Files

- `app/ui/pages.py` — property header, edit form, not-found  
- `app/modules/gallery.py`  
- `app/modules/financial.py`  
- `app/modules/neighborhood_reviews.py`  
- `app/modules/map_view.py`  
- `app/modules/street_view.py`  
- `AGENTS.md` / `README.md` — brief continuity  

## Success

Opening a property feels like the same product as the library: Creato headings, Akira street in header, dense controls, dashed empty panels; map/charts/SV still work.
