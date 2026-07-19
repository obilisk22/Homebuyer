"""Side-by-side home compare helpers (TODO-018)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.library_export import LibraryFinancialSnapshot, snapshot_from_property
from app.core.models import Property

_ID_SPLIT = re.compile(r"[,;\-\s]+")


@dataclass(frozen=True)
class CompareRow:
    id: int
    address: str
    list_price: float | None
    offer_price: float | None
    effective_price: float | None
    price_per_sqft: float | None
    beds: float | None
    baths: float | None
    monthly_piti: float | None
    cash_to_close: float | None


def parse_compare_ids(raw: str | None) -> list[int]:
    """Parse ``1,2,3`` or ``1-2-3`` style id lists; ignore non-integers."""
    text = (raw or "").strip()
    if not text:
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for part in _ID_SPLIT.split(text):
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


def build_compare_rows(props: list[Property]) -> list[CompareRow]:
    """Build compare columns for 2–4 homes (no status — TODO-015 won't fix)."""
    if not 2 <= len(props) <= 4:
        raise ValueError("Compare requires 2–4 homes.")
    rows: list[CompareRow] = []
    for prop in props:
        snap: LibraryFinancialSnapshot = snapshot_from_property(prop)
        rows.append(
            CompareRow(
                id=snap.id,
                address=snap.address,
                list_price=snap.list_price,
                offer_price=snap.offer_price,
                effective_price=snap.effective_price,
                price_per_sqft=snap.price_per_sqft,
                beds=snap.beds,
                baths=snap.baths,
                monthly_piti=snap.monthly_piti,
                cash_to_close=snap.cash_to_close,
            )
        )
    return rows
