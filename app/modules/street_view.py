"""Street View helpers — free Google svembed (no Maps Embed API / billing).

Used from the Map tab (map on top, Street View below). Not a standalone module tab.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from nicegui import ui

from app.core.db import get_session
from app.core.models import Property
from app.core.property_service import PropertyService

# Render Street View at a desktop viewport size, then scale to fill the panel.
# Google's free svembed often paints a phone UI when the iframe is narrow.
_DESKTOP_W = 1920
_DESKTOP_H = 1080


def _has_coords(prop: Property) -> bool:
    return prop.latitude is not None and prop.longitude is not None


def street_view_embed_url(lat: float, lng: float, heading: float = 0) -> str:
    """Free Google Street View iframe — no API key / Cloud billing."""
    return (
        "https://maps.google.com/maps"
        f"?q=&layer=c&cbll={lat},{lng}"
        f"&cbp=11,{heading:.0f},0,0,0"
        "&hl=en&ie=UTF8&hq=&output=svembed"
    )


def maps_search_url(query: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def street_view_open_url(lat: float, lng: float) -> str:
    return (
        "https://www.google.com/maps/@?api=1&map_action=pano"
        f"&viewpoint={lat},{lng}"
    )


def earth_open_url(lat: float, lng: float) -> str:
    """Google Earth web deep link for a pin (no API key)."""
    return (
        f"https://earth.google.com/web/@{lat},{lng},100a,1000d,35y,0h,0t,0r"
    )


def _panorama(src: str) -> None:
    # Sizing lives on .homebuy-sv in theme.py (16:9 + max-height; no min-height shell).
    ui.html(
        f"""
        <div class="homebuy-sv">
          <iframe
            src="{src}"
            title="Street View"
            allowfullscreen
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"
            style="
              position: absolute;
              top: 0; left: 0;
              width: {_DESKTOP_W}px;
              height: {_DESKTOP_H}px;
              border: 0;
              transform-origin: top left;
              transform: scale(calc(100cqw / {_DESKTOP_W}));
            "
          ></iframe>
        </div>
        """,
        sanitize=False,
    )


def ensure_pinned(property_id: int) -> Property | None:
    with get_session() as session:
        return PropertyService(session).ensure_coordinates(property_id)


def render_street_view(prop: Property, container: ui.element | None = None) -> None:
    """Render Street View panel (optionally into an existing container)."""
    property_id = prop.id

    def body() -> None:
        live = prop
        if not _has_coords(live) and (live.address or "").strip():
            try:
                pinned = ensure_pinned(property_id)
                if pinned is not None:
                    live = pinned
            except Exception:
                pass

        address = (live.address or "").strip()

        with ui.expansion("Street View", icon="streetview", value=True).classes(
            "w-full q-mt-sm hb-sv-panel"
        ).props("dense"):
            if not _has_coords(live):
                with ui.column().classes("w-full items-stretch gap-1 q-py-none"):
                    ui.label("Pin the map to load Street View.").classes("hb-page-hint")
                    if address:
                        ui.button("Open in Google Maps").props(
                            f'unelevated dense color=dark icon=map '
                            f'href="{maps_search_url(address)}" target=_blank'
                        )
                return

            lat = float(live.latitude)  # type: ignore[arg-type]
            lng = float(live.longitude)  # type: ignore[arg-type]
            query = address or f"{lat},{lng}"

            _panorama(street_view_embed_url(lat, lng))

            with ui.row().classes(
                "w-full justify-start items-center gap-2 q-mt-xs flex-wrap hb-sv-actions"
            ):
                ui.button("Open in Google Maps").props(
                    f'unelevated dense color=dark icon=map href="{maps_search_url(query)}" target=_blank'
                )
                ui.button("Open Street View").props(
                    f'unelevated dense color=dark icon=streetview '
                    f'href="{street_view_open_url(lat, lng)}" target=_blank'
                ).classes("hb-btn-cta")
                ui.button("Open in Google Earth").props(
                    f'unelevated dense color=dark icon=public '
                    f'href="{earth_open_url(lat, lng)}" target=_blank'
                )

    if container is None:
        body()
    else:
        with container:
            body()
