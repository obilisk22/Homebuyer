# Visual Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a hierarchy-through-emission visual foundation — Akira/Creato typography, denser chrome, L1–L3 neon discipline, and larger library address/price beside a large photo.

**Architecture:** Self-host fonts under `app/static/fonts/`, register `/static` in `main.py`, extend `theme.py` with `@font-face`, type/spacing/emission CSS variables and utilities, restyle library cards in `pages.py`, and document the system in AGENTS/README plus a Cursor rule.

**Tech Stack:** Python 3.12, NiceGUI, Quasar CSS overrides, local `.otf` fonts, pytest

**Spec:** [`docs/superpowers/specs/2026-07-18-visual-foundation-design.md`](../specs/2026-07-18-visual-foundation-design.md)

## Global Constraints

- Emission: cyan L1 hierarchy; amber HOA ≥ $400; magenta/lime sparse.
- Density: ~20% less gap; denser fields; **do not** hide listing info.
- Library thumb: never below ~180×135; target ~200×150.
- Address + price: ~2× prior scale (CSS vars; companion target ~32px / ~52px).
- Akira = L1 figures (price); Creato = all other UI text.
- Akira is personal-use/demo — **do not commit** Akira binaries to the public GitHub repo; Creato (OFL) may be committed.
- Do **not** git-commit unless the user asks.
- Windows: `.\.venv\Scripts\python.exe` / `.\.venv\Scripts\pytest.exe`.
- After shipping: update `AGENTS.md` + `README.md`.
- Verify: `.\.venv\Scripts\pytest.exe -q` before claiming done.

---

## File map

| File | Responsibility |
|------|----------------|
| `app/static/fonts/README.md` | Download + license notes |
| `app/static/fonts/CreatoDisplay-*.otf` | Body family (OFL; commit OK) |
| `app/static/fonts/AkiraExpanded*.otf` | L1 display (local only; gitignored) |
| `app/static/fonts/OFL-CreatoDisplay.txt` | SIL OFL text for Creato |
| `.gitignore` | Ignore Akira binaries |
| `app/main.py` | `app.add_static_files("/static", ...)` |
| `app/ui/theme.py` | `@font-face`, tokens, emission, density, library type/size |
| `app/ui/pages.py` | Library card classes + layout (large address/price row) |
| `tests/test_visual_foundation.py` | Assert theme CSS + static registration contract |
| `.cursor/rules/homebuy-visual.mdc` | Agent do/don’t for visuals |
| `AGENTS.md`, `README.md` | Continuity / user-facing theme notes |

---

### Task 1: Font hosting + static mount + license docs

**Files:**
- Create: `app/static/fonts/README.md`
- Create: `app/static/fonts/OFL-CreatoDisplay.txt` (copy of SIL OFL 1.1 notice / Creato copyright block from the DaFont download)
- Create: `app/static/.gitkeep` if needed so `static/` exists without fonts
- Modify: `.gitignore` — ignore `app/static/fonts/Akira*`
- Modify: `app/main.py` — register `/static`
- Test: `tests/test_visual_foundation.py`

**Interfaces:**
- Consumes: NiceGUI `app.add_static_files`
- Produces: browser URLs `/static/fonts/<file>`; README instruct user to drop Akira + Creato files

- [ ] **Step 1: Write the failing test**

Create `tests/test_visual_foundation.py`:

```python
from pathlib import Path

from app.ui import theme


def test_theme_declares_font_face_and_family_vars():
    css = theme._CSS
    assert "@font-face" in css or "hb-font-display" in css
    # Before Task 2 this may fail — Task 1 only needs static path contract below


def test_fonts_readme_exists():
    readme = Path(__file__).resolve().parents[1] / "app" / "static" / "fonts" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "Akira" in text and "Creato" in text
```

Split: for Task 1 only assert README + that `main.py` source contains `add_static_files("/static"`. Keep the `@font-face` assert for Task 2.

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fonts_readme_documents_akira_and_creato():
    readme = ROOT / "app" / "static" / "fonts" / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "Akira Expanded" in text
    assert "Creato Display" in text
    assert "personal" in text.lower()
    assert "OFL" in text or "Open Font License" in text


def test_main_registers_static_files():
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'add_static_files("/static"' in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py -v`

Expected: FAIL (missing README and/or static mount)

- [ ] **Step 3: Implement font docs + static mount**

1. Write `app/static/fonts/README.md`:

```markdown
# Homebuy fonts

## Creato Display (body / UI)
- Source: https://www.dafont.com/creato-display.font
- License: SIL Open Font License 1.1 (see OFL-CreatoDisplay.txt)
- Place files here, e.g. `CreatoDisplay-Regular.otf`, `CreatoDisplay-Medium.otf`, `CreatoDisplay-Bold.otf`
- Safe to commit to the repo

## Akira Expanded (L1 prices / key figures)
- Source: https://www.dafont.com/akira-expanded.font
- License: free for **personal** use only (demo on DaFont). Commercial → Creative Market
- Place e.g. `Akira Expanded Demo.otf` or `AkiraExpanded.otf` here
- **Do not commit** Akira binaries (gitignored). Keep a local copy for your machine.

After adding files, restart the app (`python -m app.main`).
```

2. Add to `.gitignore`:

```
# Personal-use display font — do not publish binaries
app/static/fonts/Akira*
app/static/fonts/**/Akira*
```

3. In `app/main.py`, after uploads static mount:

```python
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "fonts").mkdir(parents=True, exist_ok=True)
app.add_static_files("/static", str(STATIC_DIR))
```

4. Download Creato OTFs into `app/static/fonts/` if network allows; otherwise leave README and proceed (CSS fallbacks work). Copy OFL text from the zip into `OFL-CreatoDisplay.txt` when available.

5. If the user has already downloaded Akira, copy into `app/static/fonts/` (gitignored).

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py -v`

Expected: PASS

---

### Task 2: Theme tokens — fonts, emission ladder, density, library type scale

**Files:**
- Modify: `app/ui/theme.py`
- Modify: `tests/test_visual_foundation.py`

**Interfaces:**
- Consumes: `/static/fonts/*` URLs
- Produces: CSS vars `--hb-font-display`, `--hb-font-body`, `--hb-library-address-size`, `--hb-library-price-size`; classes `.hb-library-address`, `.hb-library-price`, denser `.q-field` rules; quieter non-L1 glow

- [ ] **Step 1: Extend failing assertions**

Add to `tests/test_visual_foundation.py`:

```python
from app.ui import theme


def test_theme_css_has_visual_foundation_tokens():
    css = theme._CSS
    assert "--hb-font-display" in css
    assert "--hb-font-body" in css
    assert ".hb-library-address" in css
    assert "Akira" in css or "hb-font-display" in css
    assert "Creato" in css or "hb-font-body" in css
    assert "--hb-library-price-size" in css
    assert "--hb-library-address-size" in css
```

- [ ] **Step 2: Run to verify fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py::test_theme_css_has_visual_foundation_tokens -v`

Expected: FAIL

- [ ] **Step 3: Implement theme CSS**

In `app/ui/theme.py` `_CSS` (and `:root`):

1. **`@font-face`** for Creato weights that exist on disk — use local() + url fallbacks. Prefer checking files at import time:

```python
from pathlib import Path

_FONTS_DIR = Path(__file__).resolve().parents[1] / "static" / "fonts"

def _font_face(family: str, filename: str, weight: int = 400) -> str:
    path = _FONTS_DIR / filename
    if not path.is_file():
        return ""
    return f"""
@font-face {{
  font-family: "{family}";
  src: url("/static/fonts/{filename}") format("opentype");
  font-weight: {weight};
  font-style: normal;
  font-display: swap;
}}
"""
```

Discover common filenames (CreatoDisplay-Regular.otf, etc.; Akira Expanded Demo.otf / AkiraExpanded.otf). Concatenate non-empty faces into `_CSS`.

2. **`:root` vars:**

```css
--hb-font-display: "Akira Expanded", "Akira Expanded Demo", Impact, system-ui, sans-serif;
--hb-font-body: "Creato Display", system-ui, sans-serif;
--hb-library-address-size: 2rem;   /* ~32px */
--hb-library-price-size: 3.25rem;  /* ~52px */
--hb-space-1: 0.25rem;
--hb-space-2: 0.5rem;
--hb-space-3: 0.75rem;
--hb-space-4: 1rem;
```

3. **Body default:** `font-family: var(--hb-font-body);` on `body` / `.q-body--dark`.

4. **Emission discipline:**
   - Keep strong glow on `.hb-library-price`, `.q-tab--active`, focused fields, primary buttons.
   - Soften generic `.q-card:hover` and `a:hover` text-shadow so they don’t compete with L1.
   - Brand `.hb-brand` stays L2 soft glow.

5. **Density:**
   - `.hb-library-card` padding → ~`0.7rem 0.85rem` (from ~0.85/1.1).
   - `.q-field--outlined .q-field__control` min-height ~40px; reduce padding.
   - Slightly tighter `.hb-meta-chip` padding.

6. **Library type + thumb:**

```css
.hb-library-thumb,
.hb-library-thumb--empty {
  width: 200px;
  height: 150px;
  min-width: 200px;
}
.hb-library-address {
  font-family: var(--hb-font-body);
  font-size: var(--hb-library-address-size);
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: 0.01em;
  color: var(--hb-text);
}
.hb-library-price {
  font-family: var(--hb-font-display);
  font-size: var(--hb-library-price-size);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 0.95;
  color: var(--hb-neon) !important;
  text-shadow: 0 0 14px rgba(0, 229, 255, 0.5);
}
.hb-library-place {
  font-size: 0.875rem;
  color: var(--hb-text-muted);
}
```

- [ ] **Step 4: Run visual foundation tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py -q`

Expected: PASS

---

### Task 3: Library card markup — large address/price layout

**Files:**
- Modify: `app/ui/pages.py` (library card block ~326–365)
- Test: `tests/test_visual_foundation.py` (optional source contract)

**Interfaces:**
- Consumes: `.hb-library-address`, `.hb-library-price`, `.hb-library-place`, thumb CSS
- Produces: address/price row matching approved mock (large type, photo left)

- [ ] **Step 1: Add source contract test**

```python
def test_library_page_uses_address_and_price_classes():
    src = (ROOT / "app" / "ui" / "pages.py").read_text(encoding="utf-8")
    assert "hb-library-address" in src
    assert "hb-library-price" in src
```

- [ ] **Step 2: Run — expect fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py::test_library_page_uses_address_and_price_classes -v`

- [ ] **Step 3: Restyle library card body**

Replace the address/price column so layout is:

```python
with ui.column().classes("gap-1 flex-grow").style("min-width: 0"):
    with ui.row().classes(
        "w-full items-start justify-between gap-3 flex-nowrap"
    ):
        with ui.column().classes("gap-0").style("min-width: 0"):
            ui.label(address).classes("hb-library-address")
            place = ", ".join(
                p for p in ((prop.city or "").strip(), (prop.state or "").strip()) if p
            )
            if place:
                ui.label(place).classes("hb-library-place")
        if list_price is not None:
            ui.label(_format_price(list_price)).classes("hb-library-price")
    # chips / notes unchanged below — tighten row gap classes from gap-2 → gap-1 or gap-2 keep
```

**Note:** `prop` is available in the loop; capture `city`/`state` like other fields if needed while session open (already on `prop` in loop).

Reduce outer `gap-4` to `gap-3` on the card row to hit ~20% denser spacing.

Keep overflow ⋮ behavior unchanged (`stopPropagation`).

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_visual_foundation.py tests/test_library_iteration2.py -q`

Expected: PASS

---

### Task 4: Continuity docs + Cursor visual rule

**Files:**
- Create: `.cursor/rules/homebuy-visual.mdc`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-18-visual-foundation-design.md` — status → Implemented (when done)

**Interfaces:** none (docs only)

- [ ] **Step 1: Write `.cursor/rules/homebuy-visual.mdc`**

```markdown
---
description: Homebuy visual system — emission hierarchy, fonts, density
globs: app/ui/**/*.py, app/modules/**/*.py
alwaysApply: false
---

# Homebuy visuals

- Dark near-black + cyan hierarchy. Neon is a **priority signal**, not decoration.
- L1 (always emissive): price, active tab, focused field, primary CTA.
- L2: brand; card border glow on hover/selected only.
- L3: chips/meta — no glow. Amber only for HOA ≥ $400.
- Fonts: Akira Expanded = L1 figures; Creato Display = body/UI. Self-hosted under `app/static/fonts/`.
- Density: prefer tighter gaps (~20%) and larger L1 type; never shrink library thumbs below ~180×135; never hide listing chips to save space.
- Do not introduce purple-on-white or cream-terracotta defaults; stay on the existing token set in `theme.py`.
```

- [ ] **Step 2: Update AGENTS.md**

In Product decisions / What’s done / theme notes:

- Mark visual foundation done (Akira/Creato, emission ladder, denser library cards, ~200×150 thumbs).
- Note Akira local-only / Creato OFL.
- Point to `app/static/fonts/README.md`.

- [ ] **Step 3: Update README.md**

Short “Theme / fonts” blurb: dark neon hierarchy; download Creato + Akira into `app/static/fonts/` per README there.

- [ ] **Step 4: Full verify**

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: all PASS

Manual: restart `.\.venv\Scripts\python.exe -m app.main`, open library — large photo, large address/price, quieter chip glow, denser fields.

- [ ] **Step 5: Commit only if user asks**

Suggested message if requested:

```
Polish visual foundation: emission hierarchy, Creato/Akira type, denser library cards.
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Emission L1/L2/L3 | Task 2 |
| Akira L1 / Creato body | Tasks 1–2 |
| ~20% density + denser fields | Task 2 |
| Large thumb ≥180×135 / ~200×150 | Task 2 |
| Address + price ~2× | Tasks 2–3 |
| Font hosting + licenses | Task 1 |
| Visual rule + AGENTS/README | Task 4 |
| No Map/Financials layout rewrite | (non-goal; inherit fonts only) |
| Don’t commit Akira binaries | Task 1 `.gitignore` |

## Placeholder / consistency self-review

- No TBD steps; filenames and CSS vars named consistently (`--hb-font-display`, `.hb-library-address`).
- Commit steps gated on user request (matches repo convention).
