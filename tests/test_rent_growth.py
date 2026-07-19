from unittest.mock import patch

from app.core import db
from app.core.census_acs import county_median_rent_cagr
from app.core.finance import rent_cagr_pct
from app.core.models import FinancialAssumptions, Property
from app.core.property_service import PropertyService


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DB_PATH", str(tmp_path / "rent_growth.db"))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    return db.get_session()


def test_county_median_rent_cagr_from_mocked_acs() -> None:
    end_payload = [
        ["NAME", "B25064_001E", "state", "county"],
        ["X County", "2000", "06", "037"],
    ]
    start_payload = [
        ["NAME", "B25064_001E", "state", "county"],
        ["X County", "1000", "06", "037"],
    ]

    def fake_get(url: str, params: object = None, timeout: object = None) -> object:
        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> list[list[str]]:
                if "/2018/" in url:
                    return start_payload
                return end_payload

        return Response()

    with (
        patch("app.core.census_acs.has_census_key", return_value=True),
        patch("app.core.census_acs._fcc_fips", return_value=("06", "037")),
        patch("app.core.census_acs.read_json", return_value=None),
        patch("app.core.census_acs.write_json"),
        patch("app.core.census_acs.requests.get", side_effect=fake_get),
    ):
        rate = county_median_rent_cagr(34.0, -118.0)

    expected = rent_cagr_pct(1000.0, 2000.0, years=5)
    assert rate is not None and expected is not None
    assert abs(rate - expected) < 0.01


def test_county_median_rent_cagr_no_key() -> None:
    with patch("app.core.census_acs.has_census_key", return_value=False):
        assert county_median_rent_cagr(34.0, -118.0) is None


def test_ensure_rent_growth_control_forces_two_percent(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St", zillow_url="https://www.zillow.com/homedetails/x_1_zpid/")
    prop.financial = FinancialAssumptions(rent_control=True, rent_growth_pct=4.25)
    session.add(prop)
    session.commit()

    fin = PropertyService(session).ensure_rent_growth(prop.id)

    assert fin.rent_control is True
    assert fin.rent_growth_pct == 2.0
    assert fin.rent_growth_source == "Rent control 2%"


def test_ensure_rent_growth_uses_acs_when_uncontrolled(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St",
        zillow_url="https://www.zillow.com/homedetails/x_2_zpid/",
        latitude=34.0,
        longitude=-118.0,
    )
    prop.financial = FinancialAssumptions()
    session.add(prop)
    session.commit()
    monkeypatch.setattr(
        "app.core.census_acs.county_median_rent_cagr", lambda lat, lng: 4.25
    )

    fin = PropertyService(session).ensure_rent_growth(prop.id)

    assert fin.rent_control is False
    assert fin.rent_growth_pct == 4.25
    assert fin.rent_growth_source == "ACS county ~5y CAGR"


def test_update_financial_marks_changed_rent_growth_manual(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    prop = Property(address="1 Test St", zillow_url="https://www.zillow.com/homedetails/x_3_zpid/")
    prop.financial = FinancialAssumptions(rent_growth_pct=3.0, rent_growth_source="Default")
    session.add(prop)
    session.commit()

    fin = PropertyService(session).update_financial(prop.id, rent_growth_pct=4.0)

    assert fin.rent_control is False
    assert fin.rent_growth_source == "Manual"


def test_update_financial_unchecking_control_resolves_growth(tmp_path, monkeypatch) -> None:
    session = _session(tmp_path, monkeypatch)
    prop = Property(
        address="1 Test St",
        zillow_url="https://www.zillow.com/homedetails/x_4_zpid/",
        latitude=34.0,
        longitude=-118.0,
    )
    prop.financial = FinancialAssumptions(
        rent_control=True, rent_growth_pct=2.0, rent_growth_source="Rent control 2%"
    )
    session.add(prop)
    session.commit()
    monkeypatch.setattr(
        "app.core.census_acs.county_median_rent_cagr", lambda lat, lng: 4.25
    )

    fin = PropertyService(session).update_financial(prop.id, rent_control=False)

    assert fin.rent_control is False
    assert fin.rent_growth_pct == 4.25
    assert fin.rent_growth_source == "ACS county ~5y CAGR"
