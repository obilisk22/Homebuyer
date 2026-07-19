"""Session-safe workers for NiceGUI ``run.io_bound``.

Long sync I/O (Zillow scrape, geocode, Gemini, map overlays) must not run on the
event loop — it freezes WebSocket heartbeats and shows “Connection lost”.

Each job opens its own DB session inside the worker thread. Pass only plain
values in/out; never share ORM instances or UI objects across threads.
"""

from __future__ import annotations

from typing import Any

from app.core.db import get_session
from app.core.property_service import PropertyService
from app.core.school_zones import resolve_assigned
from app.core.schooldigger import enrich_assigned, has_schooldigger_keys


def add_from_zillow_job(zillow_url: str) -> tuple[int, int]:
    """Import a home; returns ``(property_id, photo_count)``."""
    with get_session() as session:
        prop, imported = PropertyService(session).add_from_zillow(
            zillow_url,
            import_photos=True,
        )
        return int(prop.id), int(imported)


def refresh_listing_details_job(property_id: int) -> None:
    with get_session() as session:
        PropertyService(session).refresh_listing_details(property_id)


def ensure_gemini_insights_job(property_id: int, *, force: bool = False) -> dict[str, str]:
    with get_session() as session:
        return PropertyService(session).ensure_gemini_insights(
            property_id, force=force
        )


def ensure_coordinates_job(
    property_id: int, *, force: bool = False
) -> tuple[float | None, float | None]:
    with get_session() as session:
        prop = PropertyService(session).ensure_coordinates(property_id, force=force)
        lat = float(prop.latitude) if prop.latitude is not None else None
        lng = float(prop.longitude) if prop.longitude is not None else None
        return lat, lng


def refresh_stale_nearby_signals_job(*, limit: int = 3) -> int:
    with get_session() as session:
        return int(PropertyService(session).refresh_stale_nearby_signals(limit=limit))


def ensure_neighborhood_job(property_id: int, *, force: bool = False) -> dict[str, str]:
    with get_session() as session:
        prop = PropertyService(session).ensure_neighborhood(property_id, force=force)
        return {
            "neighborhood_name": (prop.neighborhood_name or "").strip(),
            "neighborhood_source": (prop.neighborhood_source or "").strip(),
            "neighborhood_override": (prop.neighborhood_override or "").strip(),
        }


def ensure_gemini_overview_job(property_id: int, *, force: bool = False) -> str:
    with get_session() as session:
        prop = PropertyService(session).ensure_gemini_overview(property_id, force=force)
        return (prop.neighborhood_gemini or "").strip()


def ensure_gemini_things_to_do_job(property_id: int, *, force: bool = False) -> str:
    with get_session() as session:
        prop = PropertyService(session).ensure_gemini_things_to_do(
            property_id, force=force
        )
        return (prop.neighborhood_things_to_do or "").strip()


def resolve_assigned_schools_job(
    lat: float | None, lng: float | None
) -> dict[str, Any]:
    """Resolve assigned schools + SchoolDigger enrichment (network I/O)."""
    result = resolve_assigned(lat, lng)
    if result.get("status") in ("ok", "gap") and has_schooldigger_keys():
        result = enrich_assigned(result)
    return result


def ensure_gemini_financial_job(
    property_id: int,
    financial_fields: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Persist form fields, run Gemini financial, return text + fingerprint inputs."""
    with get_session() as session:
        svc = PropertyService(session)
        svc.update_financial(property_id, **financial_fields)
        prop = svc.ensure_gemini_financial(property_id, force=force)
        peer_refs = svc._library_zillow_refs(property_id)
        return {
            "text": (prop.financial_gemini or "").strip(),
            "for": (prop.financial_gemini_for or "").strip(),
            "subject_zillow_url": (prop.zillow_url or "").strip(),
            "peer_refs": peer_refs,
        }
