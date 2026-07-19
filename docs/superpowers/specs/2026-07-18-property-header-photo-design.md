# Property header library photo

**Date:** 2026-07-18  
**Status:** Approved  
**Default mode:** `bleed` (B)  
**Rollback:** set `PROPERTY_HEADER_PHOTO_MODE = "beside"` (A)

## Goal

Show the home’s library thumbnail on the property page header (shared by all tabs). Default is full-bleed behind the header with a dark scrim. Mode A (thumb beside text) stays one flag flip away.

## Flag

```python
# app/ui/pages.py (or app/ui/header_photo.py)
PROPERTY_HEADER_PHOTO_MODE = "bleed"  # "bleed" | "beside"
```

| Mode | Layout |
|------|--------|
| `bleed` | Photo as background of `.hb-property-hero`; gradient/flat dark scrim; text + actions on top |
| `beside` | Library-card row: `.hb-library-thumb-wrap` left, street/price/chips right; actions top-right |

## Behavior

- Source: `resolve_library_thumbnail(prop)` (same as library list).
- No photo: solid header (no broken image / empty bleed).
- Scrim (bleed only): dark overlay so Akira street + cyan price stay readable (~60–75%).
- Responsive: beside mode stacks under ~800px (reuse library rules). Bleed stays full-width.

## Out of scope

- Library list page chrome
- Changing which photo is the library thumb (Photos tab pin stays source of truth)
