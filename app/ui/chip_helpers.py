from __future__ import annotations

import html
import re
from types import SimpleNamespace

from nicegui import ui

from app.core.library_export import LibraryFinancialSnapshot
from app.core.nearby_signals import (
    ICON_BY_KEY,
    RISK_KEYS,
    hits_in_order,
    parse_signals_json,
    source_url_for,
    tooltip_for,
)
from app.core.listing_signals import listing_risk_chips
from app.core.market_activity import (
    chip_spec_for as market_chip_spec_for,
    parse_activity_json as parse_market_activity_json,
)
from app.core.permits_nearby import chip_spec_for, parse_activity_json

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
    market_activity: str = "",
    home_type: str = "",
    townhome_position: str = "",
) -> list[dict]:
    """Listing risk + permit amber + active-market chips for library / header."""
    chips: list[dict] = list(
        listing_risk_chips(
            SimpleNamespace(
                has_central_ac=has_central_ac,
                cooling=cooling or "",
                broadband_status=broadband_status or "",
                home_type=home_type or "",
                townhome_position=townhome_position or "",
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
    market = market_chip_spec_for(parse_market_activity_json(market_activity or ""))
    if market:
        chips.append(
            {
                "key": market["key"],
                "kind": market.get("tone") or "amenity",
                "tone": market.get("tone") or "amenity",
                "icon": market.get("icon") or "local_fire_department",
                "tooltip": market.get("tooltip") or "",
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


