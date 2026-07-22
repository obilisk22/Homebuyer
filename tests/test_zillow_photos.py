from __future__ import annotations

import io
import json

from PIL import Image

import app.core.db as db
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService
from app.core.zillow_photos import FetchedListingPhotos, extract_photo_urls


def _jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 80, 120)).save(buf, format="JPEG")
    return buf.getvalue()


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


def test_import_zillow_photos_batches_db_commit(tmp_path, monkeypatch):
    """Import adds all photos then commits once (plus select_thumbnail commit)."""
    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "batch.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()

    urls = [
        "https://photos.zillowstatic.com/fp/aaa-o_a.jpg",
        "https://photos.zillowstatic.com/fp/bbb-o_a.jpg",
    ]

    def fake_fetch(zillow_url, *, html=None):
        return FetchedListingPhotos(urls=urls, raw_html_bytes=100)

    def fake_download(url):
        return (b"fake-image", "image/jpeg")

    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_photo_urls", fake_fetch
    )
    monkeypatch.setattr("app.core.property_service.download_image", fake_download)

    with db.get_session() as session:
        prop = Property(
            address="1 Batch St",
            zillow_url="https://www.zillow.com/homedetails/1-Batch-St/1_zpid/",
            financial=FinancialAssumptions(),
        )
        session.add(prop)
        session.commit()
        session.refresh(prop)

        svc = PropertyService(session)
        commit_calls = 0
        original_commit = session.commit

        def counting_commit():
            nonlocal commit_calls
            commit_calls += 1
            return original_commit()

        session.commit = counting_commit  # type: ignore[method-assign]

        count = svc.import_zillow_photos(prop.id, html="<html></html>")

        assert count == 2
        assert commit_calls == 2  # one batch import + select_thumbnail

        prop = svc.get_property(prop.id)
        assert prop is not None
        assert len(prop.photos) == 2
        assert [p.sort_order for p in prop.photos] == [0, 1]
        assert {p.source_url for p in prop.photos} == set(urls)


def test_import_writes_thumb_sidecar(tmp_path, monkeypatch):
    """Download writes mid-size file plus stem_thumb.webp beside it."""
    from app.core import listing_ingest
    from app.core.zillow_photos import FetchedListingPhotos

    uploads = tmp_path / "uploads"
    monkeypatch.setattr(listing_ingest, "UPLOADS_DIR", uploads)

    rows = listing_ingest.download_zillow_photo_files(
        9,
        LISTING_URL,
        html="<html></html>",
        photo_fetcher=lambda url, *, html=None: FetchedListingPhotos(
            urls=["https://photos.zillowstatic.com/fp/aaa-o_a.jpg"],
            raw_html_bytes=1,
        ),
        image_downloader=lambda url: (_jpeg_bytes(2400, 1800), "image/jpeg"),
    )

    assert len(rows) == 1
    mid = uploads / rows[0]["path"]
    assert mid.is_file()
    assert mid.name == "zillow_000.jpg"
    thumb = mid.with_name("zillow_000_thumb.webp")
    assert thumb.is_file()
    with Image.open(thumb) as im:
        assert max(im.size) <= 400
        assert max(im.size) == 400
    with Image.open(mid) as im:
        assert max(im.size) == 1600

