from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.zillow_photos import (
    NEXT_DATA_RE,
    _load_gdp_client_cache,
    _parse_next_data,
    fetch_listing_html,
)

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
SQFT_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?|square\s*feet|sqft)\b",
    re.IGNORECASE,
)
YEAR_BUILT_RE = re.compile(r"built\s+in\s+(\d{4})\b", re.IGNORECASE)
LOCATED_AT_RE = re.compile(
    r"located at\s+(.+?)\s+built in",
    re.IGNORECASE,
)
META_HOME_TYPE_RE = re.compile(
    r"\b(single\s+family(?:\s+home)?|townhouse|townhome|condo(?:minium)?|"
    r"multi[\s-]?family|manufactured|mobile\s+home|apartment|lot)\b",
    re.IGNORECASE,
)

# Embedded JSON field patterns (gdpClientCache / __NEXT_DATA__)
# Optional backslash escapes before quotes (gdpClientCache embeds JSON-as-string).
_Q = r'\\*"'

JSON_PRICE_RE = re.compile(_Q + r"price" + _Q + r"\s*:\s*(\d+(?:\.\d+)?)")
JSON_BEDS_RE = re.compile(
    _Q + r"(?:bedrooms|beds)" + _Q + r"\s*:\s*(\d+(?:\.\d+)?)"
)
JSON_BATHS_RE = re.compile(
    _Q
    + r"(?:bathrooms|baths|bathroomsFloat|numberOfBathroomsTotal)"
    + _Q
    + r"\s*:\s*(\d+(?:\.\d+)?)"
)
JSON_SQFT_RE = re.compile(
    _Q + r"(?:livingArea|livingAreaValue|livingAreaSquareFeet)" + _Q + r"\s*:\s*(\d+(?:\.\d+)?)"
)
JSON_HOA_RE = re.compile(
    _Q + r"(?:monthlyHoaFee|hoaFee|hoa)" + _Q + r"\s*:\s*(\d+(?:\.\d+)?)"
)
JSON_YEAR_RE = re.compile(_Q + r"yearBuilt" + _Q + r"\s*:\s*(\d{4})")
JSON_HOME_TYPE_RE = re.compile(
    _Q
    + r"(?:homeType|propertyTypeDimension|home_type)"
    + _Q
    + r"\s*:\s*"
    + _Q
    + r'([^"\\]+)'
    + _Q
)
JSON_CITY_RE = re.compile(
    _Q + r"(?:city|addressLocality)" + _Q + r"\s*:\s*" + _Q + r'([^"\\]+)' + _Q
)
JSON_STATE_RE = re.compile(
    _Q + r"(?:state|addressRegion)" + _Q + r"\s*:\s*" + _Q + r'([^"\\]+)' + _Q
)
JSON_ZIP_RE = re.compile(
    _Q + r"(?:zipcode|zipCode|postalCode)" + _Q + r"\s*:\s*" + _Q + r'([^"\\]+)' + _Q
)

JSON_NEIGHBORHOOD_RE = re.compile(
    _Q
    + r"(?:neighborhood|neighborhoodName|addr_neighborhood|communityName|regionName)"
    + _Q
    + r"\s*:\s*"
    + _Q
    + r'([^"\\]+)'
    + _Q
)
# Zillow parentRegion often holds the named neighborhood (not city/state).
# Keys may appear in any order (regionId before name is common).
JSON_PARENT_REGION_NAME_RE = re.compile(
    _Q
    + r"parentRegion"
    + _Q
    + r"\s*:\s*\{[^}]{0,500}?"
    + _Q
    + r"name"
    + _Q
    + r"\s*:\s*"
    + _Q
    + r'([^"\\]+)'
    + _Q,
    re.DOTALL,
)
# adTargets.hood e.g. "Ocean_Park"
JSON_HOOD_RE = re.compile(_Q + r"hood" + _Q + r"\s*:\s*" + _Q + r'([^"\\]+)' + _Q)
# regionType 8 is typically neighborhood on Zillow.
JSON_REGION_TYPE_8_NAME_RE = re.compile(
    _Q
    + r"regionType"
    + _Q
    + r"\s*:\s*8\s*,\s*"
    + _Q
    + r"name"
    + _Q
    + r"\s*:\s*"
    + _Q
    + r'([^"\\]+)'
    + _Q
    + r"|"
    + _Q
    + r"name"
    + _Q
    + r"\s*:\s*"
    + _Q
    + r'([^"\\]+)'
    + _Q
    + r"\s*,\s*"
    + _Q
    + r"regionType"
    + _Q
    + r"\s*:\s*8"
)
# Breadcrumb-style path: /los-angeles-ca/mar-vista/
BREADCRUMB_NEIGHBORHOOD_RE = re.compile(
    r'href="https?://www\.zillow\.com/[a-z0-9-]+/[a-z0-9-]+/"[^>]*>\s*([^<]{2,60})\s*<',
    re.IGNORECASE,
)

# Zillow homeType / schema.org @type → readable label
_HOME_TYPE_MAP: dict[str, str] = {
    "single_family": "Single Family",
    "singlefamily": "Single Family",
    "single family": "Single Family",
    "single family home": "Single Family",
    "singlefamilyresidence": "Single Family",
    "house": "Single Family",
    "condo": "Condo",
    "condominium": "Condo",
    "apartment": "Apartment",
    "townhouse": "Townhouse",
    "townhome": "Townhouse",
    "multi_family": "Multi Family",
    "multifamily": "Multi Family",
    "multi-family": "Multi Family",
    "multi family": "Multi Family",
    "manufactured": "Manufactured",
    "manufacturedhome": "Manufactured",
    "mobile": "Manufactured",
    "mobile home": "Manufactured",
    "lot": "Lot",
    "land": "Lot",
}

# Keys that mark a Zillow property payload worth reading for listing facts.
_PROPERTY_FACT_KEYS = (
    "livingArea",
    "livingAreaValue",
    "yearBuilt",
    "homeType",
    "monthlyHoaFee",
    "hoaFee",
    "bedrooms",
    "bathrooms",
    "price",
    "zpid",
)


@dataclass(frozen=True)
class ListingDetails:
    list_price: float | None = None
    beds: float | None = None
    baths: float | None = None
    sqft: float | None = None
    hoa_fee: float | None = None
    year_built: int | None = None
    home_type: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    address: str = ""
    neighborhood: str = ""

    def any_present(self) -> bool:
        return bool(
            self.list_price is not None
            or self.beds is not None
            or self.baths is not None
            or self.sqft is not None
            or self.hoa_fee is not None
            or self.year_built is not None
            or self.home_type
            or self.city
            or self.state
            or self.zip_code
            or self.address
            or self.neighborhood
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


def _parse_int(raw: object) -> int | None:
    value = _parse_float(raw)
    if value is None:
        return None
    # Reject non-year-like or fractional junk for year_built.
    if value != int(value):
        return None
    return int(value)


def _coalesce(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _coalesce_int(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None


def _coalesce_str(*values: str | None) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def normalize_home_type(raw: object) -> str:
    """Map Zillow / schema.org home-type tokens to a short readable label."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # schema.org @type may be a list
    key = re.sub(r"[\s\-]+", " ", text).strip()
    key_compact = key.replace(" ", "").replace("_", "").casefold()
    key_spaced = key.casefold()
    for candidate in (key_spaced, key_compact, key_spaced.replace(" ", "_")):
        mapped = _HOME_TYPE_MAP.get(candidate)
        if mapped:
            return mapped
    # Already human-readable (e.g. "Condo" from propertyTypeDimension)
    if text[:1].isupper() and len(text) < 40 and not text.isupper():
        return text
    # Title-case unknown SCREAMING_SNAKE
    if "_" in text or text.isupper():
        return text.replace("_", " ").title()
    return text


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


def _neighborhood_from_addr_dict(addr: dict) -> str:
    for key in ("neighborhood", "addressNeighborhood", "district"):
        value = addr.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _home_type_from_schema_types(types: object) -> str:
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        return ""
    for t in types:
        if not isinstance(t, str):
            continue
        # Skip generic Product / RealEstateListing wrappers
        if t in {"Product", "RealEstateListing", "Place", "Residence"}:
            continue
        label = normalize_home_type(t)
        if label:
            return label
    return ""


def _details_from_property_dict(obj: dict) -> ListingDetails:
    """Pull listing facts from a Zillow `property`-like dict."""
    price = _coalesce(
        _parse_float(obj.get("price")),
        _parse_float(obj.get("listPrice")),
        _parse_float(obj.get("unformattedPrice")),
    )
    beds = _coalesce(
        _parse_float(obj.get("bedrooms")),
        _parse_float(obj.get("beds")),
    )
    baths = _coalesce(
        _parse_float(obj.get("bathrooms")),
        _parse_float(obj.get("baths")),
        _parse_float(obj.get("bathroomsFloat")),
    )
    sqft = _coalesce(
        _parse_float(obj.get("livingArea")),
        _parse_float(obj.get("livingAreaValue")),
        _parse_float(obj.get("livingAreaSquareFeet")),
        _parse_float(obj.get("finishedSqFt")),
    )
    hoa = _coalesce(
        _parse_float(obj.get("monthlyHoaFee")),
        _parse_float(obj.get("hoaFee")),
        _parse_float(obj.get("hoa")),
    )
    year = _coalesce_int(_parse_int(obj.get("yearBuilt")))
    home_type = _coalesce_str(
        normalize_home_type(obj.get("homeType")),
        normalize_home_type(obj.get("propertyTypeDimension")),
        normalize_home_type(obj.get("home_type")),
    )
    city = _coalesce_str(obj.get("city"), obj.get("addressLocality"))
    state = _coalesce_str(obj.get("state"), obj.get("addressRegion"))
    zip_code = _coalesce_str(obj.get("zipcode"), obj.get("zipCode"), obj.get("postalCode"))
    neighborhood = ""
    parent = obj.get("parentRegion")
    if isinstance(parent, dict):
        neighborhood = _plausible_neighborhood(
            str(parent.get("name") or ""), city=city, state=state
        )
    addr = obj.get("address")
    if isinstance(addr, dict):
        city = _coalesce_str(city, addr.get("city"), addr.get("addressLocality"))
        state = _coalesce_str(state, addr.get("state"), addr.get("addressRegion"))
        zip_code = _coalesce_str(
            zip_code, addr.get("zipcode"), addr.get("zipCode"), addr.get("postalCode")
        )
        neighborhood = _coalesce_str(
            neighborhood, _neighborhood_from_addr_dict(addr)
        )
    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        hoa_fee=hoa,
        year_built=year,
        home_type=home_type,
        city=city,
        state=state,
        zip_code=zip_code,
        neighborhood=neighborhood,
    )


def _iter_property_fact_dicts(cache: dict) -> list[dict]:
    found: list[dict] = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            if any(k in obj for k in _PROPERTY_FACT_KEYS):
                # Prefer objects that look like the main property payload.
                if "zpid" in obj or "livingArea" in obj or "homeType" in obj:
                    found.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(cache)
    return found


def _from_gdp_cache(html: str) -> ListingDetails:
    """Walk unescaped gdpClientCache JSON for listing fields (preferred path)."""
    next_data = _parse_next_data(html)
    cache = _load_gdp_client_cache(html, next_data)
    if not cache:
        return ListingDetails()

    best = ListingDetails()
    best_score = -1
    for obj in _iter_property_fact_dicts(cache):
        details = _details_from_property_dict(obj)
        score = sum(
            [
                details.list_price is not None,
                details.beds is not None,
                details.baths is not None,
                details.sqft is not None,
                details.hoa_fee is not None,
                details.year_built is not None,
                bool(details.home_type),
                bool(details.city),
            ]
        )
        if score > best_score:
            best = details
            best_score = score
    return best


def _floor_size_sqft(blob: dict) -> float | None:
    floor = blob.get("floorSize")
    if isinstance(floor, dict):
        return _parse_float(floor.get("value"))
    return _parse_float(blob.get("floorSize"))


def _from_ld_json(html: str) -> ListingDetails:
    price = beds = baths = sqft = hoa = None
    year: int | None = None
    city = state = zip_code = address = neighborhood = home_type = ""

    for raw in LD_JSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            home_type = _coalesce_str(
                home_type, _home_type_from_schema_types(blob.get("@type"))
            )
            offers = blob.get("offers")
            if isinstance(offers, dict):
                price = _coalesce(price, _parse_float(offers.get("price")))
                item = offers.get("itemOffered")
                if isinstance(item, dict):
                    home_type = _coalesce_str(
                        home_type, _home_type_from_schema_types(item.get("@type"))
                    )
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
                    sqft = _coalesce(sqft, _floor_size_sqft(item))
                    year = _coalesce_int(year, _parse_int(item.get("yearBuilt")))
                    addr = item.get("address")
                    if isinstance(addr, dict):
                        city = _coalesce_str(city, addr.get("addressLocality"))
                        state = _coalesce_str(state, addr.get("addressRegion"))
                        zip_code = _coalesce_str(zip_code, addr.get("postalCode"))
                        neighborhood = _coalesce_str(
                            neighborhood, _neighborhood_from_addr_dict(addr)
                        )
                        street = _coalesce_str(addr.get("streetAddress"))
                        if street:
                            bits = [street, city, f"{state} {zip_code}".strip()]
                            address = _coalesce_str(
                                address, ", ".join(b for b in bits if b)
                            )
            beds = _coalesce(beds, _parse_float(blob.get("numberOfBedrooms")))
            baths = _coalesce(
                baths,
                _parse_float(blob.get("numberOfBathroomsTotal")),
                _parse_float(blob.get("numberOfBathrooms")),
            )
            sqft = _coalesce(sqft, _floor_size_sqft(blob))
            year = _coalesce_int(year, _parse_int(blob.get("yearBuilt")))
            addr = blob.get("address")
            if isinstance(addr, dict):
                city = _coalesce_str(city, addr.get("addressLocality"))
                state = _coalesce_str(state, addr.get("addressRegion"))
                zip_code = _coalesce_str(zip_code, addr.get("postalCode"))
                neighborhood = _coalesce_str(
                    neighborhood, _neighborhood_from_addr_dict(addr)
                )
                street = _coalesce_str(addr.get("streetAddress"))
                if street:
                    bits = [street, city, f"{state} {zip_code}".strip()]
                    address = _coalesce_str(address, ", ".join(b for b in bits if b))

    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        hoa_fee=hoa,
        year_built=year,
        home_type=home_type,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
        neighborhood=neighborhood,
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

    beds = baths = sqft = None
    year: int | None = None
    bm = BEDS_RE.search(desc)
    if bm:
        beds = _parse_float(bm.group(1))
    am = BATHS_RE.search(desc)
    if am:
        baths = _parse_float(am.group(1))
    sm = SQFT_RE.search(desc)
    if sm:
        sqft = _parse_float(sm.group(1))
    ym = YEAR_BUILT_RE.search(desc)
    if ym:
        year = _parse_int(ym.group(1))

    home_type = ""
    hm = META_HOME_TYPE_RE.search(desc)
    if hm:
        home_type = normalize_home_type(hm.group(1))

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
        sqft=sqft,
        year_built=year,
        home_type=home_type,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
    )


def _first_json_float(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return _parse_float(m.group(1)) if m else None


def _first_json_int(pattern: re.Pattern[str], text: str) -> int | None:
    m = pattern.search(text)
    return _parse_int(m.group(1)) if m else None


def _first_json_str(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    # Some patterns have alternate capture groups (regionType 8).
    for i in range(1, (m.lastindex or 0) + 1):
        val = m.group(i)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _plausible_neighborhood(name: str, *, city: str = "", state: str = "") -> str:
    """Reject labels that are clearly city/state rather than a neighborhood."""
    text = (name or "").strip().replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > 80:
        return ""
    lower = text.casefold()
    if city and lower == city.strip().casefold():
        return ""
    if state and lower == state.strip().casefold():
        return ""
    # Common non-neighborhood parentRegion values
    if lower in {"united states", "usa", "us"}:
        return ""
    return text


def _first_region_type_8(text: str) -> str:
    m = JSON_REGION_TYPE_8_NAME_RE.search(text)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip()


def _hood_from_ad_targets(text: str) -> str:
    m = JSON_HOOD_RE.search(text)
    if not m:
        return ""
    return (m.group(1) or "").strip().replace("_", " ")


def _breadcrumb_neighborhood(html: str, *, city: str = "") -> str:
    """Pick a breadcrumb label that is not the city name."""
    city_l = (city or "").strip().casefold()
    for m in BREADCRUMB_NEIGHBORHOOD_RE.finditer(html):
        label = (m.group(1) or "").strip()
        if not label:
            continue
        if city_l and label.casefold() == city_l:
            continue
        if label.casefold() in {"homes for sale", "for sale", "zillow"}:
            continue
        return label
    return ""


def _from_embedded_json(html: str) -> ListingDetails:
    """Scan __NEXT_DATA__ / gdpClientCache-style blobs for listing fields (regex fallback)."""
    chunks: list[str] = []
    nd = NEXT_DATA_RE.search(html)
    if nd:
        chunks.append(nd.group(1))
    # Also scan a bounded slice of the full HTML for escaped JSON fields
    chunks.append(html[:800_000])

    price = beds = baths = sqft = hoa = None
    year: int | None = None
    city = state = zip_code = neighborhood = home_type = ""
    for chunk in chunks:
        price = _coalesce(price, _first_json_float(JSON_PRICE_RE, chunk))
        beds = _coalesce(beds, _first_json_float(JSON_BEDS_RE, chunk))
        baths = _coalesce(baths, _first_json_float(JSON_BATHS_RE, chunk))
        sqft = _coalesce(sqft, _first_json_float(JSON_SQFT_RE, chunk))
        hoa = _coalesce(hoa, _first_json_float(JSON_HOA_RE, chunk))
        year = _coalesce_int(year, _first_json_int(JSON_YEAR_RE, chunk))
        home_type = _coalesce_str(
            home_type, normalize_home_type(_first_json_str(JSON_HOME_TYPE_RE, chunk))
        )
        city = _coalesce_str(city, _first_json_str(JSON_CITY_RE, chunk))
        state = _coalesce_str(state, _first_json_str(JSON_STATE_RE, chunk))
        zip_code = _coalesce_str(zip_code, _first_json_str(JSON_ZIP_RE, chunk))
        neighborhood = _coalesce_str(
            neighborhood,
            _plausible_neighborhood(
                _first_json_str(JSON_PARENT_REGION_NAME_RE, chunk),
                city=city,
                state=state,
            ),
            _plausible_neighborhood(
                _hood_from_ad_targets(chunk), city=city, state=state
            ),
            _plausible_neighborhood(
                _first_json_str(JSON_NEIGHBORHOOD_RE, chunk), city=city, state=state
            ),
            _plausible_neighborhood(_first_region_type_8(chunk), city=city, state=state),
        )
        if (
            price is not None
            and beds is not None
            and baths is not None
            and sqft is not None
            and city
            and neighborhood
            and home_type
        ):
            break

    if not neighborhood:
        neighborhood = _plausible_neighborhood(
            _breadcrumb_neighborhood(html, city=city), city=city, state=state
        )

    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        hoa_fee=hoa,
        year_built=year,
        home_type=home_type,
        city=city,
        state=state,
        zip_code=zip_code,
        neighborhood=neighborhood,
    )


def merge_listing_details(*parts: ListingDetails) -> ListingDetails:
    """Prefer earlier sources; fill gaps from later ones."""
    price = beds = baths = sqft = hoa = None
    year: int | None = None
    city = state = zip_code = address = neighborhood = home_type = ""
    for part in parts:
        price = _coalesce(price, part.list_price)
        beds = _coalesce(beds, part.beds)
        baths = _coalesce(baths, part.baths)
        sqft = _coalesce(sqft, part.sqft)
        hoa = _coalesce(hoa, part.hoa_fee)
        year = _coalesce_int(year, part.year_built)
        home_type = _coalesce_str(home_type, part.home_type)
        city = _coalesce_str(city, part.city)
        state = _coalesce_str(state, part.state)
        zip_code = _coalesce_str(zip_code, part.zip_code)
        address = _coalesce_str(address, part.address)
        neighborhood = _coalesce_str(neighborhood, part.neighborhood)
    return ListingDetails(
        list_price=price,
        beds=beds,
        baths=baths,
        sqft=sqft,
        hoa_fee=hoa,
        year_built=year,
        home_type=home_type,
        city=city,
        state=state,
        zip_code=zip_code,
        address=address,
        neighborhood=neighborhood,
    )


def extract_listing_details(html: str) -> ListingDetails:
    """Pull list price / beds / baths / sqft / HOA / year / type from Zillow HTML."""
    gdp = _from_gdp_cache(html)
    ld = _from_ld_json(html)
    meta = _from_meta_description(html)
    embedded = _from_embedded_json(html)
    # Prefer structured gdpClientCache, then LD+JSON, meta, then regex scan.
    merged = merge_listing_details(gdp, ld, meta, embedded)
    # Neighborhood labels are most reliable in Zillow's embedded JSON / breadcrumbs.
    neighborhood = (
        gdp.neighborhood
        or embedded.neighborhood
        or merged.neighborhood
    )
    if neighborhood and neighborhood != merged.neighborhood:
        return ListingDetails(
            list_price=merged.list_price,
            beds=merged.beds,
            baths=merged.baths,
            sqft=merged.sqft,
            hoa_fee=merged.hoa_fee,
            year_built=merged.year_built,
            home_type=merged.home_type,
            city=merged.city,
            state=merged.state,
            zip_code=merged.zip_code,
            address=merged.address,
            neighborhood=neighborhood,
        )
    return merged


def fetch_listing_details(zillow_url: str) -> ListingDetails:
    html = fetch_listing_html(zillow_url)
    return extract_listing_details(html)
