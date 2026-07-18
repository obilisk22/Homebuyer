from __future__ import annotations

from urllib.parse import quote_plus

from nicegui import ui

from app.core.db import get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService

# Render Street View at a desktop viewport size, then scale to fill the panel.
# Google's free svembed often paints a phone UI when the iframe is narrow.
_DESKTOP_W = 1920
_DESKTOP_H = 1080


def _has_coords(prop: Property) -> bool:
    return prop.latitude is not None and prop.longitude is not None


def _street_view_embed_url(lat: float, lng: float, heading: float = 0) -> str:
    """Free Google Street View iframe — no API key / Cloud billing."""
    return (
        "https://maps.google.com/maps"
        f"?q=&layer=c&cbll={lat},{lng}"
        f"&cbp=11,{heading:.0f},0,0,0"
        "&hl=en&ie=UTF8&hq=&output=svembed"
    )


def _maps_search_url(query: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def _street_view_open_url(lat: float, lng: float) -> str:
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
            min-height: 420px;
            max-height: min(75vh, 820px);
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


def _ensure_pinned(property_id: int) -> Property | None:
    with get_session() as session:
        return PropertyService(session).ensure_coordinates(property_id)


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id

    with container:
        live = prop
        if not _has_coords(live) and (live.address or "").strip():
            try:
                pinned = _ensure_pinned(property_id)
                if pinned is not None:
                    live = pinned
            except Exception:
                pass

        address = (live.address or "").strip()

        if not _has_coords(live):
            with ui.column().classes("w-full items-start gap-3 q-py-lg"):
                ui.label("Street View needs a map pin").classes("text-subtitle1")
                ui.label(
                    "Open the Map tab to geocode this address, then return here."
                ).classes("text-body2 text-grey-7")
                if address:
                    ui.button("Open in Google Maps").props(
                        f'outline color=primary icon=map '
                        f'href="{_maps_search_url(address)}" target=_blank'
                    )
            return

        lat = float(live.latitude)  # type: ignore[arg-type]
        lng = float(live.longitude)  # type: ignore[arg-type]
        query = address or f"{lat},{lng}"

        _panorama(_street_view_embed_url(lat, lng))

        with ui.row().classes("w-full justify-start items-center gap-2 q-mt-md flex-wrap"):
            ui.button("Open in Google Maps").props(
                f'outline dense color=primary icon=map href="{_maps_search_url(query)}" target=_blank'
            )
            ui.button("Open Street View").props(
                f'unelevated dense color=primary icon=streetview '
                f'href="{_street_view_open_url(lat, lng)}" target=_blank'
            )


MODULE = ModuleSpec(id="street_view", title="Street View", order=30, render=render)
