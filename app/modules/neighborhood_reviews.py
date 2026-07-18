"""Neighborhood — Zillow name + Gemini overview (+ optional deep links)."""

from __future__ import annotations

from nicegui import ui

from app.core.db import get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.neighborhood import (
    build_review_deep_links,
    effective_neighborhood_name,
)
from app.core.property_service import PropertyService

_SOURCE_LABELS = {
    "zillow": "From Zillow listing",
    "nominatim": "OpenStreetMap Nominatim",
    "google": "Google Geocoding",
}


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
        f'outline dense color=primary icon={icon} href="{url}" target=_blank'
    ).classes("q-mr-xs q-mb-xs")


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id

    with container:
        status = ui.label("").classes("text-caption text-grey-7")
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

        def ensure_name() -> Property | None:
            with get_session() as session:
                fresh = PropertyService(session).get_property(property_id)
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

        def redraw() -> None:
            live = ensure_name() or load()
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

            if display:
                status.set_text("")
            elif not status.text:
                status.set_text("Could not read a neighborhood from Zillow — set one below.")

            with body:
                with ui.row().classes("w-full items-baseline gap-3 flex-wrap"):
                    ui.label(display or "—").classes("text-h5").style(
                        "color: var(--hb-neon); text-shadow: 0 0 12px rgba(0, 229, 255, 0.35);"
                    )
                    ui.label(_source_label(source, has_override=bool(override))).classes(
                        "text-caption text-grey-7"
                    )

                with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                    override_input = (
                        ui.input(
                            "Neighborhood (override)",
                            value=override or display,
                            placeholder="e.g. Mar Vista",
                        )
                        .props("dense outlined dark")
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

                    def refresh_zillow() -> None:
                        live2 = resolve_name()
                        if live2 and (live2.neighborhood_name or "").strip():
                            ui.notify("Neighborhood updated from Zillow", type="positive")
                        else:
                            ui.notify(
                                "Zillow did not return a neighborhood name",
                                type="warning",
                            )
                        redraw()

                    ui.button("Save name", on_click=save_override).props(
                        "unelevated color=primary"
                    )
                    ui.button("Refresh from Zillow", on_click=refresh_zillow).props(
                        "outline dense"
                    )

                ui.separator().style("border-color: var(--hb-border);")

                ui.label("Gemini overview").classes("text-subtitle1").style(
                    "color: var(--hb-neon-2);"
                )
                overview_box = ui.column().classes("w-full gap-2")

                def render_overview(text: str) -> None:
                    overview_box.clear()
                    with overview_box:
                        if text:
                            ui.markdown(text).classes("text-body1").style(
                                "line-height: 1.65; color: #E8ECF2; max-width: 52rem;"
                            )
                        else:
                            ui.label(
                                "Generate a short AI overview of how this neighborhood feels "
                                "and what’s nearby."
                            ).classes("text-caption text-grey-7")

                render_overview(gemini)

                def ask_gemini(*, force: bool = False) -> None:
                    if not display and not (override_input.value or "").strip():
                        ui.notify("Set a neighborhood name first", type="warning")
                        return
                    # Persist override field if user typed a new name without saving
                    typed = (override_input.value or "").strip()
                    if typed and typed != override:
                        with get_session() as session:
                            PropertyService(session).update_property(
                                property_id, neighborhood_override=typed
                            )
                    status.set_text("Asking Gemini…")
                    try:
                        with get_session() as session:
                            PropertyService(session).ensure_gemini_overview(
                                property_id, force=force
                            )
                        status.set_text("")
                        ui.notify("Overview ready", type="positive")
                    except Exception as exc:
                        status.set_text("")
                        ui.notify(str(exc), type="negative")
                    redraw()

                with ui.row().classes("gap-2 flex-wrap"):
                    ui.button(
                        "Ask Gemini about this neighborhood",
                        on_click=lambda: ask_gemini(force=False),
                        icon="auto_awesome",
                    ).props("unelevated color=secondary")
                    if gemini:
                        ui.button(
                            "Regenerate",
                            on_click=lambda: ask_gemini(force=True),
                            icon="refresh",
                        ).props("outline dense")

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
                        .props("outlined dark autogrow")
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
                        "unelevated dense color=primary"
                    ).classes("q-mt-sm")

                ui.label(
                    "Gemini output is AI-generated and may be wrong — verify before deciding. "
                    "Neighborhood name is taken from the Zillow listing when available."
                ).classes("text-caption text-grey-7 q-mt-md")

        redraw()


MODULE = ModuleSpec(
    id="neighborhood_reviews",
    title="Neighborhood",
    order=35,
    render=render,
)
