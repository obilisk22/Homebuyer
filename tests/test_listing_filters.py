from types import SimpleNamespace

import pytest

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


SAMPLE_ESCAPED_GDP_EXTENDED = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"property\":{\"zpid\":123,\"price\":1298000,\"bedrooms\":3,\"bathrooms\":2,\"livingArea\":2016,\"livingAreaValue\":2016,\"monthlyHoaFee\":250,\"hoaFee\":250,\"yearBuilt\":1958,\"homeType\":\"SINGLE_FAMILY\",\"city\":\"Seattle\",\"state\":\"WA\",\"zipcode\":\"98116\",\"parentRegion\":{\"name\":\"Alki\",\"regionId\":1}}}"}}}}
</script>
"""

SAMPLE_ESCAPED_GDP_CONDO = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"ForSaleShopperPlatformFullRenderQuery\":{\"property\":{\"zpid\":99,\"price\":875000,\"bedrooms\":2,\"bathrooms\":2,\"livingArea\":1100,\"hoaFee\":425.5,\"yearBuilt\":2001,\"homeType\":\"CONDO\",\"propertyTypeDimension\":\"Condo\",\"city\":\"Santa Monica\",\"state\":\"CA\"}}}"}}}}
</script>
"""

# Zillow's property payload convention uses `rentZestimate`; the cached samples
# currently contain no rent or decade-appreciation field to fixture directly.
SAMPLE_RENT_ZESTIMATE = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"property\":{\"zpid\":1,\"rentZestimate\":4200}}"}}}}
</script>
"""

SAMPLE_HOME_VALUE_CHART = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"property\":{\"zpid\":1},\"homeValueChartData\":[{\"name\":\"Home Value\",\"points\":[{\"x\":0,\"y\":100000},{\"x\":315576000000,\"y\":200000}]}]}"}}}}
</script>
"""


def test_extract_rent_zestimate_from_gdp():
    details = extract_listing_details(SAMPLE_RENT_ZESTIMATE)
    assert details.rent_zestimate == 4200.0


def test_extract_decade_appreciation_cagr_from_home_value_chart():
    details = extract_listing_details(SAMPLE_HOME_VALUE_CHART)
    assert details.appreciation_decade_pct == pytest.approx(
        (2 ** (1 / 10) - 1) * 100, abs=0.05
    )


def test_decade_appreciation_is_none_when_payload_has_no_ten_year_metric():
    details = extract_listing_details(SAMPLE_RENT_ZESTIMATE)
    assert details.appreciation_decade_pct is None


SAMPLE_LD_WITH_EXTENDED = """
<html><head>
<meta name="description" content="Zillow has photos of this $500,000 2 beds, 1 baths, 1,200 Square Feet condo located at 1 Main St, Austin, TX 78701 built in 1985."/>
</head><body>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":["RealEstateListing","Product"],
 "offers":{"@type":"Offer","price":500000,"priceCurrency":"USD",
  "itemOffered":{"@type":"Apartment","numberOfBedrooms":2,
   "floorSize":{"@type":"QuantitativeValue","value":1200,"unitCode":"FTK"},
   "yearBuilt":1985,
   "address":{"@type":"PostalAddress","streetAddress":"1 Main St",
    "addressLocality":"Austin","addressRegion":"TX","postalCode":"78701"}}}}
</script>
</body></html>
"""


def test_extract_sqft_hoa_year_home_type_from_escaped_gdp():
    details = extract_listing_details(SAMPLE_ESCAPED_GDP_EXTENDED)
    assert details.list_price == 1_298_000
    assert details.beds == 3
    assert details.baths == 2
    assert details.sqft == 2016
    assert details.hoa_fee == 250
    assert details.year_built == 1958
    assert details.home_type == "Single Family"
    assert details.neighborhood == "Alki"


def test_extract_condo_fields_from_nested_gdp():
    details = extract_listing_details(SAMPLE_ESCAPED_GDP_CONDO)
    assert details.sqft == 1100
    assert details.hoa_fee == 425.5
    assert details.year_built == 2001
    assert details.home_type == "Condo"


def test_extract_sqft_year_home_type_from_ld_and_meta():
    details = extract_listing_details(SAMPLE_LD_WITH_EXTENDED)
    assert details.list_price == 500_000
    assert details.sqft == 1200
    assert details.year_built == 1985
    assert details.home_type in {"Condo", "Apartment"}


def test_extract_extended_fields_via_regex_fallback():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"livingArea":980,"monthlyHoaFee":0,'
        '"yearBuilt":1972,"homeType":"TOWNHOUSE"}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.sqft == 980
    assert details.hoa_fee == 0
    assert details.year_built == 1972
    assert details.home_type == "Townhouse"


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


def test_list_properties_applies_filters_in_sql(tmp_path, monkeypatch):
    """Cheap beds/price/search filters run in SQL via list_properties."""
    import app.core.db as db
    from app.core.models import FinancialAssumptions, Property
    from app.core.property_service import PropertyService

    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "filters.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    with db.get_session() as session:
        svc = PropertyService(session)
        keep = Property(
            address="100 Keep Ave, Seattle, WA 98101",
            zillow_url="https://www.zillow.com/homedetails/keep/1_zpid/",
            list_price=800_000,
            beds=3,
            city="Seattle",
            state="WA",
            zip_code="98101",
            financial=FinancialAssumptions(),
        )
        drop_price = Property(
            address="200 Cheap St, Seattle, WA 98101",
            zillow_url="https://www.zillow.com/homedetails/cheap/2_zpid/",
            list_price=200_000,
            beds=3,
            city="Seattle",
            state="WA",
            zip_code="98101",
            financial=FinancialAssumptions(),
        )
        drop_beds = Property(
            address="300 Small St, Seattle, WA 98101",
            zillow_url="https://www.zillow.com/homedetails/small/3_zpid/",
            list_price=800_000,
            beds=1,
            city="Seattle",
            state="WA",
            zip_code="98101",
            financial=FinancialAssumptions(),
        )
        drop_city = Property(
            address="400 Other St, Portland, OR 97201",
            zillow_url="https://www.zillow.com/homedetails/other/4_zpid/",
            list_price=800_000,
            beds=3,
            city="Portland",
            state="OR",
            zip_code="97201",
            financial=FinancialAssumptions(),
        )
        session.add_all([keep, drop_price, drop_beds, drop_city])
        session.commit()

        found = svc.list_properties(
            search="seattle",
            min_price=700_000,
            max_price=900_000,
            min_beds=3,
        )
        assert [p.id for p in found] == [keep.id]
        assert found[0].financial is not None



SAMPLE_TAX_INSURANCE_GDP = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"zpid\":1,\"price\":1200000,\"monthlyHoaFee\":250,\"taxAnnualAmount\":11004,\"taxAssessedValue\":1214000,\"propertyTaxRate\":0.82,\"annualHomeownersInsurance\":2400,\"taxHistory\":[{\"time\":1752811412428,\"taxPaid\":12853.69,\"value\":1214000},{\"time\":1700000000000,\"taxPaid\":11054.17,\"value\":1100000}]}"}}}}
</script>
"""


def test_extract_tax_insurance_and_assessed_from_gdp():
    details = extract_listing_details(SAMPLE_TAX_INSURANCE_GDP)
    assert details.list_price == 1_200_000
    assert details.hoa_fee == 250
    # Prefer latest taxHistory.taxPaid over taxAnnualAmount when history present
    assert details.annual_tax == 12853.69
    assert details.tax_assessed_value == 1_214_000
    # 0.82 means 0.82% → 0.0082
    assert details.property_tax_rate == pytest.approx(0.0082)
    assert details.annual_insurance == 2400


def test_extract_tax_annual_when_no_history():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":2,\\"taxAnnualAmount\\":9000,\\"propertyTaxRate\\":1.1,'
        '\\"taxAssessedValue\\":800000}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.annual_tax == 9000
    assert details.property_tax_rate == pytest.approx(0.011)
    assert details.tax_assessed_value == 800_000


def test_extract_insurance_from_nested_sibling_dict():
    """Insurance may live on a payment/calc node, not the best-scored property dict."""
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"property\\":{\\"zpid\\":9,\\"price\\":900000,\\"bedrooms\\":3,'
        '\\"bathrooms\\":2,\\"livingArea\\":1400,\\"homeType\\":\\"SINGLE_FAMILY\\",'
        '\\"city\\":\\"Seattle\\"},'
        '\\"mortgageCalculator\\":{\\"annualHomeownersInsurance\\":3180}}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.list_price == 900_000
    assert details.annual_insurance == 3180


def test_extract_insurance_monthly_key_annualized():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":3,\\"price\\":500000,\\"resoFacts\\":'
        '{\\"monthlyHomeownersInsurance\\":175}}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.annual_insurance == 2100


def test_extract_insurance_from_escaped_regex_scan():
    # No parseable gdpClientCache object — regex fallback over the HTML blob.
    html = (
        '<html><body>'
        r'\"annualHomeownersInsurance\":2640,'
        r'\"price\":750000,'
        r'\"bedrooms\":2'
        "</body></html>"
    )
    details = extract_listing_details(html)
    assert details.annual_insurance == 2640
