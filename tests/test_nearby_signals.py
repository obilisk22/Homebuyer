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
