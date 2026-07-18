from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote_plus

import requests

NOMINATIM_USER_AGENT = "Homebuy/0.1 (local research app)"
REQUEST_TIMEOUT_S = 10

# Unit / apartment / suite designators that confuse geocoders when embedded
# mid-address (e.g. "650 Pacific St UNIT 8 Santa Monica CA 90405").
_UNIT_DESIGNATOR_RE = re.compile(
    r"""
    (?<![A-Za-z0-9])          # not mid-token
    (?:
        (?:apt|apartment|unit|ste|suite|bldg|building|fl|floor|rm|room)
        \.?\s*[#:]?\s*
        [A-Za-z0-9-]+         # unit id
      |
        \#\s*[A-Za-z0-9-]+    # bare "#8" / "# 8"
    )
    (?![A-Za-z0-9])           # not mid-token
    """,
    re.IGNORECASE | re.VERBOSE,
)

_STREET_SUFFIXES = frozenset(
    {
        "st",
        "street",
        "ave",
        "avenue",
        "blvd",
        "boulevard",
        "rd",
        "road",
        "dr",
        "drive",
        "ln",
        "lane",
        "way",
        "ct",
        "court",
        "pl",
        "place",
        "ter",
        "terrace",
        "cir",
        "circle",
        "hwy",
        "highway",
        "pkwy",
        "parkway",
    }
)


def strip_unit_designator(address: str) -> str:
    """Remove apt/unit/suite/# tokens from an address string."""
    text = (address or "").strip()
    if not text:
        return ""
    cleaned = _UNIT_DESIGNATOR_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    return cleaned.strip(" ,")


def _split_us_address(address: str) -> tuple[str, str, str, str] | None:
    """Best-effort (street, city, state, zip) for US freeform addresses."""
    text = (address or "").strip()
    if not text:
        return None

    # "Street, City, ST 98116" or "Street, City, ST"
    m = re.search(
        r"^(?P<street>.+?),\s*(?P<city>[^,]+?),\s*(?P<state>[A-Za-z]{2})"
        r"(?:\s+(?P<zip>\d{5}(?:-\d{4})?))?\s*$",
        text,
    )
    if m:
        return (
            m.group("street").strip(" ,"),
            m.group("city").strip(" ,"),
            m.group("state").upper(),
            (m.group("zip") or "").strip(),
        )

    # No-comma form ending in ST ZIP — split city after a street suffix when possible.
    m2 = re.search(
        r"^(?P<head>.+?)\s+(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)\s*$",
        text,
    )
    if not m2:
        return None

    head = m2.group("head").strip(" ,")
    state = m2.group("state").upper()
    zip_code = m2.group("zip")
    tokens = head.split()
    if len(tokens) < 2:
        return None

    for i, tok in enumerate(tokens):
        if tok.rstrip(".").casefold() in _STREET_SUFFIXES and i + 1 < len(tokens):
            street = " ".join(tokens[: i + 1])
            city = " ".join(tokens[i + 1 :])
            if city:
                return street, city, state, zip_code

    # Fallback: treat the last token as city when no street suffix is found.
    street = " ".join(tokens[:-1])
    city = tokens[-1]
    return street, city, state, zip_code


def geocode_query_candidates(address: str) -> list[str]:
    """Build ordered geocode query fallbacks from a freeform address.

    Tries the original string first, then without unit designators, then
    street + city + state + ZIP, then city + state + ZIP.
    """
    addr = (address or "").strip()
    if not addr:
        return []

    candidates: list[str] = [addr]
    without_unit = strip_unit_designator(addr)
    if without_unit and without_unit.casefold() != addr.casefold():
        candidates.append(without_unit)

    parts = _split_us_address(without_unit or addr)
    if parts:
        street, city, state, zip_code = parts
        if street and city and state:
            street_query = f"{street}, {city}, {state}"
            if zip_code:
                street_query = f"{street_query} {zip_code}"
            candidates.append(street_query)
        if city and state:
            city_query = f"{city}, {state}"
            if zip_code:
                city_query = f"{city_query} {zip_code}"
            candidates.append(city_query)

    # De-dupe while preserving order (case-insensitive).
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def geocode_address(address: str) -> tuple[float, float]:
    """Resolve an address string to (latitude, longitude).

    Prefers Google Geocoding API when ``GOOGLE_MAPS_API_KEY`` is set;
    otherwise uses OpenStreetMap Nominatim (no key required).

    Tries several normalized variants (full → without unit → street+city+ZIP
    → city+ZIP) so apartment/unit lines still pin to the building.
    """
    candidates = geocode_query_candidates(address)
    if not candidates:
        raise ValueError("Address is required to geocode.")

    api_key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    last_error: ValueError | None = None

    for query in candidates:
        if api_key:
            try:
                return _geocode_google(query, api_key)
            except ValueError as exc:
                last_error = exc
        try:
            return _geocode_nominatim(query)
        except ValueError as exc:
            last_error = exc

    original = candidates[0]
    if last_error is not None:
        raise ValueError(
            f"No geocoding results for address: {original}"
        ) from last_error
    raise ValueError(f"No geocoding results for address: {original}")


def _geocode_google(address: str, api_key: str) -> tuple[float, float]:
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={quote_plus(address)}&key={api_key}"
    )
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Google geocoding request failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Google geocoding returned invalid JSON: {exc}") from exc

    status = payload.get("status")
    if status != "OK":
        error = payload.get("error_message") or status or "unknown error"
        raise ValueError(f"Google geocoding failed: {error}")

    results = payload.get("results") or []
    if not results:
        raise ValueError(f"No geocoding results for address: {address}")

    location = (results[0].get("geometry") or {}).get("location") or {}
    try:
        lat = float(location["lat"])
        lng = float(location["lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Google geocoding response missing coordinates.") from exc
    return lat, lng


def _geocode_nominatim(address: str) -> tuple[float, float]:
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": NOMINATIM_USER_AGENT, "Accept": "application/json"}
    params = {"q": address, "format": "json", "limit": 1}
    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_S
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Nominatim geocoding request failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Nominatim geocoding returned invalid JSON: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise ValueError(f"No geocoding results for address: {address}")

    hit = payload[0]
    try:
        lat = float(hit["lat"])
        lng = float(hit["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Nominatim geocoding response missing coordinates.") from exc
    return lat, lng


# Prefer neighborhood-scale labels; skip city/county/state.
_NOMINATIM_NEIGHBORHOOD_KEYS = (
    "neighbourhood",
    "neighborhood",
    "suburb",
    "quarter",
    "city_district",
    "borough",
    "hamlet",
)


def _neighborhood_from_nominatim_address(addr: dict[str, Any]) -> str:
    for key in _NOMINATIM_NEIGHBORHOOD_KEYS:
        value = addr.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def reverse_geocode_neighborhood_nominatim(lat: float, lng: float) -> str:
    """Return a neighborhood-ish label from Nominatim reverse geocode."""
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {"User-Agent": NOMINATIM_USER_AGENT, "Accept": "application/json"}
    params = {
        "lat": lat,
        "lon": lng,
        "format": "json",
        "zoom": 16,
        "addressdetails": 1,
    }
    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_S
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Nominatim reverse geocode request failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Nominatim reverse geocode returned invalid JSON: {exc}") from exc

    addr = payload.get("address")
    if not isinstance(addr, dict):
        raise ValueError("Nominatim reverse geocode missing address details.")

    name = _neighborhood_from_nominatim_address(addr)
    if not name:
        raise ValueError("Nominatim reverse geocode found no neighborhood label.")
    return name


_GOOGLE_NEIGHBORHOOD_TYPES = (
    "neighborhood",
    "sublocality",
    "sublocality_level_1",
    "sublocality_level_2",
    "colloquial_area",
)


def reverse_geocode_neighborhood_google(lat: float, lng: float, api_key: str) -> str:
    """Return a neighborhood-ish label from Google Geocoding reverse lookup."""
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json"
        f"?latlng={lat},{lng}&key={api_key}"
    )
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"Google reverse geocode request failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Google reverse geocode returned invalid JSON: {exc}") from exc

    status = payload.get("status")
    if status != "OK":
        error = payload.get("error_message") or status or "unknown error"
        raise ValueError(f"Google reverse geocode failed: {error}")

    results = payload.get("results") or []
    for result in results:
        components = result.get("address_components") or []
        for type_name in _GOOGLE_NEIGHBORHOOD_TYPES:
            for comp in components:
                types = comp.get("types") or []
                if type_name in types:
                    name = (comp.get("long_name") or "").strip()
                    if name:
                        return name

    raise ValueError("Google reverse geocode found no neighborhood label.")


def reverse_geocode_neighborhood(lat: float, lng: float) -> tuple[str, str]:
    """Resolve a neighborhood label from coordinates.

    Prefers Nominatim (no key). If that fails and ``GOOGLE_MAPS_API_KEY`` is set,
    tries Google. Returns ``(name, source)`` where source is ``nominatim`` or
    ``google``.
    """
    last_error: ValueError | None = None
    try:
        return reverse_geocode_neighborhood_nominatim(lat, lng), "nominatim"
    except ValueError as exc:
        last_error = exc

    api_key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    if api_key:
        try:
            return reverse_geocode_neighborhood_google(lat, lng, api_key), "google"
        except ValueError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("Could not reverse-geocode neighborhood.")
