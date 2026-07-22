from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.fcc_broadband import (
    needs_refresh as broadband_needs_refresh,
    refresh_property_broadband,
)
from app.core.market_activity import (
    needs_refresh as market_needs_refresh,
    refresh_property_market_activity,
)
from app.core.models import Property
from app.core.nearby_signals import needs_refresh as nearby_needs_refresh
from app.core.nearby_signals import refresh_property_signals
from app.core.permits_nearby import (
    needs_refresh as permits_needs_refresh,
    refresh_property_permits,
)

PropertyLookup = Callable[[int], Property | None]
PropertyRefresh = Callable[[int], Property]
SignalRefresh = Callable[[Property], object]


def _get_property(session: Session, property_id: int) -> Property | None:
    return session.get(Property, property_id)


def _refresh_one(
    session: Session,
    property_id: int,
    *,
    lookup: PropertyLookup | None,
    refresher: SignalRefresh,
) -> Property:
    prop = (lookup or (lambda value: _get_property(session, value)))(property_id)
    if prop is None:
        raise ValueError("Property not found.")
    try:
        refresher(prop)
        session.commit()
        session.refresh(prop)
    except Exception:  # noqa: BLE001 - area providers never block property flows
        session.rollback()
    return prop


def refresh_nearby_signals(
    session: Session,
    property_id: int,
    *,
    lookup: PropertyLookup | None = None,
    refresher: SignalRefresh = refresh_property_signals,
) -> Property:
    return _refresh_one(
        session, property_id, lookup=lookup, refresher=refresher
    )


def refresh_permits_activity(
    session: Session,
    property_id: int,
    *,
    lookup: PropertyLookup | None = None,
    refresher: SignalRefresh = refresh_property_permits,
) -> Property:
    return _refresh_one(
        session, property_id, lookup=lookup, refresher=refresher
    )


def refresh_broadband_status(
    session: Session,
    property_id: int,
    *,
    lookup: PropertyLookup | None = None,
    refresher: SignalRefresh = refresh_property_broadband,
) -> Property:
    return _refresh_one(
        session, property_id, lookup=lookup, refresher=refresher
    )


def refresh_market_activity(
    session: Session,
    property_id: int,
    *,
    lookup: PropertyLookup | None = None,
    refresher: SignalRefresh = refresh_property_market_activity,
) -> Property:
    return _refresh_one(
        session, property_id, lookup=lookup, refresher=refresher
    )


def refresh_property_all(prop: Property) -> None:
    """Best-effort refresh of every persisted area signal on an attached property."""
    for refresher in (
        refresh_property_signals,
        refresh_property_permits,
        refresh_property_broadband,
        refresh_property_market_activity,
    ):
        try:
            refresher(prop)
        except Exception:  # noqa: BLE001 - one provider must not block the others
            pass


def _refresh_stale(
    session: Session,
    *,
    limit: int,
    statement,
    is_stale: Callable[[Property], bool],
    refresh: PropertyRefresh,
    pause_seconds: float = 0,
) -> int:
    if limit <= 0:
        return 0
    refreshed = 0
    for prop in session.scalars(statement):
        if not is_stale(prop):
            continue
        refresh(prop.id)
        refreshed += 1
        if refreshed >= limit:
            break
        if pause_seconds:
            time.sleep(pause_seconds)
    return refreshed


def refresh_stale_nearby_signals(
    session: Session,
    *,
    limit: int = 3,
    refresh: PropertyRefresh | None = None,
    needs_refresh_fn: Callable[[str | None, str | None], bool] = nearby_needs_refresh,
) -> int:
    stmt = (
        select(Property)
        .where(Property.latitude.is_not(None), Property.longitude.is_not(None))
        .order_by(Property.updated_at.desc())
    )
    callback = refresh or (lambda pid: refresh_nearby_signals(session, pid))
    return _refresh_stale(
        session,
        limit=limit,
        statement=stmt,
        is_stale=lambda prop: needs_refresh_fn(
            prop.nearby_signals_at, prop.nearby_signals
        ),
        refresh=callback,
        pause_seconds=1.25,
    )


def refresh_stale_permits_activity(
    session: Session,
    *,
    limit: int = 3,
    refresh: PropertyRefresh | None = None,
    needs_refresh_fn: Callable[[str | None, str | None], bool] = permits_needs_refresh,
) -> int:
    stmt = (
        select(Property)
        .where(Property.latitude.is_not(None), Property.longitude.is_not(None))
        .order_by(Property.updated_at.desc())
    )
    callback = refresh or (lambda pid: refresh_permits_activity(session, pid))
    return _refresh_stale(
        session,
        limit=limit,
        statement=stmt,
        is_stale=lambda prop: needs_refresh_fn(
            prop.permits_activity_at, prop.permits_activity
        ),
        refresh=callback,
    )


def refresh_stale_broadband_status(
    session: Session,
    *,
    limit: int = 3,
    refresh: PropertyRefresh | None = None,
    needs_refresh_fn: Callable[[str | None, str | None], bool] = broadband_needs_refresh,
) -> int:
    stmt = (
        select(Property)
        .where(Property.latitude.is_not(None), Property.longitude.is_not(None))
        .order_by(Property.updated_at.desc())
    )
    callback = refresh or (lambda pid: refresh_broadband_status(session, pid))
    return _refresh_stale(
        session,
        limit=limit,
        statement=stmt,
        is_stale=lambda prop: needs_refresh_fn(prop.broadband_at, prop.broadband_status),
        refresh=callback,
    )


def refresh_stale_market_activity(
    session: Session,
    *,
    limit: int = 3,
    refresh: PropertyRefresh | None = None,
    needs_refresh_fn: Callable[[str | None, str | None], bool] = market_needs_refresh,
) -> int:
    stmt = select(Property).order_by(Property.updated_at.desc())
    callback = refresh or (lambda pid: refresh_market_activity(session, pid))
    return _refresh_stale(
        session,
        limit=limit,
        statement=stmt,
        is_stale=lambda prop: bool((prop.zip_code or "").strip())
        and needs_refresh_fn(prop.market_activity_at, prop.market_activity),
        refresh=callback,
    )


def refresh_stale_area_signals(
    session: Session, *, limit: int = 3
) -> dict[str, int]:
    """Refresh each stale area-signal kind and return per-kind counts."""
    return {
        "nearby": refresh_stale_nearby_signals(session, limit=limit),
        "permits": refresh_stale_permits_activity(session, limit=limit),
        "broadband": refresh_stale_broadband_status(session, limit=limit),
        "market": refresh_stale_market_activity(session, limit=limit),
    }
