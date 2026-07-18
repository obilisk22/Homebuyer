"""Tests for neighborhood name helpers and outbound review deep links."""

from unittest.mock import MagicMock, patch

from app.core.geocode import (
    NOMINATIM_USER_AGENT,
    reverse_geocode_neighborhood,
    reverse_geocode_neighborhood_nominatim,
)
from app.core.neighborhood import (
    build_review_deep_links,
    city_data_url,
    city_subreddit_url,
    effective_neighborhood_name,
    google_site_reddit_url,
    niche_place_url,
    reddit_search_url,
    slugify_city_for_subreddit,
)
from app.core.zillow_listing import extract_listing_details


def test_effective_neighborhood_prefers_override():
    assert (
        effective_neighborhood_name(
            neighborhood_name="Ballard",
            neighborhood_override="Fremont",
        )
        == "Fremont"
    )
    assert (
        effective_neighborhood_name(
            neighborhood_name="Ballard",
            neighborhood_override="  ",
        )
        == "Ballard"
    )


def test_reddit_search_url_quotes_neighborhood():
    url = reddit_search_url("Capitol Hill", "Seattle")
    assert "reddit.com/search" in url
    assert "Capitol" in url
    assert "Seattle" in url


def test_slugify_and_city_subreddit():
    assert slugify_city_for_subreddit("Los Angeles") == "LosAngeles"
    assert slugify_city_for_subreddit("Seattle") == "Seattle"
    assert city_subreddit_url("Seattle") == "https://www.reddit.com/r/Seattle/"
    assert city_subreddit_url("") is None


def test_city_data_and_google_urls():
    cd = city_data_url("Seattle", "WA")
    assert cd is not None
    assert "city-data.com/city/Seattle-Washington.html" in cd

    g = google_site_reddit_url("Ballard", "Seattle")
    assert "google.com/search" in g
    assert "site" in g
    assert "reddit.com" in g


def test_niche_place_url_ocean_park():
    assert (
        niche_place_url("Ocean Park", "Santa Monica", "CA")
        == "https://www.niche.com/places-to-live/n/ocean-park-santa-monica-ca/"
    )


def test_niche_place_url_ballard():
    assert (
        niche_place_url("Ballard", "Seattle", "WA")
        == "https://www.niche.com/places-to-live/n/ballard-seattle-wa/"
    )


def test_niche_place_url_falls_back_to_search():
    url = niche_place_url("Ocean Park", "Santa Monica", "")
    assert "niche.com/places-to-live/search" in url
    assert "Ocean" in url or "Ocean%20" in url or "q=" in url


def test_build_review_deep_links():
    links = build_review_deep_links("Ballard", city="Seattle", state="WA")
    assert "reddit.com/search" in links.reddit_search
    assert links.city_subreddit == "https://www.reddit.com/r/Seattle/"
    assert links.city_data is not None
    assert links.niche == "https://www.niche.com/places-to-live/n/ballard-seattle-wa/"
    assert "site:reddit.com" in links.google_site_reddit or "site%3Areddit.com" in links.google_site_reddit


def test_build_review_deep_links_ocean_park_niche():
    links = build_review_deep_links("Ocean Park", city="Santa Monica", state="CA")
    assert links.niche == "https://www.niche.com/places-to-live/n/ocean-park-santa-monica-ca/"


def test_extract_neighborhood_from_zillow_html():
    html = """
    <html><body>
    <script type="application/ld+json">
    {"@type":"SingleFamilyResidence","address":{
      "streetAddress":"123 Main St","addressLocality":"Seattle",
      "addressRegion":"WA","postalCode":"98101","neighborhood":"Capitol Hill"
    }}
    </script>
    </body></html>
    """
    details = extract_listing_details(html)
    assert details.neighborhood == "Capitol Hill"
    assert details.city == "Seattle"


def test_extract_neighborhood_from_embedded_json():
    html = '{"neighborhood":"Ballard","city":"Seattle","state":"WA"}'
    details = extract_listing_details(html)
    assert details.neighborhood == "Ballard"


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_reverse_geocode_nominatim(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "address": {
            "neighbourhood": "Ballard",
            "city": "Seattle",
            "state": "Washington",
        }
    }
    mock_get.return_value = response

    name = reverse_geocode_neighborhood_nominatim(47.66, -122.38)
    assert name == "Ballard"
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == NOMINATIM_USER_AGENT
    assert kwargs["params"]["lat"] == 47.66


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_reverse_geocode_neighborhood_tuple(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "address": {"suburb": "Fremont", "city": "Seattle"}
    }
    mock_get.return_value = response

    name, source = reverse_geocode_neighborhood(47.65, -122.35)
    assert name == "Fremont"
    assert source == "nominatim"


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}, clear=False)
@patch("app.core.geocode.requests.get")
def test_reverse_geocode_falls_back_to_google(mock_get: MagicMock):
    empty = MagicMock()
    empty.raise_for_status = MagicMock()
    empty.json.return_value = {"address": {"city": "Seattle"}}

    google = MagicMock()
    google.raise_for_status = MagicMock()
    google.json.return_value = {
        "status": "OK",
        "results": [
            {
                "address_components": [
                    {"long_name": "Queen Anne", "types": ["neighborhood"]},
                    {"long_name": "Seattle", "types": ["locality"]},
                ]
            }
        ],
    }
    mock_get.side_effect = [empty, google]

    name, source = reverse_geocode_neighborhood(47.63, -122.35)
    assert name == "Queen Anne"
    assert source == "google"
