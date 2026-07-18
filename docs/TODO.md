# Homebuy — Product backlog

Filed 2026-07-17. Status: **pending** unless noted.

---

## TODO-001 — Richer Zillow listing scrape

**Scrape / parse from the Zillow listing:** beds, price, square footage, HOA cost, year built, home type.

**Notes**
- Beds + list price already partially exist via `zillow_listing.py` / property fields.
- Add: `sqft`, `hoa_fee` (or similar), `year_built`, `home_type` (SFH / condo / townhouse / etc.).
- Persist on `Property`, show in library card + property header + edit form.
- Prefer structured `gdpClientCache` / LD+JSON over brittle regex where possible.

**Touch:** `app/core/zillow_listing.py`, `models.py`, `property_service.py`, `app/ui/pages.py`, tests

---

## TODO-002 — Area risk & market signals

**Add:** crime, median income, air quality, fire risk, average home price.

**Notes**
- Overlaps pending `map-overlays-impl` — see [`docs/RESEARCH.md`](RESEARCH.md) (Census ACS income/value, Redfin ZIP sales, FEMA flood/fire-adjacent, Socrata crime).
- Air quality + wildfire: pick free sources (e.g. AirNow / PurpleAir; USGS / CAL FIRE / First Street–style if ToS-OK) before implementing.
- Decide UX: map overlays vs Neighborhood tab summary cards vs both.

**Touch:** new core clients + map and/or neighborhood modules; may need `CENSUS_API_KEY`

---

## TODO-003 — Display cost per square foot

**Show Cost/Sqft** (list and/or offer ÷ living area).

**Depends on:** TODO-001 (`sqft`).
**Touch:** property header / financials module; maybe library cards.

---

## TODO-004 — Neighborhood: “Cool things to do” (Gemini)

**Add a Neighborhood-tab section** that asks Gemini for cool things to do nearby (given neighborhood + city).

**Notes**
- Mirror existing overview pattern (`gemini_neighborhood.py` + cache columns).
- Separate prompt + cache key from the vibe overview so regenerating one doesn’t wipe the other.

**Touch:** `app/core/gemini_neighborhood.py` (or sibling), `models.py`, `neighborhood_reviews.py`

---

## TODO-005 — Financials: Gemini breakdown + opinion

**In the Financials tab:** ask Gemini for a financial breakdown and an opinion on the property’s finances (offer, PITI, taxes/insurance assumptions, HOA, etc.).

**Notes**
- Feed structured numbers from `FinancialAssumptions` + listing fields — don’t invent prices silently.
- Label clearly as AI opinion; cache per property + assumption fingerprint.
- Keep Plotly / PITI calculator as source of truth; Gemini is commentary.

**Touch:** `app/modules/financial.py`, new Gemini helper, `models.py` cache fields

---

## TODO-006 — Clean up codebase

**General cleanup pass:** dead code, unused temp/debug leftovers, inconsistent naming, thin modules vs fat core, duplicate helpers, stale comments/docs.

**Notes**
- Prefer small, reviewable PRs/commits (or one focused cleanup agent pass).
- Don’t change product behavior unless removing clearly dead paths.
- Good targets: leftover `_tmp*` artifacts if any, overly broad `except Exception`, unused imports, duplicated address/slug helpers.

**Touch:** repo-wide; start with `app/core/` + modules + tests

---

## TODO-007 — Remove photo “Remove” button

**Gallery UX:** drop the per-photo **Remove** control.

**Notes**
- Keep bulk replace via **Re-import (replace)** (and optional future “clear all”) so users can still reset photos.
- Confirm `delete_photo` stays available for replace/cleanup paths even if the UI button goes away.

**Touch:** `app/modules/gallery.py`

---

## TODO-008 — Larger gallery photos, less negative space

**Gallery layout:** bigger thumbnails / tiles; tighten gaps, padding, and empty chrome so the grid feels denser.

**Notes**
- Desktop-first but still usable on narrow widths.
- Lightbox expand behavior should stay.

**Touch:** `app/modules/gallery.py` (+ any shared gallery CSS/classes)

---

## TODO-009 — Honest Gemini neighborhood prompt

**Rewrite the Neighborhood Gemini overview prompt** so it is less flowery/positive and gives a candid, realistic assessment (tradeoffs, noise, cost, drawbacks — not a sales pitch).

**Notes**
- Update `PROMPT_TEMPLATE` (or equivalent) in `app/core/gemini_neighborhood.py`.
- Bump or invalidate cache (`neighborhood_gemini_for`) so old rosy paragraphs aren’t kept forever after the prompt change.
- Keep the “AI may be wrong — verify” disclaimer.

**Touch:** `app/core/gemini_neighborhood.py`, tests for prompt text, maybe force-regenerate UX copy
