from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

from app.core.db import UPLOADS_DIR
from app.core.fcc_broadband import compute_broadband
from app.core.geocode import geocode_address
from app.core.market_activity import compute_market_activity
from app.core.models import FinancialAssumptions, Photo, Property
from app.core.nearby_signals import SIGNAL_ORDER, compute_signals
from app.core.permits_nearby import compute_permit_activity
from app.core.zillow_listing import (
    ListingDetails,
    extract_listing_details,
    fetch_listing_details,
    parse_address_parts,
)
from app.core.zillow_photos import (
    download_image,
    extension_for,
    fetch_listing_html,
    fetch_listing_photo_urls,
)

_ADD_HOME_POOL_WORKERS = 4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_message(exc: BaseException) -> str:
    return str(exc).strip() or exc.__class__.__name__


def download_zillow_photo_files(
    property_id: int,
    zillow_url: str,
    *,
    html: str | None = None,
    existing_urls: set[str] | frozenset[str] | None = None,
    start_sort_order: int = 0,
    photo_fetcher: Callable[..., Any] = fetch_listing_photo_urls,
    image_downloader: Callable[[str], tuple[bytes, str]] = download_image,
    extension_resolver: Callable[[str, str], str] = extension_for,
) -> list[dict[str, Any]]:
    """Download listing photos to disk; return plain dicts for ORM insert (no DB)."""
    skip = set(existing_urls or ())
    fetched = photo_fetcher(zillow_url, html=html)
    rows: list[dict[str, Any]] = []
    sort_order = start_sort_order
    dest_dir = UPLOADS_DIR / str(property_id)
    for index, photo_url in enumerate(fetched.urls):
        if photo_url in skip:
            continue
        try:
            data, content_type = image_downloader(photo_url)
        except ValueError:
            continue
        ext = extension_resolver(content_type, photo_url)
        filename = f"zillow_{index:03d}{ext}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            i = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{i}{suffix}"
                i += 1
        dest.write_bytes(data)
        rows.append(
            {
                "path": str(dest.relative_to(UPLOADS_DIR)).replace("\\", "/"),
                "source_url": photo_url or "",
                "caption": f"Zillow photo {index + 1}",
                "sort_order": sort_order,
            }
        )
        sort_order += 1
        skip.add(photo_url)
    return rows


def compute_nearby_signal_update(lat: float, lng: float) -> dict[str, str]:
    """Plain nearby_signals JSON + timestamp (no ORM)."""
    try:
        payload = compute_signals(float(lat), float(lng))
    except Exception as exc:  # noqa: BLE001
        payload = {
            key: {"hit": False, "error": _error_message(exc)} for key in SIGNAL_ORDER
        }
    return {
        "nearby_signals": json.dumps(payload),
        "nearby_signals_at": _utc_now_iso(),
    }


def compute_permits_signal_update(
    lat: float, lng: float, *, city: str = ""
) -> dict[str, str]:
    """Plain permits_activity JSON + timestamp (no ORM)."""
    try:
        payload = compute_permit_activity(float(lat), float(lng), city=city or "")
    except Exception as exc:  # noqa: BLE001
        payload = {
            "supported": True,
            "high_activity": False,
            "count": 0,
            "error": _error_message(exc),
        }
    return {
        "permits_activity": json.dumps(payload),
        "permits_activity_at": _utc_now_iso(),
    }


def compute_broadband_signal_update(lat: float, lng: float) -> dict[str, str]:
    """Plain broadband_status JSON + timestamp (no ORM)."""
    try:
        payload = compute_broadband(float(lat), float(lng))
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "error",
            "has_fixed": None,
            "reason": "compute_failed",
            "error": _error_message(exc),
        }
    return {
        "broadband_status": json.dumps(payload),
        "broadband_at": _utc_now_iso(),
    }


def compute_market_signal_update(zip_code: str) -> dict[str, str]:
    """Plain market_activity JSON + timestamp (no ORM). May use warm Redfin cache."""
    try:
        payload = compute_market_activity(zip_code or "")
    except Exception as exc:  # noqa: BLE001
        payload = {"zip_code": (zip_code or "").strip(), "active": False, "error": _error_message(exc)}
    return {
        "market_activity": json.dumps(payload),
        "market_activity_at": _utc_now_iso(),
    }


def _apply_signal_update(prop: Property, update: dict[str, str] | None) -> None:
    if not update:
        return
    for key, value in update.items():
        setattr(prop, key, value)


def _persist_downloaded_photos(
    session: Session,
    property_id: int,
    rows: list[dict[str, Any]],
) -> int:
    for row in rows:
        session.add(
            Photo(
                property_id=property_id,
                path=str(row["path"]),
                source_url=str(row.get("source_url") or ""),
                caption=str(row.get("caption") or ""),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
    if rows:
        session.commit()
    return len(rows)


def parse_zillow_url(url: str) -> dict[str, str | None]:
    """Extract whatever is available from a Zillow listing URL without scraping."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Zillow URL is required.")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    host_core = host[4:] if host.startswith("www.") else host
    if "zillow.com" not in host_core:
        raise ValueError("URL must be a zillow.com link.")

    address_guess: str | None = None
    zpid: str | None = None
    path = unquote(parsed.path or "")
    match = re.search(r"/homedetails/([^/]+)/(\d+)_zpid", path, re.I)
    if match:
        slug, zpid = match.group(1), match.group(2)
        address_guess = slug.replace("-", " ").strip() or None
    if not zpid:
        zpid_match = re.search(r"/(\d+)_zpid", path, re.I)
        if zpid_match:
            zpid = zpid_match.group(1)
    return {"url": url, "address_guess": address_guess, "zpid": zpid}


def apply_listing_details(
    prop: Property,
    details: ListingDetails,
    *,
    sync_financial: bool = True,
    sync_financial_fn: Callable[[Property, ListingDetails], None] | None = None,
) -> None:
    if details.list_price is not None:
        prop.list_price = details.list_price
    if details.beds is not None:
        prop.beds = details.beds
    if details.baths is not None:
        prop.baths = details.baths
    if details.sqft is not None:
        prop.sqft = details.sqft
    if details.hoa_fee is not None:
        prop.hoa_fee = details.hoa_fee
    if details.year_built is not None:
        prop.year_built = details.year_built
    if details.home_type:
        prop.home_type = details.home_type
    if details.cooling:
        prop.cooling = details.cooling
        prop.has_central_ac = details.has_central_ac
    elif details.has_central_ac is not None:
        prop.has_central_ac = details.has_central_ac

    position = (getattr(details, "townhome_position", "") or "").strip().lower()
    home_type = (details.home_type or prop.home_type or "").strip()
    if position in {"center", "end"} and home_type.casefold() == "townhouse":
        prop.townhome_position = position
    elif home_type and home_type.casefold() != "townhouse":
        prop.townhome_position = ""
    elif position == "" and details.home_type and home_type.casefold() == "townhouse":
        prop.townhome_position = ""

    if details.city:
        prop.city = details.city
    if details.state:
        prop.state = details.state
    if details.zip_code:
        prop.zip_code = details.zip_code
    if details.address:
        prop.address = details.address
    if details.neighborhood and not (prop.neighborhood_override or "").strip():
        if not (prop.neighborhood_name or "").strip():
            prop.neighborhood_name = details.neighborhood.strip()
            prop.neighborhood_source = "zillow"
    if sync_financial and sync_financial_fn is not None:
        sync_financial_fn(prop, details)


def fill_location_from_address(
    prop: Property,
    *,
    address_parser: Callable[[str], tuple[str, str, str]] = parse_address_parts,
) -> None:
    if prop.city and prop.state:
        return
    city, state, zip_code = address_parser(prop.address)
    if city and not prop.city:
        prop.city = city
    if state and not prop.state:
        prop.state = state
    if zip_code and not prop.zip_code:
        prop.zip_code = zip_code


def refresh_listing_details(
    session: Session,
    property_id: int,
    *,
    service: Any | None = None,
    details_fetcher: Callable[[str], ListingDetails] = fetch_listing_details,
) -> Property:
    if service is None:
        from app.core.property_service import PropertyService

        service = PropertyService(session)
    prop = service.get_property(property_id)
    if prop is None:
        raise ValueError("Property not found.")
    had_coords = prop.latitude is not None and prop.longitude is not None
    details: ListingDetails | None = None
    try:
        details = details_fetcher(prop.zillow_url)
        service._apply_listing_details(prop, details)
    except Exception:
        pass
    service._fill_location_from_address(prop)
    if prop.latitude is None or prop.longitude is None:
        try:
            service.ensure_coordinates(property_id)
            prop = service.get_property(property_id) or prop
        except Exception:
            pass
    if details is not None:
        now_has_coords = prop.latitude is not None and prop.longitude is not None
        if now_has_coords and not had_coords:
            service._sync_financial_from_listing(prop, details)
    session.commit()
    session.refresh(prop)
    try:
        prop = service.refresh_market_activity(prop.id)
    except Exception:
        pass
    return prop


def add_from_zillow(
    session: Session,
    url: str,
    address: str = "",
    *,
    import_photos: bool,
    service: Any | None = None,
    url_parser: Callable[[str], dict[str, str | None]] = parse_zillow_url,
    html_fetcher: Callable[[str], str] = fetch_listing_html,
    details_extractor: Callable[[str], ListingDetails] = extract_listing_details,
    geocoder: Callable[[str], tuple[float, float]] = geocode_address,
    photo_fetcher: Callable[..., Any] = fetch_listing_photo_urls,
    image_downloader: Callable[[str], tuple[bytes, str]] = download_image,
    extension_resolver: Callable[[str, str], str] = extension_for,
) -> tuple[Property, int]:
    if service is None:
        from app.core.property_service import PropertyService

        service = PropertyService(session)
    parsed = url_parser(url)
    addr = (address or "").strip() or (parsed.get("address_guess") or "")
    if not addr:
        raise ValueError(
            "Could not read an address from that link. "
            "Paste a full Zillow home details URL (…/homedetails/…)."
        )

    city, state, zip_code = parse_address_parts(addr)
    prop = Property(
        address=addr,
        zillow_url=str(parsed["url"]),
        city=city,
        state=state,
        zip_code=zip_code,
    )
    prop.financial = FinancialAssumptions()
    session.add(prop)
    session.commit()
    session.refresh(prop)

    html: str | None = None
    details_for_sync: ListingDetails | None = None
    try:
        html = html_fetcher(prop.zillow_url)
        details_for_sync = details_extractor(html)
        service._apply_listing_details(prop, details_for_sync, sync_financial=False)
        service._fill_location_from_address(prop)
        session.commit()
        session.refresh(prop)
    except Exception:
        html = None
        details_for_sync = None

    try:
        lat, lng = geocoder(prop.address)
        prop.latitude = lat
        prop.longitude = lng
        session.commit()
        session.refresh(prop)
    except ValueError:
        pass
    if details_for_sync is not None:
        service._sync_financial_from_listing(prop, details_for_sync)
        session.commit()
        session.refresh(prop)

    # Snapshot plain values for worker threads (no ORM / session across threads).
    property_id = prop.id
    zillow_url = prop.zillow_url
    pin_lat = prop.latitude
    pin_lng = prop.longitude
    pin_city = prop.city or ""
    pin_zip = (prop.zip_code or "").strip()
    existing_urls = {p.source_url for p in prop.photos if p.source_url}
    start_sort = len(prop.photos)

    photo_rows: list[dict[str, Any]] = []
    signal_updates: list[dict[str, str]] = []

    def _photos_job() -> list[dict[str, Any]]:
        return download_zillow_photo_files(
            property_id,
            zillow_url,
            html=html,
            existing_urls=existing_urls,
            start_sort_order=start_sort,
            photo_fetcher=photo_fetcher,
            image_downloader=image_downloader,
            extension_resolver=extension_resolver,
        )

    with ThreadPoolExecutor(max_workers=_ADD_HOME_POOL_WORKERS) as pool:
        futures = {}
        if import_photos:
            futures[pool.submit(_photos_job)] = "photos"
        if pin_lat is not None and pin_lng is not None:
            futures[
                pool.submit(compute_nearby_signal_update, float(pin_lat), float(pin_lng))
            ] = "nearby"
            futures[
                pool.submit(
                    compute_permits_signal_update,
                    float(pin_lat),
                    float(pin_lng),
                    city=pin_city,
                )
            ] = "permits"
            futures[
                pool.submit(
                    compute_broadband_signal_update, float(pin_lat), float(pin_lng)
                )
            ] = "broadband"
        if pin_zip:
            futures[pool.submit(compute_market_signal_update, pin_zip)] = "market"

        for fut in as_completed(futures):
            kind = futures[fut]
            try:
                result = fut.result()
            except Exception:  # noqa: BLE001 - photos/signals never fail add-home
                continue
            if kind == "photos" and isinstance(result, list):
                photo_rows = result
            elif isinstance(result, dict):
                signal_updates.append(result)

    imported = 0
    try:
        imported = _persist_downloaded_photos(session, property_id, photo_rows)
        if import_photos:
            service.select_thumbnail(property_id)
    except Exception:
        imported = 0

    try:
        prop = service.get_property(property_id) or prop
        for update in signal_updates:
            _apply_signal_update(prop, update)
        if signal_updates:
            session.commit()
            session.refresh(prop)
    except Exception:
        session.rollback()
        prop = service.get_property(property_id) or prop

    return prop, imported


def import_zillow_photos(
    session: Session,
    property_id: int,
    *,
    replace: bool = False,
    html: str | None = None,
    service: Any | None = None,
    photo_fetcher: Callable[..., Any] = fetch_listing_photo_urls,
    image_downloader: Callable[[str], tuple[bytes, str]] = download_image,
    extension_resolver: Callable[[str, str], str] = extension_for,
) -> int:
    if service is None:
        from app.core.property_service import PropertyService

        service = PropertyService(session)
    prop = service.get_property(property_id)
    if prop is None:
        raise ValueError("Property not found.")

    if replace:
        locked_id = prop.thumbnail_photo_id if prop.thumbnail_locked else None
        for photo in list(prop.photos):
            service.delete_photo(photo.id)
        prop = service.get_property(property_id)
        assert prop is not None
        if locked_id is not None and not any(p.id == locked_id for p in prop.photos):
            prop.thumbnail_locked = False
            prop.thumbnail_photo_id = None
            session.commit()

    existing_urls = {p.source_url for p in prop.photos if p.source_url}
    rows = download_zillow_photo_files(
        property_id,
        prop.zillow_url,
        html=html,
        existing_urls=existing_urls,
        start_sort_order=len(prop.photos),
        photo_fetcher=photo_fetcher,
        image_downloader=image_downloader,
        extension_resolver=extension_resolver,
    )
    imported = _persist_downloaded_photos(session, property_id, rows)
    service.select_thumbnail(property_id)
    return imported
