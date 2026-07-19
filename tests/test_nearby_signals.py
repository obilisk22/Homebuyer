from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


def test_refresh_property_signals_writes_json_and_timestamp(monkeypatch):
    from app.core import nearby_signals as ns

    expected = {key: {"hit": False} for key in ns.SIGNAL_ORDER}
    monkeypatch.setattr(ns, "compute_signals", lambda lat, lng: expected)
    prop = SimpleNamespace(
        latitude=34.0,
        longitude=-118.0,
        nearby_signals="",
        nearby_signals_at="",
    )

    out = ns.refresh_property_signals(prop)

    assert out == expected
    assert json.loads(prop.nearby_signals) == expected
    assert datetime.fromisoformat(prop.nearby_signals_at).tzinfo is not None


def test_refresh_property_signals_without_coordinates_keeps_cached_payload(monkeypatch):
    from app.core import nearby_signals as ns

    cached = {"highway": {"hit": True, "distance_ft": 400}}
    prop = SimpleNamespace(
        latitude=None,
        longitude=None,
        nearby_signals=json.dumps(cached),
        nearby_signals_at="existing",
    )
    monkeypatch.setattr(
        ns,
        "compute_signals",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not compute")),
    )

    assert ns.refresh_property_signals(prop) == cached
    assert prop.nearby_signals_at == "existing"


def test_property_maps_nearby_signal_columns():
    from app.core.models import Property

    assert Property.__table__.c.nearby_signals.type.__class__.__name__ == "Text"
    assert Property.__table__.c.nearby_signals_at.type.length == 64


def test_property_service_refresh_nearby_signals_commits(monkeypatch):
    from app.core import property_service as ps

    prop = SimpleNamespace(id=7, latitude=34.0, longitude=-118.0)

    class FakeSession:
        commits = 0
        refreshes = 0

        def commit(self):
            self.commits += 1

        def refresh(self, value):
            assert value is prop
            self.refreshes += 1

    session = FakeSession()
    service = ps.PropertyService(session)
    monkeypatch.setattr(service, "get_property", lambda property_id: prop)
    calls = []
    monkeypatch.setattr(ps, "refresh_property_signals", lambda value: calls.append(value))

    assert service.refresh_nearby_signals(7) is prop
    assert calls == [prop]
    assert session.commits == 1
    assert session.refreshes == 1


def test_property_service_refresh_nearby_signals_swallows_errors(monkeypatch):
    from app.core import property_service as ps

    prop = SimpleNamespace(id=8, latitude=34.0, longitude=-118.0)

    class FakeSession:
        commits = 0

        def commit(self):
            self.commits += 1

        def refresh(self, value):
            return None

        def rollback(self):
            return None

    service = ps.PropertyService(FakeSession())
    monkeypatch.setattr(service, "get_property", lambda property_id: prop)
    monkeypatch.setattr(
        ps,
        "refresh_property_signals",
        lambda value: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert service.refresh_nearby_signals(8) is prop
    assert service.session.commits == 0


def test_property_service_refreshes_only_stale_signals_up_to_limit(monkeypatch):
    from app.core import property_service as ps

    now = datetime.now(timezone.utc)
    props = [
        SimpleNamespace(id=1, nearby_signals_at=""),
        SimpleNamespace(
            id=2,
            nearby_signals_at=(now - timedelta(days=2)).isoformat(),
        ),
        SimpleNamespace(
            id=3,
            nearby_signals_at=(now - timedelta(days=40)).isoformat(),
        ),
        SimpleNamespace(id=4, nearby_signals_at=""),
    ]

    class FakeSession:
        def scalars(self, stmt):
            return props

    service = ps.PropertyService(FakeSession())
    refreshed = []
    monkeypatch.setattr(
        service,
        "refresh_nearby_signals",
        lambda property_id: refreshed.append(property_id),
    )

    assert service.refresh_stale_nearby_signals(limit=2) == 2
    assert refreshed == [1, 3]


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


def test_fetch_overpass_posts_query_and_caches(monkeypatch):
    from app.core import nearby_signals as ns

    writes = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"elements": [{"id": 1}]}

    class Session:
        def post(self, url, **kwargs):
            assert url == ns.OVERPASS_URL
            assert kwargs["data"] == ns.build_overpass_query(34.05, -118.25)
            assert kwargs["timeout"] == ns.REQUEST_TIMEOUT_S
            return Response()

    monkeypatch.setattr(ns.overlay_cache, "read_json", lambda *a, **k: None)
    monkeypatch.setattr(
        ns.overlay_cache, "write_json", lambda namespace, key, payload: writes.append(
            (namespace, key, payload)
        )
    )

    payload = ns.fetch_overpass(34.05, -118.25, session=Session())

    assert payload == {"elements": [{"id": 1}]}
    assert writes[0][0] == ns.CACHE_NAMESPACE
    assert writes[0][2] == payload


def test_fetch_overpass_uses_cache(monkeypatch):
    from app.core import nearby_signals as ns

    cached = {"elements": [{"id": 2}]}
    monkeypatch.setattr(ns.overlay_cache, "read_json", lambda *a, **k: cached)

    class Session:
        def post(self, *args, **kwargs):
            raise AssertionError("network should not be called for a cache hit")

    assert ns.fetch_overpass(34.05, -118.25, session=Session()) is cached


def test_parse_places_results_filters_convenience_and_radius():
    from app.core.nearby_signals import parse_places_results

    results = [
        {
            "name": "Corner Store",
            "geometry": {"location": {"lat": 34.05, "lng": -118.25}},
            "types": ["convenience_store", "store"],
        },
        {
            "name": "Market",
            "geometry": {"location": {"lat": 34.0502, "lng": -118.25}},
            "types": ["supermarket", "store"],
        },
        {
            "name": "Far Market",
            "geometry": {"location": {"lat": 35.0, "lng": -118.25}},
            "types": ["supermarket"],
        },
    ]

    hits = parse_places_results(
        results, pin_lat=34.05, pin_lng=-118.25, radius_mi=0.5
    )

    assert [hit["name"] for hit in hits] == ["Market"]


def test_compute_signals_osm_only(monkeypatch):
    from app.core import nearby_signals as ns

    def fake_overpass(lat, lng, **kwargs):
        return {
            "elements": [
                {
                    "type": "way",
                    "id": 9,
                    "center": {"lat": lat, "lon": lng},
                    "tags": {
                        "highway": "motorway",
                        "ref": "I-10",
                        "name": "Santa Monica Fwy",
                    },
                },
                {
                    "type": "node",
                    "id": 10,
                    "lat": lat,
                    "lon": lng,
                    "tags": {
                        "railway": "station",
                        "station": "light_rail",
                        "name": "Expo/Bundy",
                    },
                },
            ]
        }

    monkeypatch.setattr(ns, "fetch_overpass", fake_overpass)
    monkeypatch.setattr(ns, "google_key", lambda: "")
    payload = ns.compute_signals(34.05, -118.25)
    assert payload["highway"]["hit"] is True
    assert payload["transit"]["hit"] is True
    assert payload["playground"]["hit"] is False


def test_compute_signals_uses_places_when_key(monkeypatch):
    from app.core import nearby_signals as ns

    monkeypatch.setattr(ns, "fetch_overpass", lambda *a, **k: {"elements": []})
    monkeypatch.setattr(ns, "google_key", lambda: "fake-key")

    def fake_places(lat, lng, *, api_key, place_type, keyword, radius_m):
        if place_type == "supermarket":
            return [
                {
                    "name": "Trader Joe's",
                    "geometry": {"location": {"lat": lat, "lng": lng}},
                    "types": ["supermarket", "grocery_or_supermarket", "store"],
                }
            ]
        return []

    monkeypatch.setattr(ns, "fetch_places_nearby", fake_places)
    payload = ns.compute_signals(34.05, -118.25, api_key="fake-key")
    assert payload["grocery"]["hit"] is True
    assert payload["grocery"]["name"] == "Trader Joe's"


def test_compute_signals_shelter_searches_use_403_meters(monkeypatch):
    from app.core import nearby_signals as ns

    calls = []
    monkeypatch.setattr(ns, "fetch_overpass", lambda *a, **k: {"elements": []})

    def fake_places(lat, lng, *, api_key, place_type, keyword, radius_m):
        calls.append((place_type, keyword, radius_m))
        return []

    monkeypatch.setattr(ns, "fetch_places_nearby", fake_places)
    ns.compute_signals(34.05, -118.25, api_key="fake-key")

    shelter_calls = [call for call in calls if call[1] is not None]
    assert [call[1] for call in shelter_calls] == [
        "homeless shelter",
        "drug rehabilitation|transitional housing",
    ]
    assert all(call[2] == 403 for call in shelter_calls)


def test_compute_signals_places_failure_falls_back_per_key(monkeypatch):
    from app.core import nearby_signals as ns

    monkeypatch.setattr(
        ns,
        "fetch_overpass",
        lambda lat, lng: {
            "elements": [
                {
                    "type": "node",
                    "lat": lat,
                    "lon": lng,
                    "tags": {"shop": "supermarket", "name": "OSM Market"},
                }
            ]
        },
    )

    def failing_places(*args, **kwargs):
        raise RuntimeError("Places unavailable")

    monkeypatch.setattr(ns, "fetch_places_nearby", failing_places)
    payload = ns.compute_signals(34.05, -118.25, api_key="fake-key")

    assert payload["grocery"]["name"] == "OSM Market"
    assert payload["shelter"] == {"hit": False, "error": "Places unavailable"}


def test_compute_signals_overpass_failure_returns_all_keys(monkeypatch):
    from app.core import nearby_signals as ns

    monkeypatch.setattr(
        ns, "fetch_overpass", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
    )
    payload = ns.compute_signals(34.05, -118.25, api_key="")

    assert set(payload) == set(ns.SIGNAL_ORDER)
    assert all(entry == {"hit": False, "error": "down"} for entry in payload.values())
