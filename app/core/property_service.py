from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import UPLOADS_DIR
from app.core.finance import blend_appreciation_rates
from app.core.fhfa_hpi import zip5_cagr
from app.core.gemini_financial import (
    ZillowListingRef,
    build_financial_fingerprint,
    generate_financial_commentary,
)
from app.core.gemini_neighborhood import (
    generate_neighborhood_overview,
    generate_things_to_do,
)
from app.core.geocode import geocode_address, reverse_geocode_neighborhood
from app.core.home_insurance import resolve_annual_insurance
from app.core.models import FinancialAssumptions, Photo, Property
from app.core.mortgage_rates import resolve_interest_rate, should_autofill_interest_rate
from app.core.nearby_signals import is_stale, refresh_property_signals
from app.core.neighborhood import effective_neighborhood_name
from app.core.property_tax import resolve_annual_property_tax
from app.core.thumbnail import PhotoCandidate, pick_thumbnail_photo_id
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
        sort: str = "newest",
    ) -> list[Property]:
        stmt = select(Property).options(joinedload(Property.photos)).order_by(Property.created_at.desc())
        props = list(self.session.scalars(stmt).unique())
        if search or min_price is not None or max_price is not None or min_beds is not None:
            props = [
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
        if sort == "price_asc":
            props.sort(key=lambda p: (p.list_price is None, p.list_price or 0.0))
        elif sort == "price_desc":
            props.sort(key=lambda p: (p.list_price is None, -(p.list_price or 0.0)))
        else:
            props.sort(
                key=lambda p: p.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
        return props

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
        """Refresh and persist nearby signals without surfacing provider failures."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        try:
            refresh_property_signals(prop)
            self.session.commit()
            self.session.refresh(prop)
        except Exception:  # noqa: BLE001 - nearby providers never block property flows
            self.session.rollback()
        return prop

    def refresh_stale_nearby_signals(self, *, limit: int = 3) -> int:
        """Refresh up to ``limit`` stale properties that have map coordinates."""
        if limit <= 0:
            return 0
        stmt = (
            select(Property)
            .where(
                Property.latitude.is_not(None),
                Property.longitude.is_not(None),
            )
            .order_by(Property.updated_at.desc())
        )
        refreshed = 0
        for prop in self.session.scalars(stmt):
            if not is_stale(prop.nearby_signals_at):
                continue
            self.refresh_nearby_signals(prop.id)
            refreshed += 1
            if refreshed >= limit:
                break
        return refreshed

    def _apply_listing_details(
        self, prop: Property, details: ListingDetails, *, sync_financial: bool = True
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
        if details.city:
            prop.city = details.city
        if details.state:
            prop.state = details.state
        if details.zip_code:
            prop.zip_code = details.zip_code
        if details.address:
            prop.address = details.address
        if details.neighborhood and not (prop.neighborhood_override or "").strip():
            # Cache Zillow neighborhood when we already have the listing HTML.
            if not (prop.neighborhood_name or "").strip():
                prop.neighborhood_name = details.neighborhood.strip()
                prop.neighborhood_source = "zillow"
        if sync_financial:
            self._sync_financial_from_listing(prop, details)

    def _sync_financial_from_listing(self, prop: Property, details: ListingDetails) -> None:
        """Overwrite listing-derived Financials fields; preserve Manual loan inputs."""
        if prop.financial is None:
            prop.financial = FinancialAssumptions()
        fin = prop.financial

        if details.list_price is not None and details.list_price > 0:
            fin.list_price = float(details.list_price)
            fin.purchase_price = float(details.list_price)
        elif details.list_price is not None:
            fin.list_price = 0.0
            fin.purchase_price = 0.0

        if details.hoa_fee is not None:
            fin.monthly_hoa = float(details.hoa_fee)

        price_for_tax = None
        if fin.list_price and fin.list_price > 0:
            price_for_tax = float(fin.list_price)
        elif details.list_price and details.list_price > 0:
            price_for_tax = float(details.list_price)
        elif prop.list_price and prop.list_price > 0:
            price_for_tax = float(prop.list_price)

        tax_amt, tax_src = resolve_annual_property_tax(
            annual_tax=details.annual_tax,
            tax_assessed_value=details.tax_assessed_value,
            property_tax_rate=details.property_tax_rate,
            list_price=price_for_tax,
            lat=prop.latitude,
            lng=prop.longitude,
        )
        if tax_amt is not None and tax_amt > 0:
            fin.annual_property_tax = float(tax_amt)
            fin.property_tax_source = tax_src
        else:
            fin.annual_property_tax = 0.0
            fin.property_tax_source = ""

        state = (details.state or prop.state or "").strip()
        ins_amt, ins_src = resolve_annual_insurance(
            annual_insurance=details.annual_insurance,
            list_price=price_for_tax,
            state=state,
        )
        if ins_amt is not None and ins_amt > 0:
            fin.annual_insurance = float(ins_amt)
            fin.insurance_source = ins_src
        else:
            fin.annual_insurance = 0.0
            fin.insurance_source = ""

        if details.rent_zestimate is not None and details.rent_zestimate > 0:
            if (fin.rent_source or "").strip() in ("", "Zillow"):
                fin.monthly_rent = float(details.rent_zestimate)
                fin.rent_source = "Zillow"
        self.resolve_rent_growth(fin, prop)

        fhfa = None
        try:
            zip_code = (prop.zip_code or details.zip_code or "").strip()
            if zip_code:
                fhfa = zip5_cagr(zip_code)
        except Exception:
            fhfa = None
        if fhfa is not None:
            fin.appreciation_fhfa_pct = float(fhfa)

        if details.appreciation_decade_pct is not None:
            fin.appreciation_zillow_pct = float(details.appreciation_decade_pct)

        if (fin.appreciation_source or "").strip() != "Manual":
            blended, source = blend_appreciation_rates(
                fin.appreciation_fhfa_pct, fin.appreciation_zillow_pct
            )
            fin.appreciation_pct = float(blended)
            fin.appreciation_source = source

        self._apply_mortgage_rate_autofill(fin)

    def _apply_mortgage_rate_autofill(self, fin: FinancialAssumptions) -> None:
        """Fill interest rate from Freddie Mac PMMS for the current loan term."""
        if not should_autofill_interest_rate(fin.interest_rate_source):
            return
        term = int(fin.loan_term_years or 30)
        rate, src = resolve_interest_rate(term)
        if rate is None or rate <= 0:
            return
        fin.interest_rate_pct = float(rate)
        fin.interest_rate_source = src

    def resolve_rent_growth(self, fin: FinancialAssumptions, prop: Property) -> None:
        """Resolve rent growth from control status, ACS county data, or a default."""
        if fin.rent_control:
            fin.rent_growth_pct = 2.0
            fin.rent_growth_source = "Rent control 2%"
            return
        if (fin.rent_growth_source or "").strip() == "Manual":
            return

        cagr = None
        try:
            if prop.latitude is not None and prop.longitude is not None:
                from app.core.census_acs import county_median_rent_cagr

                cagr = county_median_rent_cagr(float(prop.latitude), float(prop.longitude))
        except Exception:  # noqa: BLE001 - data resolution must not block listing sync
            cagr = None

        if cagr is not None:
            fin.rent_growth_pct = float(cagr)
            fin.rent_growth_source = "ACS county ~5y CAGR"
        else:
            fin.rent_growth_pct = 3.0
            fin.rent_growth_source = "Default"

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
        """Re-fetch list price / beds / baths / sqft / HOA / year / type from Zillow."""
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        had_coords = prop.latitude is not None and prop.longitude is not None
        details: ListingDetails | None = None
        try:
            details = fetch_listing_details(prop.zillow_url)
            self._apply_listing_details(prop, details)
        except Exception:
            # Leave existing values; still try address parse fallback.
            pass
        self._fill_location_from_address(prop)
        if prop.latitude is None or prop.longitude is None:
            try:
                self.ensure_coordinates(property_id)
                prop = self.get_property(property_id) or prop
            except Exception:
                pass
        if details is not None:
            now_has_coords = prop.latitude is not None and prop.longitude is not None
            if now_has_coords and not had_coords:
                self._sync_financial_from_listing(prop, details)
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

        html: str | None = None
        details_for_sync: ListingDetails | None = None
        try:
            html = fetch_listing_html(prop.zillow_url)
            details_for_sync = extract_listing_details(html)
            self._apply_listing_details(
                prop, details_for_sync, sync_financial=False
            )
            self._fill_location_from_address(prop)
            self.session.commit()
            self.session.refresh(prop)
        except Exception:
            # Keep the home even if listing scrape fails; user can refresh/edit later.
            html = None
            details_for_sync = None

        try:
            lat, lng = geocode_address(prop.address)
            prop.latitude = lat
            prop.longitude = lng
            self.session.commit()
            self.session.refresh(prop)
        except ValueError:
            # Keep the home even if geocoding fails; Map tab can retry later.
            pass
        if details_for_sync is not None:
            self._sync_financial_from_listing(prop, details_for_sync)
            self.session.commit()
            self.session.refresh(prop)

        imported = 0
        if import_photos:
            try:
                imported = self.import_zillow_photos(prop.id, html=html)
            except Exception:
                # Keep the home even if Zillow photo fetch fails; user can re-import later.
                imported = 0
        try:
            prop = self.refresh_nearby_signals(prop.id)
        except Exception:
            # Nearby providers must never prevent saving a home.
            pass
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
        try:
            prop = self.refresh_nearby_signals(prop.id)
        except Exception:
            # Nearby providers must never prevent saving coordinates.
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

        cache_key = f"{name}|{(prop.city or '').strip()}|{(prop.state or '').strip()}"
        if (
            not force
            and (prop.neighborhood_gemini or "").strip()
            and (prop.neighborhood_gemini_for or "").strip() == cache_key
        ):
            return prop

        text = generate_neighborhood_overview(
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

        # Separate cache from overview; suffix keeps keys distinct if compared side-by-side.
        cache_key = (
            f"things_v2|{name}|{(prop.city or '').strip()}|{(prop.state or '').strip()}"
        )
        if (
            not force
            and (prop.neighborhood_things_to_do or "").strip()
            and (prop.neighborhood_things_to_do_for or "").strip() == cache_key
        ):
            return prop

        text = generate_things_to_do(
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
        if created or should_autofill_interest_rate(prop.financial.interest_rate_source):
            before = float(prop.financial.interest_rate_pct or 0)
            before_src = (prop.financial.interest_rate_source or "").strip()
            self._apply_mortgage_rate_autofill(prop.financial)
            after = float(prop.financial.interest_rate_pct or 0)
            after_src = (prop.financial.interest_rate_source or "").strip()
            if after != before or after_src != before_src:
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

    def ensure_gemini_insights(
        self, property_id: int, *, force: bool = False
    ) -> dict[str, str]:
        """Run neighborhood + financial Gemini jobs; return status per section.

        Continues after individual failures so one missing piece (e.g. no price)
        does not block the others. Keys: overview, things_to_do, financial.
        Values are ``ok``, ``cached``, or an error message.
        """
        results: dict[str, str] = {}

        try:
            self.ensure_neighborhood(property_id)
        except Exception as exc:  # noqa: BLE001
            results["overview"] = f"Neighborhood name: {exc}"
            results["things_to_do"] = f"Neighborhood name: {exc}"
        else:
            prop = self.get_property(property_id)
            name = self.display_neighborhood(prop) if prop else ""
            if not name:
                msg = "Set a neighborhood name first"
                results["overview"] = msg
                results["things_to_do"] = msg
            else:
                try:
                    before = (prop.neighborhood_gemini_for or "").strip() if prop else ""
                    self.ensure_gemini_overview(property_id, force=force)
                    after_prop = self.get_property(property_id)
                    after = (
                        (after_prop.neighborhood_gemini_for or "").strip()
                        if after_prop
                        else ""
                    )
                    results["overview"] = (
                        "cached"
                        if not force and before and before == after
                        else "ok"
                    )
                except Exception as exc:  # noqa: BLE001
                    results["overview"] = str(exc)
                try:
                    prop2 = self.get_property(property_id)
                    before_t = (
                        (prop2.neighborhood_things_to_do_for or "").strip()
                        if prop2
                        else ""
                    )
                    self.ensure_gemini_things_to_do(property_id, force=force)
                    after_prop2 = self.get_property(property_id)
                    after_t = (
                        (after_prop2.neighborhood_things_to_do_for or "").strip()
                        if after_prop2
                        else ""
                    )
                    results["things_to_do"] = (
                        "cached"
                        if not force and before_t and before_t == after_t
                        else "ok"
                    )
                except Exception as exc:  # noqa: BLE001
                    results["things_to_do"] = str(exc)

        try:
            prop_f = self.get_property(property_id)
            before_f = (prop_f.financial_gemini_for or "").strip() if prop_f else ""
            self.ensure_gemini_financial(property_id, force=force)
            after_f_prop = self.get_property(property_id)
            after_f = (
                (after_f_prop.financial_gemini_for or "").strip() if after_f_prop else ""
            )
            results["financial"] = (
                "cached" if not force and before_f and before_f == after_f else "ok"
            )
        except Exception as exc:  # noqa: BLE001
            results["financial"] = str(exc)

        return results

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
        for key, value in fields.items():
            if hasattr(fin, key):
                setattr(fin, key, value)
        if "annual_property_tax" in fields and float(fields["annual_property_tax"]) != prev_tax:
            fin.property_tax_source = ""
        if "annual_insurance" in fields and float(fields["annual_insurance"]) != prev_ins:
            fin.insurance_source = ""
        if "monthly_rent" in fields and float(fields["monthly_rent"]) != prev_rent:
            fin.rent_source = "Manual"
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

    def import_zillow_photos(
        self,
        property_id: int,
        *,
        replace: bool = False,
        html: str | None = None,
    ) -> int:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")

        if replace:
            locked_id = prop.thumbnail_photo_id if prop.thumbnail_locked else None
            for photo in list(prop.photos):
                self.delete_photo(photo.id)
            prop = self.get_property(property_id)
            assert prop is not None
            if locked_id is not None and not any(p.id == locked_id for p in prop.photos):
                prop.thumbnail_locked = False
                prop.thumbnail_photo_id = None
                self.session.commit()

        existing_urls = {p.source_url for p in prop.photos if p.source_url}

        fetched = fetch_listing_photo_urls(prop.zillow_url, html=html)
        imported = 0
        sort_order = len(prop.photos)
        dest_dir = UPLOADS_DIR / str(property_id)
        for index, url in enumerate(fetched.urls):
            if url in existing_urls:
                continue
            try:
                data, content_type = download_image(url)
            except ValueError:
                continue
            ext = extension_for(content_type, url)
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
            self.session.add(
                Photo(
                    property_id=property_id,
                    path=str(dest.relative_to(UPLOADS_DIR)).replace("\\", "/"),
                    source_url=url or "",
                    caption=f"Zillow photo {index + 1}",
                    sort_order=sort_order,
                )
            )
            sort_order += 1
            imported += 1
            existing_urls.add(url)
        if imported:
            self.session.commit()
        self.select_thumbnail(property_id)
        return imported

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
