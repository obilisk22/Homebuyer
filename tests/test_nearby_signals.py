from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.nearby_signals import (
    HIGHWAY_RADIUS_FT,
    SHELTER_RADIUS_MI,
    TRANSIT_RADIUS_MI,
    ft_to_miles,
    hits_in_order,
    is_stale,
    miles_to_ft,
    parse_signals_json,
    tooltip_for,
)


def test_radius_constants():
    assert HIGHWAY_RADIUS_FT == 800.0
    assert TRANSIT_RADIUS_MI == 0.5
    assert SHELTER_RADIUS_MI == 0.25
    assert abs(miles_to_ft(0.5) - 2640.0) < 0.01
    assert abs(ft_to_miles(800.0) - (800.0 / 5280.0)) < 1e-9


def test_parse_and_hits_order():
    raw = """
    {"shelter": {"hit": true, "distance_mi": 0.1, "name": "A"},
     "highway": {"hit": true, "distance_ft": 400, "name": "I-10"},
     "playground": {"hit": false}}
    """
    payload = parse_signals_json(raw)
    hits = hits_in_order(payload)
    assert [k for k, _ in hits] == ["highway", "shelter"]


def test_tooltip_units():
    assert tooltip_for("highway", {"hit": True, "distance_ft": 420, "name": "I-10"}) == "420 ft · I-10"
    assert tooltip_for(
        "transit", {"hit": True, "distance_mi": 0.31, "name": "Expo/Bundy"}
    ) == "0.31 mi · Expo/Bundy"


def test_is_stale():
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    assert is_stale(None, now=now) is True
    fresh = (now - timedelta(days=5)).isoformat()
    assert is_stale(fresh, now=now) is False
    old = (now - timedelta(days=31)).isoformat()
    assert is_stale(old, now=now) is True


def test_parse_overpass_picks_nearest_playground():
    from app.core.nearby_signals import nearest_within, parse_overpass_elements

    elements = [
        {
            "type": "node",
            "id": 1,
            "lat": 34.051,
            "lon": -118.25,
            "tags": {"leisure": "playground", "name": "Far Park Play"},
        },
        {
            "type": "node",
            "id": 2,
            "lat": 34.0502,
            "lon": -118.25,
            "tags": {"leisure": "playground", "name": "Near Play"},
        },
    ]
    hits = parse_overpass_elements(
        elements, pin_lat=34.05, pin_lng=-118.25, radius_mi=0.5
    )
    # Filter to playgrounds in test by passing only playground elements
    best = nearest_within(hits, radius_mi=0.5)
    assert best is not None
    assert best["name"] == "Near Play"


def test_signal_entry_highway_uses_feet():
    from app.core.nearby_signals import signal_entry_from_hit

    hit = {"name": "I-10", "lat": 34.0, "lng": -118.0, "distance_mi": 800 / 5280}
    entry = signal_entry_from_hit("highway", hit)
    assert entry["hit"] is True
    assert abs(entry["distance_ft"] - 800) < 1.0
    assert entry["name"] == "I-10"


def test_signal_entry_miss():
    from app.core.nearby_signals import signal_entry_from_hit

    entry = signal_entry_from_hit("grocery", None)
    assert entry == {"hit": False}


def test_parse_overpass_uses_way_center_and_filters_radius():
    from app.core.nearby_signals import parse_overpass_elements

    elements = [
        {
            "type": "way",
            "center": {"lat": 34.0501, "lon": -118.25},
            "tags": {"highway": "motorway", "ref": "I-10"},
        },
        {
            "type": "way",
            "center": {"lat": 35.0, "lon": -118.25},
            "tags": {"highway": "motorway"},
        },
    ]
    hits = parse_overpass_elements(
        elements, pin_lat=34.05, pin_lng=-118.25, radius_mi=0.5
    )
    assert len(hits) == 1
    assert hits[0]["name"] == "I-10"


def test_classify_overpass_nearest_enforces_per_signal_boundaries():
    from app.core.nearby_signals import classify_overpass_nearest

    pin_lat = 34.05
    pin_lng = -118.25
    elements = [
        {
            "type": "node",
            "lat": pin_lat + (0.30 / 69.0),
            "lon": pin_lng,
            "tags": {
                "amenity": "social_facility",
                "social_facility": "shelter",
                "name": "Too Far Shelter",
            },
        },
        {
            "type": "node",
            "lat": pin_lat + (0.40 / 69.0),
            "lon": pin_lng,
            "tags": {"leisure": "playground", "name": "Nearby Playground"},
        },
        {
            "type": "way",
            "center": {"lat": pin_lat + ((900.0 / 5280.0) / 69.0), "lon": pin_lng},
            "tags": {"highway": "motorway", "ref": "Too Far Freeway"},
        },
    ]

    nearest = classify_overpass_nearest(elements, pin_lat=pin_lat, pin_lng=pin_lng)

    assert nearest["shelter"] is None
    assert nearest["playground"] is not None
    assert nearest["playground"]["name"] == "Nearby Playground"
    assert nearest["highway"] is None


def test_build_overpass_query_contains_exact_signal_tags():
    from app.core.nearby_signals import build_overpass_query

    query = build_overpass_query(34.05, -118.25)
    assert "(around:244,34.05,-118.25)" in query
    assert 'way["highway"="motorway"]' in query
    assert 'way["highway"="motorway_link"]' in query
    assert 'node["railway"="subway_entrance"]' in query
    assert 'way["railway"="station"]["station"="light_rail"]' in query
    assert 'node["railway"="halt"]["light_rail"="yes"]' in query
    assert 'way["leisure"="playground"]' in query
    assert 'node["shop"="supermarket"]' in query
    assert 'way["shop"="grocery"]' in query
    assert '["shop"="convenience"]' not in query
    assert '["social_facility:for"="homeless"]' in query
    assert '["amenity"="shelter"]["shelter_type"="homeless"]' in query
    assert query.rstrip().endswith("out center tags;")
