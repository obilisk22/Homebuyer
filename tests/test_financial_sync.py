from app.core import db
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService
from app.core.zillow_listing import ListingDetails


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "fin_sync.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    return db.get_session()


def test_sync_overwrites_listing_fields_preserves_loan_terms(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_1_zpid/")
    fin = FinancialAssumptions(
        list_price=500_000,
        offer_price=480_000,
        purchase_price=500_000,
        down_payment_pct=15.0,
        interest_rate_pct=5.5,
        interest_rate_source="Manual",
        loan_term_years=15,
        closing_cost_pct=2.0,
        annual_property_tax=1.0,
        annual_insurance=1.0,
        monthly_hoa=99.0,
    )
    prop.financial = fin
    prop.latitude = 47.6
    prop.longitude = -122.3
    prop.state = "WA"
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (9_000.0, "Zillow"),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (3_000.0, "Zillow"),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_interest_rate",
        lambda term, **kwargs: (9.9, "Freddie Mac PMMS should not apply"),
    )

    details = ListingDetails(
        list_price=1_250_000,
        hoa_fee=250.0,
        annual_tax=9_000.0,
        annual_insurance=3_000.0,
        state="WA",
    )
    svc = PropertyService(session)
    svc._sync_financial_from_listing(prop, details)
    session.commit()
    session.refresh(fin)

    assert fin.list_price == 1_250_000
    assert fin.purchase_price == 1_250_000
    assert fin.monthly_hoa == 250.0
    assert fin.annual_property_tax == 9_000.0
    assert fin.annual_insurance == 3_000.0
    assert fin.offer_price == 480_000
    assert fin.down_payment_pct == 15.0
    assert fin.interest_rate_pct == 5.5
    assert fin.interest_rate_source == "Manual"
    assert fin.loan_term_years == 15
    assert fin.closing_cost_pct == 2.0


def test_sync_autofills_pmms_interest_rate_for_term(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_rate_zpid/",
        state="WA",
    )
    fin = FinancialAssumptions(list_price=400_000, loan_term_years=15)
    prop.financial = fin
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_interest_rate",
        lambda term, **kwargs: (5.93, f"Freddie Mac PMMS 15-yr FRM · test"),
    )

    PropertyService(session)._sync_financial_from_listing(
        prop, ListingDetails(list_price=400_000, state="WA")
    )
    session.commit()
    session.refresh(fin)

    assert fin.interest_rate_pct == 5.93
    assert fin.interest_rate_source.startswith("Freddie Mac")
    assert fin.loan_term_years == 15


def test_sync_keeps_hoa_when_listing_omits_hoa(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_2_zpid/")
    fin = FinancialAssumptions(monthly_hoa=175.0, list_price=100.0)
    prop.financial = fin
    prop.state = "WA"
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )

    details = ListingDetails(list_price=200_000, hoa_fee=None, state="WA")
    PropertyService(session)._sync_financial_from_listing(prop, details)
    session.commit()
    session.refresh(fin)
    assert fin.monthly_hoa == 175.0
    assert fin.list_price == 200_000
    assert fin.annual_property_tax == 0.0
    assert fin.annual_insurance == 0.0


def test_sync_uses_listing_rent_and_blended_appreciation(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_6_zpid/",
        zip_code="98101",
        state="WA",
        latitude=47.6,
        longitude=-122.3,
    )
    prop.financial = FinancialAssumptions()
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.zip5_cagr", lambda zip_code: 4.0, raising=False
    )
    monkeypatch.setattr(
        "app.core.census_acs.county_median_rent_cagr", lambda lat, lng: 4.25
    )

    PropertyService(session)._sync_financial_from_listing(
        prop,
        ListingDetails(
            list_price=500_000,
            rent_zestimate=2_500,
            appreciation_decade_pct=6.0,
        ),
    )
    session.commit()
    session.refresh(prop.financial)

    assert prop.financial.monthly_rent == 2_500
    assert prop.financial.rent_source == "Zillow"
    assert prop.financial.rent_growth_pct == 4.25
    assert prop.financial.rent_growth_source == "ACS county ~5y CAGR"
    assert prop.financial.appreciation_fhfa_pct == 4.0
    assert prop.financial.appreciation_zillow_pct == 6.0
    assert prop.financial.appreciation_pct == 5.0
    assert prop.financial.appreciation_source == "FHFA+Zillow"


def test_sync_defaults_monthly_rent_when_no_rent_zestimate(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_8_zpid/",
        zip_code="98101",
        state="WA",
        latitude=47.6,
        longitude=-122.3,
    )
    prop.financial = FinancialAssumptions()
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.zip5_cagr", lambda zip_code: None, raising=False
    )
    monkeypatch.setattr(
        "app.core.census_acs.county_median_rent_cagr", lambda lat, lng: None
    )

    PropertyService(session)._sync_financial_from_listing(
        prop,
        ListingDetails(list_price=500_000, rent_zestimate=None),
    )
    session.commit()
    session.refresh(prop.financial)

    assert prop.financial.monthly_rent == 5_300
    assert prop.financial.rent_source == "Default"


def test_sync_preserves_manual_rent_when_no_rent_zestimate(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_9_zpid/",
        zip_code="98101",
        state="WA",
    )
    prop.financial = FinancialAssumptions(
        monthly_rent=4_100.0,
        rent_source="Manual",
    )
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.zip5_cagr", lambda zip_code: None, raising=False
    )

    PropertyService(session)._sync_financial_from_listing(
        prop,
        ListingDetails(list_price=500_000, rent_zestimate=None),
    )
    session.commit()
    session.refresh(prop.financial)

    assert prop.financial.monthly_rent == 4_100.0
    assert prop.financial.rent_source == "Manual"


def test_sync_preserves_manual_rent_when_zillow_has_rent(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_10_zpid/",
        zip_code="98101",
        state="WA",
    )
    prop.financial = FinancialAssumptions(
        monthly_rent=4_100.0,
        rent_source="Manual",
    )
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.zip5_cagr", lambda zip_code: None, raising=False
    )

    PropertyService(session)._sync_financial_from_listing(
        prop,
        ListingDetails(list_price=500_000, rent_zestimate=2_500),
    )
    session.commit()
    session.refresh(prop.financial)

    assert prop.financial.monthly_rent == 4_100.0
    assert prop.financial.rent_source == "Manual"


def test_update_financial_clears_source_captions_on_manual_save(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_3_zpid/")
    fin = FinancialAssumptions(
        list_price=500_000,
        annual_property_tax=9_000.0,
        annual_insurance=3_000.0,
        property_tax_source="Zillow",
        insurance_source="Zillow",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    svc = PropertyService(session)
    updated = svc.update_financial(
        prop.id,
        annual_property_tax=12_000.0,
        annual_insurance=4_500.0,
    )

    assert updated.annual_property_tax == 12_000.0
    assert updated.annual_insurance == 4_500.0
    assert updated.property_tax_source == ""
    assert updated.insurance_source == ""


def test_update_financial_marks_changed_rent_and_appreciation_manual(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_7_zpid/")
    prop.financial = FinancialAssumptions(
        monthly_rent=2_500.0,
        rent_source="Zillow",
        appreciation_pct=5.0,
        appreciation_source="FHFA+Zillow",
    )
    session.add(prop)
    session.commit()

    updated = PropertyService(session).update_financial(
        prop.id, monthly_rent=2_700.0, appreciation_pct=4.5
    )

    assert updated.rent_source == "Manual"
    assert updated.appreciation_source == "Manual"


def test_update_financial_preserves_sources_when_loan_fields_only(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_4_zpid/")
    fin = FinancialAssumptions(
        list_price=500_000,
        annual_property_tax=9_000.0,
        annual_insurance=3_000.0,
        interest_rate_pct=6.5,
        property_tax_source="Zillow",
        insurance_source="Zillow",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    svc = PropertyService(session)
    updated = svc.update_financial(
        prop.id,
        interest_rate_pct=5.25,
        annual_property_tax=9_000.0,
        annual_insurance=3_000.0,
    )

    assert updated.interest_rate_pct == 5.25
    assert updated.property_tax_source == "Zillow"
    assert updated.insurance_source == "Zillow"


def test_update_financial_preserves_sources_when_only_loan_fields_passed(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St, Seattle, WA 98101", zillow_url="https://www.zillow.com/homedetails/x_5_zpid/")
    fin = FinancialAssumptions(
        list_price=500_000,
        annual_property_tax=9_000.0,
        annual_insurance=3_000.0,
        interest_rate_pct=6.5,
        property_tax_source="Estimated: ACS county",
        insurance_source="Estimated: CA avg premium",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    svc = PropertyService(session)
    updated = svc.update_financial(prop.id, interest_rate_pct=5.25, loan_term_years=15)

    assert updated.interest_rate_pct == 5.25
    assert updated.loan_term_years == 15
    assert updated.property_tax_source == "Estimated: ACS county"
    assert updated.insurance_source == "Estimated: CA avg premium"


def test_apply_listing_details_can_skip_financial_sync(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St", zillow_url="https://www.zillow.com/homedetails/x_zpid/")
    session.add(prop)
    session.commit()
    svc = PropertyService(session)
    sync_calls = []
    monkeypatch.setattr(
        svc, "_sync_financial_from_listing", lambda prop, details: sync_calls.append(details)
    )

    svc._apply_listing_details(
        prop, ListingDetails(list_price=500_000), sync_financial=False
    )

    assert prop.list_price == 500_000
    assert sync_calls == []


def test_refresh_listing_with_existing_coordinates_syncs_once(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Seattle, WA 98101",
        zillow_url="https://www.zillow.com/homedetails/x_zpid/",
        latitude=47.6,
        longitude=-122.3,
    )
    session.add(prop)
    session.commit()
    svc = PropertyService(session)
    details = ListingDetails(list_price=500_000)
    sync_calls = []
    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_details", lambda url: details
    )
    monkeypatch.setattr(
        svc, "_sync_financial_from_listing", lambda prop, details: sync_calls.append(details)
    )

    svc.refresh_listing_details(prop.id)

    assert sync_calls == [details]


def test_add_from_zillow_syncs_once_after_geocoding(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    svc = PropertyService(session)
    details = ListingDetails(list_price=500_000)
    sync_coordinates = []
    monkeypatch.setattr(
        "app.core.property_service.fetch_listing_html", lambda url: "<html></html>"
    )
    monkeypatch.setattr(
        "app.core.property_service.extract_listing_details", lambda html: details
    )
    monkeypatch.setattr(
        "app.core.property_service.geocode_address", lambda address: (47.6, -122.3)
    )
    monkeypatch.setattr(
        svc,
        "_sync_financial_from_listing",
        lambda prop, details: sync_coordinates.append((prop.latitude, prop.longitude)),
    )

    svc.add_from_zillow(
        "https://www.zillow.com/homedetails/1-Test-St-Seattle-WA-98101/1_zpid/",
        import_photos=False,
    )

    assert sync_coordinates == [(47.6, -122.3)]


def test_sync_autofills_maintenance_blend(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Los Angeles, CA 90001",
        zillow_url="https://www.zillow.com/homedetails/x_maint_zpid/",
        state="CA",
        sqft=1800,
        year_built=2000,
    )
    fin = FinancialAssumptions(list_price=0, monthly_maintenance=0)
    prop.financial = fin
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_interest_rate",
        lambda term, **kwargs: (None, ""),
    )

    details = ListingDetails(
        list_price=800_000,
        sqft=1800,
        year_built=2000,
        state="CA",
    )
    svc = PropertyService(session)
    svc._sync_financial_from_listing(prop, details)
    session.commit()
    session.refresh(fin)

    assert fin.monthly_maintenance > 0
    assert "age blend" in (fin.maintenance_source or "").lower()
    assert "CA" in (fin.maintenance_source or "")


def test_sync_preserves_manual_maintenance(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Los Angeles, CA 90001",
        zillow_url="https://www.zillow.com/homedetails/x_maint_manual_zpid/",
        state="CA",
        sqft=1800,
        year_built=2000,
    )
    fin = FinancialAssumptions(
        list_price=500_000,
        monthly_maintenance=50.0,
        maintenance_source="Manual",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_property_tax",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_annual_insurance",
        lambda **kwargs: (None, ""),
    )
    monkeypatch.setattr(
        "app.core.property_service.resolve_interest_rate",
        lambda term, **kwargs: (None, ""),
    )

    details = ListingDetails(list_price=900_000, sqft=1800, year_built=2000, state="CA")
    svc = PropertyService(session)
    svc._sync_financial_from_listing(prop, details)
    session.commit()
    session.refresh(fin)

    assert fin.monthly_maintenance == 50.0
    assert fin.maintenance_source == "Manual"


def test_update_financial_marks_maintenance_manual(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St",
        zillow_url="https://www.zillow.com/homedetails/x_maint_edit_zpid/",
    )
    fin = FinancialAssumptions(
        monthly_maintenance=100.0,
        maintenance_source="Estimated: age blend · CA×1.15",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    svc = PropertyService(session)
    updated = svc.update_financial(prop.id, monthly_maintenance=250.0)
    assert updated.monthly_maintenance == 250.0
    assert updated.maintenance_source == "Manual"


def test_ensure_financial_backfills_maintenance(tmp_path, monkeypatch):
    """Homes saved before maintenance autofill should fill on ensure_financial."""
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Los Angeles, CA 90001",
        zillow_url="https://www.zillow.com/homedetails/x_maint_ensure_zpid/",
        state="CA",
        sqft=1800,
        year_built=2000,
        list_price=800_000,
    )
    fin = FinancialAssumptions(
        list_price=800_000,
        monthly_maintenance=0.0,
        maintenance_source="",
        interest_rate_source="Manual",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    monkeypatch.setattr(
        "app.core.property_service.resolve_interest_rate",
        lambda term, **kwargs: (None, ""),
    )

    svc = PropertyService(session)
    out = svc.ensure_financial(prop)
    assert out.monthly_maintenance > 0
    assert "age blend" in (out.maintenance_source or "").lower()


def test_ensure_financial_preserves_manual_maintenance(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St, Los Angeles, CA 90001",
        zillow_url="https://www.zillow.com/homedetails/x_maint_ensure_manual_zpid/",
        state="CA",
        sqft=1800,
        year_built=2000,
        list_price=800_000,
    )
    fin = FinancialAssumptions(
        list_price=800_000,
        monthly_maintenance=42.0,
        maintenance_source="Manual",
        interest_rate_source="Manual",
    )
    prop.financial = fin
    session.add(prop)
    session.commit()

    svc = PropertyService(session)
    out = svc.ensure_financial(prop)
    assert out.monthly_maintenance == 42.0
    assert out.maintenance_source == "Manual"
