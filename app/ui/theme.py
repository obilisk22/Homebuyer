"""App-wide black / gray + neon cyberpunk theme for NiceGUI."""

from __future__ import annotations

from nicegui import ui

from app.core.map_basemap import FULLSCREEN_ICON_URL

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

_CSS = f"""
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
}}

body,
body.body--dark,
.q-body--dark {{
  background: var(--hb-bg) !important;
  color: var(--hb-text);
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
  color: var(--hb-neon) !important;
  letter-spacing: 0.04em;
  text-shadow: 0 0 12px rgba(0, 229, 255, 0.45);
  font-weight: 600;
}}

.hb-header-title {{
  color: var(--hb-text-muted) !important;
}}

/* Cards / surfaces */
.q-card {{
  background: var(--hb-surface) !important;
  color: var(--hb-text);
  border: 1px solid var(--hb-border);
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(0, 229, 255, 0.04), 0 8px 28px rgba(0, 0, 0, 0.35);
}}

.q-card:hover {{
  border-color: rgba(0, 229, 255, 0.28);
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.1), 0 8px 28px rgba(0, 0, 0, 0.4);
}}

/* Inputs */
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

.q-field__native,
.q-field__input,
.q-field__label,
.q-placeholder {{
  color: var(--hb-text) !important;
}}

.q-field__label {{
  color: var(--hb-text-muted) !important;
}}

.q-field--focused .q-field__label {{
  color: var(--hb-neon) !important;
}}

/* Buttons — soft neon on interactive */
.q-btn--unelevated.bg-primary,
.q-btn.bg-primary {{
  box-shadow: 0 0 14px rgba(0, 229, 255, 0.35);
}}

.q-btn--outline {{
  border-color: var(--hb-neon) !important;
  color: var(--hb-neon) !important;
}}

.q-btn--outline:hover {{
  background: rgba(0, 229, 255, 0.08) !important;
  box-shadow: 0 0 12px rgba(0, 229, 255, 0.2);
}}

.q-btn--flat:hover {{
  background: rgba(0, 229, 255, 0.1) !important;
}}

/* Tabs */
.q-tabs {{
  border-bottom: 1px solid var(--hb-border);
}}

.q-tab {{
  color: var(--hb-text-muted) !important;
  text-transform: none;
  letter-spacing: 0.02em;
}}

.q-tab--active {{
  color: var(--hb-neon) !important;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.35);
}}

.q-tab__indicator {{
  background: var(--hb-neon) !important;
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.55);
  height: 2px;
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
  text-shadow: 0 0 8px rgba(184, 255, 60, 0.35);
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
  padding: 0.85rem 1.1rem;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
}}

.hb-library-card:hover {{
  border-color: rgba(0, 229, 255, 0.55) !important;
  box-shadow: 0 0 22px rgba(0, 229, 255, 0.18), 0 10px 32px rgba(0, 0, 0, 0.45) !important;
  transform: translateY(-1px);
}}

.hb-library-thumb {{
  width: 180px;
  height: 135px;
  min-width: 180px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--hb-border);
  flex-shrink: 0;
}}

.hb-library-thumb--empty {{
  width: 180px;
  height: 135px;
  min-width: 180px;
  border-radius: 8px;
  border: 1px dashed var(--hb-border);
  background: var(--hb-surface-2);
  color: var(--hb-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}

.hb-library-card-body {{
  flex-grow: 1;
  min-width: 0;
}}

.hb-library-price {{
  color: var(--hb-neon) !important;
  font-weight: 700;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
}}

.hb-meta-chip {{
  background: var(--hb-surface-2);
  border: 1px solid var(--hb-border);
  border-radius: 999px;
  padding: 0.15rem 0.65rem;
  font-size: 0.78rem;
  color: var(--hb-text);
  white-space: nowrap;
}}

.hb-meta-chip--quiet {{
  color: var(--hb-text-muted);
  border-color: transparent;
  background: transparent;
  padding: 0.15rem 0.2rem;
}}

.hb-meta-chip--hoa-high {{
  color: var(--hb-amber) !important;
  border-color: rgba(255, 193, 7, 0.55);
  background: rgba(255, 193, 7, 0.12);
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
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}

.hb-photo-thumb {{
  aspect-ratio: 4 / 3;
  width: 100%;
  height: auto !important;
  min-height: 0;
  display: block;
}}

.hb-photo-card .q-card__section {{
  padding: 0.2rem 0.35rem !important;
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
  gap: 0.75rem 1.25rem;
  align-items: center;
  flex-wrap: wrap;
}}

.hb-map-status {{
  min-height: 1.25rem;
  color: var(--hb-text-muted) !important;
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

.homebuy-sv {{
  border: 1px solid var(--hb-border) !important;
  box-shadow: 0 0 24px rgba(0, 229, 255, 0.1), 0 8px 28px rgba(0, 0, 0, 0.45) !important;
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
