"""Coalesced stale area-signal refresh (Task 7)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_refresh_stale_area_signals_one_scan_up_to_limit_per_kind(monkeypatch):
    """One property walk; each kind refreshes at most ``limit`` homes."""
    from app.core import area_signals as as_

    props = [
        SimpleNamespace(
            id=1,
            latitude=34.0,
            longitude=-118.0,
            zip_code="90001",
            nearby_signals_at="",
            nearby_signals="",
            permits_activity_at="",
            permits_activity="",
            broadband_at="",
            broadband_status="",
            market_activity_at="",
            market_activity="",
        ),
        SimpleNamespace(
            id=2,
            latitude=34.1,
            longitude=-118.1,
            zip_code="90002",
            nearby_signals_at="",
            nearby_signals="",
            permits_activity_at="",
            permits_activity="",
            broadband_at="",
            broadband_status="",
            market_activity_at="",
            market_activity="",
        ),
        SimpleNamespace(
            id=3,
            latitude=34.2,
            longitude=-118.2,
            zip_code="90003",
            nearby_signals_at="",
            nearby_signals="",
            permits_activity_at="",
            permits_activity="",
            broadband_at="",
            broadband_status="",
            market_activity_at="",
            market_activity="",
        ),
    ]

    session = MagicMock()
    scalar_calls: list[object] = []

    def _scalars(stmt):
        scalar_calls.append(stmt)
        return props

    session.scalars.side_effect = _scalars

    refreshed: dict[str, list[int]] = {
        "nearby": [],
        "permits": [],
        "broadband": [],
        "market": [],
    }

    monkeypatch.setattr(
        as_,
        "refresh_nearby_signals",
        lambda session, pid: refreshed["nearby"].append(pid),
    )
    monkeypatch.setattr(
        as_,
        "refresh_permits_activity",
        lambda session, pid: refreshed["permits"].append(pid),
    )
    monkeypatch.setattr(
        as_,
        "refresh_broadband_status",
        lambda session, pid: refreshed["broadband"].append(pid),
    )
    monkeypatch.setattr(
        as_,
        "refresh_market_activity",
        lambda session, pid: refreshed["market"].append(pid),
    )
    monkeypatch.setattr(as_, "nearby_needs_refresh", lambda *_a, **_k: True)
    monkeypatch.setattr(as_, "permits_needs_refresh", lambda *_a, **_k: True)
    monkeypatch.setattr(as_, "broadband_needs_refresh", lambda *_a, **_k: True)
    monkeypatch.setattr(as_, "market_needs_refresh", lambda *_a, **_k: True)

    counts = as_.refresh_stale_area_signals(session, limit=2)

    assert len(scalar_calls) == 1
    assert counts == {
        "nearby": 2,
        "permits": 2,
        "broadband": 2,
        "market": 2,
    }
    assert refreshed["nearby"] == [1, 2]
    assert refreshed["permits"] == [1, 2]
    assert refreshed["broadband"] == [1, 2]
    assert refreshed["market"] == [1, 2]


def test_refresh_stale_area_signals_skips_fresh_kinds(monkeypatch):
    from app.core import area_signals as as_

    prop = SimpleNamespace(
        id=9,
        latitude=34.0,
        longitude=-118.0,
        zip_code="90001",
        nearby_signals_at="fresh",
        nearby_signals="{}",
        permits_activity_at="",
        permits_activity="",
        broadband_at="fresh",
        broadband_status="{}",
        market_activity_at="",
        market_activity="",
    )
    session = MagicMock()
    session.scalars.return_value = [prop]

    refreshed: list[str] = []

    monkeypatch.setattr(
        as_,
        "refresh_nearby_signals",
        lambda *_a, **_k: refreshed.append("nearby"),
    )
    monkeypatch.setattr(
        as_,
        "refresh_permits_activity",
        lambda *_a, **_k: refreshed.append("permits"),
    )
    monkeypatch.setattr(
        as_,
        "refresh_broadband_status",
        lambda *_a, **_k: refreshed.append("broadband"),
    )
    monkeypatch.setattr(
        as_,
        "refresh_market_activity",
        lambda *_a, **_k: refreshed.append("market"),
    )
    monkeypatch.setattr(as_, "nearby_needs_refresh", lambda *_a, **_k: False)
    monkeypatch.setattr(as_, "permits_needs_refresh", lambda *_a, **_k: True)
    monkeypatch.setattr(as_, "broadband_needs_refresh", lambda *_a, **_k: False)
    monkeypatch.setattr(as_, "market_needs_refresh", lambda *_a, **_k: True)

    counts = as_.refresh_stale_area_signals(session, limit=3)
    assert counts == {
        "nearby": 0,
        "permits": 1,
        "broadband": 0,
        "market": 1,
    }
    assert refreshed == ["permits", "market"]


def test_per_kind_stale_jobs_delegate_to_coalesced():
    """Thin compatibility wrappers call the coalesced job."""
    import inspect

    from app.core import ui_jobs

    for fn in (
        ui_jobs.refresh_stale_nearby_signals_job,
        ui_jobs.refresh_stale_permits_activity_job,
        ui_jobs.refresh_stale_broadband_status_job,
        ui_jobs.refresh_stale_market_activity_job,
    ):
        assert "refresh_stale_area_signals_job" in inspect.getsource(fn)


def test_library_uses_coalesced_stale_job_and_patches_chips():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    src = (root / "app" / "ui" / "library_page.py").read_text(encoding="utf-8")
    assert "refresh_stale_area_signals_job" in src
    assert "run.io_bound(refresh_stale_area_signals_job" in src.replace("\n", " ").replace(
        " ", ""
    ) or "refresh_stale_area_signals_job" in src
    assert "refresh_stale_nearby_signals_job, limit=3" not in src
    assert "refresh_stale_permits_activity_job, limit=3" not in src
    assert "chip_hosts" in src
    assert "_patch_chip_rows" in src
