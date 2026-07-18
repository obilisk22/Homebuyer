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


def _format_sqft(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.0f} sqft"


def _format_price_per_sqft(
    list_price: float | None, sqft: float | None
) -> str:
    if list_price is None or sqft is None or sqft <= 0:
        return ""
    return f"${list_price / sqft:,.0f}/sqft"


def _format_hoa(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "HOA $0"
    return f"HOA ${value:,.0f}/mo"


def _format_year_built(value: int | None) -> str:
    if value is None:
        return ""
    return f"Built {value}"


def _listing_meta_bits(
    *,
    list_price: float | None = None,
    beds: float | None = None,
    baths: float | None = None,
    sqft: float | None = None,
    hoa_fee: float | None = None,
    year_built: int | None = None,
    home_type: str = "",
    city: str = "",
    state: str = "",
) -> list[str]:
    place = ", ".join(b for b in (city, state) if b)
    return [
        b
        for b in (
            _format_price(list_price),
            _format_beds_baths(beds, baths),
            _format_sqft(sqft),
            _format_price_per_sqft(list_price, sqft),
            (home_type or "").strip(),
            _format_year_built(year_built),
            _format_hoa(hoa_fee),
            place,
        )
        if b
    ]


def _library_primary_chips(
    *,
    beds: float | None,
    baths: float | None,
    sqft: float | None,
    list_price: float | None,
) -> list[str]:
    """Beds · baths · sqft · $/sqft — the compact secondary chip row."""
    bits = []
    beds_baths = _format_beds_baths(beds, baths)
    if beds_baths:
        bits.append(beds_baths)
    sqft_str = _format_sqft(sqft)
    if sqft_str:
        bits.append(sqft_str)
    per_sqft = _format_price_per_sqft(list_price, sqft)
    if per_sqft:
        bits.append(per_sqft)
    return bits


def _library_secondary_chips(
    *,
    home_type: str,
    year_built: int | None,
    hoa_fee: float | None,
) -> list[str]:
    """Home type · year built · HOA — quieter tertiary chip row."""
    bits = []
    home_type = (home_type or "").strip()
    if home_type:
        bits.append(home_type)
    year_str = _format_year_built(year_built)
    if year_str:
        bits.append(year_str)
    hoa_str = _format_hoa(hoa_fee)
    if hoa_str:
        bits.append(hoa_str)
    return bits


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
        with ui.row().classes("items-baseline gap-3"):
            ui.label("Your homes").classes("text-h5")
            count_label = ui.label("").classes("text-body2 text-grey-6")
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

        with ui.expansion("Filter", icon="filter_list").classes("w-full"):
            with ui.row().classes("w-full gap-3 items-end flex-wrap q-pt-sm"):
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

        def delete_home(property_id: int) -> None:
            with get_session() as session:
                PropertyService(session).delete_property(property_id)
            ui.notify("Deleted", type="info")
            refresh()

        def confirm_delete(property_id: int, address: str) -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label("Delete this home?").classes("text-subtitle1")
                ui.label(address).classes("text-body2 text-grey-6")
                with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button(
                        "Delete",
                        on_click=lambda: (dialog.close(), delete_home(property_id)),
                    ).props("color=negative")
            dialog.open()

        def refresh() -> None:
            list_box.clear()
            with get_session() as session:
                has_any = PropertyService(session).list_properties()
                props = PropertyService(session).list_properties(
                    search=search_input.value or "",
                    min_price=_parse_filter_float(min_price_input.value),
                    max_price=_parse_filter_float(max_price_input.value),
                    min_beds=_parse_filter_float(min_beds_input.value),
                )
            count_label.set_text(f"{len(props)} home" + ("" if len(props) == 1 else "s") if props else "")
            with list_box:
                if not props:
                    if not has_any:
                        ui.label("No homes yet — paste a Zillow link above.").classes("text-grey-6")
                    else:
                        ui.label("No homes match these filters.").classes("text-grey-6")
                    return
                for prop in props:
                    primary_chips = _library_primary_chips(
                        beds=prop.beds,
                        baths=prop.baths,
                        sqft=prop.sqft,
                        list_price=prop.list_price,
                    )
                    secondary_chips = _library_secondary_chips(
                        home_type=prop.home_type or "",
                        year_built=prop.year_built,
                        hoa_fee=prop.hoa_fee,
                    )
                    thumb = None
                    thumb_photo = resolve_library_thumbnail(prop)
                    if thumb_photo is not None:
                        thumb = f"/uploads/{thumb_photo.path}"

                    with ui.card().classes("w-full hb-library-card") as card:
                        card.on(
                            "click",
                            lambda p=prop.id: ui.navigate.to(f"/property/{p}"),
                        )
                        with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
                            with ui.row().classes("items-start gap-4 flex-grow"):
                                if thumb:
                                    ui.image(thumb).classes("hb-library-thumb")
                                else:
                                    with ui.element("div").classes("hb-library-thumb--empty"):
                                        ui.icon("home", size="2rem")
                                with ui.column().classes("gap-1"):
                                    ui.label(prop.address).classes(
                                        "text-subtitle1 text-weight-medium"
                                    )
                                    if prop.list_price is not None:
                                        ui.label(_format_price(prop.list_price)).classes(
                                            "text-h6 hb-library-price"
                                        )
                                    if primary_chips:
                                        with ui.row().classes("gap-2 flex-wrap"):
                                            for chip in primary_chips:
                                                ui.label(chip).classes("hb-meta-chip")
                                    if secondary_chips:
                                        with ui.row().classes("gap-2 flex-wrap"):
                                            for chip in secondary_chips:
                                                ui.label(chip).classes(
                                                    "hb-meta-chip hb-meta-chip--quiet"
                                                )
                                    if not primary_chips and not secondary_chips:
                                        ui.label(
                                            "Details pending — open and refresh listing"
                                        ).classes("text-caption text-grey-6")
                                    zillow_link = ui.link(
                                        "Open on Zillow", prop.zillow_url, new_tab=True
                                    ).classes("text-caption")
                                    zillow_link.on(
                                        "click",
                                        lambda: None,
                                        js_handler="(e) => e.stopPropagation()",
                                    )
                            delete_btn = ui.button(icon="delete").props(
                                "flat round color=negative"
                            )
                            delete_btn.on(
                                "click",
                                lambda p=prop.id, a=prop.address: confirm_delete(p, a),
                                js_handler="(e) => { e.stopPropagation(); emit(e); }",
                            )

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
        sqft = prop.sqft
        hoa_fee = prop.hoa_fee
        year_built = prop.year_built
        home_type = prop.home_type or ""
        city = prop.city
        state = prop.state
        zip_code = prop.zip_code
        prop_id = prop.id

    page_header("Property")

    with ui.column().classes("w-full max-w-7xl mx-auto q-pa-md gap-4"):
        with ui.row().classes("w-full items-start justify-between flex-wrap gap-4"):
            with ui.column().classes("gap-1"):
                ui.label(address).classes("text-h5")
                meta_line = "  ·  ".join(
                    _listing_meta_bits(
                        list_price=list_price,
                        beds=beds,
                        baths=baths,
                        sqft=sqft,
                        hoa_fee=hoa_fee,
                        year_built=year_built,
                        home_type=home_type,
                        city=city,
                        state=state,
                    )
                )
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
                edit_sqft = ui.input(
                    "Sqft",
                    value="" if sqft is None else f"{sqft:g}",
                ).classes("w-28")
                edit_hoa = ui.input(
                    "HOA $/mo",
                    value="" if hoa_fee is None else f"{hoa_fee:g}",
                ).classes("w-28")
                edit_year = ui.input(
                    "Year built",
                    value="" if year_built is None else str(year_built),
                ).classes("w-28")
                edit_home_type = ui.input("Home type", value=home_type).classes(
                    "w-40"
                )
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
                            sqft=edit_sqft.value or "",
                            hoa_fee=edit_hoa.value or "",
                            year_built=edit_year.value or "",
                            home_type=edit_home_type.value or "",
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
