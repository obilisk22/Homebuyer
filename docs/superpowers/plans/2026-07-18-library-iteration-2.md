# Library Iteration 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the library home page (denser cards, compact Add, overflow menu) plus research UX (sort, filter badge, notes, high HOA) and lockable library thumbnails (smarter auto-pick + gallery set-as-thumb).

**Architecture:** Extend `PropertyService.list_properties` with in-memory sort; add `thumbnail_locked` on `Property` with migrate + service APIs; strengthen `thumbnail.py` scoring; refresh `library_page` chrome/cards and gallery tile actions. No grid redesign.

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy + SQLite, Pillow, pytest

**Spec:** [`docs/superpowers/specs/2026-07-18-library-iteration-2-design.md`](../specs/2026-07-18-library-iteration-2-design.md)

## Global Constraints

- Keep horizontal **list** layout (not a property grid).
- Do **not** commit unless the user asks.
- Windows: use `.\.venv\Scripts\python.exe` / `.\.venv\Scripts\pytest.exe`.
- After shipping: update `AGENTS.md` + `README.md`.
- Verify with `.\.venv\Scripts\pytest.exe -q` before claiming done.
- HOA high threshold is exactly `400` monthly.
- Sort values: `"newest"` | `"price_asc"` | `"price_desc"` (null prices last for price sorts).

---

## File map

| File | Responsibility |
|------|----------------|
| `app/core/thumbnail.py` | Interior avoid keywords + modest indoor image cue |
| `tests/test_thumbnail.py` | Scoring tests for interiors |
| `app/core/models.py` | `thumbnail_locked: bool` |
| `app/core/db.py` | ALTER migrate + `reselect_unlocked_thumbnails` from backfill |
| `app/core/property_service.py` | sort on list; set/unlock thumb; lock-aware select; re-import safe |
| `tests/test_library_iteration2.py` | Service tests: sort, lock, unlock |
| `app/ui/theme.py` | Larger thumbs, HOA amber chip, gallery thumb highlight |
| `app/ui/pages.py` | Library UI: compact Add, sort, badge, notes, menu, HOA |
| `app/modules/gallery.py` | Set-as-thumb button + Auto-pick again |
| `AGENTS.md`, `README.md` | Continuity / user docs |

---

### Task 1: Stronger thumbnail auto-pick

**Files:**
- Modify: `app/core/thumbnail.py`
- Test: `tests/test_thumbnail.py`

**Interfaces:**
- Consumes: existing `PhotoCandidate`, `keyword_score`, `image_score`, `pick_thumbnail_photo_id`
- Produces: stronger negative scores for interior room keywords; modest indoor warmth penalty in `image_score`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_thumbnail.py`:

```python
def test_avoids_kitchen_caption_even_when_first():
    candidates = [
        PhotoCandidate(1, "1/a.jpg", caption="Gourmet kitchen island", sort_order=0),
        PhotoCandidate(2, "1/b.jpg", caption="Front exterior curb", sort_order=1),
    ]
    assert pick_thumbnail_photo_id(candidates) == 2


def test_avoids_bedroom_and_bathroom_keywords():
    candidates = [
        PhotoCandidate(1, "1/a.jpg", caption="Primary bedroom suite", sort_order=0),
        PhotoCandidate(2, "1/b.jpg", caption="Full bathroom", sort_order=1),
        PhotoCandidate(3, "1/c.jpg", caption="Street view frontage", sort_order=2),
    ]
    assert pick_thumbnail_photo_id(candidates) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_thumbnail.py::test_avoids_kitchen_caption_even_when_first tests/test_thumbnail.py::test_avoids_bedroom_and_bathroom_keywords -v`

Expected: FAIL (picker still prefers early listing order / weak interior penalty)

- [ ] **Step 3: Implement scoring improvements**

In `app/core/thumbnail.py`:

1. Add `INTERIOR_KEYWORDS` tuple: `kitchen`, `bathroom`, `bedroom`, `living`, `closet`, `laundry`, `pantry`, `ceiling`, `island`, `granite`, `dining`, `hallway`, `fireplace` (and similar room words already needed by tests).
2. In `keyword_score`, for each interior keyword hit: `score -= 100.0` (same magnitude as floorplan avoid).
3. In `image_score`, after existing cues: if aspect `< 1.15` **and** top-band blueish ratio `<= 0.2` **and** mean red+green warmth is high (e.g. mean of `(r+g)/2 > 120` and mean `b < mean((r+g)/2) - 10`), apply `score -= 25.0`. Document in a one-line comment.

- [ ] **Step 4: Run thumbnail tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_thumbnail.py -q`

Expected: PASS (including existing tests)

---

### Task 2: `thumbnail_locked` model + migrate + service APIs + sort

**Files:**
- Modify: `app/core/models.py`
- Modify: `app/core/db.py`
- Modify: `app/core/property_service.py`
- Create: `tests/test_library_iteration2.py`

**Interfaces:**
- Consumes: `Property`, `PropertyService.select_thumbnail`, `list_properties`, photo import
- Produces:
  - `Property.thumbnail_locked: bool` (default `False`)
  - `list_properties(..., sort: str = "newest") -> list[Property]`
  - `set_library_thumbnail(property_id: int, photo_id: int) -> Photo`
  - `unlock_and_select_thumbnail(property_id: int) -> Photo | None`
  - `select_thumbnail` no-op when locked (unless no photos → clear id)
  - `reselect_unlocked_thumbnails()` in `db.py` called after migrate/backfill
  - Re-import: if locked photo missing after replace, clear lock and auto-pick

- [ ] **Step 1: Write failing service tests**

Create `tests/test_library_iteration2.py` using the project’s existing DB/session test patterns (inspect `tests/conftest.py` or sibling tests for session fixtures; if none, use a temp SQLite via `init_db` / override env — match local test style).

Minimum cases:

```python
def test_list_properties_sort_price_asc_nulls_last(...):
    # properties priced 200, None, 100 → order ids for price_asc: 100, 200, None

def test_select_thumbnail_skips_when_locked(...):
    # set thumb A, lock True, add/prefer better exterior candidate → select_thumbnail leaves A

def test_set_library_thumbnail_locks(...):
    # set_library_thumbnail(B) → thumbnail_photo_id == B and thumbnail_locked is True

def test_unlock_and_select_thumbnail_clears_lock(...):
    # unlock_and_select_thumbnail → locked False and thumb may change to auto pick
```

- [ ] **Step 2: Run to verify fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_library_iteration2.py -v`

Expected: FAIL (import/attr errors)

- [ ] **Step 3: Model + migrate**

Add to `Property` in `models.py`:

```python
thumbnail_locked: Mapped[bool] = mapped_column(default=False, nullable=False)
```

(Use SQLAlchemy `Boolean` if the codebase uses it elsewhere; else Integer 0/1 is fine if consistent — prefer `from sqlalchemy import Boolean`.)

In `_migrate_sqlite` `prop_cols` loop, add:

```python
(
    "thumbnail_locked",
    "ALTER TABLE properties ADD COLUMN thumbnail_locked BOOLEAN NOT NULL DEFAULT 0",
),
```

- [ ] **Step 4: Implement list sort + thumb APIs in `property_service.py`**

```python
def list_properties(
    self,
    *,
    search: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    min_beds: float | None = None,
    sort: str = "newest",
) -> list[Property]:
    # existing fetch + filter, then:
    if sort == "price_asc":
        props.sort(key=lambda p: (p.list_price is None, p.list_price or 0.0))
    elif sort == "price_desc":
        props.sort(key=lambda p: (p.list_price is None, -(p.list_price or 0.0)))
    else:
        props.sort(key=lambda p: p.created_at or utcnow(), reverse=True)
    return props
```

(`newest` already comes from SQL `order_by created_at desc`; re-sorting after filter is fine.)

```python
def select_thumbnail(self, property_id: int) -> Photo | None:
    prop = self.get_property(property_id)
    ...
    if prop.thumbnail_locked and prop.photos:
        # keep existing id if still present; else fall through to pick
        if prop.thumbnail_photo_id and any(p.id == prop.thumbnail_photo_id for p in prop.photos):
            ...
            return existing photo
    # existing pick logic; ensure thumbnail_locked stays False when auto-picking

def set_library_thumbnail(self, property_id: int, photo_id: int) -> Photo:
    # validate ownership; set thumbnail_photo_id + thumbnail_locked=True; commit

def unlock_and_select_thumbnail(self, property_id: int) -> Photo | None:
    prop = self.get_property(property_id)
    prop.thumbnail_locked = False
    self.session.commit()
    return self.select_thumbnail(property_id)
```

In `import_zillow_photos` after replace/delete old photos: if locked id missing, set `thumbnail_locked=False` then `select_thumbnail`.

- [ ] **Step 5: Reselect unlocked on init**

In `db.py`, add `reselect_unlocked_thumbnails()` that loads properties with photos where `thumbnail_locked` is false and calls `select_thumbnail` for each (or at least those that had a thumb — spec: re-score unlocked homes once at migrate/backfill). Call it from `init_db` after `_backfill_thumbnails`.

- [ ] **Step 6: Run service + thumbnail tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_library_iteration2.py tests/test_thumbnail.py -q`

Expected: PASS

---

### Task 3: Theme CSS for denser cards + HOA chip + gallery thumb mark

**Files:**
- Modify: `app/ui/theme.py`

**Interfaces:**
- Produces CSS classes used by Tasks 4–5: `.hb-library-thumb` 180×135, `.hb-meta-chip--hoa-high`, `.hb-photo-card--library-thumb`, optional `.hb-library-card-body`

- [ ] **Step 1: Update theme CSS**

```css
.hb-library-thumb,
.hb-library-thumb--empty {
  width: 180px;
  height: 135px;
  min-width: 180px;
}

.hb-meta-chip--hoa-high {
  color: var(--hb-amber) !important;
  border-color: rgba(255, 193, 7, 0.55);
  background: rgba(255, 193, 7, 0.12);
}

.hb-photo-card--library-thumb {
  border-color: rgba(0, 229, 255, 0.65) !important;
  box-shadow: 0 0 14px rgba(0, 229, 255, 0.25);
}
```

Ensure `.hb-library-card` row fills width (body `flex-grow: 1`).

- [ ] **Step 2: Smoke — app still imports theme**

Run: `.\.venv\Scripts\python.exe -c "from app.ui.theme import apply_theme; print('ok')"`

Expected: `ok`

---

### Task 4: Library page UI (layout + research UX)

**Files:**
- Modify: `app/ui/pages.py` (`library_page` and small helpers)

**Interfaces:**
- Consumes: `list_properties(..., sort=)`, `_library_secondary_chips`, theme classes
- Produces: compact Add when DB nonempty; sort select; filter active badge; notes teaser; HOA high chip; overflow menu (Zillow + Delete)

- [ ] **Step 1: Helpers**

```python
HOA_HIGH_MONTHLY = 400.0

def _truncate_notes(notes: str, limit: int = 100) -> str:
    text = (notes or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
```

Update secondary chip rendering: when formatting HOA, if `hoa_fee >= HOA_HIGH_MONTHLY`, apply `hb-meta-chip hb-meta-chip--hoa-high` instead of quiet.

- [ ] **Step 2: Restructure chrome**

1. Track `hint_label` / show helper sentence only when `has_any` is false (set visibility in `refresh`).
2. Add `ui.select` for sort with options Newest / Price ↑ / Price ↓; `on_value_change` → `refresh`.
3. Filter expansion: update title or trailing caption to `"Filter · N active"` / `"Filter"` based on nonempty parsed filters.
4. Pass `sort=...` into `list_properties`.

- [ ] **Step 3: Card actions menu**

Replace always-visible Zillow link + standalone delete icon with:

```python
with ui.element("div").on("click", js_handler="(e) => e.stopPropagation()"):
    with ui.button(icon="more_vert").props("flat round dense"):
        with ui.menu():
            ui.menu_item("Open on Zillow", on_click=lambda u=prop.zillow_url: ui.navigate.to(u, new_tab=True))
            # Prefer opening URL: ui.link or window open — use ui.run_javascript or ui.navigate if supported;
            # if navigate lacks new_tab, use ui.open or link via javascript: window.open
            ui.menu_item("Delete…", on_click=lambda p=prop.id, a=prop.address: confirm_delete(p, a))
```

Keep whole-card click → property. Keep existing confirm dialog.

Add notes teaser under chips when `_truncate_notes(prop.notes)` nonempty.

- [ ] **Step 4: Manual check**

Restart app (`python -m app.main`), open `http://127.0.0.1:8080/`:

- [ ] Larger thumbs, no always-on Zillow
- [ ] Sort changes order
- [ ] High HOA amber on ≥$400
- [ ] Compact Add when homes exist

---

### Task 5: Gallery set-as-thumb + Auto-pick again

**Files:**
- Modify: `app/modules/gallery.py`

**Interfaces:**
- Consumes: `set_library_thumbnail`, `unlock_and_select_thumbnail`, `thumbnail_photo_id`
- Produces: per-tile pin button; cyan border on current library thumb; Auto-pick again control

- [ ] **Step 1: Wire gallery UI**

In `refresh_gallery`, after loading photos + property:

- For each tile, if `photo.id == fresh.thumbnail_photo_id`, add class `hb-photo-card--library-thumb` and optional caption badge “Library thumb”.
- Add flat round `push_pin` (or `photo_library`) button with tooltip “Use as library thumbnail”; `stopPropagation` on click; call `set_library_thumbnail`; notify; `refresh_gallery`.
- Near import buttons: `ui.button("Auto-pick again", ...)` calling `unlock_and_select_thumbnail`; notify; refresh.

- [ ] **Step 2: Manual check**

Open a property Photos tab → set thumb → return to library → confirm new image. Auto-pick again clears lock.

---

### Task 6: Docs + full verification

**Files:**
- Modify: `AGENTS.md`, `README.md`

- [ ] **Step 1: Update docs**

- `AGENTS.md`: mark library iteration 2 done; product decision for thumb lock + library sort/HOA/menu.
- `README.md`: library sort, overflow menu, set library thumb from Photos.

- [ ] **Step 2: Full test suite**

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: all pass

- [ ] **Step 3: Done checklist**

- [ ] Nonempty library: compact Add; ⋮ menu; denser cards
- [ ] Sort + filter badge + notes + amber HOA
- [ ] Locked manual thumb + Auto-pick again
- [ ] pytest green

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Taller 180×135 thumbs, filled card row | 3, 4 |
| Compact Add when ≥1 home | 4 |
| Overflow Zillow + Delete | 4 |
| Sort newest / price asc / desc | 2, 4 |
| Active filter badge | 4 |
| Notes teaser ~100 chars | 4 |
| HOA ≥ 400 amber | 3, 4 |
| Interior keyword + indoor cue | 1 |
| `thumbnail_locked` migrate | 2 |
| set / unlock / select skip when locked | 2, 5 |
| Reselect unlocked at init | 2 |
| Re-import clears lock if photo gone | 2 |
| Gallery UI + Auto-pick again | 5 |
| AGENTS + README | 6 |
