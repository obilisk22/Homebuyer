from __future__ import annotations

from app.core.db import get_session
from app.core.property_service import PropertyService


DEMO_URL = (
    "https://www.zillow.com/homedetails/"
    "1600-Pennsylvania-Avenue-NW-Washington-DC-20500/2082063814_zpid/"
)
DEMO_ADDRESS = "1600 Pennsylvania Avenue NW, Washington, DC 20500"


def seed_demo_if_empty() -> None:
    with get_session() as session:
        service = PropertyService(session)
        if service.list_properties():
            return
        prop = service.add_from_zillow(DEMO_URL, DEMO_ADDRESS, import_photos=False)[0]
        service.update_property(
            prop.id,
            latitude=38.8977,
            longitude=-77.0365,
            list_price=1_200_000,
            beds=16,
            baths=35,
            city="Washington",
            state="DC",
            zip_code="20500",
        )
        service.update_financial(
            prop.id,
            list_price=1_200_000,
            offer_price=1_200_000,
            down_payment_pct=20,
            interest_rate_pct=6.5,
            loan_term_years=30,
            annual_property_tax=12_000,
            annual_insurance=2_400,
            monthly_hoa=0,
            closing_cost_pct=2.5,
        )
