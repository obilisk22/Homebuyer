# Visual foundation — Design Spec

**Date:** 2026-07-18  
**Status:** Implemented 2026-07-18  
**Product:** Homebuy global theme (`app/ui/theme.py`) + library cards (`app/ui/pages.py`)  
**Approach:** Hierarchy-through-emission (restrained neon used for readability)

## Problem

Homebuy already has a dark cyberpunk token set (cyan / magenta / lime / amber on near-black), but the UI still reads as “styled Quasar defaults”:

1. No distinctive type pairing — system/Quasar fonts carry no brand.
2. Neon glow is applied too broadly (cards, links, hovers), so accents don’t encode priority.
3. Text fields and inter-element gaps feel airy; high-priority data (price, address) doesn’t dominate the library card.
4. Density work must not shrink the library photo — media stays a primary signal.

## Goals

1. **Emission hierarchy** — cyan glow as a priority ladder (L1 / L2 / L3), not decoration.
2. **Typography** — Akira Expanded for L1 figures; Creato Display for all other UI text.
3. **Density** — roughly **20% less** breathing room between elements; denser Quasar field chrome; **do not** truncate or hide listing info.
4. **Library cards** — keep a **large** thumbnail (≥ current ~180×135; target ~200×150); address + price ~**2×** current visual scale so they fill the text column.
5. **Agent continuity** — installable design skills already added; add a short Homebuy visual rule so future polish stays on-brand.

## Non-goals

- Full Map / Financials / Neighborhood layout redesigns (they inherit global tokens/fonts only).
- Bold neon / HUD maximalism; magenta and lime everywhere.
- New motion systems or animated chrome.
- Purchasing a commercial Akira license (local personal app uses personal/demo terms for now).
- Changing filter/sort behavior or card click semantics.

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Direction | Approach A — hierarchy through emission |
| Neon intensity | Restrained; glow drives readability / hierarchy |
| L1 emissive | Price, active tab, focused input, primary CTA |
| L2 emissive | Brand wordmark; selected/hover card border (interaction only) |
| L3 quiet | Chips, muted meta, secondary chrome — no glow (address is large Creato but non-emissive) |
| Accents | Cyan = hierarchy; amber = HOA ≥ $400; magenta/lime sparse (link hover / rare highlight) |
| Density | ~20% less gap; denser fields; enlarge L1 type rather than remove info |
| Display font (L1) | [Akira Expanded](https://www.dafont.com/akira-expanded.font) (Typologic) — prices / key figures |
| Body font | [Creato Display](https://www.dafont.com/creato-display.font) (Lafontype, SIL OFL 1.1) |
| Library photo | Keep large; densify text column only; prefer ~200×150 |
| Address + price scale | ~2× previous mock scale (approved companion Section 3b) |
| Scope this pass | Global theme foundation + library card restyle + visual rule |
| Out of pass | Property header redesign beyond inherited fonts/tokens; tab-specific layouts |

## Visual system

### Color tokens (keep; clarify roles)

Existing hex values in `theme.py` stay. Document semantic use:

| Token | Hex | Role |
|-------|-----|------|
| `--hb-bg` | `#0B0D10` | Page |
| `--hb-surface` / `--hb-surface-2` | `#161A21` / `#1C222C` | Cards / controls |
| `--hb-text` / `--hb-text-muted` | `#E8EDF4` / `#8B96A8` | Body / secondary |
| `--hb-neon` | `#00E5FF` | L1 hierarchy + focus |
| `--hb-neon-2` / `--hb-neon-3` | `#FF2BD6` / `#B8FF3C` | Sparse secondary / highlight |
| `--hb-amber` | `#FFC107` | HOA-high chip only (semantic) |

### Emission levels

| Level | When | Treatment |
|-------|------|-----------|
| L1 | Always (price, active tab, focus, primary CTA) | Soft cyan color + restrained `text-shadow` / `box-shadow` |
| L2 | Hover/selected card; brand | Border/glow on interaction; brand soft glow at rest OK |
| L3 | Chips, muted meta, field labels at rest | No glow; muted borders |

**Change from today:** reduce blanket `.q-card:hover` / link bloom so L1 remains the loudest signal.

### Typography

| Role | Face | Approx use |
|------|------|------------|
| L1 display | Akira Expanded | Library price; other key currency/figures that are hierarchy anchors |
| Body / UI | Creato Display | Address, labels, chips, buttons, tabs, notes |
| Fallback | system-ui stack | Until files load |

**Library scale (approved):** address ~2× previous; price ~2× previous (companion used ~32px address / ~52px price against a ~200×150 thumb — implement as CSS variables so we can tune).

**Licensing:**

- Creato Display: SIL OFL 1.1 — embed OK; keep license notice with font files.
- Akira Expanded: free for **personal** use on DaFont (demo); commercial needs Creative Market purchase. Document in `app/static/fonts/README.md`. Homebuy is a personal local app → personal use is the intended path for v1.

**Delivery:** self-host under `app/static/fonts/` (no CDN). User supplies downloaded `.otf` (or we wire `@font-face` once files are present). NiceGUI: register static files + `ui.add_css` / head link.

### Spacing / density

- Introduce a small spacing scale (e.g. 4/8/12/16/24) and apply ~20% reduction vs current library card padding and vertical stack gaps.
- Quasar outlined fields: reduce control min-height / vertical padding via CSS overrides (shorter chrome, same content).
- Do **not** remove chips, notes teaser, or HOA signals to save space.

### Library card layout

```text
[  thumb ~200×150  ]  address (Creato, large)
                      city/state (muted)
                      price (Akira, L1 emissive, large)   ← may sit top-right
                      chips + quiet meta + HOA amber
                      notes teaser (if any)
                      ⋮ overflow (unchanged behavior)
```

Photo size is a hard constraint: never shrink below current ~180×135 to “fix” density.

## Architecture

```text
app/static/fonts/
  AkiraExpanded*.otf   # user-provided / personal demo
  CreatoDisplay-*.otf  # OFL family (subset of weights as needed)
  README.md            # licenses + attribution

app/ui/theme.py
  → @font-face + CSS variables (--hb-font-display, --hb-font-body)
  → emission utility classes / tightened field + gap rules
  → library card type/size rules (.hb-library-price, address class)

app/ui/pages.py
  → library markup: ensure address has a dedicated class for Creato large scale
  → thumb dimensions updated if targeting ~200×150

.cursor/rules/ or AGENTS.md snippet
  → Homebuy visual do/don’t (emission ladder, fonts, density)
```

Skills already installed globally for agents:

- `~/.cursor/skills/frontend-design/`
- `~/.cursor/skills/ui-design-brain/`

## Implementation outline (for writing-plans)

1. Add static font hosting + `@font-face`; document licenses.
2. Extend `theme.py` tokens: font families, type scale vars, emission utilities; tone down non-L1 glow.
3. Density: field CSS + library/header gap reductions (~20%).
4. Library card: large thumb, 2× address/price classes, Creato/Akira assignment.
5. Continuity: short visual rule + `AGENTS.md` / `README.md` theme notes.
6. Verify: library list at http://127.0.0.1:8080; pytest still passes; no regression to card click / ⋮ menu.

## Risks

| Risk | Mitigation |
|------|------------|
| Akira demo glyph gaps | Limit Akira to prices/`$` digits; fallback Creato if needed |
| Huge price overflows short addresses | Allow wrap; keep price top-right or flex-shrink:0 with wrap on address |
| Quasar field overrides brittle | Prefer CSS variables / specific `.q-field` selectors; visual check Add + filters |
| Font files missing in repo | Gate on files present; document download steps; don’t commit illegal redistrib if license forbids — Creato OK; Akira personal demo: confirm redistrib terms before committing binaries |

## Success criteria

1. Opening the library, price is the first neon L1 read; chips stay quiet.
2. Address + price clearly larger; card does not feel empty beside a large photo.
3. Inputs feel shorter (~denser) without losing labels or values.
4. Creato/Akira load (once files are in place); fallbacks don’t break layout.
5. Map/Financials/Neighborhood still usable — only global font/token inheritance, no layout rewrite.

## Companion reference

Session mockups under `.superpowers/brainstorm/companion-20260718-124614/content/` (gitignored): emission hierarchy, density compare, type+photo, 2× type, foundation scope.
