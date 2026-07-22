"""Add-home parallelization: photos ‖ area signals after pin + financial sync."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core import db
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService
from app.core.zillow_listing import ListingDetails
from app.core.zillow_photos import FetchedListingPhotos


ZILLOW_URL = (
    "https://www.zillow.com/homedetails/1-Test-St-Seattle-WA-98101/999_zpid/"
)


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "add_parallel.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    return db.get_session()


def _patch_listing_basics(monkeypatch, *, lat=47.6, lng=-122.3):
    details = ListingDetails(
        list_price=500_000,
        beds=3,
        baths=2.0,
        sqft=1500,
        city="Seattle",
        state="WA",
        zip_code="98101",
        address="1 Test St, Seattle, WA 98101",
    )
    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_html",
        lambda url: "<html>listing</html>",
    )
    monkeypatch.setattr(
        "app.core.property_service.extract_listing_details",
        lambda html: details,
    )
    monkeypatch.setattr(
        "app.core.property_service.geocode_address",
        lambda address: (lat, lng),
    )
    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_photo_urls",
        lambda zillow_url, *, html=None: FetchedListingPhotos(
            urls=[
                "https://photos.zillowstatic.com/fp/aaa-o_a.jpg",
                "https://photos.zillowstatic.com/fp/bbb-o_a.jpg",
            ],
            raw_html_bytes=10,
        ),
    )
    monkeypatch.setattr(
        "app.core.property_service.download_image",
        lambda url: (b"fake-bytes", "image/jpeg"),
    )
    # Avoid network during financial autofill in parallelization unit tests.
    monkeypatch.setattr(
        PropertyService,
        "_sync_financial_from_listing",
        lambda self, prop, details: None,
    )
    return details


def test_download_zillow_photo_files_returns_plain_dicts(tmp_path, monkeypatch):
    """Pure downloader writes files and returns ORM-ready dicts (no session)."""
    from app.core import listing_ingest

    uploads = tmp_path / "uploads"
    monkeypatch.setattr(listing_ingest, "UPLOADS_DIR", uploads)

    rows = listing_ingest.download_zillow_photo_files(
        42,
        ZILLOW_URL,
        html="<html></html>",
        photo_fetcher=lambda url, *, html=None: FetchedListingPhotos(
            urls=["https://photos.zillowstatic.com/fp/aaa-o_a.jpg"],
            raw_html_bytes=1,
        ),
        image_downloader=lambda url: (b"img", "image/jpeg"),
    )

    assert len(rows) == 1
    row = rows[0]
    assert set(row) >= {"path", "source_url", "caption", "sort_order"}
    assert row["source_url"].endswith("aaa-o_a.jpg")
    assert (uploads / row["path"]).is_file()
    assert row["sort_order"] == 0


def test_add_from_zillow_uses_thread_pool_for_photos_and_signals(
    tmp_path, monkeypatch
):
    """After pin + financial sync, photos and signals are scheduled on a pool."""
    session = _session(tmp_path, monkeypatch)
    _patch_listing_basics(monkeypatch)

    submitted: list[str] = []
    real_executor = ThreadPoolExecutor

    class TrackingExecutor(ThreadPoolExecutor):
        def submit(self, fn, *args, **kwargs):
            name = getattr(fn, "__name__", repr(fn))
            submitted.append(name)
            return super().submit(fn, *args, **kwargs)

    monkeypatch.setattr(
        "app.core.listing_ingest.ThreadPoolExecutor", TrackingExecutor
    )

    # Keep signal computes cheap / offline.
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_signals",
        lambda lat, lng, **kw: {
            "highway": {"hit": False},
            "transit": {"hit": False},
            "playground": {"hit": False},
            "grocery": {"hit": False},
            "shelter": {"hit": False},
        },
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_permit_activity",
        lambda lat, lng, *, city="": {
            "supported": False,
            "high_activity": False,
            "count": 0,
        },
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_broadband",
        lambda lat, lng: {"status": "ok", "has_fixed": True},
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_market_activity",
        lambda zip_code: {
            "zip_code": zip_code,
            "active": False,
            "homes_sold": 3,
        },
    )

    svc = PropertyService(session)
    prop, imported = svc.add_from_zillow(ZILLOW_URL, import_photos=True)

    assert imported == 2
    assert len(prop.photos) == 2
    assert prop.nearby_signals
    assert prop.permits_activity
    assert prop.broadband_status
    assert prop.market_activity
    assert any("photo" in n.lower() or "download" in n.lower() for n in submitted)
    assert len(submitted) >= 2  # at least photos + one signal kind


def test_add_from_zillow_photos_and_signals_overlap_in_time(tmp_path, monkeypatch):
    """Photo download work and a signal lookup should overlap (not fully serial)."""
    session = _session(tmp_path, monkeypatch)
    _patch_listing_basics(monkeypatch)

    events: list[tuple[str, float]] = []
    lock = threading.Lock()

    def mark(label: str) -> None:
        with lock:
            events.append((label, time.perf_counter()))

    def slow_download(url: str):
        mark("photo_start")
        time.sleep(0.08)
        mark("photo_end")
        return (b"fake", "image/jpeg")

    def slow_nearby(lat, lng, **kw):
        mark("nearby_start")
        time.sleep(0.08)
        mark("nearby_end")
        return {
            "highway": {"hit": False},
            "transit": {"hit": False},
            "playground": {"hit": False},
            "grocery": {"hit": False},
            "shelter": {"hit": False},
        }

    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_photo_urls",
        lambda zillow_url, *, html=None: FetchedListingPhotos(
            urls=["https://photos.zillowstatic.com/fp/aaa-o_a.jpg"],
            raw_html_bytes=10,
        ),
    )

    monkeypatch.setattr("app.core.property_service.download_image", slow_download)
    monkeypatch.setattr("app.core.listing_ingest.compute_signals", slow_nearby)
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_permit_activity",
        lambda *a, **k: {"supported": False, "high_activity": False, "count": 0},
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_broadband",
        lambda *a, **k: {"status": "ok", "has_fixed": True},
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_market_activity",
        lambda *a, **k: {"active": False, "homes_sold": 1},
    )

    svc = PropertyService(session)
    prop, imported = svc.add_from_zillow(ZILLOW_URL, import_photos=True)

    assert imported == 1
    assert prop.nearby_signals

    starts = {}
    ends = {}
    for label, t in events:
        if label.endswith("_start") and label not in starts:
            starts[label] = t
        if label.endswith("_end") and label not in ends:
            ends[label] = t
    assert "photo_start" in starts and "nearby_start" in starts
    # Overlap: each start happens before the other finishes.
    assert starts["photo_start"] < ends["nearby_end"]
    assert starts["nearby_start"] < ends["photo_end"]


def test_add_from_zillow_signal_failure_is_best_effort(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    _patch_listing_basics(monkeypatch)

    monkeypatch.setattr(
        "app.core.listing_ingest.compute_signals",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("overpass down")),
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_permit_activity",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("soda down")),
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_broadband",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fcc down")),
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_market_activity",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("redfin down")),
    )

    svc = PropertyService(session)
    prop, imported = svc.add_from_zillow(ZILLOW_URL, import_photos=True)

    assert imported == 2
    assert prop.id is not None
    assert prop.latitude == 47.6


def test_add_from_zillow_workers_do_not_receive_orm_session(tmp_path, monkeypatch):
    """Pool workers must return plain data; session.commit stays on the owner thread."""
    session = _session(tmp_path, monkeypatch)
    _patch_listing_basics(monkeypatch)

    owner_thread = threading.get_ident()
    commit_threads: list[int] = []
    original_commit = session.commit

    def tracking_commit():
        commit_threads.append(threading.get_ident())
        return original_commit()

    session.commit = tracking_commit  # type: ignore[method-assign]

    monkeypatch.setattr(
        "app.core.listing_ingest.compute_signals",
        lambda *a, **k: {
            "highway": {"hit": True, "name": "I-5", "distance_ft": 100},
            "transit": {"hit": False},
            "playground": {"hit": False},
            "grocery": {"hit": False},
            "shelter": {"hit": False},
        },
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_permit_activity",
        lambda *a, **k: {"supported": True, "high_activity": False, "count": 1},
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_broadband",
        lambda *a, **k: {"status": "ok", "has_fixed": True},
    )
    monkeypatch.setattr(
        "app.core.listing_ingest.compute_market_activity",
        lambda *a, **k: {"active": True, "homes_sold": 40},
    )

    svc = PropertyService(session)
    prop, imported = svc.add_from_zillow(ZILLOW_URL, import_photos=True)

    assert imported == 2
    assert all(t == owner_thread for t in commit_threads)
    payload = json.loads(prop.nearby_signals or "{}")
    assert payload["highway"]["hit"] is True
