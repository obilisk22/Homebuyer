from __future__ import annotations

import shutil

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import ColumnElement

from app.core import area_signals, financial_sync, listing_ingest
from app.core.db import UPLOADS_DIR
from app.core.finance import blend_appreciation_rates
from app.core.fhfa_hpi import zip5_cagr
from app.core.gemini_financial import (
    ZillowListingRef,
    build_financial_fingerprint,
    generate_financial_commentary,
)
from app.core.gemini_neighborhood import (
    build_overview_cache_key,
    build_things_to_do_cache_key,
    generate_neighborhood_overview,
    generate_things_to_do,
)
from app.core.geocode import geocode_address, reverse_geocode_neighborhood
from app.core.home_insurance import resolve_annual_insurance
from app.core.home_maintenance import resolve_monthly_maintenance
from app.core.models import DEFAULT_MONTHLY_RENT, FinancialAssumptions, Photo, Property
from app.core.mortgage_rates import resolve_interest_rate, should_autofill_interest_rate
from app.core.fcc_broadband import (
    needs_refresh as broadband_needs_refresh,
    refresh_property_broadband,
)
from app.core.gemini_photos import (
    build_photos_fingerprint,
    generate_photos_commentary,
)
from app.core.market_activity import (
    needs_refresh as market_needs_refresh,
    refresh_property_market_activity,
)
from app.core.nearby_signals import needs_refresh, refresh_property_signals
from app.core.permits_nearby import (
    needs_refresh as permits_needs_refresh,
    refresh_property_permits,
)
from app.core.neighborhood import effective_neighborhood_name
from app.core.property_tax import resolve_annual_property_tax
from app.core.thumbnail import PhotoCandidate, pick_thumbnail_photo_id
from app.core.utilities import resolve_monthly_utilities
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


def resolve_library_thumbnail(prop: Property) -> Photo | None:
    """Photo to show on library cards: persisted choice, else first by sort_order."""
    if not prop.photos:
        return None
    if prop.thumbnail_photo_id is not None:
        for photo in prop.photos:
            if photo.id == prop.thumbnail_photo_id:
                return photo
    return prop.photos[0]


def fetch_library_thumbnails(
    session: Session,
    properties: list[Property],
) -> dict[int, Photo]:
    """Batch-load one thumbnail Photo per property without hydrating photos collections.

    Honors ``thumbnail_photo_id`` when present; otherwise the lowest ``sort_order``
    (then id) photo. Properties with no photos are omitted from the result.
    """
    if not properties:
        return {}

    result: dict[int, Photo] = {}
    by_thumb_id = {
        p.thumbnail_photo_id: p.id
        for p in properties
        if p.thumbnail_photo_id is not None
    }
    if by_thumb_id:
        for photo in session.scalars(
            select(Photo).where(Photo.id.in_(by_thumb_id.keys()))
        ):
            prop_id = by_thumb_id.get(photo.id)
            if prop_id is not None and photo.property_id == prop_id:
                result[prop_id] = photo

    missing_ids = [p.id for p in properties if p.id not in result]
    if missing_ids:
        for photo in session.scalars(
            select(Photo)
            .where(Photo.property_id.in_(missing_ids))
            .order_by(Photo.property_id, Photo.sort_order, Photo.id)
        ):
            if photo.property_id not in result:
                result[photo.property_id] = photo
    return result


def parse_zillow_url(url: str) -> dict[str, str | None]:
    return listing_ingest.parse_zillow_url(url)


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


def _library_filter_clauses(
    *,
    search: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    min_beds: float | None = None,
) -> list[ColumnElement[bool]]:
    """SQL equivalents of the cheap library filters (beds / price / like search)."""
    clauses: list[ColumnElement[bool]] = []
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle}%"
        clauses.append(
            or_(
                Property.address.ilike(pattern),
                Property.city.ilike(pattern),
                Property.state.ilike(pattern),
                Property.zip_code.ilike(pattern),
            )
        )
    if min_price is not None:
        clauses.append(Property.list_price >= min_price)
    if max_price is not None:
        clauses.append(Property.list_price <= max_price)
    if min_beds is not None:
        clauses.append(Property.beds >= min_beds)
    return clauses


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
        sort: str = "newest",
    ) -> list[Property]:
        stmt = select(Property).options(joinedload(Property.financial))
        for clause in _library_filter_clauses(
            search=search,
            min_price=min_price,
            max_price=max_price,
            min_beds=min_beds,
        ):
            stmt = stmt.where(clause)
        if sort == "price_asc":
            stmt = stmt.order_by(
                Property.list_price.asc().nulls_last(),
                Property.created_at.desc(),
            )
        elif sort == "price_desc":
            stmt = stmt.order_by(
                Property.list_price.desc().nulls_last(),
                Property.created_at.desc(),
            )
        else:
            stmt = stmt.order_by(Property.created_at.desc())
        return list(self.session.scalars(stmt).unique())

    def has_any_properties(self) -> bool:
        return self.session.scalar(select(Property.id).limit(1)) is not None

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

    def refresh_nearby_signals(self, property_id: int) -> Property:
        return area_signals.refresh_nearby_signals(
            self.session,
            property_id,
            lookup=self.get_property,
            refresher=refresh_property_signals,
        )

    def refresh_permits_activity(self, property_id: int) -> Property:
        return area_signals.refresh_permits_activity(
            self.session,
            property_id,
            lookup=self.get_property,
            refresher=refresh_property_permits,
        )

    def refresh_broadband_status(self, property_id: int) -> Property:
        return area_signals.refresh_broadband_status(
            self.session,
            property_id,
            lookup=self.get_property,
            refresher=refresh_property_broadband,
        )

    def refresh_market_activity(self, property_id: int) -> Property:
        return area_signals.refresh_market_activity(
            self.session,
            property_id,
            lookup=self.get_property,
            refresher=refresh_property_market_activity,
        )

    def refresh_stale_nearby_signals(self, *, limit: int = 3) -> int:
        return area_signals.refresh_stale_nearby_signals(
            self.session,
            limit=limit,
            refresh=self.refresh_nearby_signals,
            needs_refresh_fn=needs_refresh,
        )

    def refresh_stale_permits_activity(self, *, limit: int = 3) -> int:
        return area_signals.refresh_stale_permits_activity(
            self.session,
            limit=limit,
            refresh=self.refresh_permits_activity,
            needs_refresh_fn=permits_needs_refresh,
        )

    def refresh_stale_broadband_status(self, *, limit: int = 3) -> int:
        return area_signals.refresh_stale_broadband_status(
            self.session,
            limit=limit,
            refresh=self.refresh_broadband_status,
            needs_refresh_fn=broadband_needs_refresh,
        )

    def refresh_stale_market_activity(self, *, limit: int = 3) -> int:
        return area_signals.refresh_stale_market_activity(
            self.session,
            limit=limit,
            refresh=self.refresh_market_activity,
            needs_refresh_fn=market_needs_refresh,
        )

    def _apply_listing_details(
        self, prop: Property, details: ListingDetails, *, sync_financial: bool = True
    ) -> None:
        listing_ingest.apply_listing_details(
            prop,
            details,
            sync_financial=sync_financial,
            sync_financial_fn=self._sync_financial_from_listing,
        )

    def _sync_financial_from_listing(self, prop: Property, details: ListingDetails) -> None:
        financial_sync.sync_financial_from_listing(
            self.session,
            prop,
            details,
            rent_growth_resolver=self.resolve_rent_growth,
            tax_resolver=resolve_annual_property_tax,
            insurance_resolver=resolve_annual_insurance,
            fhfa_resolver=zip5_cagr,
            appreciation_blender=blend_appreciation_rates,
            rate_resolver=resolve_interest_rate,
            maintenance_resolver=resolve_monthly_maintenance,
            utilities_resolver=resolve_monthly_utilities,
        )

    def _apply_maintenance_autofill(
        self, fin: FinancialAssumptions, prop: Property, details: ListingDetails
    ) -> None:
        financial_sync.apply_maintenance_autofill(
            fin,
            prop,
            details,
            maintenance_resolver=resolve_monthly_maintenance,
        )

    def _apply_utilities_autofill(
        self, fin: FinancialAssumptions, prop: Property, details: ListingDetails
    ) -> None:
        financial_sync.apply_utilities_autofill(
            fin,
            prop,
            details,
            utilities_resolver=resolve_monthly_utilities,
        )

    def _apply_mortgage_rate_autofill(self, fin: FinancialAssumptions) -> None:
        financial_sync.apply_mortgage_rate_autofill(
            fin, rate_resolver=resolve_interest_rate
        )

    def resolve_rent_growth(self, fin: FinancialAssumptions, prop: Property) -> None:
        financial_sync.resolve_rent_growth(fin, prop)

    def ensure_rent_growth(
        self, property_id: int, *, rent_control: bool | None = None
    ) -> FinancialAssumptions:
        """Resolve and persist rent-growth assumptions for a saved property."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        fin = self.ensure_financial(prop)
        if rent_control is not None:
            fin.rent_control = bool(rent_control)
        self.resolve_rent_growth(fin, prop)
        self.session.commit()
        self.session.refresh(fin)
        return fin

    def _fill_location_from_address(self, prop: Property) -> None:
        listing_ingest.fill_location_from_address(
            prop, address_parser=parse_address_parts
        )

    def refresh_listing_details(self, property_id: int) -> Property:
        return listing_ingest.refresh_listing_details(
            self.session,
            property_id,
            service=self,
            details_fetcher=fetch_listing_details,
        )

    def add_from_zillow(
        self,
        zillow_url: str,
        address: str = "",
        *,
        import_photos: bool = True,
    ) -> tuple[Property, int]:
        return listing_ingest.add_from_zillow(
            self.session,
            zillow_url,
            address,
            import_photos=import_photos,
            service=self,
            url_parser=parse_zillow_url,
            html_fetcher=fetch_listing_html,
            details_extractor=extract_listing_details,
            geocoder=geocode_address,
        )

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
        try:
            prop = self.refresh_nearby_signals(prop.id)
        except Exception:
            # Nearby providers must never prevent saving coordinates.
            pass
        try:
            prop = self.refresh_permits_activity(prop.id)
        except Exception:
            # Permit SODA lookups must never prevent saving coordinates.
            pass
        try:
            prop = self.refresh_broadband_status(prop.id)
        except Exception:
            # FCC BDC lookups must never prevent saving coordinates.
            pass
        try:
            prop = self.refresh_market_activity(prop.id)
        except Exception:
            # Redfin ZIP activity must never prevent saving coordinates.
            pass
        return prop

    def ensure_neighborhood(self, property_id: int, *, force: bool = False) -> Property:
        """Resolve and cache neighborhood name when missing (or always when ``force``).

        Prefers Zillow listing HTML (parentRegion / hood). Falls back to Nominatim /
        Google reverse only when Zillow has no neighborhood label.
        """
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        has_name = bool((prop.neighborhood_name or "").strip())
        from_zillow = (prop.neighborhood_source or "").strip().lower() == "zillow"
        if not force and has_name and from_zillow:
            return prop

        # 1) Zillow listing HTML — prefer over Nominatim junk labels.
        try:
            details = fetch_listing_details(prop.zillow_url)
            if details.neighborhood:
                prop.neighborhood_name = details.neighborhood.strip()
                prop.neighborhood_source = "zillow"
                self.session.commit()
                self.session.refresh(prop)
                return prop
        except Exception:
            pass

        if not force and has_name:
            # Keep existing non-Zillow name if Zillow had nothing.
            return prop

        # 2/3) Reverse geocode — need coordinates first.
        if prop.latitude is None or prop.longitude is None:
            try:
                prop = self.ensure_coordinates(property_id)
            except ValueError:
                self.session.commit()
                self.session.refresh(prop)
                return prop

        if prop.latitude is not None and prop.longitude is not None:
            try:
                name, source = reverse_geocode_neighborhood(
                    float(prop.latitude), float(prop.longitude)
                )
                prop.neighborhood_name = name
                prop.neighborhood_source = source
                self.session.commit()
                self.session.refresh(prop)
            except ValueError:
                self.session.commit()
                self.session.refresh(prop)

        return prop

    def display_neighborhood(self, prop: Property) -> str:
        return effective_neighborhood_name(
            neighborhood_name=prop.neighborhood_name or "",
            neighborhood_override=prop.neighborhood_override or "",
        )

    def ensure_gemini_overview(self, property_id: int, *, force: bool = False) -> Property:
        """Generate and cache a Gemini paragraph for the effective neighborhood."""
        prop = self.ensure_neighborhood(property_id)
        name = self.display_neighborhood(prop)
        if not name:
            raise ValueError(
                "No neighborhood name yet — refresh from Zillow or set an override."
            )

        address = (prop.address or "").strip()
        cache_key = build_overview_cache_key(
            address=address,
            neighborhood=name,
            city=prop.city or "",
            state=prop.state or "",
        )
        if (
            not force
            and (prop.neighborhood_gemini or "").strip()
            and (prop.neighborhood_gemini_for or "").strip() == cache_key
        ):
            return prop

        text = generate_neighborhood_overview(
            address=address,
            neighborhood=name,
            city=prop.city or "",
            state=prop.state or "",
        )
        prop.neighborhood_gemini = text
        prop.neighborhood_gemini_for = cache_key
        self.session.commit()
        self.session.refresh(prop)
        return prop

    def ensure_gemini_things_to_do(
        self, property_id: int, *, force: bool = False
    ) -> Property:
        """Generate and cache a Gemini things-to-do list for the effective neighborhood."""
        prop = self.ensure_neighborhood(property_id)
        name = self.display_neighborhood(prop)
        if not name:
            raise ValueError(
                "No neighborhood name yet — refresh from Zillow or set an override."
            )

        address = (prop.address or "").strip()
        # Separate cache from overview; prefix keeps keys distinct if compared side-by-side.
        cache_key = build_things_to_do_cache_key(
            address=address,
            neighborhood=name,
            city=prop.city or "",
            state=prop.state or "",
        )
        if (
            not force
            and (prop.neighborhood_things_to_do or "").strip()
            and (prop.neighborhood_things_to_do_for or "").strip() == cache_key
        ):
            return prop

        text = generate_things_to_do(
            address=address,
            neighborhood=name,
            city=prop.city or "",
            state=prop.state or "",
        )
        prop.neighborhood_things_to_do = text
        prop.neighborhood_things_to_do_for = cache_key
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
        sqft: float | None | str | object = _UNSET,
        hoa_fee: float | None | str | object = _UNSET,
        year_built: int | None | str | object = _UNSET,
        home_type: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        clear_coords: bool = False,
        neighborhood_override: str | None = None,
        neighborhood_notes: str | None = None,
        clear_neighborhood: bool = False,
        clear_gemini: bool = False,
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
        if sqft is not _UNSET:
            prop.sqft = _optional_float(sqft)  # type: ignore[arg-type]
        if hoa_fee is not _UNSET:
            prop.hoa_fee = _optional_float(hoa_fee)  # type: ignore[arg-type]
        if year_built is not _UNSET:
            raw_year = _optional_float(year_built)  # type: ignore[arg-type]
            prop.year_built = int(raw_year) if raw_year is not None else None
        if home_type is not None:
            prop.home_type = home_type.strip()
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
        if neighborhood_override is not None:
            prop.neighborhood_override = neighborhood_override.strip()
            # Override change invalidates cached Gemini text for the old name.
            prop.neighborhood_gemini = ""
            prop.neighborhood_gemini_for = ""
            prop.neighborhood_things_to_do = ""
            prop.neighborhood_things_to_do_for = ""
        if neighborhood_notes is not None:
            prop.neighborhood_notes = neighborhood_notes
        if clear_neighborhood:
            prop.neighborhood_name = ""
            prop.neighborhood_source = ""
            prop.neighborhood_gemini = ""
            prop.neighborhood_gemini_for = ""
            prop.neighborhood_things_to_do = ""
            prop.neighborhood_things_to_do_for = ""
        if clear_gemini:
            prop.neighborhood_gemini = ""
            prop.neighborhood_gemini_for = ""
            prop.neighborhood_things_to_do = ""
            prop.neighborhood_things_to_do_for = ""

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
        created = prop.financial is None
        if created:
            prop.financial = FinancialAssumptions()
            self.session.commit()
            self.session.refresh(prop)
        assert prop.financial is not None
        dirty = False
        if created or should_autofill_interest_rate(prop.financial.interest_rate_source):
            before = float(prop.financial.interest_rate_pct or 0)
            before_src = (prop.financial.interest_rate_source or "").strip()
            self._apply_mortgage_rate_autofill(prop.financial)
            after = float(prop.financial.interest_rate_pct or 0)
            after_src = (prop.financial.interest_rate_source or "").strip()
            if after != before or after_src != before_src:
                dirty = True

        # Backfill maintenance for homes synced before the feature (or never Manual).
        if (prop.financial.maintenance_source or "").strip() != "Manual":
            before_m = float(prop.financial.monthly_maintenance or 0)
            before_ms = (prop.financial.maintenance_source or "").strip()
            self._apply_maintenance_autofill(prop.financial, prop, ListingDetails())
            after_m = float(prop.financial.monthly_maintenance or 0)
            after_ms = (prop.financial.maintenance_source or "").strip()
            if after_m != before_m or after_ms != before_ms:
                dirty = True

        # Backfill utilities estimate (provider × sqft × age) unless Manual.
        if (prop.financial.utilities_source or "").strip() != "Manual":
            before_u = float(prop.financial.monthly_utilities or 0)
            before_us = (prop.financial.utilities_source or "").strip()
            self._apply_utilities_autofill(prop.financial, prop, ListingDetails())
            after_u = float(prop.financial.monthly_utilities or 0)
            after_us = (prop.financial.utilities_source or "").strip()
            if after_u != before_u or after_us != before_us:
                dirty = True

        if dirty:
            self.session.commit()
            self.session.refresh(prop.financial)
        return prop.financial

    def ensure_gemini_financial(
        self, property_id: int, *, force: bool = False
    ) -> Property:
        """Generate and cache Gemini financial opinion from Zillow URLs (URL context)."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        subject_url = (prop.zillow_url or "").strip()
        if not subject_url:
            raise ValueError("This home needs a Zillow URL before asking Gemini about finances.")

        peers = self._library_zillow_refs(property_id)
        cache_key = build_financial_fingerprint(
            subject_zillow_url=subject_url,
            peer_refs=peers,
        )
        if (
            not force
            and (prop.financial_gemini or "").strip()
            and (prop.financial_gemini_for or "").strip() == cache_key
        ):
            return prop

        text = generate_financial_commentary(
            subject_zillow_url=subject_url,
            subject_label=prop.address or "",
            peer_refs=peers,
        )
        prop.financial_gemini = text
        prop.financial_gemini_for = cache_key
        self.session.commit()
        self.session.refresh(prop)
        return prop

    def ensure_gemini_photos(self, property_id: int, *, force: bool = False) -> Property:
        """Generate and cache Photos-tab Gemini blurb from the subject Zillow URL."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        subject_url = (prop.zillow_url or "").strip()
        if not subject_url:
            raise ValueError("This home needs a Zillow URL before asking Gemini about photos.")

        cache_key = build_photos_fingerprint(
            subject_zillow_url=subject_url,
            address=prop.address or "",
        )
        if (
            not force
            and (prop.photos_gemini or "").strip()
            and (prop.photos_gemini_for or "").strip() == cache_key
        ):
            return prop

        text = generate_photos_commentary(
            subject_zillow_url=subject_url,
            subject_label=prop.address or "",
        )
        prop.photos_gemini = text
        prop.photos_gemini_for = cache_key
        self.session.commit()
        self.session.refresh(prop)
        return prop

    def _library_zillow_refs(self, exclude_property_id: int) -> list[ZillowListingRef]:
        """Other saved homes as Zillow URL peers for Gemini (max 19 peers → 20 URLs)."""
        rows = self.session.execute(
            select(Property.id, Property.zillow_url, Property.address)
            .where(Property.id != exclude_property_id)
            .order_by(Property.created_at.desc())
        ).all()
        refs: list[ZillowListingRef] = []
        for pid, zurl, address in rows:
            url = (zurl or "").strip()
            if not url:
                continue
            refs.append(
                ZillowListingRef(
                    property_id=int(pid),
                    zillow_url=url,
                    label=(address or "").strip(),
                )
            )
            if len(refs) >= 19:
                break
        return refs

    def update_financial(self, property_id: int, **fields: float | int) -> FinancialAssumptions:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        fin = self.ensure_financial(prop)
        prev_tax = float(fin.annual_property_tax or 0)
        prev_ins = float(fin.annual_insurance or 0)
        prev_rent = float(fin.monthly_rent or 0)
        prev_growth = float(fin.rent_growth_pct or 0)
        prev_rent_control = bool(fin.rent_control)
        prev_appr = float(fin.appreciation_pct or 0)
        prev_rate = float(fin.interest_rate_pct or 0)
        prev_term = int(fin.loan_term_years or 30)
        prev_rate_src = (fin.interest_rate_source or "").strip()
        prev_maint = float(fin.monthly_maintenance or 0)
        prev_utils = float(fin.monthly_utilities or 0)
        for key, value in fields.items():
            if hasattr(fin, key):
                setattr(fin, key, value)
        if "annual_property_tax" in fields and float(fields["annual_property_tax"]) != prev_tax:
            fin.property_tax_source = ""
        if "annual_insurance" in fields and float(fields["annual_insurance"]) != prev_ins:
            fin.insurance_source = ""
        if "monthly_rent" in fields and float(fields["monthly_rent"]) != prev_rent:
            fin.rent_source = "Manual"
        if (
            "monthly_maintenance" in fields
            and float(fields["monthly_maintenance"]) != prev_maint
        ):
            fin.maintenance_source = "Manual"
        if (
            "monthly_utilities" in fields
            and float(fields["monthly_utilities"]) != prev_utils
        ):
            fin.utilities_source = "Manual"
        if "rent_control" in fields and bool(fields["rent_control"]):
            fin.rent_control = True
            fin.rent_growth_pct = 2.0
            fin.rent_growth_source = "Rent control 2%"
        elif (
            "rent_growth_pct" in fields
            and float(fields["rent_growth_pct"]) != prev_growth
        ):
            fin.rent_growth_source = "Manual"
            fin.rent_control = False
        elif (
            "rent_control" in fields
            and prev_rent_control
            and not bool(fin.rent_control)
        ):
            self.resolve_rent_growth(fin, prop)
        if "appreciation_pct" in fields and float(fields["appreciation_pct"]) != prev_appr:
            fin.appreciation_source = "Manual"
        term_changed = (
            "loan_term_years" in fields and int(fields["loan_term_years"]) != prev_term
        )
        rate_changed = (
            "interest_rate_pct" in fields
            and float(fields["interest_rate_pct"]) != prev_rate
        )
        if rate_changed and term_changed and should_autofill_interest_rate(prev_rate_src):
            # UI may refresh rate when Term changes; keep PMMS if it still matches.
            expected, src = resolve_interest_rate(int(fin.loan_term_years or 30))
            if expected is not None and abs(float(fin.interest_rate_pct) - expected) < 0.001:
                fin.interest_rate_pct = float(expected)
                fin.interest_rate_source = src
            else:
                fin.interest_rate_source = "Manual"
        elif term_changed and should_autofill_interest_rate(prev_rate_src):
            fin.interest_rate_source = prev_rate_src
            self._apply_mortgage_rate_autofill(fin)
        elif rate_changed:
            fin.interest_rate_source = "Manual"
        self.session.commit()
        self.session.refresh(fin)
        return fin

    def revert_financial_field(self, property_id: int, field: str) -> FinancialAssumptions:
        """Restore one Financials field to product / autofill baseline; clear Manual."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        fin = self.ensure_financial(prop)
        details = ListingDetails()
        key = (field or "").strip()

        if key == "offer_price":
            fin.offer_price = 0.0
        elif key == "down_payment_pct":
            fin.down_payment_pct = 20.0
        elif key == "list_price":
            fin.list_price = float(prop.list_price or 0)
            if fin.list_price > 0:
                fin.purchase_price = float(fin.list_price)
        elif key == "interest_rate_pct":
            fin.interest_rate_source = ""
            self._apply_mortgage_rate_autofill(fin)
        elif key == "loan_term_years":
            fin.loan_term_years = 30
            if should_autofill_interest_rate(fin.interest_rate_source):
                self._apply_mortgage_rate_autofill(fin)
        elif key == "closing_cost_pct":
            fin.closing_cost_pct = 3.0
        elif key == "annual_property_tax":
            price = float(fin.list_price or prop.list_price or 0) or None
            tax_amt, tax_src = resolve_annual_property_tax(
                annual_tax=None,
                tax_assessed_value=None,
                property_tax_rate=None,
                list_price=price,
                lat=prop.latitude,
                lng=prop.longitude,
            )
            if tax_amt is not None and tax_amt > 0:
                fin.annual_property_tax = float(tax_amt)
                fin.property_tax_source = tax_src
            else:
                fin.annual_property_tax = 0.0
                fin.property_tax_source = ""
        elif key == "annual_insurance":
            price = float(fin.list_price or prop.list_price or 0) or None
            ins_amt, ins_src = resolve_annual_insurance(
                annual_insurance=None,
                list_price=price,
                state=(prop.state or "").strip(),
            )
            if ins_amt is not None and ins_amt > 0:
                fin.annual_insurance = float(ins_amt)
                fin.insurance_source = ins_src
            else:
                fin.annual_insurance = 0.0
                fin.insurance_source = ""
        elif key == "monthly_hoa":
            fin.monthly_hoa = float(prop.hoa_fee or 0)
        elif key == "monthly_maintenance":
            fin.maintenance_source = ""
            self._apply_maintenance_autofill(fin, prop, details)
        elif key == "monthly_utilities":
            fin.utilities_source = ""
            self._apply_utilities_autofill(fin, prop, details)
        elif key == "monthly_rent":
            fin.monthly_rent = float(DEFAULT_MONTHLY_RENT)
            fin.rent_source = "Default"
        elif key == "rent_control":
            fin.rent_control = False
            self.resolve_rent_growth(fin, prop)
        elif key == "appreciation_pct":
            blended, source = blend_appreciation_rates(
                fin.appreciation_fhfa_pct, fin.appreciation_zillow_pct
            )
            fin.appreciation_pct = float(blended)
            fin.appreciation_source = source
        elif key == "invest_return_pct":
            fin.invest_return_pct = 10.0
        elif key == "selling_cost_pct":
            fin.selling_cost_pct = 6.0
        elif key == "monthly_budget":
            fin.monthly_budget = 13_000.0
        elif key == "marginal_tax_pct":
            fin.marginal_tax_pct = 41.0
        elif key == "cg_tax_pct":
            fin.cg_tax_pct = 24.0
        elif key == "cg_exclusion":
            fin.cg_exclusion = 500_000.0
        elif key == "salt_cap":
            fin.salt_cap = 10_000.0
        else:
            raise ValueError(f"Unknown financial field: {field}")

        self.session.commit()
        self.session.refresh(fin)
        return fin

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

    def import_zillow_photos(
        self,
        property_id: int,
        *,
        replace: bool = False,
        html: str | None = None,
    ) -> int:
        return listing_ingest.import_zillow_photos(
            self.session,
            property_id,
            replace=replace,
            html=html,
            service=self,
            photo_fetcher=fetch_listing_photo_urls,
            image_downloader=download_image,
            extension_resolver=extension_for,
        )

    def select_thumbnail(self, property_id: int) -> Photo | None:
        """Choose and persist a front-of-house style thumbnail for library cards."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        if not prop.photos:
            prop.thumbnail_photo_id = None
            prop.thumbnail_locked = False
            self.session.commit()
            return None

        if prop.thumbnail_locked and prop.thumbnail_photo_id is not None:
            for photo in prop.photos:
                if photo.id == prop.thumbnail_photo_id:
                    return photo
            prop.thumbnail_locked = False

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
        prop.thumbnail_locked = False
        self.session.commit()
        self.session.refresh(prop)
        if chosen_id is None:
            return None
        for photo in prop.photos:
            if photo.id == chosen_id:
                return photo
        return None

    def set_library_thumbnail(self, property_id: int, photo_id: int) -> Photo:
        """Pin a photo as the library card thumbnail (manual lock)."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        photo = next((p for p in prop.photos if p.id == photo_id), None)
        if photo is None:
            raise ValueError("Photo not found for this property.")
        prop.thumbnail_photo_id = photo_id
        prop.thumbnail_locked = True
        self.session.commit()
        self.session.refresh(photo)
        return photo

    def unlock_and_select_thumbnail(self, property_id: int) -> Photo | None:
        """Clear manual thumb lock and re-run auto-pick."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        prop.thumbnail_locked = False
        self.session.commit()
        return self.select_thumbnail(property_id)

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
            prop.thumbnail_locked = False
        full = UPLOADS_DIR / photo.path
        if full.exists():
            full.unlink(missing_ok=True)
        self.session.delete(photo)
        self.session.commit()
        if was_thumbnail:
            self.select_thumbnail(property_id)
