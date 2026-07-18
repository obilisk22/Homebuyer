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


def _panorama(src: str) -> None:
    ui.html(
        f"""
        <div class="homebuy-sv" style="
            container-type: inline-size;
            width: 100%;
            aspect-ratio: 16 / 9;
            min-height: 280px;
            max-height: min(50vh, 560px);
            overflow: hidden;
            border-radius: 12px;
            background: #111;
            position: relative;
            box-shadow: 0 0 24px rgba(0, 229, 255, 0.1), 0 8px 28px rgba(0, 0, 0, 0.45);
            border: 1px solid #2A3340;
        ">
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

        with ui.expansion("Street View", icon="streetview", value=True).classes("w-full q-mt-md"):
            if not _has_coords(live):
                with ui.column().classes("w-full items-stretch gap-3 q-py-md"):
                    ui.label("Street View needs a map pin").classes(
                        "hb-empty-state w-full"
                    )
                    ui.label(
                        "Geocode the address above, then Street View will appear here."
                    ).classes("hb-page-hint")
                    if address:
                        ui.button("Open in Google Maps").props(
                            f'outline color=primary dense icon=map '
                            f'href="{maps_search_url(address)}" target=_blank'
                        )
                return

            lat = float(live.latitude)  # type: ignore[arg-type]
            lng = float(live.longitude)  # type: ignore[arg-type]
            query = address or f"{lat},{lng}"

            _panorama(street_view_embed_url(lat, lng))

            with ui.row().classes("w-full justify-start items-center gap-2 q-mt-sm flex-wrap"):
                ui.button("Open in Google Maps").props(
                    f'outline dense color=primary icon=map href="{maps_search_url(query)}" target=_blank'
                )
                ui.button("Open Street View").props(
                    f'unelevated dense color=primary icon=streetview '
                    f'href="{street_view_open_url(lat, lng)}" target=_blank'
                )

    if container is None:
        body()
    else:
        with container:
            body()
