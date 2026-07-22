"""User-editable API keys stored in the local ``.env`` file (never shipped in builds)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import env_file

SECRET_KEYS: tuple[str, ...] = (
    "GOOGLE_MAPS_API_KEY",
    "CENSUS_API_KEY",
    "GEMINI_API_KEY",
    "SOCRATA_APP_TOKEN",
)

ADVANCED_KEYS: tuple[str, ...] = (
    "GEMINI_MODEL",
    "GEMINI_FINANCIAL_MODEL",
)

MANAGED_KEYS: tuple[str, ...] = SECRET_KEYS + ADVANCED_KEYS

_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class KeySpec:
    name: str
    label: str
    help: str
    secret: bool = True
    signup_url: str = ""


KEY_SPECS: tuple[KeySpec, ...] = (
    KeySpec(
        "GOOGLE_MAPS_API_KEY",
        "Google Maps",
        "Geocoding + Places nearby (grocery/shelter). Optional — Nominatim works without it.",
        signup_url="https://console.cloud.google.com/google/maps-apis",
    ),
    KeySpec(
        "CENSUS_API_KEY",
        "Census Bureau",
        "Map ACS choropleths + Financials county tax / rent-growth estimates.",
        signup_url="https://api.census.gov/data/key_signup.html",
    ),
    KeySpec(
        "GEMINI_API_KEY",
        "Gemini",
        "Neighborhood overview / things-to-do + Financials commentary.",
        signup_url="https://aistudio.google.com/apikey",
    ),
    KeySpec(
        "SOCRATA_APP_TOKEN",
        "Socrata",
        "Optional — higher rate limits for crime overlays and permit lookups.",
        signup_url="https://dev.socrata.com/register",
    ),
    KeySpec(
        "GEMINI_MODEL",
        "Gemini model (Neighborhood)",
        "Default gemini-3.1-flash-lite",
        secret=False,
    ),
    KeySpec(
        "GEMINI_FINANCIAL_MODEL",
        "Gemini model (Financials)",
        "Default gemini-2.5-flash-lite",
        secret=False,
    ),
)

SPECS_BY_NAME = {s.name: s for s in KEY_SPECS}


def key_is_set(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def status_label(name: str) -> str:
    return "Set" if key_is_set(name) else "Missing"


def _iter_file_keys(text: str) -> list[tuple[str, str | None, str]]:
    """Rows: ('kv', key, line_with_ending) or ('other', None, line_with_ending)."""
    rows: list[tuple[str, str | None, str]] = []
    lines = text.splitlines(keepends=True)
    if not lines and text == "":
        return rows
    for line in lines:
        body = line.rstrip("\r\n")
        m = _KEY_LINE.match(body)
        if m and not body.lstrip().startswith("#"):
            rows.append(("kv", m.group(1), line))
        else:
            rows.append(("other", None, line))
    return rows


def apply_env_updates(updates: dict[str, str], *, path: Path | None = None) -> Path:
    """Merge ``updates`` into ``.env`` and ``os.environ``.

    Only keys present in ``updates`` change. Empty string clears the key.
    """
    path = path or env_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    rows = _iter_file_keys(existing)
    seen: set[str] = set()
    out: list[str] = []

    for kind, key, raw in rows:
        if kind == "kv" and key in updates:
            seen.add(key)
            ending = "\r\n" if raw.endswith("\r\n") else "\n"
            out.append(f"{key}={updates[key]}{ending}")
        else:
            out.append(raw if raw.endswith(("\n", "\r\n")) else raw + "\n")

    for key, val in updates.items():
        if key in seen or key not in MANAGED_KEYS:
            continue
        out.append(f"{key}={val}\n")

    path.write_text("".join(out), encoding="utf-8")

    for key, val in updates.items():
        if val == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    return path


def build_updates_from_form(
    *,
    typed: dict[str, str],
    clear: set[str],
) -> dict[str, str]:
    """Blank typed fields leave keys unchanged; ``clear`` wipes them."""
    updates: dict[str, str] = {}
    for key in MANAGED_KEYS:
        if key in clear:
            updates[key] = ""
            continue
        raw = (typed.get(key) or "").strip()
        if raw:
            updates[key] = raw
    return updates
