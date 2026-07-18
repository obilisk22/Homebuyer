"""Map tab: Leaflet pin + overlay toggles + Street View below."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from app.core.census_acs import (
    ACS_LAYERS,
    CensusKeyMissing,
    build_acs_geojson,
    has_census_key,
)
from app.core.crime_density import CRIME_LEGEND, build_crime_density_geojson
from app.core.crime_socrata import DEFAULT_DAYS as CRIME_DAYS, crime_supported, fetch_crime_near_pin
from app.core.db import get_session
from app.core.fema_flood import flood_wms_layer_args
from app.core.map_basemap import apply_dark_basemap, leaflet_map_kwargs
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService
from app.core.zoning_gis import ZONING_LEGEND, build_zoning_geojson, zoning_supported
from app.modules.street_view import render_street_view

_STYLE_JS = (
    "function(f){var c=(f.properties&&f.properties.fillColor)||'#2A3340';"
    "return {fillColor:c,color:'#8B96A8',weight:1,fillOpacity:0.45,opacity:0.85};}"
)
_POPUP_JS = (
    "function(layer){var f=layer.feature;if(f&&f.properties&&f.properties.popup)"
    "{layer.bindPopup(f.properties.popup);}}"
)

_ACS_LAYER_LABELS = {
    "income": "Income",
    "home_value": "Home value",
    "median_age": "Med. age",
    "avg_kids": "Kids / HH",
    "owner_occ": "Owner-occ",
    "year_built": "Year built",
    "gross_rent": "Rent",
    "bachelors": "Bachelor's+",
}

_ACS_ORDER = (
    "income",
    "home_value",
    "median_age",
    "avg_kids",
    "owner_occ",
    "year_built",
    "gross_rent",
    "bachelors",
)


def render(prop: Property, container: ui.element) -> None:
    with container:
        layer_btns: dict[str, Any] = {}
        layer_on: dict[str, bool] = {}

        def set_layer_on(key: str, on: bool) -> None:
            """Sync button glow: --on class only when the layer is enabled."""
            layer_on[key] = bool(on)
            btn = layer_btns[key]
            # Rebuild class string so add/remove cannot drift out of sync with state.
            kept = [
                c
                for c in list(btn.classes)
                if c not in ("hb-map-layer-btn", "hb-map-layer-btn--on")
            ]
            parts = kept + ["hb-map-layer-btn"]
            if layer_on[key]:
                parts.append("hb-map-layer-btn--on")
            btn.classes(replace=" ".join(parts))

        def make_layer_btn(key: str, label: str) -> None:
            btn = (
                ui.button(label)
                .props("unelevated dense no-caps color=dark")
                .classes("hb-map-layer-btn")
            )
            layer_btns[key] = btn
            layer_on[key] = False

        ui.label("Map").classes("hb-page-title")
        ui.label("Overlays and Street View for this pin.").classes("hb-page-hint")

        with ui.row().classes("w-full hb-map-layers"):
            make_layer_btn("flood", "Flood")
            make_layer_btn("zoning", "Zoning")
            for layer_id in _ACS_ORDER:
                make_layer_btn(layer_id, _ACS_LAYER_LABELS[layer_id])
            make_layer_btn("crime", "Crime")

        status = ui.label("").classes("hb-page-meta hb-map-status")
        legend_box = ui.column().classes("w-full hb-map-legend")
        map_box = ui.column().classes("w-full hb-map-box")

        with ui.expansion("Pin tools", icon="tune").classes("w-full q-mt-md"):
            with ui.row().classes("w-full items-end gap-4 flex-wrap"):
                lat_input = (
                    ui.number("Latitude", value=prop.latitude, format="%.6f")
                    .classes("w-40")
                    .props("dense outlined stack-label")
                )
                lng_input = (
                    ui.number("Longitude", value=prop.longitude, format="%.6f")
                    .classes("w-40")
                    .props("dense outlined stack-label")
                )

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

                ui.button("Save pin", on_click=save_coords).props(
                    "unelevated color=primary dense"
                )

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

                ui.button("Re-geocode from address", on_click=regeocode).props(
                    "outline dense"
                )

        sv_box = ui.column().classes("w-full")

        state: dict[str, Any] = {
            "map": None,
            "flood": None,
            "zoning": None,
            "acs_layers": {lid: None for lid in _ACS_ORDER},
            "show_acs_legend": {lid: False for lid in _ACS_ORDER},
            "show_zoning_legend": False,
            "crime": None,
            "show_crime_legend": False,
            "city": prop.city or "",
            "suppress_toggle": False,
        }

        def _legend_swatches(title: str, items: list[tuple[str, str]]) -> None:
            ui.label(title).classes("hb-page-meta")
            with ui.row().classes("gap-3 flex-wrap items-center"):
                for label, color in items:
                    with ui.row().classes("items-center gap-1"):
                        ui.element("div").style(
                            f"width:14px;height:14px;border-radius:2px;background:{color};"
                            "border:1px solid #2A3340;"
                        )
                        ui.label(label).classes("hb-page-meta")

        def _render_legends() -> None:
            legend_box.clear()
            any_acs = any(state["show_acs_legend"].values())
            show_zoning = bool(state.get("show_zoning_legend"))
            show_crime = bool(state.get("show_crime_legend"))
            if not any_acs and not show_zoning and not show_crime:
                return
            with legend_box:
                if show_zoning:
                    _legend_swatches("Zoning (near pin)", ZONING_LEGEND)
                for lid in _ACS_ORDER:
                    if state["show_acs_legend"].get(lid):
                        cfg = ACS_LAYERS[lid]
                        _legend_swatches(cfg.legend_title, cfg.legend)
                if show_crime:
                    _legend_swatches("Crime incidents per hex (near pin)", CRIME_LEGEND)

        def _apply_choropleth_style(layer: Any) -> None:
            m = state["map"]
            if m is None:
                return
            m.run_layer_method(layer.id, ":setStyle", _STYLE_JS)
            m.run_layer_method(layer.id, ":eachLayer", _POPUP_JS)

        def _clear_acs_layer(layer_id: str) -> None:
            m = state.get("map")
            layer = state["acs_layers"].get(layer_id)
            if m is not None and layer is not None:
                try:
                    m.remove_layer(layer)
                except (ValueError, RuntimeError):
                    pass
            state["acs_layers"][layer_id] = None
            state["show_acs_legend"][layer_id] = False

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

        def toggle_zoning(enabled: bool) -> None:
            if state["suppress_toggle"]:
                return
            m = state.get("map")
            if m is None:
                return
            if state["zoning"] is not None:
                try:
                    m.remove_layer(state["zoning"])
                except (ValueError, RuntimeError):
                    pass
                state["zoning"] = None
            state["show_zoning_legend"] = False
            _render_legends()
            if not enabled:
                return

            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            if fresh is None or fresh.latitude is None or fresh.longitude is None:
                state["suppress_toggle"] = True
                set_layer_on("zoning", False)
                state["suppress_toggle"] = False
                status.set_text("Zoning layer needs a map pin.")
                return

            city = fresh.city or state.get("city") or ""
            plat = float(fresh.latitude)
            plng = float(fresh.longitude)
            if not zoning_supported(city, plat, plng):
                state["suppress_toggle"] = True
                set_layer_on("zoning", False)
                state["suppress_toggle"] = False
                status.set_text(
                    "No zoning layer for this area — v1 covers City of Los Angeles, "
                    "Santa Monica, and unincorporated LA County."
                )
                ui.notify("Zoning overlay not available for this area", type="info")
                return

            status.set_text("Loading…")
            try:
                geo = build_zoning_geojson(city, plat, plng)
            except Exception as exc:  # noqa: BLE001
                state["suppress_toggle"] = True
                set_layer_on("zoning", False)
                state["suppress_toggle"] = False
                status.set_text(f"Zoning layer failed: {exc}")
                ui.notify(f"Zoning layer failed: {exc}", type="negative")
                return

            fc = {"type": "FeatureCollection", "features": geo.get("features") or []}
            layer = m.generic_layer(name="geoJSON", args=[fc, {}])
            state["zoning"] = layer
            _apply_choropleth_style(layer)
            state["show_zoning_legend"] = bool(fc["features"])
            _render_legends()
            status.set_text(str((geo.get("meta") or {}).get("message") or "Zoning loaded"))

        def make_toggle_acs(layer_id: str):
            cfg = ACS_LAYERS[layer_id]

            def toggle_acs(enabled: bool) -> None:
                if state["suppress_toggle"]:
                    return
                m = state.get("map")
                if m is None:
                    return
                _clear_acs_layer(layer_id)
                _render_legends()
                if not enabled:
                    return
                if not has_census_key():
                    state["suppress_toggle"] = True
                    set_layer_on(layer_id, False)
                    state["suppress_toggle"] = False
                    status.set_text(
                        "ACS layers need CENSUS_API_KEY — add it to .env "
                        "(free signup: https://api.census.gov/data/key_signup.html), then restart."
                    )
                    ui.notify("Add CENSUS_API_KEY to enable ACS layers", type="warning")
                    return
                with get_session() as session:
                    fresh = PropertyService(session).get_property(prop.id)
                if fresh is None or fresh.latitude is None or fresh.longitude is None:
                    state["suppress_toggle"] = True
                    set_layer_on(layer_id, False)
                    state["suppress_toggle"] = False
                    status.set_text(f"{cfg.popup_metric} layer needs a map pin.")
                    return
                status.set_text("Loading…")
                try:
                    geo = build_acs_geojson(
                        layer_id, float(fresh.latitude), float(fresh.longitude)
                    )
                except CensusKeyMissing as exc:
                    state["suppress_toggle"] = True
                    set_layer_on(layer_id, False)
                    state["suppress_toggle"] = False
                    status.set_text(str(exc))
                    ui.notify(str(exc), type="warning")
                    return
                except Exception as exc:  # noqa: BLE001
                    state["suppress_toggle"] = True
                    set_layer_on(layer_id, False)
                    state["suppress_toggle"] = False
                    status.set_text(f"{cfg.popup_metric} failed: {exc}")
                    ui.notify(f"{cfg.popup_metric} failed: {exc}", type="negative")
                    return

                fc = {"type": "FeatureCollection", "features": geo.get("features") or []}
                layer = m.generic_layer(name="geoJSON", args=[fc, {}])
                state["acs_layers"][layer_id] = layer
                _apply_choropleth_style(layer)
                state["show_acs_legend"][layer_id] = True
                _render_legends()
                n = len(fc["features"])
                year = geo.get("meta", {}).get("year", "")
                status.set_text(
                    f"{cfg.popup_metric}: {n} tracts near pin "
                    f"(ACS {cfg.variable_label}, {year})"
                )

            return toggle_acs

        def toggle_crime(enabled: bool) -> None:
            if state["suppress_toggle"]:
                return
            m = state.get("map")
            if m is None:
                return
            if state["crime"] is not None:
                try:
                    m.remove_layer(state["crime"])
                except (ValueError, RuntimeError):
                    pass
                state["crime"] = None
            state["show_crime_legend"] = False
            _render_legends()
            if not enabled:
                return

            with get_session() as session:
                fresh = PropertyService(session).get_property(prop.id)
            if fresh is None or fresh.latitude is None or fresh.longitude is None:
                state["suppress_toggle"] = True
                set_layer_on("crime", False)
                state["suppress_toggle"] = False
                status.set_text("Crime layer needs a map pin.")
                return

            city = fresh.city or state.get("city") or ""
            plat = float(fresh.latitude)
            plng = float(fresh.longitude)
            if not crime_supported(city, plat, plng):
                state["suppress_toggle"] = True
                set_layer_on("crime", False)
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
                set_layer_on("crime", False)
                state["suppress_toggle"] = False
                status.set_text(f"Crime layer failed: {exc}")
                ui.notify(f"Crime layer failed: {exc}", type="negative")
                return

            points = result.get("points") or []
            geo = build_crime_density_geojson(points, days=CRIME_DAYS)
            fc = {"type": "FeatureCollection", "features": geo.get("features") or []}
            layer = m.generic_layer(name="geoJSON", args=[fc, {}])
            state["crime"] = layer
            _apply_choropleth_style(layer)
            state["show_crime_legend"] = True
            _render_legends()
            meta = geo.get("meta") or {}
            incidents = int(meta.get("incidents") or 0)
            cells = int(meta.get("cells") or 0)
            if incidents == 0:
                status.set_text(
                    str(result.get("message") or "Crime: no incidents near pin")
                )
            else:
                status.set_text(
                    f"Crime: {incidents} incidents in {cells} cells near pin"
                )

        def wire_layer(key: str, handler: Any) -> None:
            handlers[key] = handler

            def _click() -> None:
                if state["suppress_toggle"]:
                    return
                turning_on = not layer_on[key]
                if turning_on:
                    # Exclusive overlays: only one layer active at a time.
                    for other, other_handler in handlers.items():
                        if other == key or not layer_on[other]:
                            continue
                        set_layer_on(other, False)
                        other_handler(False)
                    set_layer_on(key, True)
                    handler(True)
                else:
                    set_layer_on(key, False)
                    handler(False)

            layer_btns[key].on_click(_click)

        handlers: dict[str, Any] = {}
        wire_layer("flood", toggle_flood)
        wire_layer("zoning", toggle_zoning)
        for lid in _ACS_ORDER:
            wire_layer(lid, make_toggle_acs(lid))
        wire_layer("crime", toggle_crime)

        if not zoning_supported(prop.city, prop.latitude, prop.longitude):
            layer_btns["zoning"].props("disable")
            layer_btns["zoning"].tooltip(
                "Zoning overlay: City of Los Angeles, Santa Monica, "
                "unincorporated LA County"
            )

        if not crime_supported(prop.city, prop.latitude, prop.longitude):
            layer_btns["crime"].props("disable")
            layer_btns["crime"].tooltip(
                "Crime overlay available for Los Angeles County and Seattle"
            )

        def redraw(initial: Property | None = None) -> None:
            if initial is None:
                with get_session() as session:
                    fresh = PropertyService(session).get_property(prop.id)
            else:
                fresh = initial
            lat = fresh.latitude if fresh else None
            lng = fresh.longitude if fresh else None
            state["city"] = (fresh.city if fresh else prop.city) or ""

            if lat is not None and lng is not None:
                lat_input.value = lat
                lng_input.value = lng

            state["suppress_toggle"] = True
            for key in layer_btns:
                set_layer_on(key, False)
            state["suppress_toggle"] = False
            state["flood"] = None
            state["zoning"] = None
            state["show_zoning_legend"] = False
            state["acs_layers"] = {lid: None for lid in _ACS_ORDER}
            state["show_acs_legend"] = {lid: False for lid in _ACS_ORDER}
            state["crime"] = None
            state["show_crime_legend"] = False
            state["map"] = None
            _render_legends()

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
                        "hb-empty-state w-full q-mt-sm"
                    )

            sv_box.clear()
            render_street_view(fresh or prop, sv_box)

        def auto_geocode_if_needed() -> None:
            fresh = prop
            if fresh.latitude is not None and fresh.longitude is not None:
                status.set_text("")
                redraw(fresh)
                return
            if not (fresh.address or "").strip():
                status.set_text("No address on file — add one to auto-pin the map.")
                redraw(fresh)
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
