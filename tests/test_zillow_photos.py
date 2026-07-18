from __future__ import annotations

import json

from app.core.zillow_photos import extract_photo_urls


SAMPLE_HTML = """
<html><body>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-p_e.jpg"/>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-cc_ft_384.jpg"/>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-o_a.jpg"/>
<img src="https://photos.zillowstatic.com/fp/aaa111bbb222ccc333ddd444eee555ff-sc_192_128.jpg"/>
<img src="https://photos.zillowstatic.com/fp/fff000eee111ddd222ccc333bbb444aa-cc_ft_1536.jpg"/>
</body></html>
"""

PRIMARY_HASH = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SIMILAR_HASH = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
PRIMARY_ZPID = 20479997
LISTING_URL = (
    "https://www.zillow.com/homedetails/"
    "1834-11th-St-APT-2-Santa-Monica-CA-90404/20479997_zpid/"
)


def _escaped_gdp_cache(cache_obj: dict) -> str:
    """Embed cache as an escaped JSON string value (Zillow gdpClientCache shape)."""
    inner = json.dumps(cache_obj, separators=(",", ":"))
    return json.dumps(inner)[1:-1]  # strip surrounding quotes; keep escapes


def _html_with_structured_and_similar() -> str:
    cache = {
        f'ForSalePriorityQuery{{"zpid":{PRIMARY_ZPID}}}': {
            "property": {
                "zpid": PRIMARY_ZPID,
                "streetAddress": "1834 11th St APT 2",
                "city": "Santa Monica",
                "state": "CA",
                "zipcode": "90404",
                "originalPhotos": [
                    {
                        "mixedSources": {
                            "jpeg": [
                                {
                                    "url": (
                                        f"https://photos.zillowstatic.com/fp/"
                                        f"{PRIMARY_HASH}-cc_ft_384.jpg"
                                    ),
                                    "width": 384,
                                },
                                {
                                    "url": (
                                        f"https://photos.zillowstatic.com/fp/"
                                        f"{PRIMARY_HASH}-o_a.jpg"
                                    ),
                                    "width": 1024,
                                },
                            ]
                        }
                    }
                ],
                "responsivePhotos": [
                    {
                        "url": (
                            f"https://photos.zillowstatic.com/fp/"
                            f"{PRIMARY_HASH}-p_d.jpg"
                        ),
                        "mixedSources": {
                            "jpeg": [
                                {
                                    "url": (
                                        f"https://photos.zillowstatic.com/fp/"
                                        f"{PRIMARY_HASH}-cc_ft_1536.jpg"
                                    ),
                                    "width": 1536,
                                }
                            ]
                        },
                    }
                ],
            }
        }
    }
    escaped = _escaped_gdp_cache(cache)
    next_data = {
        "props": {
            "pageProps": {
                "componentProps": {
                    "gdpQueryVariables": {"zpid": PRIMARY_ZPID},
                    "gdpClientCache": json.loads(f'"{escaped}"'),
                }
            }
        }
    }
    # Similar-home thumbs only appear as loose HTML (not in primary property).
    return f"""
<html><head>
<meta property="og:title" content="1834 11th St APT 2, Santa Monica, CA 90404 | Zillow"/>
</head><body>
<img src="https://photos.zillowstatic.com/fp/{SIMILAR_HASH}-cc_ft_1536.jpg"/>
<img src="https://photos.zillowstatic.com/fp/{SIMILAR_HASH}-o_a.jpg"/>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>
</body></html>
"""


def _html_with_escaped_string_cache() -> str:
    """gdpClientCache as a JSON-escaped string inside __NEXT_DATA__ (common shape)."""
    cache = {
        f'ForSalePriorityQuery{{"zpid":{PRIMARY_ZPID}}}': {
            "property": {
                "zpid": PRIMARY_ZPID,
                "streetAddress": "1834 11th St APT 2",
                "originalPhotos": [
                    {
                        "mixedSources": {
                            "jpeg": [
                                {
                                    "url": (
                                        f"https://photos.zillowstatic.com/fp/"
                                        f"{PRIMARY_HASH}-o_a.jpg"
                                    ),
                                    "width": 1024,
                                }
                            ]
                        }
                    }
                ],
            }
        }
    }
    escaped = _escaped_gdp_cache(cache)
    raw = (
        '{"props":{"pageProps":{"componentProps":{'
        f'"gdpQueryVariables":{{"zpid":{PRIMARY_ZPID}}},'
        f'"gdpClientCache":"{escaped}"'
        "}}}}"
    )
    return f"""
<html><body>
<img src="https://photos.zillowstatic.com/fp/{SIMILAR_HASH}-cc_ft_1536.jpg"/>
<script id="__NEXT_DATA__" type="application/json">{raw}</script>
</body></html>
"""


def test_extract_prefers_high_res_and_dedupes():
    urls = extract_photo_urls(SAMPLE_HTML)
    assert len(urls) == 2
    assert urls[0].endswith("-o_a.jpg")
    assert any("cc_ft_1536" in u for u in urls)


def test_extract_skips_ui_thumbs_only():
    html = (
        '<img src="https://photos.zillowstatic.com/fp/'
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-sc_192_128.jpg"/>'
    )
    assert extract_photo_urls(html) == []


def test_structured_ignores_similar_home_thumbs():
    html = _html_with_structured_and_similar()
    urls = extract_photo_urls(html, zillow_url=LISTING_URL)
    hashes = {u.split("/fp/")[1].split("-")[0] for u in urls}
    assert PRIMARY_HASH in hashes
    assert SIMILAR_HASH not in hashes
    assert len(urls) == 1
    assert urls[0].endswith(f"{PRIMARY_HASH}-o_a.jpg")


def test_structured_from_escaped_gdp_string_cache():
    html = _html_with_escaped_string_cache()
    urls = extract_photo_urls(html, zillow_url=LISTING_URL)
    assert len(urls) == 1
    assert PRIMARY_HASH in urls[0]
    assert SIMILAR_HASH not in urls[0]


def test_address_mismatch_returns_empty_not_wrong_photos():
    cache = {
        f'ForSalePriorityQuery{{"zpid":{PRIMARY_ZPID}}}': {
            "property": {
                "zpid": PRIMARY_ZPID,
                "streetAddress": "999 Wrong St",
                "originalPhotos": [
                    {
                        "mixedSources": {
                            "jpeg": [
                                {
                                    "url": (
                                        f"https://photos.zillowstatic.com/fp/"
                                        f"{PRIMARY_HASH}-o_a.jpg"
                                    ),
                                    "width": 1024,
                                }
                            ]
                        }
                    }
                ],
            }
        }
    }
    escaped = _escaped_gdp_cache(cache)
    raw = (
        '{"props":{"pageProps":{"componentProps":{'
        f'"gdpClientCache":"{escaped}"'
        "}}}}"
    )
    html = f"""
<html><head>
<meta property="og:title" content="1834 11th St APT 2 | Zillow"/>
</head><body>
<img src="https://photos.zillowstatic.com/fp/{SIMILAR_HASH}-o_a.jpg"/>
<script id="__NEXT_DATA__" type="application/json">{raw}</script>
</body></html>
"""
    # Structured path rejects mismatch; must not fall back to similar-home regex.
    assert extract_photo_urls(html, zillow_url=LISTING_URL) == []
