from __future__ import annotations

from nicegui import run, ui

from app.core.db import get_session
from app.core.library_export import (
    export_library_csv,
    export_library_json,
    snapshot_from_property,
)
from app.core.models import Property
from app.core.property_service import PropertyService, fetch_library_thumbnails
from app.core.thumbnail import resolve_library_thumbnail_url
from app.core.ui_jobs import (
    add_from_zillow_job,
    refresh_stale_area_signals_job,
)
from app.ui.chip_helpers import (
    _extra_signal_chips,
    _format_price,
    _library_appreciation_caption,
    _library_appreciation_tone_class,
    _library_financial_caption,
    _library_primary_chips,
    _library_secondary_chips,
    _render_nearby_signal_chips,
    _render_street_address,
    _street_address_line,
    _truncate_notes,
)
from app.ui.pages import page_header

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
    page_header("Library", show_api_keys=True)

    sort_options = {
        "Newest": "newest",
        "Price ↑": "price_asc",
        "Price ↓": "price_desc",
    }

    with ui.column().classes("w-full hb-library-shell q-pa-md gap-3"):
        with ui.row().classes("items-baseline gap-3"):
            ui.label("Your homes").classes("hb-page-title")
            count_label = ui.label("").classes("hb-page-meta")
        hint_label = ui.label(
            "Paste a Zillow listing link — address, photos, and details import automatically."
        ).classes("hb-page-hint")

        with ui.card().classes("w-full hb-add-card"):
            with ui.row().classes("w-full gap-3 items-end flex-wrap"):
                url_input = ui.input(
                    "Zillow URL",
                    placeholder="https://www.zillow.com/homedetails/...",
                ).classes("flex-grow min-w-64").props("dense outlined stack-label")

                async def add_home() -> None:
                    add_btn.disable()
                    try:
                        ui.notify(
                            "Saving home and importing listing…",
                            type="ongoing",
                            timeout=0,
                        )
                        new_id, imported = await run.io_bound(
                            add_from_zillow_job, url_input.value or ""
                        )
                        ui.notify(
                            f"Home saved — imported {imported} photos",
                            type="positive",
                        )
                        ui.navigate.to(f"/property/{new_id}")
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                    except Exception as exc:  # noqa: BLE001
                        ui.notify(f"Failed: {exc}", type="negative")
                    finally:
                        add_btn.enable()

                add_btn = (
                    ui.button("Add home", on_click=add_home)
                    .props("unelevated dense color=dark")
                    .classes("hb-btn-cta")
                )

        with ui.row().classes("w-full hb-toolbar-row flex-wrap"):
            sort_select = ui.select(
                options=list(sort_options.keys()),
                value="Newest",
                label="Sort",
            ).classes("w-40").props("dense outlined stack-label")
            filter_expansion = ui.expansion("Filter", icon="filter_list").classes(
                "flex-grow"
            )
            with filter_expansion:
                with ui.row().classes("w-full gap-3 items-end flex-wrap q-pt-sm"):
                    search_input = ui.input(
                        "Search",
                        placeholder="Address or city",
                    ).classes("flex-grow min-w-48").props("dense outlined stack-label")
                    min_price_input = ui.input(
                        "Min price", placeholder="e.g. 500000"
                    ).classes("w-36").props("dense outlined stack-label")
                    max_price_input = ui.input(
                        "Max price", placeholder="e.g. 1200000"
                    ).classes("w-36").props("dense outlined stack-label")
                    min_beds_input = ui.input(
                        "Min beds", placeholder="e.g. 3"
                    ).classes("w-28").props("dense outlined stack-label")
                    ui.button("Apply", on_click=lambda: refresh()).props(
                        "unelevated dense color=dark"
                    )
                    ui.button(
                        "Clear",
                        on_click=lambda: (
                            search_input.set_value(""),
                            min_price_input.set_value(""),
                            max_price_input.set_value(""),
                            min_beds_input.set_value(""),
                            refresh(),
                        ),
                    ).props("flat dense color=dark")

            export_btn = ui.button("Export", icon="download").props(
                "unelevated dense color=dark"
            )
            with export_btn:
                with ui.menu().props('anchor="top end" self="top end"'):
                    ui.menu_item("Download CSV", on_click=lambda: _export("csv"))
                    ui.menu_item("Download JSON", on_click=lambda: _export("json"))

        list_box = ui.column().classes("w-full gap-3")
        filter_debounce = None
        chip_hosts: dict[int, ui.element] = {}

        def _export(fmt: str) -> None:
            with get_session() as session:
                props = PropertyService(session).list_properties(sort="newest")
                snaps = [snapshot_from_property(p) for p in props]
            if not snaps:
                ui.notify("Nothing to export yet", type="info")
                return
            if fmt == "json":
                ui.download(
                    export_library_json(snaps).encode("utf-8"),
                    "homebuy-library.json",
                    "application/json",
                )
            else:
                ui.download(
                    export_library_csv(snaps).encode("utf-8"),
                    "homebuy-library.csv",
                    "text/csv",
                )

        def delete_home(property_id: int) -> None:
            with get_session() as session:
                PropertyService(session).delete_property(property_id)
            ui.notify("Deleted", type="info")
            refresh()

        def confirm_delete(property_id: int, address: str) -> None:
            with ui.dialog() as dialog, ui.card():
                ui.label("Delete this home?").classes("hb-page-title")
                ui.label(address).classes("hb-page-meta")
                with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
                    ui.button("Cancel", on_click=dialog.close).props("flat color=dark")
                    ui.button(
                        "Delete",
                        on_click=lambda: (dialog.close(), delete_home(property_id)),
                    ).props("color=negative")
            dialog.open()

        def _active_filter_count() -> int:
            n = 0
            if (search_input.value or "").strip():
                n += 1
            if _parse_filter_float(min_price_input.value) is not None:
                n += 1
            if _parse_filter_float(max_price_input.value) is not None:
                n += 1
            if _parse_filter_float(min_beds_input.value) is not None:
                n += 1
            return n

        def refresh() -> None:
            nonlocal filter_debounce
            if filter_debounce is not None:
                filter_debounce.deactivate()
                filter_debounce = None
            list_box.clear()
            chip_hosts.clear()
            sort_key = sort_options.get(str(sort_select.value or "Newest"), "newest")
            active = _active_filter_count()
            filter_expansion._props["label"] = (
                f"Filter · {active} active" if active else "Filter"
            )
            filter_expansion.update()

            card_rows: list[dict] = []
            with get_session() as session:
                service = PropertyService(session)
                props = service.list_properties(
                    search=search_input.value or "",
                    min_price=_parse_filter_float(min_price_input.value),
                    max_price=_parse_filter_float(max_price_input.value),
                    min_beds=_parse_filter_float(min_beds_input.value),
                    sort=sort_key,
                )
                has_any = True if props else service.has_any_properties()
                thumbs = fetch_library_thumbnails(session, props)
                for prop in props:
                    snap = snapshot_from_property(prop)
                    thumb = None
                    thumb_photo = thumbs.get(prop.id)
                    if thumb_photo is not None:
                        thumb = resolve_library_thumbnail_url(thumb_photo)
                    card_rows.append(
                        {
                            "id": prop.id,
                            "address": prop.address,
                            "list_price": prop.list_price,
                            "beds": prop.beds,
                            "baths": prop.baths,
                            "sqft": prop.sqft,
                            "home_type": prop.home_type or "",
                            "year_built": prop.year_built,
                            "hoa_fee": prop.hoa_fee,
                            "notes": prop.notes or "",
                            "city": (prop.city or "").strip(),
                            "state": (prop.state or "").strip(),
                            "zip_code": (prop.zip_code or "").strip(),
                            "zillow_url": prop.zillow_url,
                            "thumb": thumb,
                            "fin_caption": _library_financial_caption(snap),
                            "appr_caption": _library_appreciation_caption(snap),
                            "appr_pct": snap.appreciation_pct,
                            "appr_source": snap.appreciation_source or "",
                            "nearby_signals": prop.nearby_signals or "",
                            "latitude": prop.latitude,
                            "longitude": prop.longitude,
                            "cooling": prop.cooling or "",
                            "has_central_ac": prop.has_central_ac,
                            "broadband_status": prop.broadband_status or "",
                            "permits_activity": prop.permits_activity or "",
                            "market_activity": prop.market_activity or "",
                            "townhome_position": prop.townhome_position or "",
                        }
                    )
            hint_label.set_visibility(not has_any)
            if card_rows:
                count_label.set_text(
                    f"{len(card_rows)} home" + ("" if len(card_rows) == 1 else "s")
                )
            elif has_any:
                count_label.set_text("0 homes")
            else:
                count_label.set_text("")
            with list_box:
                if not card_rows:
                    if not has_any:
                        ui.label(
                            "No homes yet — paste a Zillow link above."
                        ).classes("hb-empty-state w-full")
                    else:
                        ui.label("No homes match these filters.").classes(
                            "hb-empty-state w-full"
                        )
                    return
                for row in card_rows:
                    prop_id = row["id"]
                    address = row["address"]
                    list_price = row["list_price"]
                    city = row["city"]
                    state = row["state"]
                    zip_code = row["zip_code"]
                    street = _street_address_line(
                        address, city=city, state=state, zip_code=zip_code
                    )
                    primary_chips = _library_primary_chips(
                        beds=row["beds"],
                        baths=row["baths"],
                        sqft=row["sqft"],
                        list_price=list_price,
                    )
                    secondary_chips = _library_secondary_chips(
                        home_type=row["home_type"],
                        year_built=row["year_built"],
                        hoa_fee=row["hoa_fee"],
                    )
                    notes_teaser = _truncate_notes(row["notes"])
                    thumb = row["thumb"]
                    zillow_url = row["zillow_url"]
                    fin_caption = row["fin_caption"]
                    appr_caption = row["appr_caption"]
                    appr_pct = row["appr_pct"]
                    appr_source = row["appr_source"]

                    with ui.card().classes("w-full hb-library-card") as card:
                        card.on(
                            "click",
                            lambda p=prop_id: ui.navigate.to(f"/property/{p}"),
                        )
                        with ui.row().classes(
                            "w-full items-stretch justify-between gap-3 flex-nowrap"
                        ):
                            with ui.row().classes(
                                "items-stretch gap-3 flex-grow hb-library-card-body"
                            ):
                                thumb_classes = "hb-library-thumb-wrap"
                                if not thumb:
                                    thumb_classes += " hb-library-thumb-wrap--empty"
                                with ui.element("div").classes(thumb_classes):
                                    if thumb:
                                        ui.image(thumb).classes("hb-library-thumb")
                                    else:
                                        ui.icon("home", size="2rem")
                                with ui.column().classes("gap-1 flex-grow").style(
                                    "min-width: 0"
                                ):
                                    _render_street_address(street, fallback=address)
                                    place = ", ".join(
                                        p for p in (city, state) if p
                                    )
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
                                    if not primary_chips and not secondary_chips:
                                        ui.label(
                                            "Details pending — open and refresh listing"
                                        ).classes("hb-page-meta")
                                    if fin_caption or appr_caption:
                                        with ui.row().classes(
                                            "gap-2 flex-wrap items-baseline"
                                        ):
                                            if fin_caption:
                                                ui.label(fin_caption).classes(
                                                    "hb-page-meta"
                                                )
                                            if appr_caption:
                                                appr_classes = "hb-page-meta"
                                                tone = _library_appreciation_tone_class(
                                                    appr_pct
                                                )
                                                if tone:
                                                    appr_classes += f" {tone}"
                                                appr_lbl = ui.label(
                                                    appr_caption
                                                ).classes(appr_classes)
                                                if appr_source:
                                                    appr_lbl._props["title"] = (
                                                        appr_source
                                                    )
                                    if notes_teaser:
                                        ui.label(notes_teaser).classes("hb-library-notes")

                            with ui.element("div").classes("flex-shrink-0 self-start"):
                                menu_btn = ui.button(icon="more_vert").props(
                                    "unelevated round dense color=dark"
                                )
                                menu_btn.on(
                                    "click",
                                    lambda: None,
                                    js_handler="(e) => { e.stopPropagation(); emit(e); }",
                                )
                                with menu_btn:
                                    with ui.menu().props('anchor="top end" self="top end"'):
                                        def open_zillow(u=zillow_url) -> None:
                                            ui.run_javascript(
                                                f"window.open({u!r}, '_blank')"
                                            )

                                        ui.menu_item(
                                            "Open on Zillow",
                                            on_click=open_zillow,
                                        )
                                        ui.menu_item(
                                            "Delete…",
                                            on_click=lambda p=prop_id, a=address: confirm_delete(
                                                p, a
                                            ),
                                        )

                        chip_host = ui.element("div").classes("hb-library-chip-host")
                        chip_hosts[prop_id] = chip_host
                        with chip_host:
                            _render_nearby_signal_chips(
                                row["nearby_signals"],
                                home_lat=row.get("latitude"),
                                home_lng=row.get("longitude"),
                                stop_card_nav=True,
                                listing_chips=_extra_signal_chips(
                                    has_central_ac=row.get("has_central_ac"),
                                    cooling=row.get("cooling") or "",
                                    broadband_status=row.get("broadband_status") or "",
                                    permits_activity=row.get("permits_activity") or "",
                                    market_activity=row.get("market_activity") or "",
                                    home_type=row.get("home_type") or "",
                                    townhome_position=row.get("townhome_position") or "",
                                ),
                            )

        def _patch_chip_rows() -> None:
            """Re-render chip hosts after stale refresh without rebuilding the list."""
            if not chip_hosts:
                return
            rows: dict[int, dict] = {}
            with get_session() as session:
                for prop_id in list(chip_hosts):
                    prop = session.get(Property, prop_id)
                    if prop is None:
                        continue
                    rows[prop_id] = {
                        "nearby_signals": prop.nearby_signals or "",
                        "latitude": prop.latitude,
                        "longitude": prop.longitude,
                        "cooling": prop.cooling or "",
                        "has_central_ac": prop.has_central_ac,
                        "broadband_status": prop.broadband_status or "",
                        "permits_activity": prop.permits_activity or "",
                        "market_activity": prop.market_activity or "",
                        "home_type": prop.home_type or "",
                        "townhome_position": prop.townhome_position or "",
                    }
            for prop_id, host in list(chip_hosts.items()):
                row = rows.get(prop_id)
                if row is None:
                    continue
                host.clear()
                with host:
                    _render_nearby_signal_chips(
                        row["nearby_signals"],
                        home_lat=row.get("latitude"),
                        home_lng=row.get("longitude"),
                        stop_card_nav=True,
                        listing_chips=_extra_signal_chips(
                            has_central_ac=row.get("has_central_ac"),
                            cooling=row.get("cooling") or "",
                            broadband_status=row.get("broadband_status") or "",
                            permits_activity=row.get("permits_activity") or "",
                            market_activity=row.get("market_activity") or "",
                            home_type=row.get("home_type") or "",
                            townhome_position=row.get("townhome_position") or "",
                        ),
                    )

        async def _refresh_stale_nearby_after_paint() -> None:
            try:
                counts = await run.io_bound(
                    refresh_stale_area_signals_job, limit=3
                )
                if any(int(v or 0) for v in (counts or {}).values()):
                    _patch_chip_rows()
            except Exception:  # noqa: BLE001 - background signals never break library
                pass

        def _schedule_filter_refresh() -> None:
            nonlocal filter_debounce
            if filter_debounce is not None:
                filter_debounce.deactivate()
            filter_debounce = ui.timer(0.35, refresh, once=True)

        for _field in (
            search_input,
            min_price_input,
            max_price_input,
            min_beds_input,
        ):
            _field.on("keydown.enter", lambda: refresh())
            _field.on_value_change(lambda _: _schedule_filter_refresh())

        sort_select.on_value_change(lambda: refresh())
        refresh()
        ui.timer(0.1, _refresh_stale_nearby_after_paint, once=True)

