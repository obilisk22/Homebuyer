from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from curl_cffi import requests as curl_requests

PHOTO_URL_RE = re.compile(
    r"https://photos\.zillowstatic\.com/fp/([a-f0-9]+)-([A-Za-z0-9_]+)\.(jpg|webp)",
    re.IGNORECASE,
)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
GDP_CACHE_RE = re.compile(r'"gdpClientCache"\s*:\s*"((?:\\.|[^"\\])*)"')
ZPID_IN_URL_RE = re.compile(r"/(\d+)_zpid", re.I)
OG_TITLE_RE = re.compile(
    r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
    re.I,
)
OG_TITLE_RE_REV = re.compile(
    r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']og:title["\']',
    re.I,
)

# Variants that are tiny UI chrome / maps / logos — skip.
SKIP_VARIANT_BITS = (
    "zillow_web",
    "sc_",
    "p_c",
    "p_e",
    "p_h",
    "dots",
    "map",
    "logo",
)

# Gallery arrays on the primary `property` object inside gdpClientCache.
PHOTO_ARRAY_KEYS = (
    "originalPhotos",
    "responsivePhotosOriginalRatio",
    "responsivePhotos",
    "hugePhotos",
)

# Prefer originalPhotos (has o_a / uncropped) when present.
PREFERRED_PHOTO_ARRAY_KEYS = (
    "originalPhotos",
    "responsivePhotosOriginalRatio",
    "responsivePhotos",
    "hugePhotos",
)


@dataclass(frozen=True)
class FetchedListingPhotos:
    urls: list[str]
    raw_html_bytes: int


def _score_variant(variant: str, ext: str) -> int:
    variant_l = variant.lower()
    if any(bit in variant_l for bit in SKIP_VARIANT_BITS):
        return -1

    score = 0
    if variant_l.startswith("o_a") or variant_l in {"unc_f", "p_f"}:
        score = 50_000
    else:
        m = re.search(r"cc_ft_(\d+)", variant_l)
        if m:
            score = int(m.group(1))
        elif m := re.search(r"uncropped_scaled_within_(\d+)", variant_l):
            score = int(m.group(1))
        elif variant_l.startswith("cc_"):
            score = 500
        else:
            score = 10

    if ext.lower() == "webp":
        score -= 1
    return score


def _best_urls_for_matches(matches: list[tuple[str, str, str, int]]) -> list[str]:
    """Pick best URL per hash from (hid, variant, ext, order_index) matches."""
    best: dict[str, tuple[int, str, int]] = {}
    for hid, variant, ext, index in matches:
        score = _score_variant(variant, ext)
        if score < 1_000:
            continue
        use_ext = (
            "jpg"
            if ext.lower() == "webp"
            and (
                variant.lower().startswith("o_a")
                or "cc_ft_" in variant.lower()
                or "uncropped_scaled_within_" in variant.lower()
                or variant.lower() in {"p_f", "unc_f"}
            )
            else ext
        )
        url = f"https://photos.zillowstatic.com/fp/{hid}-{variant}.{use_ext}"
        prev = best.get(hid)
        if prev is None:
            best[hid] = (score, url, index)
        elif score > prev[0]:
            best[hid] = (score, url, prev[2])

    ordered = sorted(best.items(), key=lambda kv: kv[1][2])
    return [url for _, (_, url, _) in ordered]


def _urls_from_regex_scan(html: str) -> list[str]:
    """Legacy: scan entire HTML for photo URLs (may include similar-homes)."""
    matches = [
        (hid, variant, ext, index)
        for index, (hid, variant, ext) in enumerate(PHOTO_URL_RE.findall(html))
    ]
    return _best_urls_for_matches(matches)


def _parse_next_data(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _load_gdp_client_cache(html: str, next_data: dict | None = None) -> dict | None:
    """Unescape and parse gdpClientCache from __NEXT_DATA__ or raw HTML."""

    def _from_escaped(escaped: str) -> dict | None:
        try:
            cache_str = json.loads(f'"{escaped}"')
            cache = json.loads(cache_str)
            return cache if isinstance(cache, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def _walk_for_cache(obj: object) -> dict | None:
        if isinstance(obj, dict):
            raw = obj.get("gdpClientCache")
            if isinstance(raw, str) and raw.strip().startswith("{"):
                try:
                    cache = json.loads(raw)
                    if isinstance(cache, dict):
                        return cache
                except json.JSONDecodeError:
                    pass
            if isinstance(raw, dict):
                return raw
            for v in obj.values():
                found = _walk_for_cache(v)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for v in obj:
                found = _walk_for_cache(v)
                if found is not None:
                    return found
        return None

    if next_data is not None:
        found = _walk_for_cache(next_data)
        if found is not None:
            return found

    m = GDP_CACHE_RE.search(html)
    if m:
        return _from_escaped(m.group(1))
    return None


def zpid_from_zillow_url(zillow_url: str | None) -> str | None:
    if not zillow_url:
        return None
    m = ZPID_IN_URL_RE.search(zillow_url)
    return m.group(1) if m else None


def _zpid_from_next_data(next_data: dict | None) -> str | None:
    if not next_data:
        return None

    try:
        props = next_data.get("props") or {}
        page = props.get("pageProps") or {}
        comp = page.get("componentProps") or {}
        gqv = comp.get("gdpQueryVariables") or {}
        if gqv.get("zpid") is not None:
            return str(gqv["zpid"])
        if comp.get("zpid") is not None:
            return str(comp["zpid"])
    except (TypeError, AttributeError):
        pass
    return None


def _iter_property_objects(cache: dict) -> list[dict]:
    """Return dicts that look like a Zillow `property` payload with photos."""
    found: list[dict] = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            if "zpid" in obj and any(k in obj for k in PHOTO_ARRAY_KEYS):
                found.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(cache)
    return found


def _normalize_addr_tokens(text: str) -> list[str]:
    text = unquote(text or "").lower()
    text = text.replace("-", " ")
    return re.findall(r"[a-z0-9]+", text)


def _street_number(tokens: list[str]) -> str | None:
    return tokens[0] if tokens and tokens[0].isdigit() else None


def _listing_address_mismatch(
    prop: dict,
    *,
    zillow_url: str | None,
    html: str,
) -> bool:
    """True when structured street address clearly disagrees with the URL slug / og:title."""
    street = str(prop.get("streetAddress") or "").strip()
    if not street:
        return False

    street_tokens = _normalize_addr_tokens(street)
    street_num = _street_number(street_tokens)
    if not street_num:
        return False

    candidates: list[str] = []
    if zillow_url:
        path = unquote(urlparse(zillow_url).path or "")
        m = re.search(r"/homedetails/([^/]+)/", path, re.I)
        if m:
            candidates.append(m.group(1))
    for pattern in (OG_TITLE_RE, OG_TITLE_RE_REV):
        om = pattern.search(html)
        if om:
            candidates.append(om.group(1))
            break

    for cand in candidates:
        cand_tokens = _normalize_addr_tokens(cand)
        cand_num = _street_number(cand_tokens)
        if cand_num and cand_num != street_num:
            return True
    return False


def _collect_urls_from_photo_item(item: object) -> list[str]:
    urls: list[str] = []
    if not isinstance(item, dict):
        return urls
    raw = item.get("url")
    if isinstance(raw, str) and "photos.zillowstatic.com" in raw:
        urls.append(raw)
    mixed = item.get("mixedSources")
    if isinstance(mixed, dict):
        for arr in mixed.values():
            if not isinstance(arr, list):
                continue
            for entry in arr:
                if isinstance(entry, dict):
                    u = entry.get("url")
                    if isinstance(u, str) and "photos.zillowstatic.com" in u:
                        urls.append(u)
    return urls


def _photo_list_for_property(prop: dict) -> list:
    for key in PREFERRED_PHOTO_ARRAY_KEYS:
        photos = prop.get(key)
        if isinstance(photos, list) and photos:
            return photos
    return []


def _urls_from_property_photos(prop: dict) -> list[str]:
    """Best variant per gallery image, preserving gallery order."""
    photo_list = _photo_list_for_property(prop)
    all_by_hash: dict[str, list[tuple[str, str, str]]] = {}

    def ingest(url: str) -> None:
        m = PHOTO_URL_RE.search(url)
        if not m:
            return
        hid, variant, ext = m.group(1), m.group(2), m.group(3)
        all_by_hash.setdefault(hid, []).append((hid, variant, ext))

    for key in PHOTO_ARRAY_KEYS:
        for item in prop.get(key) or []:
            for url in _collect_urls_from_photo_item(item):
                ingest(url)

    ordered_hashes: list[str] = []
    seen: set[str] = set()
    for item in photo_list:
        for url in _collect_urls_from_photo_item(item):
            m = PHOTO_URL_RE.search(url)
            if not m:
                continue
            hid = m.group(1)
            if hid not in seen:
                seen.add(hid)
                ordered_hashes.append(hid)
            break

    for hid in all_by_hash:
        if hid not in seen:
            ordered_hashes.append(hid)

    matches: list[tuple[str, str, str, int]] = []
    for index, hid in enumerate(ordered_hashes):
        for h, variant, ext in all_by_hash.get(hid, []):
            matches.append((h, variant, ext, index))

    return _best_urls_for_matches(matches)


def _extract_from_structured(
    html: str, zillow_url: str | None = None
) -> tuple[list[str], bool]:
    """Return (urls, definitive).

    When ``definitive`` is True we found the primary listing blob (by zpid) and
    must not fall back to a full-HTML regex scan — that would reintroduce
    similar-homes thumbs, including after an address mismatch reject.
    """
    next_data = _parse_next_data(html)
    cache = _load_gdp_client_cache(html, next_data)
    if not cache:
        return [], False

    want_zpid = zpid_from_zillow_url(zillow_url) or _zpid_from_next_data(next_data)
    properties = _iter_property_objects(cache)
    if not properties:
        return [], False

    primary: dict | None = None
    if want_zpid:
        for prop in properties:
            if str(prop.get("zpid")) == str(want_zpid):
                primary = prop
                break
        if primary is None:
            # URL/page zpid present but no matching property blob — do not
            # guess from another home's photos or loose HTML thumbs.
            return [], True
    else:
        primary = properties[0]

    if _listing_address_mismatch(primary, zillow_url=zillow_url, html=html):
        return [], True

    return _urls_from_property_photos(primary), True


def extract_photo_urls(html: str, zillow_url: str | None = None) -> list[str]:
    """Pick one best URL per listing photo hash.

    Prefers the primary listing's structured photo arrays inside
    ``__NEXT_DATA__`` / ``gdpClientCache`` (matched by zpid). Falls back to a
    full-HTML regex scan only when structured extraction finds nothing — the
    regex path can pick up similar-homes carousel thumbs.
    """
    structured, definitive = _extract_from_structured(html, zillow_url=zillow_url)
    if definitive:
        return structured
    if structured:
        return structured
    return _urls_from_regex_scan(html)


def fetch_listing_html(zillow_url: str) -> str:
    response = curl_requests.get(
        zillow_url,
        impersonate="chrome124",
        timeout=45,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    if response.status_code >= 400:
        raise ValueError(f"Zillow returned HTTP {response.status_code} for this listing.")
    return response.text


def fetch_listing_photo_urls(
    zillow_url: str,
    *,
    html: str | None = None,
) -> FetchedListingPhotos:
    page = html if html is not None else fetch_listing_html(zillow_url)
    urls = extract_photo_urls(page, zillow_url=zillow_url)
    if not urls:
        raise ValueError(
            "No listing photos found on that Zillow page. "
            "The link may be invalid, blocked, or not a home details page."
        )
    return FetchedListingPhotos(urls=urls, raw_html_bytes=len(page))


def download_image(url: str) -> tuple[bytes, str]:
    response = curl_requests.get(
        url,
        impersonate="chrome124",
        timeout=45,
        headers={"Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
    )
    if response.status_code >= 400:
        raise ValueError(f"Failed to download image ({response.status_code})")
    content_type = (response.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
    return response.content, content_type


def extension_for(content_type: str, url: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in mapping:
        return mapping[content_type]
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"
