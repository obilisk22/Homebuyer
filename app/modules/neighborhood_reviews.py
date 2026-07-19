"""Neighborhood — Zillow name + Gemini overview (+ optional deep links)."""

from __future__ import annotations

from nicegui import run, ui

from app.core.db import get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.neighborhood import (
    build_review_deep_links,
    effective_neighborhood_name,
)
from app.core.property_service import PropertyService
from app.core.schooldigger import has_schooldigger_keys
from app.core.ui_jobs import (
    ensure_gemini_overview_job,
    ensure_gemini_things_to_do_job,
    ensure_neighborhood_job,
    resolve_assigned_schools_job,
)

_SOURCE_LABELS = {
    "zillow": "From Zillow listing",
    "nominatim": "OpenStreetMap Nominatim",
    "google": "Google Geocoding",
}

# (level key, display label, accent token) — one card each, in this order.
_SCHOOL_LEVELS: tuple[tuple[str, str, str], ...] = (
    ("elementary", "Elementary", "cyan"),
    ("middle", "Middle", "magenta"),
    ("high", "High", "lime"),
)

# Design-spec caption text for resolve_assigned() statuses that are not the
# happy path — shown verbatim instead of the raw core message.
_ASSIGNED_SCHOOLS_STATUS_TEXT: dict[str, str] = {
    "no_pin": "Needs a map pin — geocode this home first.",
    "outside": "Assigned schools not available for this district yet (SoCal GIS).",
    "gap": "No attendance match for this pin (rare boundary gap).",
}


def _assigned_schools_caption(result: dict, *, has_keys: bool) -> str:
    """Map a resolve_assigned() result to the design-spec caption text."""
    status = (result.get("status") or "").strip()
    if status == "ok":
        source = (result.get("source") or "").strip() or "Assigned schools resolved"
        if has_keys:
            return f"{source} · ratings via SchoolDigger"
        return f"{source} · add SchoolDigger keys in .env for ratings & reviews"
    if status == "error":
        return (result.get("message") or "Could not load assigned schools.").strip()
    return _ASSIGNED_SCHOOLS_STATUS_TEXT.get(
        status, (result.get("message") or "").strip()
    )


def _star_string(stars: float | int | None) -> str:
    if stars is None:
        return ""
    try:
        count = max(0, min(5, round(float(stars))))
    except (TypeError, ValueError):
        return ""
    return "★" * count + "☆" * (5 - count)


def _render_school_card(
    level_label: str, accent: str, school: dict | None, *, not_found_text: str
) -> None:
    with ui.card().classes("hb-school-card"):
        with ui.row().classes("items-center gap-2 w-full no-wrap"):
            with ui.element("div").classes(f"hb-school-level-ph hb-school-level-ph--{accent}"):
                ui.icon("school")
            ui.label(level_label).classes("hb-page-meta").style("font-weight: 600;")

        name = (school or {}).get("name") if school else None
        ui.label(name or not_found_text).classes("hb-page-title").style(
            "font-size: 1rem; margin-top: 0.4rem;"
        )

        stars = (school or {}).get("rating_stars") if school else None
        star_str = _star_string(stars)
        ui.label(f"{star_str} · SchoolDigger" if star_str else "—").classes(
            "hb-page-meta"
        )

        review_avg = (school or {}).get("review_avg") if school else None
        review_count = (school or {}).get("review_count") if school else None
        if review_avg is not None and review_count:
            ui.label(f"Parent reviews: {review_avg} · {review_count}").classes(
                "hb-page-meta"
            )
            quote = (school or {}).get("review_quote") if school else None
            if quote:
                ui.label(f"“{quote}”").classes("hb-page-hint")

        url = (school or {}).get("schooldigger_url") if school else None
        if url:
            ui.button("SchoolDigger", icon="open_in_new").props(
                f'unelevated dense color=dark href="{url}" target=_blank'
            ).classes("q-mt-sm")


def _source_label(source: str, *, has_override: bool) -> str:
    if has_override:
        resolved = _SOURCE_LABELS.get((source or "").strip().lower(), "")
        if resolved:
            return f"Manual override (auto: {resolved})"
        return "Manual override"
    key = (source or "").strip().lower()
    return _SOURCE_LABELS.get(key, source or "unknown")


def _link_chip(label: str, url: str, *, icon: str = "open_in_new") -> None:
    ui.button(label).props(
        f'unelevated dense color=dark icon={icon} href="{url}" target=_blank'
    ).classes("q-mr-xs q-mb-xs")


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id

    with container:
        status = ui.label("").classes("hb-page-meta")
        body = ui.column().classes("w-full gap-4")

        def load() -> Property | None:
            with get_session() as session:
                return PropertyService(session).get_property(property_id)

        def resolve_name() -> Property | None:
            status.set_text("Pulling neighborhood from Zillow…")
            try:
                with get_session() as session:
                    return PropertyService(session).ensure_neighborhood(
                        property_id, force=True
                    )
            except Exception as exc:
                status.set_text(str(exc))
                return load()

        def ensure_name(initial: Property | None = None) -> Property | None:
            if initial is None:
                with get_session() as session:
                    fresh = PropertyService(session).get_property(property_id)
            else:
                fresh = initial
            if fresh is None:
                return None
            # Upgrade empty or non-Zillow labels (e.g. bad Nominatim) via listing HTML.
            source = (fresh.neighborhood_source or "").strip().lower()
            has_zillow = bool((fresh.neighborhood_name or "").strip()) and source == "zillow"
            has_override = bool((fresh.neighborhood_override or "").strip())
            if has_zillow or has_override:
                return fresh
            status.set_text("Pulling neighborhood from Zillow…")
            try:
                with get_session() as session:
                    return PropertyService(session).ensure_neighborhood(property_id)
            except Exception as exc:
                status.set_text(str(exc))
                return load()

        def redraw(initial: Property | None = None) -> None:
            live = ensure_name(initial) or load()
            body.clear()
            if live is None:
                with body:
                    ui.label("Property not found.").classes("text-negative")
                return

            override = (live.neighborhood_override or "").strip()
            resolved = (live.neighborhood_name or "").strip()
            display = effective_neighborhood_name(
                neighborhood_name=resolved,
                neighborhood_override=override,
            )
            source = (live.neighborhood_source or "").strip()
            city = (live.city or "").strip()
            state = (live.state or "").strip()
            gemini = (live.neighborhood_gemini or "").strip()
            things = (live.neighborhood_things_to_do or "").strip()

            if display:
                status.set_text("")
            elif not status.text:
                status.set_text("Could not read a neighborhood from Zillow — set one below.")

            with body:
                with ui.row().classes("w-full items-baseline gap-3 flex-wrap"):
                    ui.label(display or "—").classes("hb-page-title")
                    ui.label(_source_label(source, has_override=bool(override))).classes(
                        "hb-page-meta"
                    )

                with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                    override_input = (
                        ui.input(
                            "Neighborhood (override)",
                            value=override or display,
                            placeholder="e.g. Mar Vista",
                        )
                        .props("dense outlined dark stack-label")
                        .classes("flex-grow")
                        .style("min-width: 220px; max-width: 420px;")
                    )

                    def save_override() -> None:
                        with get_session() as session:
                            PropertyService(session).update_property(
                                property_id,
                                neighborhood_override=override_input.value or "",
                            )
                        ui.notify("Neighborhood saved", type="positive")
                        redraw()

                    async def refresh_zillow() -> None:
                        status.set_text("Pulling neighborhood from Zillow…")
                        try:
                            data = await run.io_bound(
                                ensure_neighborhood_job, property_id, force=True
                            )
                            if (data.get("neighborhood_name") or "").strip():
                                ui.notify(
                                    "Neighborhood updated from Zillow", type="positive"
                                )
                            else:
                                ui.notify(
                                    "Zillow did not return a neighborhood name",
                                    type="warning",
                                )
                        except Exception as exc:  # noqa: BLE001
                            status.set_text(str(exc))
                            ui.notify(str(exc), type="negative")
                        redraw()

                    ui.button("Save name", on_click=save_override).props(
                        "unelevated dense color=dark"
                    ).classes("hb-btn-cta")
                    ui.button("Refresh from Zillow", on_click=refresh_zillow).props(
                        "unelevated dense color=dark"
                    )

                ui.separator().style("border-color: var(--hb-border);")

                ui.label("Assigned schools").classes("hb-section-title")
                schools_hint = ui.label("").classes("hb-page-hint")
                schools_row = ui.row().classes("w-full gap-3 flex-wrap")

                def render_school_cards(
                    schools: dict, *, not_found_text: str
                ) -> None:
                    schools_row.clear()
                    with schools_row:
                        for level_key, level_label, accent in _SCHOOL_LEVELS:
                            _render_school_card(
                                level_label,
                                accent,
                                schools.get(level_key),
                                not_found_text=not_found_text,
                            )

                _EMPTY_SCHOOLS = {"elementary": None, "middle": None, "high": None}
                schools_hint.set_text("Looking up assigned schools…")
                render_school_cards(_EMPTY_SCHOOLS, not_found_text="Loading…")

                async def load_assigned_schools() -> None:
                    lat = live.latitude
                    lng = live.longitude
                    try:
                        result = await run.io_bound(
                            resolve_assigned_schools_job, lat, lng
                        )
                    except Exception as exc:  # noqa: BLE001
                        result = {
                            "status": "error",
                            "message": f"Could not load assigned schools: {exc}",
                            "schools": dict(_EMPTY_SCHOOLS),
                        }

                    schools_hint.set_text(
                        _assigned_schools_caption(
                            result, has_keys=has_schooldigger_keys()
                        )
                    )

                    status_value = result.get("status")
                    not_found_text = "—" if status_value == "no_pin" else "Not found"
                    render_school_cards(
                        result.get("schools") or _EMPTY_SCHOOLS,
                        not_found_text=not_found_text,
                    )

                ui.timer(0.05, load_assigned_schools, once=True)

                ui.separator().style("border-color: var(--hb-border);")

                ui.label("Gemini neighborhood assessment").classes("hb-section-title")
                overview_box = ui.column().classes("w-full gap-2")
                overview_actions = ui.row().classes("w-full gap-2 flex-wrap")

                def render_overview(text: str) -> None:
                    overview_box.clear()
                    with overview_box:
                        if text:
                            ui.markdown(text).classes("hb-gemini-prose")
                        else:
                            ui.label(
                                "No overview yet — use Ask Gemini below for a candid "
                                "long-term take on this neighborhood (header Gemini "
                                "insights still works too)."
                            ).classes("hb-empty-state w-full")

                    overview_actions.clear()
                    with overview_actions:
                        ui.button(
                            "Ask Gemini about this neighborhood",
                            on_click=lambda: ask_overview(force=False),
                            icon="auto_awesome",
                        ).props("unelevated dense color=dark").classes("hb-btn-cta")
                        if text:
                            ui.button(
                                "Regenerate",
                                on_click=lambda: ask_overview(force=True),
                                icon="refresh",
                            ).props("unelevated dense color=dark")

                async def ask_overview(*, force: bool) -> None:
                    status.set_text("Asking Gemini for a neighborhood overview…")
                    try:
                        text = await run.io_bound(
                            ensure_gemini_overview_job, property_id, force=force
                        )
                        render_overview(text)
                        status.set_text("")
                        ui.notify(
                            "Neighborhood overview ready"
                            if force or text
                            else "Overview unchanged (cached)",
                            type="positive",
                        )
                    except Exception as exc:
                        status.set_text(str(exc))
                        ui.notify(str(exc), type="negative")

                render_overview(gemini)

                ui.label(
                    "Uses the neighborhood name above. Overview and things-to-do "
                    "are cached separately — regenerating one does not wipe the other."
                ).classes("hb-page-hint")

                ui.separator().style("border-color: var(--hb-border);")

                ui.label("Cool things to do nearby").classes("hb-section-title")
                things_box = ui.column().classes("w-full gap-2")
                things_actions = ui.row().classes("w-full gap-2 flex-wrap")

                def render_things(text: str) -> None:
                    things_box.clear()
                    with things_box:
                        if text:
                            ui.markdown(text).classes("hb-gemini-prose")
                        else:
                            ui.label(
                                "No list yet — use Ask Gemini below for walkable "
                                "spots with Google Maps links (header Gemini "
                                "insights still works too)."
                            ).classes("hb-empty-state w-full")

                    things_actions.clear()
                    with things_actions:
                        ui.button(
                            "Ask Gemini: things to do",
                            on_click=lambda: ask_things(force=False),
                            icon="auto_awesome",
                        ).props("unelevated dense color=dark").classes("hb-btn-cta")
                        if text:
                            ui.button(
                                "Regenerate",
                                on_click=lambda: ask_things(force=True),
                                icon="refresh",
                            ).props("unelevated dense color=dark")

                async def ask_things(*, force: bool) -> None:
                    status.set_text("Asking Gemini for things to do…")
                    try:
                        text = await run.io_bound(
                            ensure_gemini_things_to_do_job, property_id, force=force
                        )
                        render_things(text)
                        status.set_text("")
                        ui.notify(
                            "Things to do ready"
                            if force or text
                            else "Things to do unchanged (cached)",
                            type="positive",
                        )
                    except Exception as exc:
                        status.set_text(str(exc))
                        ui.notify(str(exc), type="negative")

                render_things(things)

                ui.separator().style("border-color: var(--hb-border);")

                with ui.expansion("More links & notes", icon="link").classes("w-full"):
                    if display:
                        links = build_review_deep_links(display, city=city, state=state)
                        with ui.row().classes("w-full flex-wrap gap-1 q-mb-md"):
                            _link_chip("Reddit search", links.reddit_search, icon="forum")
                            if links.city_subreddit:
                                _link_chip(
                                    f"r/{links.city_subreddit.rstrip('/').split('/')[-1]}",
                                    links.city_subreddit,
                                    icon="groups",
                                )
                            if links.city_data:
                                _link_chip(
                                    "City-Data", links.city_data, icon="location_city"
                                )
                            if links.niche:
                                _link_chip("Niche", links.niche, icon="star_outline")
                            _link_chip(
                                "Google · site:reddit.com",
                                links.google_site_reddit,
                                icon="travel_explore",
                            )

                    notes_area = (
                        ui.textarea(
                            value=live.neighborhood_notes or "",
                            placeholder="Your notes…",
                        )
                        .props("outlined dark autogrow dense stack-label")
                        .classes("w-full")
                    )

                    def save_notes() -> None:
                        with get_session() as session:
                            PropertyService(session).update_property(
                                property_id,
                                neighborhood_notes=notes_area.value or "",
                            )
                        ui.notify("Notes saved", type="positive")

                    ui.button("Save notes", on_click=save_notes).props(
                        "unelevated dense color=dark"
                    ).classes("hb-btn-cta").classes("q-mt-sm")

                ui.label(
                    "Gemini output is AI-generated and may be wrong — verify before deciding. "
                    "Neighborhood name is taken from the Zillow listing when available."
                ).classes("hb-page-hint q-mt-md")

        redraw(prop)


MODULE = ModuleSpec(
    id="neighborhood_reviews",
    title="Neighborhood",
    order=35,
    render=render,
)
