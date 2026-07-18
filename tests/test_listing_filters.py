from types import SimpleNamespace

from app.core.property_service import property_matches_filters
from app.core.zillow_listing import (
    extract_listing_details,
    parse_address_parts,
)


SAMPLE_LD_HTML = """
<html><head>
<meta name="description" content="Zillow has 40 photos of this $1,298,000 3 beds, 2 baths, 2,016 Square Feet single family home located at 5414 SW Beach Drive Terrace, Seattle, WA 98116 built in 1958."/>
</head><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":["RealEstateListing","Product"],
 "offers":{"@type":"Offer","price":1298000,"priceCurrency":"USD",
  "itemOffered":{"@type":"SingleFamilyResidence","numberOfBedrooms":3,
   "address":{"@type":"PostalAddress","streetAddress":"5414 SW Beach Drive Terrace",
    "addressLocality":"Seattle","addressRegion":"WA","postalCode":"98116"}}}}
</script>
</body></html>
"""

SAMPLE_META_ONLY = """
<meta name="description" content="Zillow has photos of this $875,500 4 beds, 2.5 baths home located at 10 Oak Ave, Portland, OR 97201 built in 1990."/>
"""

SAMPLE_ESCAPED_PARENT_REGION = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"parentRegion\":{\"name\":\"Ocean Park\",\"regionId\":117023},\"adTargets\":{\"hood\":\"Ocean_Park\",\"city\":\"Santa Monica\"}}"}}}}
</script>
"""

# Real Zillow blobs often put regionId before name inside parentRegion.
SAMPLE_ESCAPED_PARENT_REGION_ID_FIRST = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"parentRegion\":{\"regionId\":117023,\"name\":\"Ocean Park\",\"regionType\":8},\"city\":\"Santa Monica\"}"}}}}
</script>
"""


def test_extract_escaped_parent_region_neighborhood():
    details = extract_listing_details(SAMPLE_ESCAPED_PARENT_REGION)
    assert details.neighborhood == "Ocean Park"


def test_extract_parent_region_when_region_id_precedes_name():
    details = extract_listing_details(SAMPLE_ESCAPED_PARENT_REGION_ID_FIRST)
    assert details.neighborhood == "Ocean Park"


def test_extract_from_ld_and_meta():
    details = extract_listing_details(SAMPLE_LD_HTML)
    assert details.list_price == 1_298_000
    assert details.beds == 3
    assert details.baths == 2  # from meta (LD has no baths)
    assert details.city == "Seattle"
    assert details.state == "WA"
    assert details.zip_code == "98116"


def test_extract_meta_only_with_half_bath():
    details = extract_listing_details(SAMPLE_META_ONLY)
    assert details.list_price == 875_500
    assert details.beds == 4
    assert details.baths == 2.5
    assert details.city == "Portland"
    assert details.state == "OR"
    assert details.zip_code == "97201"


def test_extract_embedded_json_fields():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"price":450000,"bedrooms":2,"bathrooms":1,'
        '"city":"Austin","state":"TX","zipcode":"78701"}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.list_price == 450_000
    assert details.beds == 2
    assert details.baths == 1
    assert details.city == "Austin"
    assert details.state == "TX"
    assert details.zip_code == "78701"


def test_parse_address_parts():
    assert parse_address_parts("123 Main St, Seattle, WA 98101") == (
        "Seattle",
        "WA",
        "98101",
    )
    assert parse_address_parts("1600 Pennsylvania Avenue NW, Washington, DC 20500") == (
        "Washington",
        "DC",
        "20500",
    )


def _prop(**kwargs):
    defaults = {
        "address": "123 Main St, Seattle, WA 98101",
        "city": "Seattle",
        "state": "WA",
        "zip_code": "98101",
        "list_price": 800_000,
        "beds": 3,
        "baths": 2,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_filter_search_address_and_city():
    prop = _prop()
    assert property_matches_filters(prop, search="seattle")
    assert property_matches_filters(prop, search="Main")
    assert not property_matches_filters(prop, search="portland")


def test_filter_price_and_beds():
    prop = _prop(list_price=800_000, beds=3)
    assert property_matches_filters(prop, min_price=700_000, max_price=900_000, min_beds=3)
    assert not property_matches_filters(prop, min_price=900_000)
    assert not property_matches_filters(prop, max_price=500_000)
    assert not property_matches_filters(prop, min_beds=4)
    assert not property_matches_filters(_prop(list_price=None), min_price=100_000)
