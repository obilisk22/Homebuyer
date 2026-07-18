"""Library iteration 2: sort + thumbnail lock APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import app.core.db as db
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService


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
