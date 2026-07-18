from __future__ import annotations

from nicegui import ui

from app.core.db import get_session
from app.core.module_registry import get_modules
from app.core.property_service import PropertyService, resolve_library_thumbnail
from app.ui.theme import apply_theme


def page_header(title: str) -> None:
    apply_theme()
    with ui.header().classes("hb-header items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "flat round color=primary"
            )
            ui.label("Homebuy").classes("text-h6 hb-brand")
            ui.label(title).classes("text-subtitle1 hb-header-title")


def _format_price(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.0f}"


def _format_beds_baths(beds: float | None, baths: float | None) -> str:
    parts: list[str] = []
    if beds is not None:
        parts.append(f"{beds:g} bd")
    if baths is not None:
        parts.append(f"{baths:g} ba")
    return " · ".join(parts)


def _parse_filter_float(raw: str | float | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("$", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@ui.page("/")
def library_page() -> None:
    page_header("Library")

    with ui.column().classes("w-full max-w-5xl mx-auto q-pa-md gap-4"):
        ui.label("Your homes").classes("text-h5")
        ui.label("Paste a Zillow listing link — address, photos, and details import automatically.").classes(
            "text-body2 text-grey-6"
        )

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full gap-4 items-end flex-wrap"):
                url_input = ui.input(
                    "Zillow URL",
                    placeholder="https://www.zillow.com/homedetails/...",
                ).classes("flex-grow min-w-64")

                def add_home() -> None:
                    try:
                        ui.notify("Saving home and importing listing…", type="ongoing", timeout=0)
                        with get_session() as session:
                            prop, imported = PropertyService(session).add_from_zillow(
                                url_input.value or "",
                                import_photos=True,
                            )
                            new_id = prop.id
                        ui.notify(
                            f"Home saved — imported {imported} photos",
                            type="positive",
                        )
                        ui.navigate.to(f"/property/{new_id}")
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                    except Exception as exc:  # noqa: BLE001
                        ui.notify(f"Failed: {exc}", type="negative")

                ui.button("Add home", on_click=add_home).props("color=primary")

        with ui.card().classes("w-full"):
            with ui.row().classes("w-full gap-3 items-end flex-wrap"):
                search_input = ui.input(
                    "Search",
                    placeholder="Address or city",
                ).classes("flex-grow min-w-48")
                min_price_input = ui.input("Min price", placeholder="e.g. 500000").classes("w-36")
                max_price_input = ui.input("Max price", placeholder="e.g. 1200000").classes("w-36")
                min_beds_input = ui.input("Min beds", placeholder="e.g. 3").classes("w-28")
                ui.button("Filter", on_click=lambda: refresh()).props("outline color=primary")
                ui.button(
                    "Clear",
                    on_click=lambda: (
                        search_input.set_value(""),
                        min_price_input.set_value(""),
                        max_price_input.set_value(""),
                        min_beds_input.set_value(""),
                        refresh(),
                    ),
                ).props("flat")

            search_input.on("keydown.enter", lambda: refresh())

        list_box = ui.column().classes("w-full gap-3")

        def refresh() -> None:
            list_box.clear()
            with get_session() as session:
                props = PropertyService(session).list_properties(
                    search=search_input.value or "",
                    min_price=_parse_filter_float(min_price_input.value),
                    max_price=_parse_filter_float(max_price_input.value),
                    min_beds=_parse_filter_float(min_beds_input.value),
                )
            with list_box:
                if not props:
                    ui.label("No homes match — adjust filters or add a Zillow link above.").classes(
                        "text-grey-6"
                    )
                    return
                for prop in props:
                    price_text = _format_price(prop.list_price) or "Price —"
                    beds_baths = _format_beds_baths(prop.beds, prop.baths) or "Beds/baths —"
                    place_bits = [b for b in (prop.city, prop.state) if b]
                    place = ", ".join(place_bits) or "City —"
                    thumb = None
                    thumb_photo = resolve_library_thumbnail(prop)
                    if thumb_photo is not None:
                        thumb = f"/uploads/{thumb_photo.path}"

                    with ui.card().classes("w-full"):
                        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                            with ui.row().classes("items-center gap-4 flex-grow"):
                                if thumb:
                                    ui.image(thumb).classes("rounded").style(
                                        "width: 88px; height: 66px; object-fit: cover;"
                                    )
                                with ui.column().classes("gap-0"):
                                    ui.label(prop.address).classes(
                                        "text-subtitle1 text-weight-medium"
                                    )
                                    ui.label(f"{price_text}  ·  {beds_baths}  ·  {place}").classes(
                                        "text-body2 text-grey-6"
                                    )
                                    ui.link("Open on Zillow", prop.zillow_url, new_tab=True).classes(
                                        "text-caption"
                                    )
                            with ui.row().classes("gap-2"):
                                ui.button(
                                    "Open",
                                    on_click=lambda p=prop.id: ui.navigate.to(f"/property/{p}"),
                                ).props("flat color=primary")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda p=prop.id: delete_home(p),
                                ).props("flat round color=negative")

        def delete_home(property_id: int) -> None:
            with get_session() as session:
                PropertyService(session).delete_property(property_id)
            ui.notify("Deleted", type="info")
            refresh()

        refresh()


@ui.page("/property/{property_id}")
def property_page(property_id: int) -> None:
    with get_session() as session:
        prop = PropertyService(session).get_property(property_id)
        if prop is None:
            page_header("Missing")
            with ui.column().classes("q-pa-md"):
                ui.label("Property not found.")
                ui.button("Back to library", on_click=lambda: ui.navigate.to("/"))
            return
        # Capture fields while session is open
        address = prop.address
        zillow_url = prop.zillow_url
        notes = prop.notes
        list_price = prop.list_price
        beds = prop.beds
        baths = prop.baths
        city = prop.city
        state = prop.state
        zip_code = prop.zip_code
        prop_id = prop.id

    page_header("Property")

    with ui.column().classes("w-full max-w-7xl mx-auto q-pa-md gap-4"):
        with ui.row().classes("w-full items-start justify-between flex-wrap gap-4"):
            with ui.column().classes("gap-1"):
                ui.label(address).classes("text-h5")
                meta_bits = [
                    _format_price(list_price),
                    _format_beds_baths(beds, baths),
                    ", ".join(b for b in (city, state) if b),
                ]
                meta_line = "  ·  ".join(b for b in meta_bits if b)
                if meta_line:
                    ui.label(meta_line).classes("text-subtitle1 text-grey-6")
                ui.link("View on Zillow", zillow_url, new_tab=True)
            with ui.row().classes("gap-2"):
                def refresh_details() -> None:
                    try:
                        ui.notify("Refreshing listing details…", type="ongoing", timeout=0)
                        with get_session() as session:
                            PropertyService(session).refresh_listing_details(prop_id)
                        ui.notify("Listing details updated", type="positive")
                        ui.navigate.to(f"/property/{prop_id}")
                    except Exception as exc:  # noqa: BLE001
                        ui.notify(f"Refresh failed: {exc}", type="negative")

                ui.button("Refresh listing details", on_click=refresh_details).props("outline")
                ui.button("Back", on_click=lambda: ui.navigate.to("/")).props("outline")

        with ui.expansion("Edit listing details", icon="edit").classes("w-full"):
            edit_url = ui.input("Zillow URL", value=zillow_url).classes("w-full")
            edit_address = ui.input("Address", value=address).classes("w-full")
            with ui.row().classes("w-full gap-3 flex-wrap"):
                edit_price = ui.input(
                    "List price",
                    value="" if list_price is None else str(int(list_price) if list_price == int(list_price) else list_price),
                ).classes("w-40")
                edit_beds = ui.input(
                    "Beds",
                    value="" if beds is None else f"{beds:g}",
                ).classes("w-28")
                edit_baths = ui.input(
                    "Baths",
                    value="" if baths is None else f"{baths:g}",
                ).classes("w-28")
                edit_city = ui.input("City", value=city or "").classes("flex-grow min-w-40")
                edit_state = ui.input("State", value=state or "").classes("w-24")
                edit_zip = ui.input("ZIP", value=zip_code or "").classes("w-28")
            edit_notes = ui.textarea("Notes", value=notes).classes("w-full")

            def save_meta() -> None:
                try:
                    with get_session() as session:
                        PropertyService(session).update_property(
                            prop_id,
                            address=edit_address.value or "",
                            zillow_url=edit_url.value or "",
                            notes=edit_notes.value or "",
                            list_price=edit_price.value or "",
                            beds=edit_beds.value or "",
                            baths=edit_baths.value or "",
                            city=edit_city.value or "",
                            state=edit_state.value or "",
                            zip_code=edit_zip.value or "",
                        )
                    ui.notify("Saved", type="positive")
                    ui.navigate.to(f"/property/{prop_id}")
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")

            ui.button("Save", on_click=save_meta).props("color=primary")

        modules = get_modules()
        if not modules:
            ui.label("No modules registered.").classes("text-negative")
            return

        with ui.tabs().classes("w-full").props("dense indicator-color=primary active-color=primary") as tabs:
            tab_refs = {m.id: ui.tab(m.title) for m in modules}

        with ui.tab_panels(tabs, value=tab_refs[modules[0].id]).classes("w-full").props(
            "animated"
        ):
            for mod in modules:
                with ui.tab_panel(tab_refs[mod.id]):
                    panel = ui.column().classes("w-full")
                    with get_session() as session:
                        live = PropertyService(session).get_property(prop_id)
                        if live is None:
                            ui.label("Property missing.")
                            continue
                        mod.render(live, panel)
