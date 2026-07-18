from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests

PHOTO_URL_RE = re.compile(
    r"https://photos\.zillowstatic\.com/fp/([a-f0-9]+)-([A-Za-z0-9_]+)\.(jpg|webp)",
    re.IGNORECASE,
)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
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
        elif variant_l.startswith("cc_"):
            score = 500
        else:
            score = 10

    if ext.lower() == "webp":
        score -= 1
    return score


def extract_photo_urls(html: str) -> list[str]:
    """Pick one best URL per photo hash from listing HTML / embedded JSON.

    Order follows first appearance in the page (Zillow heroes are usually early),
    while still selecting the highest-quality variant for each hash.
    """
    best: dict[str, tuple[int, str, int]] = {}
    for index, (hid, variant, ext) in enumerate(PHOTO_URL_RE.findall(html)):
        score = _score_variant(variant, ext)
        if score < 1_000:
            continue
        # Prefer jpg downloads when a sized variant exists
        use_ext = "jpg" if ext.lower() == "webp" and (
            variant.lower().startswith("o_a") or "cc_ft_" in variant.lower() or variant.lower() in {"p_f", "unc_f"}
        ) else ext
        url = f"https://photos.zillowstatic.com/fp/{hid}-{variant}.{use_ext}"
        prev = best.get(hid)
        if prev is None:
            best[hid] = (score, url, index)
        elif score > prev[0]:
            best[hid] = (score, url, prev[2])

    ordered = sorted(best.items(), key=lambda kv: kv[1][2])
    return [url for _, (_, url, _) in ordered]


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


def fetch_listing_photo_urls(zillow_url: str) -> FetchedListingPhotos:
    html = fetch_listing_html(zillow_url)
    urls = extract_photo_urls(html)
    if not urls and NEXT_DATA_RE.search(html):
        # Still try extraction on NEXT_DATA alone (same regex over full HTML already covers it)
        urls = extract_photo_urls(html)
    if not urls:
        raise ValueError(
            "No listing photos found on that Zillow page. "
            "The link may be invalid, blocked, or not a home details page."
        )
    return FetchedListingPhotos(urls=urls, raw_html_bytes=len(html))


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
