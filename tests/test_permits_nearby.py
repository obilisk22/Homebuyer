"""Tests for nearby building-permit activity (TODO-043)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core import permits_nearby as pn


def test_radius_and_threshold_constants():
    assert pn.RADIUS_MI == 0.25
    assert pn.RADIUS_M == 402
    assert pn.WINDOW_MONTHS == 24
    assert pn.HIGH_ACTIVITY_THRESHOLD == 8


def test_resolve_permit_city_by_name_and_bbox():
    assert pn.resolve_permit_city("Los Angeles").key == "los_angeles"
    assert pn.resolve_permit_city("Seattle").key == "seattle"
    assert pn.resolve_permit_city("Austin").key == "austin"
    assert pn.resolve_permit_city("Sherman Oaks").key == "los_angeles"
    assert pn.resolve_permit_city("Portland") is None
    # Pin in Seattle metro without city string.
    assert pn.resolve_permit_city("", 47.61, -122.33).key == "seattle"
    # Outside supported metros.
    assert pn.resolve_permit_city("Denver", 39.74, -104.99) is None
    assert pn.resolve_permit_city("Austin") is not None
    assert pn.resolve_permit_city("Miami") is None


def test_empty_activity_and_parse_roundtrip():
    empty = pn.empty_activity()
    assert empty["high_activity"] is False
    assert empty["count"] == 0
    assert empty["supported"] is False

    raw = json.dumps(
        {
            "city": "los_angeles",
            "supported": True,
            "high_activity": True,
            "count": 12,
            "radius_mi": 0.25,
            "window_months": 24,
            "threshold": 8,
            "nearest_distance_mi": 0.08,
            "sample_types": ["Bldg-New", "Bldg-Demolition"],
        }
    )
    parsed = pn.parse_activity_json(raw)
    assert parsed["high_activity"] is True
    assert parsed["count"] == 12
    assert parsed["sample_types"] == ["Bldg-New", "Bldg-Demolition"]
    assert pn.parse_activity_json("")["count"] == 0
    assert pn.parse_activity_json("not-json")["supported"] is False


def test_tooltip_and_chip_spec():
    low = pn.empty_activity(city="seattle", supported=True)
    low["count"] = 3
    low["high_activity"] = False
    assert pn.chip_spec_for(low) is None

    high = {
        "city": "austin",
        "supported": True,
        "high_activity": True,
        "count": 11,
        "radius_mi": 0.25,
        "window_months": 24,
        "threshold": 8,
        "nearest_distance_mi": 0.12,
        "sample_types": ["Building Permit", "Electrical Permit"],
    }
    tip = pn.tooltip_for(high)
    assert "11 permits" in tip
    assert "0.25 mi" in tip
    assert "nearest 0.12 mi" in tip
    chip = pn.chip_spec_for(high)
    assert chip is not None
    assert chip["key"] == "permits"
    assert chip["icon"] == "construction"
    assert chip["tone"] == "amber"
    assert chip["count"] == 11
    assert "11 permits" in chip["tooltip"]

    unsupported = pn.empty_activity(supported=False)
    assert pn.chip_spec_for(unsupported) is None


def test_is_stale_and_needs_refresh():
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    assert pn.is_stale(None, now=now) is True
    fresh = (now - timedelta(days=5)).isoformat()
    assert pn.is_stale(fresh, now=now) is False
    old = (now - timedelta(days=31)).isoformat()
    assert pn.is_stale(old, now=now) is True

    errored = json.dumps(
        {"city": "seattle", "supported": True, "high_activity": False, "count": 0, "error": "503"}
    )
    assert pn.needs_refresh(fresh, errored, now=now) is True
    ok = json.dumps(
        {"city": "seattle", "supported": True, "high_activity": False, "count": 2}
    )
    assert pn.needs_refresh(fresh, ok, now=now) is False


def test_status_cancelled_filter():
    assert pn._status_cancelled("Withdrawn") is True
    assert pn._status_cancelled("Canceled") is True
    assert pn._status_cancelled("Issued") is False
    assert pn._status_cancelled("Permit Finaled") is False


def _fake_row(cfg_key: str, *, lat: float, lng: float, ptype: str, status: str, issued: str):
    if cfg_key == "los_angeles":
        return {
            "lat": str(lat),
            "lon": str(lng),
            "permit_type": ptype,
            "status_desc": status,
            "issue_date": issued,
        }
    if cfg_key == "seattle":
        return {
            "latitude": str(lat),
            "longitude": str(lng),
            "permittypemapped": ptype,
            "statuscurrent": status,
            "issueddate": issued,
        }
    return {
        "latitude": str(lat),
        "longitude": str(lng),
        "permit_type_desc": ptype,
        "status_current": status,
        "issue_date": issued,
    }


def test_compute_high_activity_with_mocked_soda(monkeypatch):
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    pin_lat, pin_lng = 34.0522, -118.2437
    issued = "2025-06-01T00:00:00.000"
    rows = []
    for i in range(10):
        # ~0.05 mi north offsets (small enough to stay in radius).
        rows.append(
            _fake_row(
                "los_angeles",
                lat=pin_lat + 0.0005 * (i % 3),
                lng=pin_lng + 0.0005 * (i % 2),
                ptype="Bldg-Alter/Repair" if i % 2 == 0 else "Bldg-Demolition",
                status="Issued",
                issued=issued,
            )
        )
    # Cancelled should be ignored.
    rows.append(
        _fake_row(
            "los_angeles",
            lat=pin_lat,
            lng=pin_lng,
            ptype="Bldg-New",
            status="Permit Cancelled",
            issued=issued,
        )
    )
    # Sign type should be filtered client-side if it slipped through.
    rows.append(
        _fake_row(
            "los_angeles",
            lat=pin_lat,
            lng=pin_lng,
            ptype="Sign",
            status="Issued",
            issued=issued,
        )
    )

    monkeypatch.setattr(pn, "_soda_fetch", lambda *a, **k: rows)

    out = pn.compute_permit_activity(pin_lat, pin_lng, city="Los Angeles", now=now)
    assert out["supported"] is True
    assert out["city"] == "los_angeles"
    assert out["count"] == 10
    assert out["high_activity"] is True
    assert out["threshold"] == 8
    assert out["nearest_distance_mi"] is not None
    assert "Bldg-Alter/Repair" in out["sample_types"]


def test_compute_below_threshold_not_high(monkeypatch):
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    pin_lat, pin_lng = 47.6062, -122.3321
    rows = [
        _fake_row(
            "seattle",
            lat=pin_lat + 0.0003,
            lng=pin_lng,
            ptype="Building",
            status="Issued",
            issued="2025-01-15T00:00:00.000",
        )
        for _ in range(5)
    ]
    monkeypatch.setattr(pn, "_soda_fetch", lambda *a, **k: rows)
    out = pn.compute_permit_activity(pin_lat, pin_lng, city="Seattle", now=now)
    assert out["count"] == 5
    assert out["high_activity"] is False
    assert pn.chip_spec_for(out) is None


def test_compute_unsupported_city_skips_network(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not call SODA")

    monkeypatch.setattr(pn, "_soda_fetch", boom)
    out = pn.compute_permit_activity(39.74, -104.99, city="Denver")
    assert out["supported"] is False
    assert out["high_activity"] is False
    assert out["count"] == 0


def test_compute_soda_error_is_best_effort(monkeypatch):
    def fail(*_a, **_k):
        raise requests_http_error()

    class requests_http_error(Exception):
        pass

    monkeypatch.setattr(pn, "_soda_fetch", fail)
    out = pn.compute_permit_activity(30.27, -97.74, city="Austin")
    assert out["supported"] is True
    assert out["high_activity"] is False
    assert out["count"] == 0
    assert out.get("error")


def test_soda_fetch_builds_within_circle_and_caches(monkeypatch, tmp_path):
    cfg = pn.PERMIT_CITIES["austin"]
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "latitude": "30.27",
                    "longitude": "-97.74",
                    "permit_type_desc": "Building Permit",
                    "status_current": "Active",
                    "issue_date": "2025-06-01T00:00:00.000",
                }
            ]

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(pn.requests, "get", fake_get)
    monkeypatch.setattr(pn.overlay_cache, "cache_dir", lambda *p: tmp_path.joinpath(*p))
    # Force miss then hit.
    monkeypatch.setattr(pn.overlay_cache, "read_json", lambda *a, **k: None)
    written: list = []

    def fake_write(ns, key, payload):
        written.append((ns, key, payload))
        return tmp_path / f"{key}.json"

    monkeypatch.setattr(pn.overlay_cache, "write_json", fake_write)
    monkeypatch.setattr(pn, "socrata_app_token", lambda: "tok-123")

    since = datetime(2024, 7, 19, tzinfo=timezone.utc)
    rows = pn._soda_fetch(cfg, 30.2672, -97.7431, since=since, limit=50)
    assert len(rows) == 1
    assert "data.austintexas.gov" in captured["url"]
    assert "3syk-w9eu" in captured["url"]
    where = captured["params"]["$where"]
    assert "within_circle(location, 30.2672, -97.7431, 402)" in where
    assert "issue_date >=" in where
    assert "Building Permit" in where
    assert captured["headers"]["X-App-Token"] == "tok-123"
    assert written and written[0][0] == "permits"


def test_refresh_property_permits_writes_json(monkeypatch):
    expected = {
        "city": "los_angeles",
        "supported": True,
        "high_activity": True,
        "count": 9,
        "radius_mi": 0.25,
        "window_months": 24,
        "threshold": 8,
        "nearest_distance_mi": 0.1,
        "sample_types": ["Bldg-New"],
    }
    monkeypatch.setattr(pn, "compute_permit_activity", lambda *a, **k: expected)
    prop = SimpleNamespace(
        latitude=34.0,
        longitude=-118.0,
        city="Los Angeles",
        permits_activity="",
        permits_activity_at="",
    )
    out = pn.refresh_property_permits(prop)
    assert out == expected
    assert json.loads(prop.permits_activity)["count"] == 9
    assert datetime.fromisoformat(prop.permits_activity_at).tzinfo is not None


def test_refresh_property_permits_without_coordinates_keeps_cache(monkeypatch):
    cached = {"city": "seattle", "supported": True, "high_activity": False, "count": 1}
    prop = SimpleNamespace(
        latitude=None,
        longitude=None,
        city="Seattle",
        permits_activity=json.dumps(cached),
        permits_activity_at="existing",
    )
    monkeypatch.setattr(
        pn,
        "compute_permit_activity",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not compute")),
    )
    assert pn.refresh_property_permits(prop)["count"] == 1
    assert prop.permits_activity_at == "existing"


def test_property_maps_permits_columns():
    from app.core.models import Property

    assert Property.__table__.c.permits_activity.type.__class__.__name__ == "Text"
    assert Property.__table__.c.permits_activity_at.type.__class__.__name__ == "String"


def test_property_service_refresh_permits_swallows_errors(monkeypatch):
    from app.core import property_service as ps
    from app.core.property_service import PropertyService

    prop = SimpleNamespace(
        id=1,
        latitude=34.0,
        longitude=-118.0,
        city="Los Angeles",
        permits_activity="",
        permits_activity_at="",
    )
    session = MagicMock()
    service = PropertyService(session)
    monkeypatch.setattr(service, "get_property", lambda _id: prop)

    def boom(_prop):
        raise RuntimeError("network down")

    monkeypatch.setattr(ps, "refresh_property_permits", boom)
    out = service.refresh_permits_activity(1)
    assert out is prop
    session.rollback.assert_called()


def test_austin_type_filter_client():
    cfg = pn.PERMIT_CITIES["austin"]
    assert pn._type_matches_client(cfg, "Building Permit") is True
    assert pn._type_matches_client(cfg, "Electrical Permit") is True
    assert pn._type_matches_client(cfg, "Plumbing Permit") is False
