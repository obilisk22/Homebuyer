"""Map tab: Leaflet pin + overlay toggles + Street View below."""

from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from app.core.census_acs import (
    CensusKeyMissing,
    INCOME_LEGEND,
    build_income_geojson,
    has_census_key,
)
from app.core.crime_socrata import crime_supported, fetch_crime_near_pin
from app.core.db import get_session
from app.core.fema_flood import flood_wms_layer_args
from app.core.map_basemap import apply_dark_basemap, leaflet_map_kwargs
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService
from app.modules.street_view import render_street_view

_STYLE_JS = (
    "function(f){var c=(f.properties&&f.properties.fillColor)||'#2A3340';"
    "return {fillColor:c,color:'#8B96A8',weight:1,fillOpacity:0.45,opacity:0.85};}"
)
_POPUP_JS = (
    "function(layer){var f=layer.feature;if(f&&f.properties&&f.properties.popup)"
    "{layer.bindPopup(f.properties.popup);}}"
)


def render(prop: Property, container: ui.element) -> None:
    with container:
        with ui.row().classes("w-full hb-map-layers q-mt-sm"):
            flood_cb = ui.checkbox("Flood (FEMA)", value=False)
            income_cb = ui.checkbox("Median income (ACS)", value=False)
            crime_cb = ui.checkbox("Crime near pin", value=False)

        status = ui.label("").classes("text-caption hb-map-status q-mt-xs")
        legend_box = ui.column().classes("w-full q-mt-xs")
        map_box = ui.column().classes("w-full q-mt-sm")

        with ui.expansion("Pin tools", icon="tune").classes("w-full q-mt-md"):
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

        sv_box = ui.column().classes("w-full")

        state: dict[str, Any] = {
            "map": None,
            "flood": None,
            "income": None,
            "crime": [],
            "city": prop.city or "",
            "suppress_toggle": False,
        }

        def _render_legend(show_income: bool) -> None:
            legend_box.clear()
            if not show_income:
                return
            with legend_box:
                ui.label("Median household income (ACS tracts)").classes("text-caption text-grey-7")
                with ui.row().classes("gap-3 flex-wrap items-center"):
                    for label, color in INCOME_LEGEND:
                        with ui.row().classes("items-center gap-1"):
                            ui.element("div").style(
                                f"width:14px;height:14px;border-radius:2px;background:{color};"
                                "border:1px solid #2A3340;"
                            )
                            ui.label(label).classes("text-caption")

        def _apply_income_style(layer: Any) -> None:
            m = state["map"]
            if m is None:
                return
            m.run_layer_method(layer.id, ":setStyle", _STYLE_JS)
            m.run_layer_method(layer.id, ":eachLayer", _POPUP_JS)

        def toggle_flood(enabled: bool) -> None:
            if state["suppress_toggle"]:
                return
            m = state.get("map")
            if m is None:
                return
            if state["flood"] is not None:
                try:
                    m.remove_layer(state["flood"])
                except (ValueError, RuntimeError):
                    pass
                state["flood"] = None
            if not enabled:
                return
            url, options = flood_wms_layer_args()
            state["flood"] = m.wms_layer(url_template=url, options=options)
            status.set_text("Flood zones: FEMA NFHL WMS")

        def toggle_income(enabled: bool) -> None:
            if state["suppress_toggle"]:
                return
            m = state.get("map")
            if m is None:
                return
            if state["income"] is not None:
                try:
                    m.remove_layer(state["income"])
                except (ValueError, RuntimeError):
                    pass
                state["income"] = None
            _render_legend(False)
            if not enabled:
                return
            if not has_census_key():
                state["suppress_toggle"] = True
                income_cb.value = False
                state["suppress_toggle"] = False
                status.set_text(
                    "Income layer needs CENSUS_API_KEY — add it to .env "
                    "(free signup: https://api.census.gov/data/key_signup.html), then restart."
                )
                ui.notify("Add CENSUS_API_KEY to enable income layer", type="warning")
                return
            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            if fresh is None or fresh.latitude is None or fresh.longitude is None:
                state["suppress_toggle"] = True
                income_cb.value = False
                state["suppress_toggle"] = False
                status.set_text("Income layer needs a map pin.")
                return
            status.set_text("Loading…")
            try:
                geo = build_income_geojson(float(fresh.latitude), float(fresh.longitude))
            except CensusKeyMissing as exc:
                state["suppress_toggle"] = True
                income_cb.value = False
                state["suppress_toggle"] = False
                status.set_text(str(exc))
                ui.notify(str(exc), type="warning")
                return
            except Exception as exc:  # noqa: BLE001 — surface API errors in UI
                state["suppress_toggle"] = True
                income_cb.value = False
                state["suppress_toggle"] = False
                status.set_text(f"Income layer failed: {exc}")
                ui.notify(f"Income layer failed: {exc}", type="negative")
                return

            fc = {"type": "FeatureCollection", "features": geo.get("features") or []}
            layer = m.generic_layer(name="geoJSON", args=[fc, {}])
            state["income"] = layer
            _apply_income_style(layer)
            _render_legend(True)
            n = len(fc["features"])
            year = geo.get("meta", {}).get("year", "")
            status.set_text(f"Income: {n} tracts near pin (ACS B19013, {year})")

        def toggle_crime(enabled: bool) -> None:
            if state["suppress_toggle"]:
                return
            m = state.get("map")
            if m is None:
                return
            for layer in state["crime"]:
                try:
                    m.remove_layer(layer)
                except (ValueError, RuntimeError):
                    pass
            state["crime"] = []
            if not enabled:
                return

            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            if fresh is None or fresh.latitude is None or fresh.longitude is None:
                state["suppress_toggle"] = True
                crime_cb.value = False
                state["suppress_toggle"] = False
                status.set_text("Crime layer needs a map pin.")
                return

            city = fresh.city or state.get("city") or ""
            plat = float(fresh.latitude)
            plng = float(fresh.longitude)
            if not crime_supported(city, plat, plng):
                state["suppress_toggle"] = True
                crime_cb.value = False
                state["suppress_toggle"] = False
                status.set_text(
                    "No crime layer for this area — open data covers "
                    "Los Angeles County and Seattle."
                )
                ui.notify("Crime overlay not available for this area", type="info")
                return

            status.set_text("Loading…")
            try:
                result = fetch_crime_near_pin(city, plat, plng)
            except Exception as exc:  # noqa: BLE001
                state["suppress_toggle"] = True
                crime_cb.value = False
                state["suppress_toggle"] = False
                status.set_text(f"Crime layer failed: {exc}")
                ui.notify(f"Crime layer failed: {exc}", type="negative")
                return

            points = result.get("points") or []
            layers = []
            for pt in points[:200]:
                try:
                    plat = float(pt["lat"])
                    plng = float(pt["lng"])
                except (KeyError, TypeError, ValueError):
                    continue
                marker = m.generic_layer(
                    name="circleMarker",
                    args=[
                        [plat, plng],
                        {
                            "radius": 5,
                            "color": "#FF2BD6",
                            "fillColor": "#FF2BD6",
                            "fillOpacity": 0.7,
                            "weight": 1,
                        },
                    ],
                )
                desc = str(pt.get("desc") or "Incident")
                when = str(pt.get("when") or "")
                popup = json.dumps(f"{desc}<br>{when}")
                m.run_layer_method(marker.id, ":bindPopup", popup)
                layers.append(marker)
            state["crime"] = layers
            status.set_text(str(result.get("message") or f"{len(layers)} crime points"))

        flood_cb.on_value_change(lambda e: toggle_flood(bool(e.value)))
        income_cb.on_value_change(lambda e: toggle_income(bool(e.value)))
        crime_cb.on_value_change(lambda e: toggle_crime(bool(e.value)))

        if not crime_supported(prop.city, prop.latitude, prop.longitude):
            crime_cb.props("disable")
            crime_cb.tooltip(
                "Crime overlay available for Los Angeles County and Seattle"
            )

        def redraw() -> None:
            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            lat = fresh.latitude if fresh else None
            lng = fresh.longitude if fresh else None
            state["city"] = (fresh.city if fresh else prop.city) or ""

            if lat is not None and lng is not None:
                lat_input.value = lat
                lng_input.value = lng

            state["suppress_toggle"] = True
            flood_cb.value = False
            income_cb.value = False
            crime_cb.value = False
            state["suppress_toggle"] = False
            state["flood"] = None
            state["income"] = None
            state["crime"] = []
            state["map"] = None
            _render_legend(False)

            map_box.clear()
            with map_box:
                map_kwargs = leaflet_map_kwargs()
                if lat is not None and lng is not None:
                    m = ui.leaflet(center=(lat, lng), zoom=14, **map_kwargs).classes("hb-map")
                    apply_dark_basemap(m)
                    m.marker(latlng=(lat, lng))
                    state["map"] = m
                else:
                    m = ui.leaflet(center=(39.8283, -98.5795), zoom=4, **map_kwargs).classes(
                        "hb-map"
                    )
                    apply_dark_basemap(m)
                    ui.label("No pin yet — geocode the address or enter coordinates.").classes(
                        "text-caption text-grey-7 q-mt-sm"
                    )

            sv_box.clear()
            with get_session() as session:
                live = PropertyService(session).get_property(prop.id) or prop
            render_street_view(live, sv_box)

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
