from __future__ import annotations

from nicegui import ui

from app.core.api_keys import (
    ADVANCED_KEYS,
    KEY_SPECS,
    SECRET_KEYS,
    apply_env_updates,
    build_updates_from_form,
    key_is_set,
    status_label,
)
from app.core.paths import env_file
from app.ui.theme import apply_theme


def page_header(title: str, *, show_api_keys: bool = False) -> None:
    apply_theme()
    with ui.header().classes("hb-header items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "unelevated round dense color=dark"
            )
            brand = ui.label("Homebuy").classes("hb-brand").style("cursor: pointer")
            brand.on("click", lambda: ui.navigate.to("/"))
            ui.label(title).classes("hb-header-title")
        if show_api_keys:
            ui.button(
                icon="vpn_key",
                on_click=_open_api_keys_dialog,
            ).props("unelevated round dense color=dark flat").tooltip("API keys")


def _open_api_keys_dialog() -> None:
    """Library settings: paste user API keys into the local ``.env`` (not distributed)."""
    clear_flags: set[str] = set()
    inputs: dict = {}
    status_els: dict = {}

    with ui.dialog() as dialog, ui.card().classes("hb-api-keys-dialog w-full"):
        ui.label("API keys").classes("text-h6")
        ui.label(
            f"Stored only on this machine at {env_file()}. "
            "Never bundled with the app installer."
        ).classes("hb-page-hint")
        ui.label(
            "Leave a field blank to keep the current value. Use Clear to remove a key."
        ).classes("hb-page-hint q-mb-sm")

        def _row(spec) -> None:
            with ui.row().classes("w-full items-end gap-2 no-wrap"):
                with ui.column().classes("flex-grow gap-0"):
                    props = "dense outlined stack-label"
                    if spec.secret:
                        props += " type=password"
                    placeholder = (
                        "Leave blank to keep current"
                        if key_is_set(spec.name)
                        else "Paste key…"
                    )
                    inp = (
                        ui.input(spec.label, placeholder=placeholder)
                        .classes("w-full")
                        .props(props)
                    )
                    inputs[spec.name] = inp
                    help_bits = [spec.help]
                    if spec.signup_url:
                        help_bits.append(spec.signup_url)
                    ui.label(" · ".join(help_bits)).classes("hb-page-hint")
                st = ui.badge(status_label(spec.name)).props(
                    "outline color=grey-7" if not key_is_set(spec.name) else "color=positive"
                )
                status_els[spec.name] = st

                def _clear(name: str = spec.name) -> None:
                    clear_flags.add(name)
                    inputs[name].set_value("")
                    status_els[name].set_text("Will clear")
                    status_els[name].props(color="warning")

                ui.button("Clear", on_click=_clear).props("flat dense color=dark")

        for spec in KEY_SPECS:
            if spec.name in SECRET_KEYS:
                _row(spec)

        with ui.expansion("Advanced models", icon="tune").classes("w-full q-mt-sm"):
            for spec in KEY_SPECS:
                if spec.name in ADVANCED_KEYS:
                    _row(spec)

        def save() -> None:
            typed = {name: (inputs[name].value or "") for name in inputs}
            updates = build_updates_from_form(typed=typed, clear=clear_flags)
            if not updates:
                ui.notify("Nothing to change — enter a new key or Clear one.", type="info")
                return
            apply_env_updates(updates)
            ui.notify(
                "Saved. Restart Homebuy so every feature picks up the new keys.",
                type="positive",
            )
            dialog.close()

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("Cancel", on_click=dialog.close).props("flat dense color=dark")
            ui.button("Save", on_click=save).props(
                "unelevated dense color=dark"
            ).classes("hb-btn-cta")

    dialog.open()


from app.ui.chip_helpers import (  # noqa: F401
    HOA_HIGH_MONTHLY,
    _extra_signal_chips,
    _format_beds_baths,
    _format_hoa,
    _format_price,
    _format_price_per_sqft,
    _format_sqft,
    _format_year_built,
    _library_appreciation_caption,
    _library_appreciation_tone_class,
    _library_financial_caption,
    _library_primary_chips,
    _library_secondary_chips,
    _render_nearby_signal_chips,
    _render_street_address,
    _split_street_unit,
    _street_address_line,
    _truncate_notes,
)
from app.ui.library_page import library_page  # noqa: F401 — registers /
from app.ui.property_page import (  # noqa: F401 — registers /property
    PROPERTY_HEADER_PHOTO_MODE,
    property_page,
)
