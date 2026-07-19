"""Library financial snapshots and CSV/JSON export (TODO-016)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from typing import Any

from app.core.finance import summarize
from app.core.models import FinancialAssumptions, Property


@dataclass(frozen=True)
class LibraryFinancialSnapshot:
    id: int
    address: str
    zillow_url: str
    city: str
    state: str
    zip_code: str
    beds: float | None
    baths: float | None
    sqft: float | None
    list_price: float | None
    offer_price: float | None
    effective_price: float | None
    price_per_sqft: float | None
    monthly_piti: float | None
    cash_to_close: float | None
    has_financials: bool
    down_payment_pct: float | None = None
    interest_rate_pct: float | None = None
    loan_term_years: int | None = None
    annual_property_tax: float | None = None
    annual_insurance: float | None = None
    monthly_hoa: float | None = None
    notes: str = ""


def _price_per_sqft(list_price: float | None, sqft: float | None) -> float | None:
    if list_price is None or sqft is None or sqft <= 0:
        return None
    return float(list_price) / float(sqft)


def _summarize_assumptions(
    prop: Property, fin: FinancialAssumptions
):
    list_price = float(fin.list_price or 0) or float(prop.list_price or 0)
    return summarize(
        list_price=list_price,
        offer_price=float(fin.offer_price or 0),
        down_payment_pct=float(fin.down_payment_pct or 0),
        interest_rate_pct=float(fin.interest_rate_pct or 0),
        loan_term_years=int(fin.loan_term_years or 30),
        annual_property_tax=float(fin.annual_property_tax or 0),
        annual_insurance=float(fin.annual_insurance or 0),
        monthly_hoa=float(fin.monthly_hoa or 0),
        closing_cost_pct=float(fin.closing_cost_pct or 0),
    )


def snapshot_from_property(prop: Property) -> LibraryFinancialSnapshot:
    """Derive display/export fields from a property + optional FinancialAssumptions."""
    list_price = prop.list_price
    offer_price: float | None = None
    effective: float | None = None
    monthly_piti: float | None = None
    cash_to_close: float | None = None
    has_financials = prop.financial is not None
    down_pct = rate = tax = ins = hoa = None
    term: int | None = None

    if has_financials:
        fin = prop.financial
        assert fin is not None
        summary = _summarize_assumptions(prop, fin)
        list_price = float(fin.list_price or 0) or prop.list_price
        offer_price = float(fin.offer_price or 0) or None
        effective = summary.effective_price
        monthly_piti = summary.monthly_total
        cash_to_close = summary.cash_to_close
        down_pct = float(fin.down_payment_pct or 0)
        rate = float(fin.interest_rate_pct or 0)
        term = int(fin.loan_term_years or 30)
        tax = float(fin.annual_property_tax or 0)
        ins = float(fin.annual_insurance or 0)
        hoa = float(fin.monthly_hoa or 0)

    return LibraryFinancialSnapshot(
        id=int(prop.id or 0),
        address=prop.address or "",
        zillow_url=prop.zillow_url or "",
        city=prop.city or "",
        state=prop.state or "",
        zip_code=prop.zip_code or "",
        beds=prop.beds,
        baths=prop.baths,
        sqft=prop.sqft,
        list_price=list_price,
        offer_price=offer_price,
        effective_price=effective,
        price_per_sqft=_price_per_sqft(list_price, prop.sqft),
        monthly_piti=monthly_piti,
        cash_to_close=cash_to_close,
        has_financials=has_financials,
        down_payment_pct=down_pct,
        interest_rate_pct=rate,
        loan_term_years=term,
        annual_property_tax=tax,
        annual_insurance=ins,
        monthly_hoa=hoa,
        notes=(prop.notes or "").strip(),
    )


_CSV_FIELDS = [
    "id",
    "address",
    "city",
    "state",
    "zip_code",
    "zillow_url",
    "beds",
    "baths",
    "sqft",
    "list_price",
    "offer_price",
    "effective_price",
    "price_per_sqft",
    "monthly_piti",
    "cash_to_close",
    "down_payment_pct",
    "interest_rate_pct",
    "loan_term_years",
    "annual_property_tax",
    "annual_insurance",
    "monthly_hoa",
    "notes",
]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.6g}"
    return str(value)


def export_library_csv(snapshots: list[LibraryFinancialSnapshot]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for snap in snapshots:
        data = asdict(snap)
        writer.writerow({k: _cell(data.get(k)) for k in _CSV_FIELDS})
    return buf.getvalue()


def export_library_json(snapshots: list[LibraryFinancialSnapshot]) -> str:
    rows = []
    for snap in snapshots:
        data = asdict(snap)
        data.pop("has_financials", None)
        rows.append(data)
    return json.dumps(rows, indent=2)
