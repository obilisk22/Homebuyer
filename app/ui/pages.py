from __future__ import annotations

import html
import re
from types import SimpleNamespace

from nicegui import run, ui

from app.core.db import get_session
from app.core.library_export import (
    LibraryFinancialSnapshot,
    export_library_csv,
    export_library_json,
    snapshot_from_property,
)
from app.core.module_registry import get_modules
from app.core.nearby_signals import (
    ICON_BY_KEY,
    RISK_KEYS,
    hits_in_order,
    parse_signals_json,
    source_url_for,
    tooltip_for,
)
from app.core.listing_signals import listing_risk_chips
from app.core.permits_nearby import chip_spec_for, parse_activity_json
from app.core.property_service import PropertyService, resolve_library_thumbnail
from app.core.ui_jobs import (
    add_from_zillow_job,
    ensure_gemini_insights_job,
    refresh_listing_details_job,
    refresh_stale_broadband_status_job,
    refresh_stale_nearby_signals_job,
    refresh_stale_permits_activity_job,
)
from app.ui.theme import apply_theme

# Property header library photo: "bleed" (full-bleed + scrim) or "beside" (card-style).
# Flip to "beside" to roll back without other code changes.
PROPERTY_HEADER_PHOTO_MODE = "bleed"  # "bleed" | "beside"


def page_header(title: str) -> None:
    apply_theme()
    with ui.header().classes("hb-header items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "unelevated round dense color=dark"
            )
            brand = ui.label("Homebuy").classes("hb-brand").style("cursor: pointer")
            brand.on("click", lambda: ui.navigate.to("/"))
            ui.label(title).classes("hb-header-title")


def _format_price(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.0f}"


def _library_financial_caption(snap: LibraryFinancialSnapshot) -> str:
    """Quiet PITI line when saved financials exist."""
    if not snap.has_financials:
        return ""
    if not (snap.effective_price or 0) > 0:
        return ""
    if snap.monthly_piti is None:
        return ""
    return f"PITI {_format_price(snap.monthly_piti)}/mo"


def _library_appreciation_caption(snap: LibraryFinancialSnapshot) -> str:
    """Quiet appreciation / Growth line when financials include a rate."""
    if not snap.has_financials or snap.appreciation_pct is None:
        return ""
    return f"Growth {snap.appreciation_pct:.1f}%/yr"


def _library_appreciation_tone_class(pct: float | None) -> str:
    """Caption tone: amber <3%, lime >6%, neutral 3–6% inclusive."""
    if pct is None:
        return ""
    if pct < 3.0:
        return "hb-appr-low"
    if pct > 6.0:
        return "hb-appr-high"
    return ""


def _render_nearby_signal_chips(
    nearby_signals: str,
    *,
    home_lat: float | None = None,
    home_lng: float | None = None,
    stop_card_nav: bool = False,
    listing_chips: list | None = None,
) -> None:
    """Soft neo proximity + listing risk chips (library card + property header)."""
    nearby_hits = hits_in_order(parse_signals_json(nearby_signals or ""))
    extra = list(listing_chips or [])
    if not nearby_hits and not extra:
        return
    with ui.element("div").classes("hb-nearby-icons"):
        for chip_info in extra:
            tone = chip_info.get("tone") or chip_info.get("kind") or "risk"
            chip = ui.element("div").classes(
                f"hb-nearby-chip hb-nearby-chip--{tone}"
            )
            chip._props["title"] = chip_info.get("tooltip") or ""
            if stop_card_nav:
                chip.on(
                    "click",
                    lambda: None,
                    js_handler=(
                        "(e) => { e.stopPropagation(); emit(e); }"
                    ),
                )
            with chip:
                ui.icon(chip_info.get("icon") or "ac_unit", size="xs")
        for key, entry in nearby_hits:
            kind = "risk" if key in RISK_KEYS else "amenity"
            chip = ui.element("div").classes(
                f"hb-nearby-chip hb-nearby-chip--{kind}"
            )
            chip._props["title"] = tooltip_for(key, entry)
            url = source_url_for(entry, home_lat=home_lat, home_lng=home_lng)

            def _open_source(_e=None, *, u: str = url or "") -> None:
                if u:
                    ui.navigate.to(u, new_tab=True)

            if url:
                if stop_card_nav:
                    chip.on(
                        "click",
                        _open_source,
                        js_handler=(
                            "(e) => { e.stopPropagation(); emit(e); }"
                        ),
                    )
                else:
                    chip.on("click", _open_source)
            elif stop_card_nav:
                chip.on(
                    "click",
                    lambda: None,
                    js_handler=(
                        "(e) => { e.stopPropagation(); emit(e); }"
                    ),
                )
            with chip:
                ui.icon(ICON_BY_KEY[key], size="xs")


def _extra_signal_chips(
    *,
    has_central_ac: bool | None = None,
    cooling: str = "",
    broadband_status: str = "",
    permits_activity: str = "",
) -> list[dict]:
    """Listing risk + permit amber chips for library / header rows."""
    chips: list[dict] = list(
        listing_risk_chips(
            SimpleNamespace(
                has_central_ac=has_central_ac,
                cooling=cooling or "",
                broadband_status=broadband_status or "",
            )
        )
    )
    permit = chip_spec_for(parse_activity_json(permits_activity or ""))
    if permit:
        chips.append(
            {
                "key": permit["key"],
                "kind": permit.get("tone") or "amber",
                "tone": permit.get("tone") or "amber",
                "icon": permit.get("icon") or "construction",
                "tooltip": permit.get("tooltip") or "",
            }
        )
    return chips


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


HOA_HIGH_MONTHLY = 400.0


def _library_secondary_chips(
    *,
    home_type: str,
    year_built: int | None,
    hoa_fee: float | None,
) -> list[tuple[str, str]]:
    """Home type · year built · HOA — (label, css classes) for tertiary row."""
    bits: list[tuple[str, str]] = []
    home_type = (home_type or "").strip()
    if home_type:
        bits.append((home_type, "hb-meta-chip hb-meta-chip--quiet"))
    year_str = _format_year_built(year_built)
    if year_str:
        bits.append((year_str, "hb-meta-chip hb-meta-chip--quiet"))
    hoa_str = _format_hoa(hoa_fee)
    if hoa_str:
        if hoa_fee is not None and hoa_fee >= HOA_HIGH_MONTHLY:
            bits.append((hoa_str, "hb-meta-chip hb-meta-chip--hoa-high"))
        else:
            bits.append((hoa_str, "hb-meta-chip hb-meta-chip--quiet"))
    return bits


def _truncate_notes(notes: str, limit: int = 100) -> str:
    text = (notes or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _street_address_line(
    address: str,
    *,
    city: str = "",
    state: str = "",
    zip_code: str = "",
) -> str:
    """Street-only line for library cards (city/state/ZIP shown separately)."""
    text = (address or "").strip()
    if not text:
        return ""
    from app.core.geocode import _split_us_address

    parts = _split_us_address(text)
    if parts and parts[0]:
        return parts[0]
    # Strip known trailing ", City, ST ZIP" when structured fields exist
    city_s, state_s, zip_s = city.strip(), state.strip(), (zip_code or "").strip()
    if city_s and state_s:
        tail = f", {city_s}, {state_s}"
        if zip_s and text.endswith(zip_s):
            text = text[: -len(zip_s)].rstrip()
        if text.lower().endswith(tail.lower()):
            return text[: -len(tail)].rstrip(" ,")
        # Comma-first segment often is the street
        if "," in text:
            return text.split(",", 1)[0].strip()
    if "," in text:
        return text.split(",", 1)[0].strip()
    return text


# Display-only: APT/UNIT/SUITE/#… → compact "#…" suffix (does not mutate stored address).
_UNIT_MARKER_RE = re.compile(
    r"""
    ^(?P<street>.*?)\s+
    (?:
        (?:APT|APARTMENT|UNIT|STE|SUITE)\.?\s+(?P<label>[A-Za-z0-9\-]+)
        |
        \#\s*(?P<hash>[A-Za-z0-9\-]+)
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _split_street_unit(street: str) -> tuple[str, str | None]:
    """Split street vs unit; unit returned as ``#…`` or None. Display-only."""
    text = (street or "").strip()
    if not text:
        return "", None
    m = _UNIT_MARKER_RE.match(text)
    if not m:
        return text, None
    base = (m.group("street") or "").strip().rstrip(",")
    unit = (m.group("label") or m.group("hash") or "").strip()
    if not base or not unit:
        return text, None
    return base, f"#{unit}"


def _render_street_address(street: str, *, fallback: str = "") -> None:
    """Akira street line with optional smaller ``#unit`` span (library + header)."""
    base, unit = _split_street_unit(street or "")
    display = base or (fallback or "").strip()
    if not display and not unit:
        return
    if not unit:
        ui.label(display).classes("hb-library-address")
        return
    # Keep Akira size on the wrapper; unit uses 0.75em relative to that.
    with ui.element("div").classes("hb-library-address"):
        parts = []
        if display:
            parts.append(html.escape(display))
        parts.append(
            f'<span class="hb-library-unit">{" " if display else ""}'
            f"{html.escape(unit)}</span>"
        )
        ui.html("".join(parts), sanitize=False)


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
                for prop in props:
                    snap = snapshot_from_property(prop)
                    thumb = None
                    thumb_photo = resolve_library_thumbnail(prop)
                    if thumb_photo is not None:
                        thumb = f"/uploads/{thumb_photo.path}"
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
                            ),
                        )

        async def _refresh_stale_nearby_after_paint() -> None:
            try:
                refreshed = await run.io_bound(
                    refresh_stale_nearby_signals_job, limit=3
                )
                refreshed_permits = await run.io_bound(
                    refresh_stale_permits_activity_job, limit=3
                )
                refreshed_bb = await run.io_bound(
                    refresh_stale_broadband_status_job, limit=3
                )
                if refreshed or refreshed_permits or refreshed_bb:
                    refresh()
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

                        async def run_gemini_insights() -> None:
                            try:
                                ui.notify(
                                    "Generating Gemini insights… (neighborhood + finances)",
                                    type="ongoing",
                                    timeout=0,
                                )
                                results = await run.io_bound(
                                    ensure_gemini_insights_job, prop_id, force=False
                                )
                                ok_bits = [
                                    label
                                    for key, label in (
                                        ("overview", "assessment"),
                                        ("things_to_do", "things to do"),
                                        ("financial", "financials"),
                                    )
                                    if results.get(key) in {"ok", "cached"}
                                ]
                                fail_bits = [
                                    f"{label}: {results[key]}"
                                    for key, label in (
                                        ("overview", "assessment"),
                                        ("things_to_do", "things to do"),
                                        ("financial", "financials"),
                                    )
                                    if results.get(key) not in {"ok", "cached", None}
                                ]
                                if ok_bits and not fail_bits:
                                    ui.notify(
                                        "Gemini insights ready — see Neighborhood & Financials tabs",
                                        type="positive",
                                    )
                                elif ok_bits and fail_bits:
                                    ui.notify(
                                        "Partial Gemini insights: "
                                        + "; ".join(fail_bits[:2]),
                                        type="warning",
                                    )
                                else:
                                    ui.notify(
                                        fail_bits[0]
                                        if fail_bits
                                        else "Gemini insights failed",
                                        type="negative",
                                    )
                                ui.navigate.to(f"/property/{prop_id}")
                            except Exception as exc:  # noqa: BLE001
                                ui.notify(
                                    f"Gemini insights failed: {exc}", type="negative"
                                )

                        ui.button(
                            "Refresh listing details", on_click=refresh_details
                        ).props("unelevated dense color=dark")
                        ui.button(
                            "Gemini insights",
                            on_click=run_gemini_insights,
                            icon="auto_awesome",
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
