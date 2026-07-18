# Map layer neo toggles

**Date:** 2026-07-18  
**Status:** Approved

## Goal

Replace Map tab overlay checkboxes with compact neumorphic text toggle buttons. Emission (cyan glow) marks enabled overlays; neo extrusion marks the control chrome.

## Behavior

- Same multi-select semantics as checkboxes (any combo of Flood / Zoning / ACS / Crime).
- Click toggles on ↔ off.
- Failed load / unsupported area still forces the button back to off (existing `suppress_toggle` pattern).
- Disabled Zoning/Crime: muted neo + existing tooltips.
- Labels unchanged (Flood (FEMA), Zoning, ACS short names, Crime near pin).

## Visual

| State | Look |
|-------|------|
| Off | Soft extruded neo face, muted Creato label, no glow |
| On | Inset neo + cyan text + soft emissive glow (L1) |
| Disabled | Lower opacity, no hover glow |

Class: `.hb-map-layer-btn` / `.hb-map-layer-btn--on` in `theme.py`. Row: `.hb-map-layers`.

## Out of scope

- Leaflet / overlay data logic
- Changing which layers exist
- Exclusive (single) selection
