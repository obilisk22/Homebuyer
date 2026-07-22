from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.cache import memo_clear
from app.core.geocode import (
    NOMINATIM_USER_AGENT,
    geocode_address,
    geocode_query_candidates,
    strip_unit_designator,
)


@pytest.fixture(autouse=True)
def _isolate_geocode_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    from app.core import paths

    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    paths.refresh_data_dirs()
    memo_clear()
    yield
    memo_clear()


def test_geocode_requires_address():
    with pytest.raises(ValueError, match="Address is required"):
        geocode_address("  ")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "650 Pacific St UNIT 8 Santa Monica CA 90405",
            "650 Pacific St Santa Monica CA 90405",
        ),
        (
            "123 Main St Apt 4B Seattle WA 98101",
            "123 Main St Seattle WA 98101",
        ),
        (
            "100 Oak Ave #12, Portland, OR 97201",
            "100 Oak Ave, Portland, OR 97201",
        ),
        (
            "200 Pine St Suite 300 San Francisco CA 94102",
            "200 Pine St San Francisco CA 94102",
        ),
        (
            "45 Elm Road Ste. 5A Austin TX 78701",
            "45 Elm Road Austin TX 78701",
        ),
        ("123 Main St Seattle WA", "123 Main St Seattle WA"),
    ],
)
def test_strip_unit_designator(raw: str, expected: str):
    assert strip_unit_designator(raw) == expected


def test_geocode_query_candidates_unit_fallbacks():
    candidates = geocode_query_candidates(
        "650 Pacific St UNIT 8 Santa Monica CA 90405"
    )
    assert candidates[0] == "650 Pacific St UNIT 8 Santa Monica CA 90405"
    assert candidates[1] == "650 Pacific St Santa Monica CA 90405"
    assert "650 Pacific St, Santa Monica, CA 90405" in candidates
    assert "Santa Monica, CA 90405" in candidates


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_uses_disk_cache_on_second_call(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = [{"lat": "34.0", "lon": "-118.0"}]
    mock_get.return_value = response

    a1 = geocode_address("123 Main St Santa Monica CA 90401")
    a2 = geocode_address("123 Main St Santa Monica CA 90401")
    assert a1 == a2
    assert mock_get.call_count == 1


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_nominatim_success(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = [{"lat": "47.6062", "lon": "-122.3321"}]
    mock_get.return_value = response

    lat, lng = geocode_address("123 Main St Seattle WA")

    assert lat == pytest.approx(47.6062)
    assert lng == pytest.approx(-122.3321)
    mock_get.assert_called()
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == NOMINATIM_USER_AGENT
    assert kwargs["params"]["q"] == "123 Main St Seattle WA"
    assert kwargs["timeout"] == 10


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_google_success(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 38.8977, "lng": -77.0365}}}],
    }
    mock_get.return_value = response

    lat, lng = geocode_address("1600 Pennsylvania Ave NW, Washington, DC")

    assert lat == pytest.approx(38.8977)
    assert lng == pytest.approx(-77.0365)
    url = mock_get.call_args.args[0]
    assert "maps.googleapis.com/maps/api/geocode/json" in url
    assert "key=test-key" in url


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_nominatim_no_results(mock_get: MagicMock):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = []
    mock_get.return_value = response

    with pytest.raises(ValueError, match="No geocoding results"):
        geocode_address("zzzzz nowhere land")


@patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False)
@patch("app.core.geocode.requests.get")
def test_geocode_falls_back_without_unit(mock_get: MagicMock):
    empty = MagicMock()
    empty.raise_for_status = MagicMock()
    empty.json.return_value = []

    hit = MagicMock()
    hit.raise_for_status = MagicMock()
    hit.json.return_value = [{"lat": "34.0091657", "lon": "-118.4824828"}]

    mock_get.side_effect = [empty, hit]

    lat, lng = geocode_address("650 Pacific St UNIT 8 Santa Monica CA 90405")

    assert lat == pytest.approx(34.0091657)
    assert lng == pytest.approx(-118.4824828)
    assert mock_get.call_count == 2
    first_q = mock_get.call_args_list[0].kwargs["params"]["q"]
    second_q = mock_get.call_args_list[1].kwargs["params"]["q"]
    assert first_q == "650 Pacific St UNIT 8 Santa Monica CA 90405"
    assert second_q == "650 Pacific St Santa Monica CA 90405"
