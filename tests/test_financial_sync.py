from types import SimpleNamespace

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
    assert fin.loan_term_years == 15
    assert fin.closing_cost_pct == 2.0


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
