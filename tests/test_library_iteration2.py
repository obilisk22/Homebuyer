"""Library iteration 2: sort + thumbnail lock APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect as sa_inspect

import app.core.db as db
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService, fetch_library_thumbnails


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "iter2.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    return db.get_session()


def _add_prop(
    session,
    *,
    address: str,
    list_price: float | None,
    created_offset_hours: int = 0,
) -> Property:
    prop = Property(
        address=address,
        zillow_url=f"https://www.zillow.com/homedetails/{address.replace(' ', '-')}/1_zpid/",
        list_price=list_price,
        financial=FinancialAssumptions(),
    )
    if created_offset_hours:
        prop.created_at = datetime.now(timezone.utc) - timedelta(hours=created_offset_hours)
    session.add(prop)
    session.commit()
    session.refresh(prop)
    return prop


def test_has_any_properties_distinguishes_empty_library(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        assert svc.has_any_properties() is False

        _add_prop(session, address="1 Any St", list_price=1.0)

        assert svc.has_any_properties() is True


def test_list_properties_sort_price_asc_nulls_last(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        p_mid = _add_prop(session, address="200 Mid St", list_price=200_000)
        p_null = _add_prop(session, address="No Price St", list_price=None)
        p_low = _add_prop(session, address="100 Low St", list_price=100_000)

        ordered = svc.list_properties(sort="price_asc")
        ids = [p.id for p in ordered]
        assert ids.index(p_low.id) < ids.index(p_mid.id)
        assert ids.index(p_mid.id) < ids.index(p_null.id)


def test_list_properties_does_not_eager_load_all_photos(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        prop = _add_prop(session, address="9 Photo Heavy St", list_price=500_000)
        for i in range(8):
            svc.add_photo_bytes(prop.id, f"img-{i}".encode(), f"p{i}.jpg", caption=f"Shot {i}")

        # Fresh list query — must not pull the full photo graph.
        listed = svc.list_properties()
        assert len(listed) == 1
        listed_prop = listed[0]
        state = sa_inspect(listed_prop)
        assert "photos" in state.unloaded
        assert "financial" not in state.unloaded
        assert listed_prop.financial is not None


def test_fetch_library_thumbnails_batch(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        with_id = _add_prop(session, address="1 Chosen Thumb St", list_price=1.0)
        a = svc.add_photo_bytes(with_id.id, b"a", "a.jpg", caption="A")
        b = svc.add_photo_bytes(with_id.id, b"b", "b.jpg", caption="B")
        svc.set_library_thumbnail(with_id.id, b.id)

        fallback = _add_prop(session, address="2 First Photo St", list_price=2.0)
        first = svc.add_photo_bytes(fallback.id, b"f0", "f0.jpg", caption="First")
        svc.add_photo_bytes(fallback.id, b"f1", "f1.jpg", caption="Second")

        empty = _add_prop(session, address="3 No Photos St", list_price=3.0)

        props = svc.list_properties(sort="newest")
        # Ensure list did not eager-load photos (batch path must not rely on it).
        for p in props:
            assert "photos" in sa_inspect(p).unloaded

        thumbs = fetch_library_thumbnails(session, props)
        assert thumbs[with_id.id].id == b.id
        assert thumbs[fallback.id].id == first.id
        assert empty.id not in thumbs
        assert a.id != b.id


def test_select_thumbnail_skips_when_locked(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        prop = _add_prop(session, address="1 Thumb St", list_price=1.0)
        kitchen = svc.add_photo_bytes(
            prop.id,
            b"fake-jpg-1",
            "k.jpg",
            caption="Living room",
        )
        exterior = svc.add_photo_bytes(
            prop.id,
            b"fake-jpg-2",
            "e.jpg",
            caption="Front exterior curb",
        )
        prop = svc.get_property(prop.id)
        assert prop is not None
        prop.thumbnail_photo_id = kitchen.id
        prop.thumbnail_locked = True
        session.commit()

        chosen = svc.select_thumbnail(prop.id)
        assert chosen is not None
        assert chosen.id == kitchen.id
        prop = svc.get_property(prop.id)
        assert prop is not None
        assert prop.thumbnail_photo_id == kitchen.id
        assert prop.thumbnail_locked is True
        assert exterior.id != kitchen.id


def test_set_library_thumbnail_locks(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        prop = _add_prop(session, address="2 Thumb St", list_price=1.0)
        a = svc.add_photo_bytes(prop.id, b"a", "a.jpg", caption="A")
        b = svc.add_photo_bytes(prop.id, b"b", "b.jpg", caption="B")
        photo = svc.set_library_thumbnail(prop.id, b.id)
        assert photo.id == b.id
        prop = svc.get_property(prop.id)
        assert prop is not None
        assert prop.thumbnail_photo_id == b.id
        assert prop.thumbnail_locked is True
        assert a.id != b.id


def test_unlock_and_select_thumbnail_clears_lock(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        svc = PropertyService(session)
        prop = _add_prop(session, address="3 Thumb St", list_price=1.0)
        living = svc.add_photo_bytes(
            prop.id, b"l", "l.jpg", caption="Living room", 
        )
        exterior = svc.add_photo_bytes(
            prop.id, b"e", "e.jpg", caption="Front exterior curb",
        )
        svc.set_library_thumbnail(prop.id, living.id)
        picked = svc.unlock_and_select_thumbnail(prop.id)
        prop = svc.get_property(prop.id)
        assert prop is not None
        assert prop.thumbnail_locked is False
        assert picked is not None
        assert picked.id == exterior.id
        assert prop.thumbnail_photo_id == exterior.id
