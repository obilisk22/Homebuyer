"""App-wide black / gray + neon cyberpunk theme for NiceGUI."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from app.core.map_basemap import FULLSCREEN_ICON_URL
from app.core.paths import static_dir

# Accent set: cyan (primary), magenta (secondary), electric lime (highlight)
NEON = {
    "cyan": "#00E5FF",
    "magenta": "#FF2BD6",
    "lime": "#B8FF3C",
    "amber": "#FFC107",
}

COLORS = {
    "bg": "#0B0D10",
    "bg_elevated": "#12151A",
    "surface": "#161A21",
    "surface_2": "#1C222C",
    "border": "#2A3340",
    "border_glow": "rgba(0, 229, 255, 0.35)",
    "text": "#E8EDF4",
    "text_muted": "#8B96A8",
    "neon": NEON["cyan"],
    "neon_2": NEON["magenta"],
    "neon_3": NEON["lime"],
}

_THEME_APPLIED_ATTR = "_homebuy_theme_applied"
_FONTS_DIR = static_dir() / "fonts"

# (family, relative path under fonts/, weight)
_FONT_CANDIDATES: list[tuple[str, str, int]] = [
    ("Creato Display", "creato_display/CreatoDisplay-Thin.otf", 100),
    ("Creato Display", "creato_display/CreatoDisplay-Light.otf", 300),
    ("Creato Display", "creato_display/CreatoDisplay-Regular.otf", 400),
    ("Creato Display", "creato_display/CreatoDisplay-Medium.otf", 500),
    ("Creato Display", "creato_display/CreatoDisplay-Bold.otf", 700),
    ("Creato Display", "creato_display/CreatoDisplay-ExtraBold.otf", 800),
    ("Creato Display", "creato_display/CreatoDisplay-Black.otf", 900),
    # Flat fallbacks if files are moved to fonts/ root
    ("Creato Display", "CreatoDisplay-Regular.otf", 400),
    ("Creato Display", "CreatoDisplay-Medium.otf", 500),
    ("Creato Display", "CreatoDisplay-Bold.otf", 700),
    ("Akira Expanded", "akira_expanded/Akira Expanded Demo.otf", 700),
    ("Akira Expanded", "Akira Expanded Demo.otf", 700),
    ("Akira Expanded", "AkiraExpanded.otf", 700),
]


def _font_face(family: str, rel_path: str, weight: int | str) -> str:
    path = _FONTS_DIR / rel_path
    if not path.is_file():
        return ""
    # CSS url path: encode spaces in filenames
    url_path = "/static/fonts/" + "/".join(
        part.replace(" ", "%20") for part in Path(rel_path).parts
    )
    return f"""
@font-face {{
  font-family: "{family}";
  src: url("{url_path}") format("opentype");
  font-weight: {weight};
  font-style: normal;
  font-display: swap;
}}
"""


def _build_font_faces() -> str:
    """Emit @font-face rules for every font file found on disk."""
    chunks: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for family, rel_path, weight in _FONT_CANDIDATES:
        key = (family, rel_path, str(weight))
        if key in seen:
            continue
        seen.add(key)
        face = _font_face(family, rel_path, weight)
        if not face:
            continue
        chunks.append(face)
        # Single-cut display fonts (Akira Super Bold): map all common
        # weights to the same file so Quasar/body weights still match.
        if family == "Akira Expanded":
            for w in (400, 500, 600, 700, 800, 900):
                if w == weight:
                    continue
                extra = _font_face(family, rel_path, w)
                if extra:
                    chunks.append(extra)
    return "".join(chunks)


_FONT_FACES = _build_font_faces()


_CSS = f"""
{_FONT_FACES}
:root {{
  --hb-bg: {COLORS["bg"]};
  --hb-bg-elevated: {COLORS["bg_elevated"]};
  --hb-surface: {COLORS["surface"]};
  --hb-surface-2: {COLORS["surface_2"]};
  --hb-border: {COLORS["border"]};
  --hb-border-glow: {COLORS["border_glow"]};
  --hb-text: {COLORS["text"]};
  --hb-text-muted: {COLORS["text_muted"]};
  --hb-neon: {COLORS["neon"]};
  --hb-neon-2: {COLORS["neon_2"]};
  --hb-neon-3: {COLORS["neon_3"]};
  --hb-amber: {NEON["amber"]};
  --hb-font-display: "Akira Expanded", Impact, system-ui, sans-serif;
  --hb-font-body: "Creato Display", system-ui, sans-serif;
  --hb-library-address-size: clamp(1.215rem, 3.6vw, 2.25rem);
  --hb-library-price-size: 1.35rem;
  --hb-space-1: 0.25rem;
  --hb-space-2: 0.5rem;
  --hb-space-3: 0.75rem;
  --hb-space-4: 1rem;
  /* Dark neumorphism — soft extrusion on near-black */
  --hb-neo-face: #14181f;
  --hb-neo-dark: #080a0d;
  --hb-neo-light: #1e2530;
  --hb-neo-out:
    5px 5px 12px var(--hb-neo-dark),
    -4px -4px 10px var(--hb-neo-light);
  --hb-neo-out-sm:
    3px 3px 7px var(--hb-neo-dark),
    -2px -2px 6px var(--hb-neo-light);
  --hb-neo-in:
    inset 4px 4px 9px var(--hb-neo-dark),
    inset -3px -3px 7px var(--hb-neo-light);
  --hb-neo-in-sm:
    inset 2px 2px 5px var(--hb-neo-dark),
    inset -2px -2px 4px var(--hb-neo-light);
}}

body,
body.body--dark,
.q-body--dark {{
  background: var(--hb-bg) !important;
  color: var(--hb-text);
  font-family: var(--hb-font-body);
}}

.nicegui-content {{
  background: transparent;
}}

/* Layered depth behind the page */
.q-page,
.q-layout {{
  background:
    radial-gradient(ellipse 80% 50% at 10% -10%, rgba(0, 229, 255, 0.07), transparent 55%),
    radial-gradient(ellipse 60% 40% at 90% 0%, rgba(255, 43, 214, 0.05), transparent 50%),
    var(--hb-bg) !important;
}}

/* Header */
.hb-header {{
  background: linear-gradient(180deg, var(--hb-bg-elevated) 0%, rgba(18, 21, 26, 0.92) 100%) !important;
  border-bottom: 1px solid var(--hb-border);
  box-shadow: 0 0 24px rgba(0, 229, 255, 0.08);
  backdrop-filter: blur(8px);
}}

.hb-brand {{
  font-family: "Akira Expanded", var(--hb-font-display) !important;
  color: var(--hb-neon) !important;
  letter-spacing: 0.06em;
  text-shadow: 0 0 12px rgba(0, 229, 255, 0.45);
  font-weight: 800 !important;
  font-size: 1.05rem;
  font-synthesis: none;
}}

.hb-header-title {{
  font-family: var(--hb-font-body);
  color: var(--hb-text-muted) !important;
  font-weight: 500;
  font-size: 0.95rem;
  letter-spacing: 0.02em;
  opacity: 0.9;
}}

/* Page chrome — Creato headings, shared library shell */
.hb-page-title {{
  font-family: var(--hb-font-body);
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--hb-text);
  line-height: 1.2;
}}

.hb-page-meta {{
  font-family: var(--hb-font-body);
  font-size: 0.875rem;
  color: var(--hb-text-muted);
}}

.hb-page-hint {{
  font-family: var(--hb-font-body);
  font-size: 0.875rem;
  color: var(--hb-text-muted);
  line-height: 1.4;
}}

.hb-section-title {{
  font-family: var(--hb-font-body);
  font-size: 1.05rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--hb-text);
  margin-top: 0.25rem;
}}

/* Gemini output — Creato body hierarchy (no Akira; AI text is L3 content) */
.hb-gemini-prose {{
  font-family: var(--hb-font-body);
  color: var(--hb-text);
  font-size: 0.95rem;
  line-height: 1.65;
  max-width: 52rem;
}}

.hb-gemini-prose p {{
  margin: 0 0 0.75rem;
  color: var(--hb-text);
}}

.hb-gemini-prose p:last-child {{
  margin-bottom: 0;
}}

.hb-gemini-prose h1,
.hb-gemini-prose h2,
.hb-gemini-prose h3,
.hb-gemini-prose h4 {{
  font-family: var(--hb-font-body);
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--hb-text);
  line-height: 1.25;
  margin: 1rem 0 0.45rem;
}}

.hb-gemini-prose h1 {{ font-size: 1.25rem; }}
.hb-gemini-prose h2 {{ font-size: 1.1rem; }}
.hb-gemini-prose h3,
.hb-gemini-prose h4 {{
  font-size: 1rem;
  color: var(--hb-neon);
  text-shadow: none;
  font-weight: 600;
}}

.hb-gemini-prose ul,
.hb-gemini-prose ol {{
  margin: 0.35rem 0 0.85rem;
  padding-left: 1.25rem;
}}

.hb-gemini-prose li {{
  margin: 0.25rem 0;
  color: var(--hb-text);
}}

.hb-gemini-prose strong {{
  font-weight: 700;
  color: var(--hb-text);
}}

.hb-gemini-prose a {{
  color: var(--hb-neon);
  text-decoration: none;
}}

.hb-gemini-prose a:hover {{
  color: var(--hb-neon-3);
}}

.hb-gemini-prose--stale {{
  color: var(--hb-text-muted);
  opacity: 0.85;
}}

.hb-gemini-prose--stale h1,
.hb-gemini-prose--stale h2,
.hb-gemini-prose--stale h3,
.hb-gemini-prose--stale h4,
.hb-gemini-prose--stale strong {{
  color: var(--hb-text-muted);
}}

.hb-library-shell {{
  width: 100%;
  max-width: 72rem; /* ~max-w-6xl — room for Akira streets */
  margin-left: auto;
  margin-right: auto;
}}

.hb-property-shell {{
  width: 100%;
  max-width: 80rem;
  margin-left: auto;
  margin-right: auto;
}}

/* Property header photo — modes: bleed (default) | beside (rollback) */
.hb-property-hero {{
  position: relative;
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
}}

.hb-property-hero__bg {{
  position: absolute;
  inset: 0;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  z-index: 0;
}}

.hb-property-hero__scrim {{
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(
    105deg,
    rgba(8, 10, 13, 0.88) 0%,
    rgba(8, 10, 13, 0.72) 45%,
    rgba(8, 10, 13, 0.55) 100%
  );
}}

.hb-property-hero__content {{
  position: relative;
  z-index: 2;
  padding: 1rem 1.1rem;
}}

.hb-property-hero--bleed:not(.hb-property-hero--has-photo) .hb-property-hero__content {{
  padding: 0;
}}

.hb-property-hero--bleed.hb-property-hero--has-photo {{
  min-height: 11rem;
  border: 1px solid var(--hb-border);
  box-shadow: var(--hb-neo-out-sm);
}}

.hb-property-hero--bleed.hb-property-hero--has-photo .hb-library-address {{
  text-shadow: 0 2px 18px rgba(0, 0, 0, 0.85);
}}

.hb-property-hero--bleed.hb-property-hero--has-photo .hb-library-place,
.hb-property-hero--bleed.hb-property-hero--has-photo .hb-page-meta {{
  text-shadow: 0 1px 10px rgba(0, 0, 0, 0.75);
}}

.hb-property-hero--beside .hb-property-hero__content {{
  padding: 0;
}}

.hb-property-hero--beside .hb-property-hero__listing {{
  align-items: stretch;
}}

.hb-property-hero:has(.hb-nearby-icons) .hb-property-hero__content {{
  padding-bottom: 2.35rem;
}}

.hb-property-hero--bleed:not(.hb-property-hero--has-photo):has(.hb-nearby-icons)
  .hb-property-hero__content {{
  padding-bottom: 2.35rem;
}}

.hb-property-hero .hb-nearby-icons {{
  right: 1.1rem;
  bottom: 0.65rem;
}}

/* Secondary edit control — muted so it doesn't compete with module tabs */
.hb-edit-listing-expansion {{
  margin-top: 0.35rem;
  opacity: 0.72;
  transition: opacity 0.15s ease;
}}

.hb-edit-listing-expansion:hover,
.hb-edit-listing-expansion:focus-within {{
  opacity: 1;
}}

.hb-edit-listing-expansion .q-item {{
  min-height: 2rem !important;
  padding: 0.2rem 0.35rem !important;
  color: var(--hb-text-muted) !important;
}}

.hb-edit-listing-expansion .q-item__label,
.hb-edit-listing-expansion .q-icon {{
  color: var(--hb-text-muted) !important;
  font-size: 0.85rem !important;
  font-weight: 400 !important;
}}

.hb-edit-listing-expansion .q-expansion-item__content {{
  opacity: 1;
}}

@media (max-width: 800px) {{
  .hb-property-hero--beside .hb-property-hero__listing {{
    flex-wrap: wrap;
  }}
}}

/* Financials form: primary deal + rent side-by-side; expansions below */
.hb-financial-form {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1.5rem;
  align-items: start;
}}

.hb-financial-form__deal,
.hb-financial-form__rent {{
  min-width: 0;
}}

.hb-financial-expansion {{
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  background: rgba(28, 34, 44, 0.35);
}}

.hb-financial-expansion .q-expansion-item__container {{
  padding: 0.15rem 0.35rem;
}}

.hb-field-label {{
  font-family: var(--hb-font-body);
  font-size: 0.78rem;
  color: var(--hb-text-muted);
  letter-spacing: 0.02em;
}}

.hb-field-chrome {{
  opacity: 0.55;
}}

.hb-field-chrome:hover {{
  opacity: 0.9;
}}

.hb-field-help {{
  color: var(--hb-text-muted) !important;
  cursor: help;
  opacity: 0.4;
}}

.hb-field-help:hover {{
  color: var(--hb-cyan, #00E5FF) !important;
  opacity: 1;
}}

.hb-field-revert {{
  color: var(--hb-text-muted) !important;
  min-height: 1.5rem !important;
  min-width: 1.5rem !important;
  padding: 0 !important;
}}

.hb-field-revert:hover {{
  color: var(--hb-cyan, #00E5FF) !important;
}}

.hb-field-source {{
  opacity: 0.75;
}}

@media (max-width: 900px) {{
  .hb-financial-form {{
    grid-template-columns: 1fr;
  }}
}}

.hb-add-card {{
  padding: 0.7rem 0.85rem !important;
}}

.hb-add-card .q-card__section {{
  padding: 0 !important;
}}

/* Add-home card stays flat — not a listing */
.hb-add-card:hover {{
  border-color: var(--hb-border) !important;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35) !important;
  transform: none !important;
}}

.hb-toolbar-row {{
  gap: 0.75rem;
  align-items: center;
}}

.hb-empty-state {{
  font-family: var(--hb-font-body);
  color: var(--hb-text-muted);
  font-size: 0.95rem;
  padding: 1.25rem 0.5rem;
  border: 1px dashed var(--hb-border);
  border-radius: 10px;
  background: rgba(28, 34, 44, 0.35);
  text-align: center;
}}

/* Single focus ring language (L1) */
.q-btn:focus-visible,
.q-field--outlined.q-field--focused .q-field__control:before,
a:focus-visible {{
  outline: none;
}}
.q-btn:focus-visible {{
  box-shadow: 0 0 0 2px var(--hb-bg), 0 0 0 4px var(--hb-neon), 0 0 14px rgba(0, 229, 255, 0.35);
}}

/* Cards / surfaces — no always-on cyan hairline; L2 hover only on library cards */
.q-card {{
  background: var(--hb-surface) !important;
  color: var(--hb-text);
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}}

.q-card:hover {{
  border-color: var(--hb-border);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}}

/* Inputs — labels ABOVE the box; value / $/% / spinner centered inside */
.q-field {{
  font-family: var(--hb-font-body);
}}

.q-field--outlined .q-field__control {{
  background: var(--hb-surface-2);
  border-radius: 8px;
}}

.q-field--outlined .q-field__control:before {{
  border-color: var(--hb-border) !important;
}}

.q-field--outlined.q-field--focused .q-field__control:before,
.q-field--outlined.q-field--highlighted .q-field__control:before {{
  border-color: var(--hb-neon) !important;
  box-shadow: 0 0 0 1px var(--hb-neon), 0 0 14px rgba(0, 229, 255, 0.25);
}}

/* Room above the control so labels never sit on the border */
.q-field--outlined.q-field--labeled:not(.q-textarea) {{
  padding-top: 1.15rem;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__control {{
  height: 40px !important;
  min-height: 40px !important;
  max-height: 40px !important;
  align-items: center;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__control-container {{
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  height: 100%;
  display: flex;
  align-items: center;
}}

/* Label sits fully above the outlined box (no border tangent) */
.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__label {{
  top: -1.2rem !important;
  left: 0 !important;
  right: auto !important;
  max-width: 100%;
  transform: none !important;
  font-size: 0.78rem !important;
  font-weight: 500;
  line-height: 1.2 !important;
  background: transparent !important;
  padding: 0 !important;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
  z-index: 1;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__native,
.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__input {{
  min-height: 0 !important;
  height: 100% !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  line-height: 40px !important;
  display: flex;
  align-items: center;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__prefix,
.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__suffix {{
  display: flex;
  align-items: center;
  align-self: center;
  height: 40px;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  line-height: 40px !important;
  color: var(--hb-text-muted) !important;
  opacity: 0.9;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__marginal {{
  height: 40px !important;
  min-height: 40px !important;
  max-height: 40px !important;
  align-items: center;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__append,
.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__prepend {{
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 40px;
  padding: 0 2px;
}}

.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__append .q-btn,
.q-field--outlined.q-field--labeled:not(.q-textarea) .q-field__prepend .q-btn {{
  padding: 0;
  min-height: 16px;
  max-height: 16px;
  line-height: 16px;
}}

/* Unlabeled single-line fields (rare) — same 40px center */
.q-field--outlined:not(.q-field--labeled):not(.q-textarea) .q-field__control {{
  height: 40px;
  min-height: 40px;
  max-height: 40px;
  align-items: center;
}}

.q-field--with-bottom {{
  padding-bottom: 8px;
}}

/* Captions under fields — clear of the control / spinner */
.q-field + .hb-page-meta,
.q-field + .hb-page-hint {{
  margin-top: 0.15rem;
  margin-bottom: 0.15rem;
}}

.q-field__native,
.q-field__input,
.q-field__label,
.q-placeholder {{
  color: var(--hb-text) !important;
  font-family: var(--hb-font-body);
}}

.q-field__label {{
  color: var(--hb-text-muted) !important;
}}

.q-field--focused .q-field__label {{
  color: var(--hb-neon) !important;
}}

.q-select .q-field__native {{
  line-height: 40px !important;
}}

/* Buttons — unified dark neumorphism (no Quasar cyan fill / cyan outline) */
.q-btn {{
  font-family: var(--hb-font-body) !important;
  border-radius: 10px !important;
  transition:
    box-shadow 0.15s ease,
    background-color 0.15s ease,
    color 0.15s ease,
    transform 0.12s ease;
}}

.q-btn:not(.q-btn--round):not(.q-btn--dense) {{
  min-height: 2.35rem;
}}

/* Filled / unelevated / primary / secondary → soft extruded neo face */
.q-btn--unelevated,
.q-btn--standard,
.q-btn.bg-primary,
.q-btn.bg-secondary,
.q-btn.bg-accent,
.q-btn.bg-dark,
.q-btn.bg-grey-9,
.q-btn.bg-grey-8 {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text-muted) !important;
  border: none !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  text-shadow: none !important;
}}

.q-btn--unelevated:hover,
.q-btn--standard:hover,
.q-btn.bg-primary:hover,
.q-btn.bg-secondary:hover,
.q-btn.bg-accent:hover,
.q-btn.bg-dark:hover,
.q-btn.bg-grey-9:hover,
.q-btn.bg-grey-8:hover {{
  background: #171c25 !important;
  color: var(--hb-text) !important;
  box-shadow: var(--hb-neo-out) !important;
  text-shadow: none !important;
}}

.q-btn--unelevated:active,
.q-btn--standard:active,
.q-btn.bg-primary:active,
.q-btn.bg-secondary:active,
.q-btn.bg-dark:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
  transform: translateY(1px);
}}

/* Outline — neo face, no cyan ring (was “black + blue outline”) */
.q-btn--outline,
.q-btn--outline.text-primary,
.q-btn--outline.text-secondary,
.q-btn--outline.text-accent,
.q-btn--outline.text-dark {{
  background: var(--hb-neo-face) !important;
  border: 1px solid transparent !important;
  color: var(--hb-text-muted) !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  text-shadow: none !important;
}}

.q-btn--outline:hover,
.q-btn--outline.text-primary:hover,
.q-btn--outline.text-secondary:hover {{
  background: #171c25 !important;
  border-color: transparent !important;
  color: var(--hb-text) !important;
  box-shadow: var(--hb-neo-out) !important;
}}

.q-btn--outline:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
  transform: translateY(1px);
}}

/* Optional CTA — same neo face; cyan label only on hover (hierarchy without fill) */
.q-btn.hb-btn-cta {{
  color: var(--hb-text) !important;
}}

.q-btn.hb-btn-cta:hover {{
  color: var(--hb-neon) !important;
  text-shadow: 0 0 8px rgba(0, 229, 255, 0.28);
}}

/* Flat — quiet; neo on hover */
.q-btn--flat {{
  background: transparent !important;
  box-shadow: none !important;
  color: var(--hb-text-muted) !important;
}}

.q-btn--flat.text-primary,
.q-btn--flat.text-secondary {{
  color: var(--hb-text-muted) !important;
}}

.q-btn--flat:hover {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text) !important;
  box-shadow: var(--hb-neo-out-sm) !important;
}}

.q-btn--flat:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
}}

/* Round icon buttons — circular extrusion (not cyan flat) */
.q-btn--round,
.q-btn--round.bg-primary,
.q-btn--round.text-primary {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text-muted) !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  text-shadow: none !important;
}}

.q-btn--round:hover,
.q-btn--round.text-primary:hover {{
  color: var(--hb-neon) !important;
  box-shadow:
    var(--hb-neo-out),
    0 0 10px rgba(0, 229, 255, 0.15) !important;
}}

.q-btn--round:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
}}

/* Destructive — neo face, danger label (keep readable) */
.q-btn.bg-negative,
.q-btn--unelevated.bg-negative {{
  background: var(--hb-neo-face) !important;
  color: #ff6b85 !important;
  border: none !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  text-shadow: none !important;
}}

.q-btn.bg-negative:hover {{
  color: #ff8a9e !important;
  box-shadow: var(--hb-neo-out) !important;
}}

/* Number-field spinners stay flat (too small for neo) */
.q-field__append .q-btn,
.q-field__prepend .q-btn {{
  background: transparent !important;
  box-shadow: none !important;
  border-radius: 4px !important;
  min-height: 16px !important;
  transform: none !important;
}}

/* Tabs — extruded / pressed pills (no recessed tray) */
.q-tabs {{
  border-bottom: none;
  padding: 2px 0 6px;
  background: transparent;
  box-shadow: none;
  margin-bottom: 0.35rem;
}}

.q-tabs .q-tab {{
  color: var(--hb-text-muted) !important;
  text-transform: none;
  letter-spacing: 0.02em;
  font-family: var(--hb-font-body);
  border-radius: 9px;
  margin: 0 3px;
  min-height: 2.4rem;
  background: var(--hb-neo-face);
  box-shadow: var(--hb-neo-out-sm);
  transition:
    box-shadow 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease;
}}

.q-tabs .q-tab:hover {{
  color: var(--hb-text) !important;
  box-shadow: var(--hb-neo-out);
}}

.q-tabs .q-tab--active {{
  color: var(--hb-neon) !important;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.35);
  background: #12161d;
  box-shadow: var(--hb-neo-in-sm);
}}

.q-tab__indicator {{
  display: none;
}}

.q-tab-panels {{
  background: transparent !important;
}}

.q-tab-panel {{
  background: transparent !important;
}}

/* Expansion / dialogs */
.q-expansion-item {{
  background: var(--hb-surface);
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  overflow: hidden;
}}

.q-expansion-item__container {{
  background: transparent !important;
}}

.q-dialog__inner > .q-card {{
  background: var(--hb-surface) !important;
}}

/* Links */
a {{
  color: var(--hb-neon);
}}

a:hover {{
  color: var(--hb-neon-3);
}}

/* Muted / secondary text overrides for Quasar grey helpers */
.text-grey-6,
.text-grey-7,
.text-grey-8,
.text-blue-grey-2 {{
  color: var(--hb-text-muted) !important;
}}

/* Summary / metric chips used in Financials */
.hb-metric {{
  background: var(--hb-surface-2);
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  color: var(--hb-text);
}}

.hb-metric--accent {{
  background: linear-gradient(145deg, rgba(0, 229, 255, 0.12), rgba(255, 43, 214, 0.08));
  border-color: rgba(0, 229, 255, 0.45);
  box-shadow: 0 0 18px rgba(0, 229, 255, 0.15);
  color: var(--hb-text);
}}

.hb-metric--accent .text-caption {{
  color: var(--hb-neon) !important;
  opacity: 1 !important;
}}

/* Library — list-style home cards */
.hb-library-card {{
  position: relative;
  padding: 0.7rem 0.85rem;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
}}

.hb-library-card:has(.hb-nearby-icons) {{
  padding-bottom: 2.35rem;
}}

.hb-library-card:hover {{
  border-color: rgba(0, 229, 255, 0.45) !important;
  box-shadow: 0 0 14px rgba(0, 229, 255, 0.12), 0 10px 32px rgba(0, 0, 0, 0.45) !important;
  transform: translateY(-1px);
}}

.hb-library-card-body {{
  flex-grow: 1;
  min-width: 0;
  align-items: stretch;
}}

/* Thumb stretches to match the text column height beside it.
   min-height floors the box — stretch + height:100% on the image can
   otherwise resolve to 0px and hide library photos entirely. */
.hb-library-thumb-wrap {{
  position: relative;
  width: clamp(168px, 20vw, 220px);
  min-width: 168px;
  min-height: 135px;
  flex-shrink: 0;
  align-self: stretch;
  border-radius: 8px;
  border: 1px solid var(--hb-border);
  overflow: hidden;
  background: var(--hb-surface-2);
}}

.hb-nearby-icons {{
  position: absolute;
  right: 0.85rem;
  bottom: 0.55rem;
  left: auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  z-index: 2;
  pointer-events: none;
}}

.hb-nearby-chip {{
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(12, 16, 22, 0.82);
  border: 1px solid var(--hb-border);
  box-shadow:
    2px 2px 6px rgba(0, 0, 0, 0.45),
    inset 1px 1px 0 rgba(255, 255, 255, 0.06);
  font-size: 15px;
  line-height: 1;
  pointer-events: auto;
}}

.hb-nearby-chip--amenity {{
  color: var(--hb-lime, #B8FF3C);
}}

.hb-nearby-chip--risk {{
  color: var(--hb-magenta, #FF2BD6);
}}

.hb-nearby-chip--amber {{
  color: var(--hb-amber, #FFC107);
}}

.hb-library-thumb-wrap--empty {{
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: dashed;
  color: var(--hb-text-muted);
}}

.hb-library-thumb {{
  width: 100%;
  height: 100%;
  min-height: 135px;
  object-fit: cover;
  display: block;
  border: none;
  border-radius: 0;
}}

/* NiceGUI wraps ui.image in a custom element — force it to fill the wrap */
.hb-library-thumb-wrap > .hb-library-thumb,
.hb-library-thumb-wrap nicegui-image.hb-library-thumb {{
  width: 100% !important;
  height: 100% !important;
  min-height: 135px;
  display: block;
}}

.hb-library-address {{
  font-family: "Akira Expanded", var(--hb-font-display) !important;
  font-size: var(--hb-library-address-size);
  font-weight: 800 !important;
  line-height: 1.1;
  letter-spacing: 0.04em;
  color: var(--hb-text);
  font-synthesis: none;
  overflow-wrap: anywhere;
  word-break: break-word;
}}

.hb-library-unit {{
  font-size: 0.75em;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
  opacity: 0.92;
}}

/* Stack library card row on narrow viewports (overrides Quasar flex-nowrap) */
@media (max-width: 800px) {{
  .hb-library-card .flex-nowrap {{
    flex-wrap: wrap !important;
  }}

  .hb-library-card-body {{
    width: 100%;
    flex-basis: 100%;
    flex-wrap: wrap !important;
  }}

  .hb-library-thumb-wrap {{
    width: 100%;
    min-width: 0;
    max-width: 100%;
    height: 180px;
    align-self: stretch;
  }}
}}

.hb-library-place {{
  font-family: var(--hb-font-body);
  font-size: 0.8rem;
  color: var(--hb-text-muted);
  margin-top: 0.1rem;
}}

.hb-library-price {{
  font-family: var(--hb-font-body);
  font-size: var(--hb-library-price-size);
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.2;
  color: var(--hb-neon) !important;
  text-shadow: 0 0 8px rgba(0, 229, 255, 0.25);
  margin-top: 0.15rem;
  font-synthesis: none;
}}

.hb-meta-chip {{
  font-family: var(--hb-font-body);
  background: var(--hb-surface-2);
  border: 1px solid rgba(42, 51, 64, 0.95);
  border-radius: 999px;
  padding: 0.12rem 0.55rem;
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--hb-text);
  white-space: nowrap;
}}

.hb-meta-chip--quiet {{
  color: var(--hb-text-muted);
  opacity: 0.85;
  border-color: transparent;
  background: transparent;
  padding: 0.12rem 0.25rem;
  font-weight: 400;
  letter-spacing: 0.01em;
}}

.hb-meta-chip--hoa-high {{
  color: var(--hb-amber) !important;
  border-color: rgba(255, 193, 7, 0.55);
  background: rgba(255, 193, 7, 0.12);
  opacity: 1;
  font-weight: 600;
}}

.hb-appr-low {{
  color: var(--hb-amber) !important;
  opacity: 1 !important;
  font-weight: 600;
}}

.hb-appr-high {{
  color: var(--hb-neon-3) !important;
  opacity: 1 !important;
  font-weight: 600;
}}

/* Neighborhood — assigned schools (three info cards, no map) */
.hb-school-card {{
  background: var(--hb-surface) !important;
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  padding: 0.8rem 1rem;
  flex: 1 1 220px;
  min-width: 220px;
  max-width: 300px;
}}

.hb-school-level-ph {{
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--hb-surface-2);
  flex-shrink: 0;
}}

.hb-school-level-ph--cyan {{
  border: 1px solid rgba(0, 229, 255, 0.5);
  color: var(--hb-neon);
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.18);
}}

.hb-school-level-ph--magenta {{
  border: 1px solid rgba(255, 43, 214, 0.5);
  color: var(--hb-neon-2);
  box-shadow: 0 0 10px rgba(255, 43, 214, 0.18);
}}

.hb-school-level-ph--lime {{
  border: 1px solid rgba(184, 255, 60, 0.5);
  color: var(--hb-neon-3);
  box-shadow: 0 0 10px rgba(184, 255, 60, 0.18);
}}

/* CA School Dashboard color badge (Blue/Green/Yellow/Orange/Red) — a quiet
   outlined chip; free real-world color, distinct from the cyan/magenta/lime
   level accents above. */
.hb-dashboard-badge {{
  display: inline-block;
  margin-top: 0.3rem;
  padding: 0.05rem 0.4rem;
  border: 1px solid var(--hb-border);
  border-radius: 6px;
  font-weight: 600;
}}

.hb-library-notes {{
  font-family: var(--hb-font-body);
  font-size: 0.8rem;
  color: var(--hb-text-muted);
  opacity: 0.9;
  line-height: 1.35;
}}

.hb-photo-card--library-thumb {{
  border-color: rgba(0, 229, 255, 0.65) !important;
  box-shadow: 0 0 14px rgba(0, 229, 255, 0.25);
}}

/* Photo gallery — 4-across, full-bleed within the tab panel */
.hb-photo-gallery {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
  width: 100%;
  margin: 0;
  padding: 0;
}}

@media (max-width: 900px) {{
  .hb-photo-gallery {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}
}}

@media (max-width: 600px) {{
  .hb-photo-gallery {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}
}}

.hb-photo-card {{
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 0 !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}

.hb-photo-frame {{
  position: relative;
  width: 100%;
  line-height: 0;
}}

.hb-photo-thumb {{
  aspect-ratio: 4 / 3;
  width: 100%;
  height: auto !important;
  min-height: 0;
  display: block;
}}

.hb-photo-pin {{
  position: absolute !important;
  top: 0.35rem !important;
  right: 0.35rem !important;
  z-index: 2;
  min-height: 1.35rem !important;
  min-width: 1.35rem !important;
  padding: 0 !important;
  opacity: 0.28;
  color: #fff !important;
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
  border: none !important;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.7);
  transition: opacity 0.15s ease;
}}

.hb-photo-pin::before,
.hb-photo-pin::after {{
  display: none !important;
  box-shadow: none !important;
}}

.hb-photo-pin .q-icon {{
  color: #fff !important;
  font-size: 1.05rem !important;
  opacity: 1;
}}

.hb-photo-card:hover .hb-photo-pin {{
  opacity: 0.55;
}}

.hb-photo-pin--active {{
  opacity: 0.7;
  color: var(--hb-neon) !important;
}}

.hb-photo-pin--active .q-icon {{
  color: var(--hb-neon) !important;
}}

.hb-photo-pin:hover {{
  opacity: 0.95 !important;
}}

.hb-photo-card .q-card__section {{
  display: none !important;
  padding: 0 !important;
}}

.hb-photo-card:hover {{
  border-color: rgba(0, 229, 255, 0.55) !important;
  box-shadow: 0 0 18px rgba(0, 229, 255, 0.2), 0 8px 28px rgba(0, 0, 0, 0.45) !important;
}}

/* Upload area */
.q-uploader {{
  background: var(--hb-surface) !important;
  border: 1px dashed var(--hb-border);
  border-radius: 10px;
}}

/* Leaflet / iframe chrome */
.leaflet-container {{
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  box-shadow: 0 0 20px rgba(0, 229, 255, 0.08);
}}

.hb-map {{
  width: 100%;
  height: 32rem;
  max-height: min(60vh, 40rem);
  border-radius: 10px;
}}

/* Fullscreen must ignore the in-tab height cap */
.leaflet-container:fullscreen,
.leaflet-container:-webkit-full-screen,
.leaflet-pseudo-fullscreen {{
  max-height: none !important;
  border-radius: 0 !important;
  border: none !important;
  box-shadow: none !important;
}}

.hb-map-layers {{
  gap: 0.25rem 0.4rem;
  align-items: center;
  flex-wrap: wrap;
  margin: 0 0 0.15rem;
}}

/* Match property tab neo pills — muted off, cyan text only when on */
.hb-map-layers .hb-map-layer-btn,
.hb-map-layers .hb-map-layer-btn.bg-primary,
.hb-map-layers .hb-map-layer-btn.bg-dark {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text-muted) !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  border: none !important;
  border-radius: 9px !important;
  min-height: 1.85rem !important;
  padding: 0.15rem 0.65rem !important;
  font-size: 0.82rem !important;
  font-family: var(--hb-font-body) !important;
  font-weight: 500 !important;
  letter-spacing: 0.02em;
  text-transform: none !important;
  text-shadow: none !important;
  line-height: 1.2 !important;
  transition:
    box-shadow 0.15s ease,
    color 0.15s ease,
    background-color 0.15s ease,
    text-shadow 0.15s ease;
}}

.hb-map-layers .hb-map-layer-btn:hover {{
  color: var(--hb-text) !important;
  box-shadow: var(--hb-neo-out) !important;
  text-shadow: none !important;
}}

.hb-map-layers .hb-map-layer-btn:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
}}

/* Glow only when on — never on the off / hover-off states above */
.hb-map-layers .hb-map-layer-btn--on,
.hb-map-layers .hb-map-layer-btn--on.bg-primary,
.hb-map-layers .hb-map-layer-btn--on.bg-dark {{
  background: #12161d !important;
  color: var(--hb-neon) !important;
  box-shadow:
    var(--hb-neo-in-sm),
    0 0 12px rgba(0, 229, 255, 0.22) !important;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.35);
}}

.hb-map-layers .hb-map-layer-btn--on:hover {{
  color: var(--hb-neon) !important;
  box-shadow:
    var(--hb-neo-in-sm),
    0 0 14px rgba(0, 229, 255, 0.28) !important;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.35);
}}

.hb-map-layers .hb-map-layer-btn.disabled,
.hb-map-layers .hb-map-layer-btn[disabled] {{
  opacity: 0.38 !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  color: var(--hb-text-muted) !important;
  text-shadow: none !important;
}}

.hb-map-status {{
  min-height: 0;
  margin: 0;
  line-height: 1.25;
  color: var(--hb-text-muted) !important;
}}

.hb-map-status:empty {{
  display: none;
}}

.hb-map-legend {{
  margin: 0.15rem 0 0;
  gap: 0.2rem;
}}

.hb-map-legend:empty {{
  display: none;
}}

.hb-map-box {{
  margin-top: 0.35rem;
}}

/* Zoom + fullscreen controls readable on dark basemap.
   Use background-color (not shorthand background) so leaflet.fullscreen's
   background-image icon sprite is not wiped by !important. */
.leaflet-bar a {{
  background-color: var(--hb-surface) !important;
  color: var(--hb-text) !important;
  border-bottom-color: var(--hb-border) !important;
}}
.leaflet-bar a:hover {{
  background-color: var(--hb-surface-2) !important;
  color: var(--hb-neon) !important;
}}
/* Absolute icon URL keeps the expand/exit sprite even if plugin relative url() breaks. */
.leaflet-control-fullscreen a.leaflet-fullscreen-icon {{
  background-color: var(--hb-surface) !important;
  background-image: url("{FULLSCREEN_ICON_URL}") !important;
  background-size: 26px 52px !important;
  background-repeat: no-repeat !important;
  /* SVG sprite is black; invert → white on dark control chrome */
  filter: invert(1);
}}
.leaflet-control-fullscreen a.leaflet-fullscreen-icon:hover {{
  background-color: var(--hb-surface-2) !important;
  filter: invert(1) brightness(1.15);
}}

/* Street View panel — 16:9 desktop-scale iframe; no min-height empty shell */
.hb-sv-panel {{
  margin-top: 0.35rem;
}}
.hb-sv-panel .q-expansion-item__content > .q-card__section {{
  padding: 0.35rem 0.5rem 0.45rem !important;
}}
.hb-sv-actions {{
  margin-top: 0.25rem;
  gap: 0.35rem 0.5rem;
}}
.homebuy-sv {{
  container-type: inline-size;
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: min(42vh, 480px);
  height: auto;
  overflow: hidden;
  border-radius: 10px;
  background: #111;
  position: relative;
  border: 1px solid var(--hb-border) !important;
  box-shadow: 0 0 18px rgba(0, 229, 255, 0.08), 0 6px 20px rgba(0, 0, 0, 0.4) !important;
}}
/* When max-height binds, keep the frame 16:9 instead of letterboxing */
@supports (width: min(100%, 1px)) {{
  .homebuy-sv {{
    width: min(100%, calc(min(42vh, 480px) * 16 / 9));
  }}
}}

/* Gallery lightbox — dark neo (classes applied by gallery.py) */
.hb-lightbox {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text) !important;
  border: 1px solid var(--hb-border) !important;
  border-radius: 12px !important;
  box-shadow: var(--hb-neo-out), 0 16px 48px rgba(0, 0, 0, 0.55) !important;
}}

.hb-lightbox-close,
.hb-lightbox-nav {{
  background: var(--hb-neo-face) !important;
  color: var(--hb-text-muted) !important;
  border: none !important;
  border-radius: 999px !important;
  box-shadow: var(--hb-neo-out-sm) !important;
  text-shadow: none !important;
  transition:
    color 0.15s ease,
    box-shadow 0.15s ease;
}}

.hb-lightbox-close:hover,
.hb-lightbox-nav:hover {{
  color: var(--hb-neon) !important;
  box-shadow:
    var(--hb-neo-out),
    0 0 12px rgba(0, 229, 255, 0.22) !important;
}}

.hb-lightbox-close:active,
.hb-lightbox-nav:active {{
  box-shadow: var(--hb-neo-in-sm) !important;
}}

.hb-lightbox-caption {{
  font-family: var(--hb-font-body);
  font-size: 0.875rem;
  color: var(--hb-text-muted);
  line-height: 1.4;
}}

/* Scrollbars */
::-webkit-scrollbar {{
  width: 8px;
  height: 8px;
}}
::-webkit-scrollbar-track {{
  background: var(--hb-bg);
}}
::-webkit-scrollbar-thumb {{
  background: var(--hb-border);
  border-radius: 4px;
}}
::-webkit-scrollbar-thumb:hover {{
  background: var(--hb-neon);
}}

/* ── FINAL button hammer (must stay last) ───────────────────────────
   Quasar paints .bg-primary with --q-primary (cyan). Force black neo
   faces + grey labels; CTAs use cyan text only. */
html body.body--dark .q-btn,
html body.body--dark .q-btn.bg-primary,
html body.body--dark .q-btn.bg-secondary,
html body.body--dark .q-btn.bg-accent,
html body.body--dark .q-btn.bg-dark,
html body.body--dark .q-btn.bg-grey-9,
html body.body--dark .q-btn.bg-grey-8,
html body.body--dark .q-btn.text-primary,
html body.body--dark .q-btn--unelevated,
html body.body--dark .q-btn--standard,
html body.body--dark .q-btn--outline {{
  background: #14181f !important;
  background-color: #14181f !important;
  color: #8B96A8 !important;
  border: none !important;
  border-color: transparent !important;
  box-shadow:
    3px 3px 7px #080a0d,
    -2px -2px 6px #1e2530 !important;
  text-shadow: none !important;
}}

html body.body--dark .q-btn .q-btn__content,
html body.body--dark .q-btn .q-icon {{
  color: inherit !important;
}}

html body.body--dark .q-btn:hover {{
  background: #171c25 !important;
  background-color: #171c25 !important;
  color: #E8EDF4 !important;
}}

html body.body--dark .q-btn.hb-btn-cta,
html body.body--dark .q-btn.hb-btn-cta.bg-primary,
html body.body--dark .q-btn.hb-btn-cta.bg-dark {{
  background: #14181f !important;
  background-color: #14181f !important;
  color: #00E5FF !important;
}}

html body.body--dark .q-btn.hb-btn-cta:hover {{
  color: #00E5FF !important;
  text-shadow: 0 0 8px rgba(0, 229, 255, 0.28);
}}

html body.body--dark .q-btn.q-btn--flat:not(.q-btn--round) {{
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
  color: #8B96A8 !important;
}}

html body.body--dark .q-btn.q-btn--flat:not(.q-btn--round):hover {{
  background: #14181f !important;
  background-color: #14181f !important;
  color: #E8EDF4 !important;
  box-shadow:
    3px 3px 7px #080a0d,
    -2px -2px 6px #1e2530 !important;
}}

html body.body--dark .q-btn.bg-negative {{
  background: #14181f !important;
  background-color: #14181f !important;
  color: #ff6b85 !important;
}}

html body.body--dark .q-field__append .q-btn,
html body.body--dark .q-field__prepend .q-btn {{
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
}}

/* Map layer toggles — keep cyan label when enabled (after button hammer) */
html body.body--dark .hb-map-layers .hb-map-layer-btn--on,
html body.body--dark .hb-map-layers .hb-map-layer-btn--on.bg-dark {{
  background: #12161d !important;
  background-color: #12161d !important;
  color: #00E5FF !important;
  box-shadow:
    inset 2px 2px 5px #080a0d,
    inset -2px -2px 4px #1e2530,
    0 0 12px rgba(0, 229, 255, 0.28) !important;
}}

/* Photo pin — icon only, no neo button face (after button hammer) */
html body.body--dark .q-btn.hb-photo-pin,
html body.body--dark .q-btn.hb-photo-pin.bg-dark,
html body.body--dark .q-btn.hb-photo-pin.q-btn--round,
html body.body--dark .q-btn.hb-photo-pin.q-btn--flat,
html body.body--dark .q-btn.hb-photo-pin:hover {{
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
  border: none !important;
  color: #fff !important;
}}

html body.body--dark .q-btn.hb-photo-pin .q-icon {{
  color: #fff !important;
}}

html body.body--dark .q-btn.hb-photo-pin--active,
html body.body--dark .q-btn.hb-photo-pin--active:hover {{
  background: transparent !important;
  background-color: transparent !important;
  box-shadow: none !important;
  color: #00E5FF !important;
}}

html body.body--dark .q-btn.hb-photo-pin--active .q-icon {{
  color: #00E5FF !important;
}}
"""


def apply_theme() -> None:
    """Enable dark mode, Quasar brand colors, and cyberpunk CSS once per page."""
    # Guard against duplicate CSS if page_header is called more than once
    client = getattr(ui.context, "client", None)
    if client is not None and getattr(client, _THEME_APPLIED_ATTR, False):
        return
    if client is not None:
        setattr(client, _THEME_APPLIED_ATTR, True)

    ui.dark_mode(True)
    ui.colors(
        primary=NEON["cyan"],
        secondary=NEON["magenta"],
        accent=NEON["lime"],
        dark=COLORS["bg_elevated"],
        dark_page=COLORS["bg"],
        positive="#3DFF9A",
        negative="#FF4D6D",
        info=NEON["cyan"],
        warning=NEON["amber"],
    )
    ui.add_css(_CSS)
