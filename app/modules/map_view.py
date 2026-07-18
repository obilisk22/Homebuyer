from __future__ import annotations

from nicegui import ui

from app.core.db import get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService


def render(prop: Property, container: ui.element) -> None:
    with container:
        ui.label("Map").classes("text-h6")
        ui.label(
            "The pin is set automatically from the property address. "
            "You can override coordinates manually if needed."
        ).classes("text-caption text-grey-7")

        status = ui.label("").classes("text-caption text-grey-7 q-mt-sm")

        with ui.expansion("Manual coordinates (advanced)", icon="tune").classes("w-full q-mt-md"):
            with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                lat_input = ui.number("Latitude", value=prop.latitude, format="%.6f").classes("w-40")
                lng_input = ui.number("Longitude", value=prop.longitude, format="%.6f").classes("w-40")

                def save_coords() -> None:
                    lat = lat_input.value
                    lng = lng_input.value
                    missing = lat is None or lng is None
                    with get_session() as session:
                        PropertyService(session).update_property(
                            prop.id,
                            latitude=float(lat) if lat is not None else None,
                            longitude=float(lng) if lng is not None else None,
                            clear_coords=missing,
                        )
                    ui.notify("Coordinates saved", type="positive")
                    redraw()

                ui.button("Save pin", on_click=save_coords).props("color=primary")

                def regeocode() -> None:
                    try:
                        with get_session() as session:
                            fresh = PropertyService(session).ensure_coordinates(prop.id, force=True)
                        lat_input.value = fresh.latitude
                        lng_input.value = fresh.longitude
                        ui.notify("Re-geocoded from address", type="positive")
                        redraw()
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")

                ui.button("Re-geocode from address", on_click=regeocode).props("outline")

        map_box = ui.column().classes("w-full q-mt-md")

        def redraw() -> None:
            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            lat = fresh.latitude if fresh else None
            lng = fresh.longitude if fresh else None
            address = fresh.address if fresh else prop.address

            if lat is not None and lng is not None:
                lat_input.value = lat
                lng_input.value = lng

            map_box.clear()
            with map_box:
                if lat is not None and lng is not None:
                    m = ui.leaflet(center=(lat, lng), zoom=16).classes("w-full h-96 rounded-borders")
                    m.marker(latlng=(lat, lng))
                    ui.label(f"Pinned: {address}").classes("text-caption q-mt-sm")
                else:
                    ui.leaflet(center=(39.8283, -98.5795), zoom=4).classes(
                        "w-full h-96 rounded-borders"
                    )
                    ui.label("No pin yet — geocode the address or enter coordinates.").classes(
                        "text-caption text-grey-7 q-mt-sm"
                    )

        def auto_geocode_if_needed() -> None:
            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            if fresh is None:
                return
            if fresh.latitude is not None and fresh.longitude is not None:
                status.set_text("")
                redraw()
                return
            if not (fresh.address or "").strip():
                status.set_text("No address on file — add one to auto-pin the map.")
                redraw()
                return

            status.set_text("Looking up coordinates from address…")
            try:
                with get_session() as session:
                    PropertyService(session).ensure_coordinates(prop.id)
                status.set_text("")
                ui.notify("Pinned from address", type="positive")
            except ValueError as exc:
                status.set_text(str(exc))
                ui.notify(str(exc), type="warning")
            redraw()

        auto_geocode_if_needed()


MODULE = ModuleSpec(id="map_view", title="Map", order=20, render=render)
