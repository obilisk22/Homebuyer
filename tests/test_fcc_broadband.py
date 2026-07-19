"""Tests for FCC BDC broadband status (TODO-042)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core import fcc_broadband as bb
from app.core.listing_signals import listing_risk_chips


def test_has_fixed_and_tech_summary_rules():
    # Cable/DSL without fiber is still fixed — not a risk.
    assert bb.has_fixed_broadband(copper=1, cable=0, fiber=0) is True
    assert bb.has_fixed_broadband(copper=0, cable=2, fiber=0) is True
    assert bb.has_fixed_broadband(fiber=1) is True
    assert bb.has_fixed_broadband(ltfw=1) is True
    assert bb.has_fixed_broadband() is False
    assert bb.tech_summary_from_counts(fiber=1, cable=1) == "Fiber, Cable"
    assert bb.tech_summary_from_counts() == "None"


def test_status_from_block_attrs_missing_vs_ok():
    ok = bb.status_from_block_attrs(
        {
            "GEOID": "060372074001024",
            "TotalBSLs": 1,
            "ServedBSLs": 1,
            "UnderservedBSLs": 0,
            "UnservedBSLs": 0,
            "UniqueProvidersCopper": None,
            "UniqueProvidersCable": 1,
            "UniqueProvidersFiber": None,
            "UniqueProvidersLTFW": 0,
            "UniqueProvidersLBRTFW": None,
        }
    )
    assert ok["status"] == "ok"
    assert ok["has_fixed"] is True
    assert ok["providers_cable"] == 1
    assert "Cable" in ok["tech_summary"]
    assert bb.is_broadband_risk(ok) is False
    assert bb.chip_spec_for(ok) is None

    missing = bb.status_from_block_attrs(
        {
            "GEOID": "999990000000000",
            "TotalBSLs": 2,
            "ServedBSLs": 0,
            "UnderservedBSLs": 0,
            "UnservedBSLs": 2,
            "UniqueProvidersCopper": 0,
            "UniqueProvidersCable": None,
            "UniqueProvidersFiber": 0,
            "UniqueProvidersLTFW": None,
            "UniqueProvidersLBRTFW": 0,
        }
    )
    assert missing["status"] == "missing"
    assert missing["has_fixed"] is False
    assert bb.is_broadband_risk(missing) is True
    chip = bb.chip_spec_for(missing)
    assert chip is not None
    assert chip["key"] == "no_broadband"
    assert chip["icon"] == "wifi_off"


def test_lookup_never_raises_and_empty_status():
    empty = bb.lookup_broadband()
    assert empty["status"] == "unknown"
    assert empty["reason"] == "no_input"
    assert empty["has_fixed"] is None
    assert bb.chip_spec_for(empty) is None


def test_needs_refresh_when_stale():
    assert bb.needs_refresh(None, None) is True
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    fresh = (now - timedelta(days=5)).isoformat()
    assert (
        bb.needs_refresh(
            fresh,
            json.dumps({"status": "ok", "has_fixed": True}),
            now=now,
        )
        is False
    )


def test_parse_status_json_roundtrip():
    raw = json.dumps(
        {
            "status": "missing",
            "has_fixed": False,
            "block_geoid": "060371234567890",
            "providers_copper": 0,
            "providers_cable": 0,
            "providers_fiber": 0,
            "providers_ltfw": 0,
            "providers_lbrtfw": 0,
            "tech_summary": "None",
            "source": bb.BDC_SOURCE_LABEL,
        }
    )
    parsed = bb.parse_status_json(raw)
    assert parsed["has_fixed"] is False
    assert parsed["block_geoid"] == "060371234567890"
    assert parsed["block_fips"] == "060371234567890"
    assert bb.parse_status_json("")["status"] == "unknown"
    assert bb.parse_status_json("not-json")["status"] == "error"


def test_broadband_risk_chip_tuple():
    prop = SimpleNamespace(
        broadband_status=json.dumps(
            {
                "status": "missing",
                "has_fixed": False,
                "tech_summary": "None",
                "block_geoid": "06037",
            }
        )
    )
    chip = bb.broadband_risk_chip(prop)
    assert chip is not None
    key, entry = chip
    assert key == "no_broadband"
    assert entry["icon"] == "wifi_off"
    assert "No fixed broadband" in entry["tooltip"]
    assert bb.broadband_risk_entry(prop)["key"] == "no_broadband"

    ok_prop = SimpleNamespace(
        broadband_status=json.dumps({"status": "ok", "has_fixed": True, "tech_summary": "Fiber"})
    )
    assert bb.broadband_risk_chip(ok_prop) is None


def test_is_stale_and_needs_refresh():
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    assert bb.is_stale(None, now=now) is True
    fresh = (now - timedelta(days=5)).isoformat()
    assert bb.is_stale(fresh, now=now) is False
    old = (now - timedelta(days=31)).isoformat()
    assert bb.is_stale(old, now=now) is True
    assert bb.needs_refresh(fresh, json.dumps({"status": "ok", "has_fixed": True}), now=now) is False
    assert (
        bb.needs_refresh(
            fresh,
            json.dumps({"status": "unknown", "has_fixed": None, "error": "boom"}),
            now=now,
        )
        is True
    )


def test_compute_broadband_mocked_http(monkeypatch):
    calls: list[str] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.status_code = 200
        if "block/find" in url:
            resp.json.return_value = {
                "Block": {"FIPS": "060372074001024"},
                "status": "OK",
            }
        else:
            resp.json.return_value = {
                "features": [
                    {
                        "attributes": {
                            "GEOID": "060372074001024",
                            "TotalBSLs": 1,
                            "ServedBSLs": 0,
                            "UnderservedBSLs": 0,
                            "UnservedBSLs": 1,
                            "UniqueProvidersCopper": 0,
                            "UniqueProvidersCable": 0,
                            "UniqueProvidersFiber": 0,
                            "UniqueProvidersLTFW": 0,
                            "UniqueProvidersLBRTFW": 0,
                        }
                    }
                ]
            }
        return resp

    monkeypatch.setattr(bb.requests, "get", fake_get)
    monkeypatch.setattr(bb.overlay_cache, "read_json", lambda *a, **k: None)
    monkeypatch.setattr(bb.overlay_cache, "write_json", lambda *a, **k: None)

    status = bb.compute_broadband(34.05, -118.25)
    assert status["has_fixed"] is False
    assert status["block_geoid"] == "060372074001024"
    assert any("block/find" in u for u in calls)
    assert any("FeatureServer" in u for u in calls)

    never_raises = bb.compute_broadband_status(34.05, -118.25)
    assert never_raises["has_fixed"] is False

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(bb, "compute_broadband", boom)
    failed = bb.lookup_broadband(lat=34.0, lng=-118.0)
    assert failed["status"] == "error"
    assert "network" in (failed.get("error") or "")


def test_refresh_property_broadband_writes_json(monkeypatch):
    monkeypatch.setattr(
        bb,
        "compute_broadband",
        lambda lat, lng: {
            "status": "ok",
            "has_fixed": True,
            "block_geoid": "06037",
            "block_fips": "06037",
            "providers_copper": 0,
            "providers_cable": 1,
            "providers_fiber": 0,
            "providers_ltfw": 0,
            "providers_lbrtfw": 0,
            "tech_summary": "Cable",
            "source": bb.BDC_SOURCE_LABEL,
            "reason": "living_atlas_bdc_block",
        },
    )
    prop = SimpleNamespace(
        latitude=34.0,
        longitude=-118.0,
        broadband_status="",
        broadband_at="",
    )
    out = bb.refresh_property_broadband(prop)
    assert out["has_fixed"] is True
    assert json.loads(prop.broadband_status)["providers_cable"] == 1
    assert datetime.fromisoformat(prop.broadband_at).tzinfo is not None


def test_refresh_property_broadband_without_coordinates_keeps_cache(monkeypatch):
    cached = {"status": "ok", "has_fixed": True, "providers_fiber": 1}
    prop = SimpleNamespace(
        latitude=None,
        longitude=None,
        broadband_status=json.dumps(cached),
        broadband_at="existing",
    )
    monkeypatch.setattr(
        bb,
        "compute_broadband",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")),
    )
    assert bb.refresh_property_broadband(prop)["has_fixed"] is True
    assert prop.broadband_at == "existing"


def test_property_maps_broadband_columns():
    from app.core.models import Property

    assert Property.__table__.c.broadband_status.type.__class__.__name__ == "Text"
    assert Property.__table__.c.broadband_at.type.__class__.__name__ == "String"


def test_property_service_refresh_broadband_swallows_errors(monkeypatch):
    from app.core import property_service as ps

    prop = SimpleNamespace(
        id=1,
        latitude=34.0,
        longitude=-118.0,
        broadband_status="",
        broadband_at="",
    )
    session = MagicMock()
    service = ps.PropertyService(session)
    monkeypatch.setattr(service, "get_property", lambda _id: prop)

    def boom(_prop):
        raise RuntimeError("fcc down")

    monkeypatch.setattr(ps, "refresh_property_broadband", boom)
    out = service.refresh_broadband_status(1)
    assert out is prop
    session.rollback.assert_called()


def test_listing_risk_chips_includes_broadband():
    chips = listing_risk_chips(
        SimpleNamespace(
            has_central_ac=True,
            cooling="Central",
            broadband_status=json.dumps({"status": "missing", "has_fixed": False}),
        )
    )
    assert any(c["key"] == "no_broadband" for c in chips)

    chips2 = listing_risk_chips(
        SimpleNamespace(
            has_central_ac=False,
            cooling="None",
            broadband_status=json.dumps({"status": "ok", "has_fixed": True}),
        )
    )
    keys = [c["key"] for c in chips2]
    assert keys == ["no_central_ac"]


def test_endpoints_documented():
    assert "broadbandmap.fcc.gov/api/public/map" in bb.BDC_PUBLIC_MAP_BASE
    assert "geo.fcc.gov" in bb.GEO_BLOCK_URL
    assert "FeatureServer" in bb.BDC_BLOCKS_URL
    assert bb.CACHE_NAMESPACE == "fcc_broadband"
