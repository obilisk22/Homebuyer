# Bugs / follow-ups

## Fixed

### BUG-002: Zillow photo import pulled similar-homes images

**Status:** fixed (2026-07-17) — archived, no action  
**Priority:** high

#### Symptom
Adding a home could show gallery photos that looked like another listing. Disk paths were correctly per-property (`data/uploads/{id}/`); `source_url` hashes did not overlap across properties — wrong URLs were extracted from the HTML.

#### Cause
`extract_photo_urls` regex-scanned the **entire** listing HTML for `photos.zillowstatic.com` URLs, including similar-homes / nearby carousel thumbs.

#### Fix
Prefer primary listing photo arrays (`originalPhotos` / `responsivePhotos` / …) from `__NEXT_DATA__` → `gdpClientCache` for the page zpid. Fall back to full-HTML regex only when structured extraction does not find that property. Address street-number mismatch against the URL slug / `og:title` fails closed (no regex fallback).

#### Related
- `app/core/zillow_photos.py`
- `tests/test_zillow_photos.py`

---

## Open

## BUG-001: Double-check Zillow neighborhood autofill

**Status:** open (deferred)  
**Filed:** 2026-07-17  
**Priority:** low — working again in-session; verify later

### Symptom
Neighborhood name sometimes looked empty in the Neighborhood tab / override field even after Zillow import. Autofill appeared correct again before debugging finished.

### Suspected causes (from partial investigation)
- Escaped `gdpClientCache` JSON needs quote-aware matching (`_Q` in `zillow_listing.py`).
- `parentRegion` may list `regionId` before `name` — regex must allow other keys between `{` and `name`.
- Wrong/stale zpids or soft-blocked HTML can return a different listing (or `"neighborhood": null`); Nominatim reverse-geocode is the fallback via `ensure_neighborhood`.

### Verify later
- [ ] Fresh add from a for-sale Zillow URL populates neighborhood without manual Refresh
- [ ] Existing homes (Beethoven → Del Rey, Pacific → Ocean Park) still show the name on the Neighborhood tab
- [ ] Not-for-sale / remapped zpid pages fall back cleanly instead of leaving the field blank
- [ ] **Refresh listing details** does not wipe a good neighborhood when Zillow omits it
- [ ] Regression tests in `tests/test_listing_filters.py` (escaped `parentRegion`, regionId-before-name) still pass if Zillow markup changes

### Related paths
- `app/core/zillow_listing.py`
- `app/core/property_service.py` (`ensure_neighborhood`, `_apply_listing_details`)
- `app/modules/neighborhood_reviews.py`

### Promote to GitHub
When `gh` is available:

```powershell
cd C:\Users\hheaf\Projects\homebuy
gh issue create --title "Verify Zillow neighborhood autofill is reliable" --body-file docs/BUGS.md
```

(Or paste this section into a new issue.)
