from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import UPLOADS_DIR
from app.core.geocode import geocode_address
from app.core.models import FinancialAssumptions, Photo, Property
from app.core.thumbnail import PhotoCandidate, pick_thumbnail_photo_id
from app.core.zillow_listing import (
    ListingDetails,
    fetch_listing_details,
    parse_address_parts,
)
from app.core.zillow_photos import download_image, extension_for, fetch_listing_photo_urls


def resolve_library_thumbnail(prop: Property) -> Photo | None:
    """Photo to show on library cards: persisted choice, else first by sort_order."""
    if not prop.photos:
        return None
    if prop.thumbnail_photo_id is not None:
        for photo in prop.photos:
            if photo.id == prop.thumbnail_photo_id:
                return photo
    return prop.photos[0]


def parse_zillow_url(url: str) -> dict[str, str | None]:
    """Extract whatever we can from a Zillow listing URL without scraping.

    Typical pattern:
      https://www.zillow.com/homedetails/123-Main-St-Seattle-WA-98101/12345678_zpid/
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Zillow URL is required.")

    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host_core = host[4:]
    else:
        host_core = host

    if "zillow.com" not in host_core:
        raise ValueError("URL must be a zillow.com link.")

    address_guess: str | None = None
    zpid: str | None = None

    path = unquote(parsed.path or "")
    # /homedetails/<slug>/<zpid>_zpid/
    m = re.search(r"/homedetails/([^/]+)/(\d+)_zpid", path, re.I)
    if m:
        slug, zpid = m.group(1), m.group(2)
        address_guess = slug.replace("-", " ").strip() or None

    if not zpid:
        m2 = re.search(r"/(\d+)_zpid", path, re.I)
        if m2:
            zpid = m2.group(1)

    return {"url": url, "address_guess": address_guess, "zpid": zpid}


def property_matches_filters(
    prop: Property,
    *,
    search: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    min_beds: float | None = None,
) -> bool:
    """Pure filter helper for library search (also unit-tested)."""
    needle = (search or "").strip().lower()
    if needle:
        hay = " ".join(
            [
                prop.address or "",
                prop.city or "",
                prop.state or "",
                prop.zip_code or "",
            ]
        ).lower()
        if needle not in hay:
            return False

    if min_price is not None:
        if prop.list_price is None or prop.list_price < min_price:
            return False
    if max_price is not None:
        if prop.list_price is None or prop.list_price > max_price:
            return False
    if min_beds is not None:
        if prop.beds is None or prop.beds < min_beds:
            return False
    return True


_UNSET = object()


def _optional_float(value: float | None | str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return float(value)


class PropertyService:
    def __init__(self, session: Session):
        self.session = session

    def list_properties(
        self,
        *,
        search: str = "",
        min_price: float | None = None,
        max_price: float | None = None,
        min_beds: float | None = None,
    ) -> list[Property]:
        stmt = select(Property).options(joinedload(Property.photos)).order_by(Property.created_at.desc())
        props = list(self.session.scalars(stmt).unique())
        if not (search or min_price is not None or max_price is not None or min_beds is not None):
            return props
        return [
            p
            for p in props
            if property_matches_filters(
                p,
                search=search,
                min_price=min_price,
                max_price=max_price,
                min_beds=min_beds,
            )
        ]

    def get_property(self, property_id: int) -> Property | None:
        stmt = (
            select(Property)
            .where(Property.id == property_id)
            .options(
                joinedload(Property.photos),
                joinedload(Property.financial),
            )
        )
        return self.session.scalars(stmt).unique().first()

    def _apply_listing_details(self, prop: Property, details: ListingDetails) -> None:
        if details.list_price is not None:
            prop.list_price = details.list_price
        if details.beds is not None:
            prop.beds = details.beds
        if details.baths is not None:
            prop.baths = details.baths
        if details.city:
            prop.city = details.city
        if details.state:
            prop.state = details.state
        if details.zip_code:
            prop.zip_code = details.zip_code
        if details.address:
            prop.address = details.address

    def _fill_location_from_address(self, prop: Property) -> None:
        if prop.city and prop.state:
            return
        city, state, zip_code = parse_address_parts(prop.address)
        if city and not prop.city:
            prop.city = city
        if state and not prop.state:
            prop.state = state
        if zip_code and not prop.zip_code:
            prop.zip_code = zip_code

    def refresh_listing_details(self, property_id: int) -> Property:
        """Re-fetch list price / beds / baths / city from the Zillow page."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        try:
            details = fetch_listing_details(prop.zillow_url)
            self._apply_listing_details(prop, details)
        except Exception:
            # Leave existing values; still try address parse fallback.
            pass
        self._fill_location_from_address(prop)
        self.session.commit()
        self.session.refresh(prop)
        return prop

    def add_from_zillow(
        self,
        zillow_url: str,
        address: str = "",
        *,
        import_photos: bool = True,
    ) -> tuple[Property, int]:
        parsed = parse_zillow_url(zillow_url)
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
        self.session.add(prop)
        self.session.commit()
        self.session.refresh(prop)

        try:
            details = fetch_listing_details(prop.zillow_url)
            self._apply_listing_details(prop, details)
            self._fill_location_from_address(prop)
            self.session.commit()
            self.session.refresh(prop)
        except Exception:
            # Keep the home even if listing scrape fails; user can refresh/edit later.
            pass

        try:
            lat, lng = geocode_address(prop.address)
            prop.latitude = lat
            prop.longitude = lng
            self.session.commit()
            self.session.refresh(prop)
        except ValueError:
            # Keep the home even if geocoding fails; Map tab can retry later.
            pass

        imported = 0
        if import_photos:
            try:
                imported = self.import_zillow_photos(prop.id)
            except Exception:
                # Keep the home even if Zillow photo fetch fails; user can re-import later.
                imported = 0
        return prop, imported

    def ensure_coordinates(self, property_id: int, *, force: bool = False) -> Property:
        """Geocode and persist lat/lng when missing (or always when ``force``)."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        if not force and prop.latitude is not None and prop.longitude is not None:
            return prop

        lat, lng = geocode_address(prop.address)
        prop.latitude = lat
        prop.longitude = lng
        self.session.commit()
        self.session.refresh(prop)
        return prop

    def update_property(
        self,
        property_id: int,
        *,
        address: str | None = None,
        zillow_url: str | None = None,
        notes: str | None = None,
        list_price: float | None | str | object = _UNSET,
        beds: float | None | str | object = _UNSET,
        baths: float | None | str | object = _UNSET,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        clear_coords: bool = False,
    ) -> Property:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        if address is not None:
            prop.address = address.strip()
            self._fill_location_from_address(prop)
        if zillow_url is not None:
            parsed = parse_zillow_url(zillow_url)
            prop.zillow_url = str(parsed["url"])
        if notes is not None:
            prop.notes = notes
        if list_price is not _UNSET:
            prop.list_price = _optional_float(list_price)  # type: ignore[arg-type]
        if beds is not _UNSET:
            prop.beds = _optional_float(beds)  # type: ignore[arg-type]
        if baths is not _UNSET:
            prop.baths = _optional_float(baths)  # type: ignore[arg-type]
        if city is not None:
            prop.city = city.strip()
        if state is not None:
            prop.state = state.strip().upper()
        if zip_code is not None:
            prop.zip_code = zip_code.strip()
        if clear_coords:
            prop.latitude = None
            prop.longitude = None
        else:
            if latitude is not None:
                prop.latitude = latitude
            if longitude is not None:
                prop.longitude = longitude

        self.session.commit()
        self.session.refresh(prop)
        return prop

    def delete_property(self, property_id: int) -> None:
        prop = self.get_property(property_id)
        if prop is None:
            return
        prop_dir = UPLOADS_DIR / str(property_id)
        if prop_dir.exists():
            shutil.rmtree(prop_dir, ignore_errors=True)
        self.session.delete(prop)
        self.session.commit()

    def ensure_financial(self, prop: Property) -> FinancialAssumptions:
        if prop.financial is None:
            prop.financial = FinancialAssumptions()
            self.session.commit()
            self.session.refresh(prop)
        assert prop.financial is not None
        return prop.financial

    def update_financial(self, property_id: int, **fields: float | int) -> FinancialAssumptions:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        fin = self.ensure_financial(prop)
        for key, value in fields.items():
            if hasattr(fin, key):
                setattr(fin, key, value)
        self.session.commit()
        self.session.refresh(fin)
        return fin

    def add_photo(
        self,
        property_id: int,
        source_path: Path,
        caption: str = "",
        *,
        source_url: str = "",
    ) -> Photo:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        dest_dir = UPLOADS_DIR / str(property_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source_path.name
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            i = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{i}{suffix}"
                i += 1
        shutil.copy2(source_path, dest)

        photo = Photo(
            property_id=property_id,
            path=str(dest.relative_to(UPLOADS_DIR)).replace("\\", "/"),
            source_url=source_url or "",
            caption=caption,
            sort_order=len(prop.photos),
        )
        self.session.add(photo)
        self.session.commit()
        self.session.refresh(photo)
        return photo

    def add_photo_bytes(
        self,
        property_id: int,
        data: bytes,
        filename: str,
        *,
        caption: str = "",
        source_url: str = "",
    ) -> Photo:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        dest_dir = UPLOADS_DIR / str(property_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            i = 1
            while dest.exists():
                dest = dest_dir / f"{stem}_{i}{suffix}"
                i += 1
        dest.write_bytes(data)

        photo = Photo(
            property_id=property_id,
            path=str(dest.relative_to(UPLOADS_DIR)).replace("\\", "/"),
            source_url=source_url or "",
            caption=caption,
            sort_order=len(prop.photos),
        )
        self.session.add(photo)
        self.session.commit()
        self.session.refresh(photo)
        return photo

    def import_zillow_photos(self, property_id: int, *, replace: bool = False) -> int:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        if replace:
            for photo in list(prop.photos):
                self.delete_photo(photo.id)
            prop = self.get_property(property_id)
            assert prop is not None

        existing_urls = {p.source_url for p in prop.photos if p.source_url}

        fetched = fetch_listing_photo_urls(prop.zillow_url)
        imported = 0
        for index, url in enumerate(fetched.urls):
            if url in existing_urls:
                continue
            try:
                data, content_type = download_image(url)
            except ValueError:
                continue
            ext = extension_for(content_type, url)
            filename = f"zillow_{index:03d}{ext}"
            self.add_photo_bytes(
                property_id,
                data,
                filename,
                caption=f"Zillow photo {index + 1}",
                source_url=url,
            )
            imported += 1
            existing_urls.add(url)
        self.select_thumbnail(property_id)
        return imported

    def select_thumbnail(self, property_id: int) -> Photo | None:
        """Choose and persist a front-of-house style thumbnail for library cards."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        if not prop.photos:
            prop.thumbnail_photo_id = None
            self.session.commit()
            return None

        candidates = [
            PhotoCandidate(
                photo_id=p.id,
                path=p.path,
                source_url=p.source_url or "",
                caption=p.caption or "",
                sort_order=p.sort_order,
            )
            for p in prop.photos
        ]
        chosen_id = pick_thumbnail_photo_id(candidates, uploads_root=UPLOADS_DIR)
        prop.thumbnail_photo_id = chosen_id
        self.session.commit()
        self.session.refresh(prop)
        if chosen_id is None:
            return None
        for photo in prop.photos:
            if photo.id == chosen_id:
                return photo
        return None

    def delete_photo(self, photo_id: int) -> None:
        photo = self.session.get(Photo, photo_id)
        if photo is None:
            return
        property_id = photo.property_id
        was_thumbnail = False
        prop = self.session.get(Property, property_id)
        if prop is not None and prop.thumbnail_photo_id == photo_id:
            was_thumbnail = True
            prop.thumbnail_photo_id = None
        full = UPLOADS_DIR / photo.path
        if full.exists():
            full.unlink(missing_ok=True)
        self.session.delete(photo)
        self.session.commit()
        if was_thumbnail:
            self.select_thumbnail(property_id)

    def photo_absolute_path(self, photo: Photo) -> Path:
        return UPLOADS_DIR / photo.path
