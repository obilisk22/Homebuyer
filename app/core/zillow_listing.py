from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.zillow_photos import NEXT_DATA_RE, fetch_listing_html

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
META_DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
META_DESC_RE_REV = re.compile(
    r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']description["\']',
    re.IGNORECASE,
)

# "$1,298,000 3 beds, 2 baths" / "3 bd, 2 ba"
PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
BEDS_RE = re.compile(r"([\d]+(?:\.\d+)?)\s*(?:beds?|bd|bedrooms?)\b", re.IGNORECASE)
BATHS_RE = re.compile(r"([\d]+(?:\.\d+)?)\s*(?:baths?|ba|bathrooms?)\b", re.IGNORECASE)
LOCATED_AT_RE = re.compile(
    r"located at\s+(.+?)\s+built in",
    re.IGNORECASE,
)

# Embedded JSON field patterns (gdpClientCache / __NEXT_DATA__)
JSON_PRICE_RE = re.compile(r'"price"\s*:\s*(\d+(?:\.\d+)?)')
JSON_BEDS_RE = re.compile(r'"(?:bedrooms|beds)"\s*:\s*(\d+(?:\.\d+)?)')
JSON_BATHS_RE = re.compile(
    r'"(?:bathrooms|baths|bathroomsFloat|numberOfBathroomsTotal)"\s*:\s*(\d+(?:\.\d+)?)'
)
JSON_CITY_RE = re.compile(r'"(?:city|addressLocality)"\s*:\s*"([^"]+)"')
JSON_STATE_RE = re.compile(r'"(?:state|addressRegion)"\s*:\s*"([^"]+)"')
JSON_ZIP_RE = re.compile(r'"(?:zipcode|zipCode|postalCode)"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class ListingDetails:
    list_price: float | None = None
    beds: float | None = None
    baths: float | None = None
    city: str = ""
    state: str = ""
    zip_code: str = ""
    address: str = ""

    def any_present(self) -> bool:
        return bool(
            self.list_price is not None
            or self.beds is not None
            or self.baths is not None
            or self.city
            or self.state
            or self.zip_code
            or self.address
        )


def _parse_float(raw: object) -> float | None:
    if raw is None or raw is False:
        return None
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _coalesce(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _coalesce_str(*values: str | None) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def parse_address_parts(address: str) -> tuple[str, str, str]:
    """Best-effort city / state / ZIP from a freeform US address."""
    text = (address or "").strip()
    if not text:
        return "", "", ""

    # "Street, City, ST 98116" or "Street, City, ST"
    m = re.search(
        r",\s*([^,]+?)\s*,\s*([A-Za-z]{2})(?:\s+(\d{5}(?:-\d{4})?))?\s*$",
        text,
    )
    if m:
        return m.group(1).strip(), m.group(2).upper(), (m.group(3) or "").strip()

    # Trailing "City ST 98116"
    m2 = re.search(r"([A-Za-z .'-]+)\s+([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)\s*$", text)
    if m2:
        return m2.group(1).strip(" ,"), m2.group(2).upper(), m2.group(3)

    return "", "", ""


def _from_ld_json(html: str) -> ListingDetails:
    price = beds = baths = None
    city = state = zip_code = address = ""

    for raw in LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            offers = blob.get("offers")
            if isinstance(offers, dict):
                price = _coalesce(price, _parse_float(offers.get("price")))
                item = offers.get("itemOffered")
                if isinstance(item, dict):
                    beds = _coalesce(
                        beds,
                        _parse_float(item.get("numberOfBedrooms")),
                        _parse_float(item.get("numberOfRooms")),
                    )
                    baths = _coalesce(
                        baths,
                        _parse_float(item.get("numberOfBathroomsTotal")),
                        _parse_float(item.get("numberOfBathrooms")),
                    )
                    addr = item.get("address")
                    if isinstance(addr, dict):
                        city = _coalesce_str(city, addr.get("addressLocality"))
                        state = _coalesce_str(state, addr.get("addressRegion"))
                        zip_code = _coalesce_str(zip_code, addr.get("postalCode"))
                        street = _coalesce_str(addr.get("streetAddress"))
                        if street:
                            bits = [street, city, f"{state} {zip_code}".strip()]
                            address = _coalesce_str(address, ", ".join(b for b in bits if b))
            beds = _coalesce(beds, _parse_float(blob.get("numberOfBedrooms")))
            baths = _coalesce(
                baths,
                _parse_float(blob.get("numberOfBathroomsTotal")),
                _parse_float(blob.get("numberOfBathrooms")),
            )
            addr = blob.get("address")
            if isinstance(addr, dict):
                city = _coalesce_str(city, addr.get("addressLocality"))
                state = _coalesce_str(state, addr.get("addressRegion"))
                zip_code = _coalesce_str(zip_code, addr.get("postalCode"))
                street = _coalesce_str(addr.get("streetAddress"))
                if street:
                    bits = [street, city, f"{state} {zip_code}".strip()]
                    address = _coalesce_str(address, ", ".join(b for b in bits if b))

    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
    )


def _from_meta_description(html: str) -> ListingDetails:
    m = META_DESC_RE.search(html) or META_DESC_RE_REV.search(html)
    if not m:
        return ListingDetails()
    desc = m.group(1)

    price = None
    pm = PRICE_RE.search(desc)
    if pm:
        price = _parse_float(pm.group(1))

    beds = baths = None
    bm = BEDS_RE.search(desc)
    if bm:
        beds = _parse_float(bm.group(1))
    am = BATHS_RE.search(desc)
    if am:
        baths = _parse_float(am.group(1))

    city = state = zip_code = ""
    address = ""
    loc = LOCATED_AT_RE.search(desc)
    if loc:
        address = loc.group(1).strip()
        city, state, zip_code = parse_address_parts(address)

    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
    )


def _first_json_float(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return _parse_float(m.group(1)) if m else None


def _first_json_str(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return (m.group(1).strip() if m else "") or ""


def _from_embedded_json(html: str) -> ListingDetails:
    """Scan __NEXT_DATA__ / gdpClientCache-style blobs for listing fields."""
    chunks: list[str] = []
    nd = NEXT_DATA_RE.search(html)
    if nd:
        chunks.append(nd.group(1))
    # Also scan a bounded slice of the full HTML for escaped JSON fields
    chunks.append(html[:500_000])

    price = beds = baths = None
    city = state = zip_code = ""
    for chunk in chunks:
        price = _coalesce(price, _first_json_float(JSON_PRICE_RE, chunk))
        beds = _coalesce(beds, _first_json_float(JSON_BEDS_RE, chunk))
        baths = _coalesce(baths, _first_json_float(JSON_BATHS_RE, chunk))
        city = _coalesce_str(city, _first_json_str(JSON_CITY_RE, chunk))
        state = _coalesce_str(state, _first_json_str(JSON_STATE_RE, chunk))
        zip_code = _coalesce_str(zip_code, _first_json_str(JSON_ZIP_RE, chunk))
        if price is not None and beds is not None and baths is not None and city:
            break

    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        city=city,
        state=state,
        zip_code=zip_code,
    )


def merge_listing_details(*parts: ListingDetails) -> ListingDetails:
    """Prefer earlier sources; fill gaps from later ones."""
    price = beds = baths = None
    city = state = zip_code = address = ""
    for part in parts:
        price = _coalesce(price, part.list_price)
        beds = _coalesce(beds, part.beds)
        baths = _coalesce(baths, part.baths)
        city = _coalesce_str(city, part.city)
        state = _coalesce_str(state, part.state)
        zip_code = _coalesce_str(zip_code, part.zip_code)
        address = _coalesce_str(address, part.address)
    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
    )


def extract_listing_details(html: str) -> ListingDetails:
    """Pull list price / beds / baths / city from Zillow listing HTML."""
    ld = _from_ld_json(html)
    meta = _from_meta_description(html)
    embedded = _from_embedded_json(html)
    # Prefer structured LD+JSON, then meta (good for baths), then embedded JSON.
    return merge_listing_details(ld, meta, embedded)


def fetch_listing_details(zillow_url: str) -> ListingDetails:
    html = fetch_listing_html(zillow_url)
    return extract_listing_details(html)
