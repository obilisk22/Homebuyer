from __future__ import annotations

from nicegui import run, ui

from app.core.db import get_session
from app.core.module_registry import get_modules
from app.core.property_service import PropertyService, resolve_library_thumbnail
from app.core.ui_jobs import refresh_listing_details_job
from app.ui.chip_helpers import (
    _extra_signal_chips,
    _format_price,
    _library_primary_chips,
    _library_secondary_chips,
    _render_nearby_signal_chips,
    _render_street_address,
    _street_address_line,
)
from app.ui.pages import page_header

PROPERTY_HEADER_PHOTO_MODE = "bleed"  # "bleed" | "beside"

@ui.page("/property/{property_id}")
def property_page(property_id: int) -> None:
    with get_session() as session:
        prop = PropertyService(session).get_property(property_id)
        if prop is None:
            page_header("Missing")
            with ui.column().classes("hb-property-shell q-pa-md gap-3"):
                ui.label("Property not found.").classes("hb-empty-state w-full")
                ui.button("Back to library", on_click=lambda: ui.navigate.to("/")).props(
                    "unelevated dense color=dark"
                )
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
        thumb_photo = resolve_library_thumbnail(prop)
        thumb_url = (
            f"/uploads/{thumb_photo.path}" if thumb_photo is not None else None
        )
        nearby_signals = prop.nearby_signals or ""
        # `get_property` eager-loads module relationships; detach the fully loaded
        # object so all module first paints can share it after this session closes.
        session.expunge(prop)

    page_header("Property")

    city_s = (city or "").strip()
    state_s = (state or "").strip()
    zip_s = (zip_code or "").strip()
    street = _street_address_line(
        address, city=city_s, state=state_s, zip_code=zip_s
    )
    primary_chips = _library_primary_chips(
        beds=beds, baths=baths, sqft=sqft, list_price=list_price
    )
    secondary_chips = _library_secondary_chips(
        home_type=home_type, year_built=year_built, hoa_fee=hoa_fee
    )
    place = ", ".join(p for p in (city_s, state_s) if p)
    mode = PROPERTY_HEADER_PHOTO_MODE if PROPERTY_HEADER_PHOTO_MODE in ("bleed", "beside") else "bleed"
    hero_mod = f"hb-property-hero--{mode}"
    if thumb_url and mode == "bleed":
        hero_mod += " hb-property-hero--has-photo"

    with ui.column().classes("w-full hb-property-shell q-pa-md gap-3"):
        with ui.element("div").classes(f"hb-property-hero {hero_mod}"):
            if thumb_url and mode == "bleed":
                ui.element("div").classes("hb-property-hero__bg").style(
                    f"background-image: url('{thumb_url}')"
                )
                ui.element("div").classes("hb-property-hero__scrim")

            with ui.element("div").classes("hb-property-hero__content"):
                with ui.row().classes(
                    "w-full items-start justify-between flex-wrap gap-3"
                ):
                    with ui.row().classes(
                        "items-stretch gap-3 flex-grow hb-property-hero__listing"
                    ).style("min-width: 0"):
                        if mode == "beside":
                            if thumb_url:
                                with ui.element("div").classes(
                                    "hb-library-thumb-wrap"
                                ):
                                    ui.image(thumb_url).classes("hb-library-thumb")
                            else:
                                with ui.element("div").classes(
                                    "hb-library-thumb-wrap hb-library-thumb-wrap--empty"
                                ):
                                    ui.icon("home", size="2rem")
                        with ui.column().classes("gap-1 flex-grow").style(
                            "min-width: 0"
                        ):
                            _render_street_address(street, fallback=address)
                            if place:
                                ui.label(place).classes("hb-library-place")
                            if list_price is not None:
                                ui.label(_format_price(list_price)).classes(
                                    "hb-library-price"
                                )
                            if primary_chips:
                                with ui.row().classes("gap-1 flex-wrap"):
                                    for chip in primary_chips:
                                        ui.label(chip).classes("hb-meta-chip")
                            if secondary_chips:
                                with ui.row().classes("gap-1 flex-wrap"):
                                    for label, classes in secondary_chips:
                                        ui.label(label).classes(classes)
                            ui.link(
                                "View on Zillow", zillow_url, new_tab=True
                            ).classes("hb-page-meta")

                    with ui.row().classes("gap-2 flex-wrap"):
                        async def refresh_details() -> None:
                            try:
                                ui.notify(
                                    "Refreshing listing details…",
                                    type="ongoing",
                                    timeout=0,
                                )
                                await run.io_bound(
                                    refresh_listing_details_job, prop_id
                                )
                                ui.notify("Listing details updated", type="positive")
                                ui.navigate.to(f"/property/{prop_id}")
                            except Exception as exc:  # noqa: BLE001
                                ui.notify(f"Refresh failed: {exc}", type="negative")

                        ui.button(
                            "Refresh listing details", on_click=refresh_details
                        ).props("unelevated dense color=dark")

                with ui.expansion("Edit listing details", icon="edit").classes(
                    "w-full hb-edit-listing-expansion"
                ).props("dense"):
                    edit_url = (
                        ui.input("Zillow URL", value=zillow_url)
                        .classes("w-full")
                        .props("dense outlined stack-label")
                    )
                    edit_address = (
                        ui.input("Address", value=address)
                        .classes("w-full")
                        .props("dense outlined stack-label")
                    )
                    with ui.row().classes("w-full gap-3 flex-wrap"):
                        edit_price = (
                            ui.input(
                                "List price",
                                value=""
                                if list_price is None
                                else str(
                                    int(list_price)
                                    if list_price == int(list_price)
                                    else list_price
                                ),
                            )
                            .classes("w-40")
                            .props("dense outlined stack-label")
                        )
                        edit_beds = (
                            ui.input(
                                "Beds",
                                value="" if beds is None else f"{beds:g}",
                            )
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                        edit_baths = (
                            ui.input(
                                "Baths",
                                value="" if baths is None else f"{baths:g}",
                            )
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                        edit_sqft = (
                            ui.input(
                                "Sqft",
                                value="" if sqft is None else f"{sqft:g}",
                            )
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                        edit_hoa = (
                            ui.input(
                                "HOA $/mo",
                                value="" if hoa_fee is None else f"{hoa_fee:g}",
                            )
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                        edit_year = (
                            ui.input(
                                "Year built",
                                value="" if year_built is None else str(year_built),
                            )
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                        edit_home_type = (
                            ui.input("Home type", value=home_type)
                            .classes("w-40")
                            .props("dense outlined stack-label")
                        )
                        edit_city = (
                            ui.input("City", value=city or "")
                            .classes("flex-grow min-w-40")
                            .props("dense outlined stack-label")
                        )
                        edit_state = (
                            ui.input("State", value=state or "")
                            .classes("w-24")
                            .props("dense outlined stack-label")
                        )
                        edit_zip = (
                            ui.input("ZIP", value=zip_code or "")
                            .classes("w-28")
                            .props("dense outlined stack-label")
                        )
                    edit_notes = (
                        ui.textarea("Notes", value=notes)
                        .classes("w-full")
                        .props("dense outlined stack-label")
                    )

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

                    ui.button("Save", on_click=save_meta).props(
                        "unelevated dense color=dark"
                    ).classes("hb-btn-cta")

            _render_nearby_signal_chips(
                nearby_signals,
                home_lat=getattr(prop, "latitude", None),
                home_lng=getattr(prop, "longitude", None),
                listing_chips=_extra_signal_chips(
                    has_central_ac=getattr(prop, "has_central_ac", None),
                    cooling=getattr(prop, "cooling", "") or "",
                    broadband_status=getattr(prop, "broadband_status", "") or "",
                    permits_activity=getattr(prop, "permits_activity", "") or "",
                    market_activity=getattr(prop, "market_activity", "") or "",
                    home_type=getattr(prop, "home_type", "") or "",
                    townhome_position=getattr(prop, "townhome_position", "") or "",
                ),
            )

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
                    mod.render(prop, panel)
