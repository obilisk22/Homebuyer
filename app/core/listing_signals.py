"""Listing-derived library risk chips (e.g. no Central AC, missing broadband).

UI (library / property header) should call ``listing_risk_chips(prop)`` and
render magenta risk chips beside nearby proximity icons.
"""
from __future__ import annotations

import re
from typing import Any, TypedDict

# Material icon name used by NiceGUI ui.icon
NO_CENTRAL_AC_ICON = "ac_unit"
NO_CENTRAL_AC_KEY = "no_central_ac"

_CENTRAL_RE = re.compile(
    r"\bcentral(?:\s+air|\s+a/?c|\s+ac|\s+cooling|\s+air\s*conditioning)?\b",
    re.IGNORECASE,
)
_NO_CENTRAL_RE = re.compile(
    r"(?:"
    r"\bwindow(?:\s+units?)?\b|"
    r"\bwall(?:\s+units?)?\b|"
    r"\bevaporative\b|"
    r"\bswamp(?:\s+cooler)?\b|"
    r"\bductless\b|"
    r"\bmini[\s-]?splits?\b|"
    r"\bno\s+a/?c\b|"
    r"\bno\s+air(?:\s*conditioning)?\b|"
    r"\bno\s+cooling\b|"
    r"^none$|"
    r"\bnone\b"
    r")",
    re.IGNORECASE,
)


class RiskChip(TypedDict):
    key: str
    kind: str
    icon: str
    tooltip: str


def format_cooling_label(cooling: str | None) -> str:
    return (cooling or "").strip()


def classify_has_central_ac(cooling: str | None) -> bool | None:
    """Return True/False only when cooling text clearly indicates central AC presence.

    Unknown / ambiguous labels → None (no library risk chip).
    """
    text = format_cooling_label(cooling)
    if not text:
        return None
    if _CENTRAL_RE.search(text):
        return True
    # Exact "None" or clear non-central systems
    folded = text.casefold().strip()
    if folded in {"none", "n/a", "na", "no", "false", "0"}:
        return False
    if _NO_CENTRAL_RE.search(text):
        return False
    return None


def central_ac_risk_entry(prop: Any) -> RiskChip | None:
    """Magenta risk chip only when listing clearly lacks Central AC."""
    flag = getattr(prop, "has_central_ac", None)
    if flag is not False:
        return None
    cooling = format_cooling_label(getattr(prop, "cooling", "") or "")
    detail = cooling if cooling else "Not listed as central"
    return {
        "key": NO_CENTRAL_AC_KEY,
        "kind": "risk",
        "icon": NO_CENTRAL_AC_ICON,
        "tooltip": f"No central AC · {detail}",
    }


def listing_risk_chips(prop: Any) -> list[RiskChip]:
    """Ordered listing-derived risk chips for library / header rows.

    Call from ``pages.py`` next to nearby proximity icons.
    Includes FCC BDC missing-broadband when ``prop.broadband_status`` is set.
    """
    from app.core.fcc_broadband import chip_spec_for, parse_status_json

    chips: list[RiskChip] = []
    ac = central_ac_risk_entry(prop)
    if ac is not None:
        chips.append(ac)
    bb = chip_spec_for(parse_status_json(getattr(prop, "broadband_status", None) or ""))
    if bb is not None:
        chips.append(bb)  # type: ignore[arg-type]
    return chips
