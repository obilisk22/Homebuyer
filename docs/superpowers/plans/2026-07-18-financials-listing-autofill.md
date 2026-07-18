# Financials Listing Autofill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Add home and Refresh listing, autofill Financials list price, HOA, annual tax, and insurance from Zillow first, then Census ACS county tax rates and a published state insurance table — without overwriting offer price or loan terms.

**Architecture:** Extend `ListingDetails` scrape → pure resolvers (`property_tax`, `home_insurance`) → `_sync_financial_from_listing` inside `PropertyService` (called from listing apply, and again after geocode so ACS can run). Light source caption strings on `FinancialAssumptions` feed Ownership UI labels.

**Tech Stack:** Python 3.12, SQLAlchemy/SQLite, existing `census_acs` + `overlay_cache`, pytest, NiceGUI Financials module

**Spec:** `docs/superpowers/specs/2026-07-18-financials-listing-autofill-design.md`

## Global Constraints

- Prefer Windows venv: `.\.venv\Scripts\python.exe` / `.\.venv\Scripts\pytest.exe`
- Do **not** commit unless the user asks (plan steps may say “commit” — skip unless requested)
- After user-facing work: update `AGENTS.md` + `README.md` + `docs/TODO.md` in the same pass as Task 5
- Never overwrite on sync: `offer_price`, `down_payment_pct`, `interest_rate_pct`, `loan_term_years`, `closing_cost_pct`
- Tax rate × value uses **assessed value when known, else list price**
- `propertyTaxRate` from Zillow sample dumps is percent-like (`0.82` → 0.82%); if value `> 0.2`, treat as percent and divide by 100
- No national-average tax fallback; no fixed $6k / $1.8k as “researched” fills after a seed attempt
- ACS tax fallback needs lat/lng — re-run sync after geocode on add

---

## File map

| File | Responsibility |
|------|----------------|
| `app/core/zillow_listing.py` | Parse tax/insurance/assessed/rate into `ListingDetails` |
| `app/core/census_acs.py` | County ACS effective tax rate (B25103 / B25077) + public FIPS helper |
| `app/core/property_tax.py` | Tax precedence resolver → `(amount, source_label)` |
| `app/core/home_insurance.py` | Insurance resolver + load state premium table |
| `app/data/home_insurance_rates.json` | State avg HO-3 premiums + source metadata |
| `app/core/models.py` | Defaults → `0.0` for listing money; source caption columns |
| `app/core/db.py` | Migrate new financial columns |
| `app/core/property_service.py` | `_sync_financial_from_listing`; call after apply + after geocode |
| `app/modules/financial.py` | Ownership captions from source fields |
| `tests/test_listing_filters.py` | Scrape tax/insurance fixtures |
| `tests/test_property_tax.py` | New — tax chain + ACS mock |
| `tests/test_home_insurance.py` | New — insurance chain |
| `tests/test_financial_sync.py` | New — sync overwrite / preserve rules |
| `.env.example`, `AGENTS.md`, `README.md`, `docs/TODO.md` | Docs |

---

### Task 1: Extend Zillow scrape for tax / insurance / assessed / rate

**Files:**
- Modify: `app/core/zillow_listing.py`
- Modify: `tests/test_listing_filters.py`

**Interfaces:**
- Consumes: existing `extract_listing_details(html: str) -> ListingDetails`
- Produces: `ListingDetails` gains:
  - `annual_tax: float | None = None`
  - `annual_insurance: float | None = None`
  - `tax_assessed_value: float | None = None`
  - `property_tax_rate: float | None = None`  # fraction 0–1 after normalization
  - Update `any_present`, `merge_listing_details`, `_details_from_property_dict`

- [ ] **Step 1: Write the failing scrape tests**

Append to `tests/test_listing_filters.py`:

```python
SAMPLE_TAX_INSURANCE_GDP = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"zpid\":1,\"price\":1200000,\"monthlyHoaFee\":250,\"taxAnnualAmount\":11004,\"taxAssessedValue\":1214000,\"propertyTaxRate\":0.82,\"annualHomeownersInsurance\":2400,\"taxHistory\":[{\"time\":1752811412428,\"taxPaid\":12853.69,\"value\":1214000},{\"time\":1700000000000,\"taxPaid\":11054.17,\"value\":1100000}]}"}}}}
</script>
"""


def test_extract_tax_insurance_and_assessed_from_gdp():
    details = extract_listing_details(SAMPLE_TAX_INSURANCE_GDP)
    assert details.list_price == 1_200_000
    assert details.hoa_fee == 250
    # Prefer latest taxHistory.taxPaid over taxAnnualAmount when history present
    assert details.annual_tax == 12853.69
    assert details.tax_assessed_value == 1_214_000
    # 0.82 means 0.82% → 0.0082
    assert details.property_tax_rate == pytest.approx(0.0082)
    assert details.annual_insurance == 2400


def test_extract_tax_annual_when_no_history():
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"componentProps":{"gdpClientCache":"'
        '{\\"zpid\\":2,\\"taxAnnualAmount\\":9000,\\"propertyTaxRate\\":1.1,'
        '\\"taxAssessedValue\\":800000}"'
        '}}}}'
        "</script>"
    )
    details = extract_listing_details(html)
    assert details.annual_tax == 9000
    assert details.property_tax_rate == pytest.approx(0.011)
    assert details.tax_assessed_value == 800_000
```

Add `import pytest` at top of the test file if missing.

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\pytest.exe tests/test_listing_filters.py::test_extract_tax_insurance_and_assessed_from_gdp tests/test_listing_filters.py::test_extract_tax_annual_when_no_history -v
```

Expected: FAIL (attributes missing on `ListingDetails` / assertions fail).

- [ ] **Step 3: Implement scrape fields**

In `app/core/zillow_listing.py`:

1. Add to `_PROPERTY_FACT_KEYS`: `"taxAnnualAmount"`, `"taxAssessedValue"`, `"propertyTaxRate"`, `"annualHomeownersInsurance"`, `"taxHistory"`.

2. Extend `ListingDetails` with the four new optional fields; include them in `any_present`.

3. Add helpers near other parsers:

```python
def _normalize_property_tax_rate(raw: object) -> float | None:
    rate = _parse_float(raw)
    if rate is None or rate <= 0:
        return None
    # Zillow samples use percent units (0.82 → 0.82%); fractions stay as-is.
    if rate > 0.2:
        rate = rate / 100.0
    return rate


def _annual_tax_from_property_dict(d: dict) -> float | None:
    history = d.get("taxHistory")
    best_paid: float | None = None
    best_time: float | None = None
    if isinstance(history, list):
        for row in history:
            if not isinstance(row, dict):
                continue
            paid = _parse_float(row.get("taxPaid") or row.get("taxAmount"))
            if paid is None or paid <= 0:
                continue
            t = _parse_float(row.get("time")) or 0.0
            if best_paid is None or t >= (best_time or 0):
                best_paid = paid
                best_time = t
    if best_paid is not None:
        return best_paid
    for key in ("taxAnnualAmount", "annualTax", "taxAmount"):
        val = _parse_float(d.get(key))
        if val is not None and val > 0:
            return val
    reso = d.get("resoFacts")
    if isinstance(reso, dict):
        for key in ("taxAnnualAmount", "annualTax"):
            val = _parse_float(reso.get(key))
            if val is not None and val > 0:
                return val
    return None
```

4. In `_details_from_property_dict`, set:

```python
annual_tax=_annual_tax_from_property_dict(d),
annual_insurance=_parse_float(
    d.get("annualHomeownersInsurance")
    or (d.get("resoFacts") or {}).get("annualHomeownersInsurance")
    if isinstance(d.get("resoFacts"), dict)
    else d.get("annualHomeownersInsurance")
),
tax_assessed_value=_parse_float(
    d.get("taxAssessedValue") or d.get("assessedValue")
),
property_tax_rate=_normalize_property_tax_rate(d.get("propertyTaxRate")),
```

(Keep insurance parse readable — prefer a small `_first_float(d, *keys)` helper if that matches file style.)

5. Update `merge_listing_details` to prefer first non-`None` for the new float fields (same pattern as `list_price` / `hoa_fee`).

- [ ] **Step 4: Run scrape tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_listing_filters.py -q
```

Expected: PASS.

---

### Task 2: Census ACS county effective tax rate + `property_tax` resolver

**Files:**
- Modify: `app/core/census_acs.py`
- Create: `app/core/property_tax.py`
- Create: `tests/test_property_tax.py`

**Interfaces:**
- Consumes: `overlay_cache.cache_key/read_json/write_json`, existing ACS year/dataset/key helpers
- Produces:
  - `county_fips_for(lat: float, lng: float) -> tuple[str, str]` (wrapper around `_fcc_fips`)
  - `county_effective_property_tax_rate(lat: float, lng: float) -> float | None`
  - `resolve_annual_property_tax(*, annual_tax, tax_assessed_value, property_tax_rate, list_price, lat, lng) -> tuple[float | None, str]`  
    Returns `(amount_or_None, source_label)` where label is one of  
    `"Zillow"`, `"Zillow assessed × rate"`, `"Estimated: ACS county"`, `""`

- [ ] **Step 1: Write failing resolver tests**

Create `tests/test_property_tax.py`:

```python
from app.core.property_tax import resolve_annual_property_tax


def test_prefers_explicit_zillow_tax():
    amount, source = resolve_annual_property_tax(
        annual_tax=12_853.69,
        tax_assessed_value=1_214_000,
        property_tax_rate=0.0082,
        list_price=1_200_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 12_853.69
    assert source == "Zillow"


def test_assessed_times_rate_when_no_explicit_tax(monkeypatch):
    # Ensure ACS is not consulted
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.99,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=1_000_000,
        property_tax_rate=0.01,
        list_price=900_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 10_000.0
    assert source == "Zillow assessed × rate"


def test_acs_uses_assessed_when_present(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.01,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=800_000,
        property_tax_rate=None,
        list_price=1_000_000,
        lat=34.0,
        lng=-118.5,
    )
    assert amount == 8_000.0
    assert "ACS" in source


def test_acs_falls_back_to_list_price(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: 0.012,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=None,
        property_tax_rate=None,
        list_price=500_000,
        lat=47.6,
        lng=-122.3,
    )
    assert amount == 6_000.0
    assert "ACS" in source


def test_unresolved_when_no_data(monkeypatch):
    monkeypatch.setattr(
        "app.core.property_tax.county_effective_property_tax_rate",
        lambda lat, lng: None,
    )
    amount, source = resolve_annual_property_tax(
        annual_tax=None,
        tax_assessed_value=None,
        property_tax_rate=None,
        list_price=500_000,
        lat=None,
        lng=None,
    )
    assert amount is None
    assert source == ""
```

- [ ] **Step 2: Run to verify fail**

```powershell
.\.venv\Scripts\pytest.exe tests/test_property_tax.py -v
```

Expected: FAIL (import error).

- [ ] **Step 3: Implement ACS county rate helper**

In `app/core/census_acs.py`, add:

```python
def county_fips_for(lat: float, lng: float) -> tuple[str, str]:
    """Public wrapper: (state_fips, county_fips) via FCC block API."""
    return _fcc_fips(lat, lng)


def _parse_acs_missing(raw: object) -> float | None:
    if raw is None or raw == "" or raw is False:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    # Census sentinel for missing / not available
    if val < -1_000_000:
        return None
    if val <= 0:
        return None
    return val


def county_effective_property_tax_rate(lat: float, lng: float) -> float | None:
    """Median real-estate taxes / median home value for the pin's county (ACS 5-year).

    Tables: B25103_001E (median real estate taxes), B25077_001E (median value).
    Requires CENSUS_API_KEY. Returns None on any failure.
    """
    if not has_census_key():
        return None
    try:
        state_fips, county_fips = _fcc_fips(lat, lng)
    except Exception:
        return None

    key = cache_key("acs", ACS_YEAR, state_fips, county_fips, "B25103_B25077")
    cached = read_json("acs_tax_rate", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and "rate" in cached:
        rate = cached.get("rate")
        return float(rate) if rate is not None else None

    url = f"https://api.census.gov/data/{ACS_DATASET}"
    params = {
        "get": "NAME,B25103_001E,B25077_001E",
        "for": f"county:{county_fips}",
        "in": f"state:{state_fips}",
        "key": census_api_key(),
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return None

    if not isinstance(rows, list) or len(rows) < 2:
        return None
    header, data = rows[0], rows[1]
    try:
        tax_i = header.index("B25103_001E")
        val_i = header.index("B25077_001E")
    except ValueError:
        return None
    median_tax = _parse_acs_missing(data[tax_i])
    median_value = _parse_acs_missing(data[val_i])
    rate: float | None = None
    if median_tax is not None and median_value is not None and median_value > 0:
        rate = median_tax / median_value
    write_json(
        "acs_tax_rate",
        key,
        {
            "rate": rate,
            "median_tax": median_tax,
            "median_value": median_value,
            "name": data[header.index("NAME")] if "NAME" in header else "",
        },
    )
    return rate
```

Mirror request/header error handling style already used in `_fetch_acs_incomes`.

- [ ] **Step 4: Implement `app/core/property_tax.py`**

```python
"""Resolve annual property tax from listing facts + Census ACS county rates."""

from __future__ import annotations

from app.core.census_acs import county_effective_property_tax_rate


def resolve_annual_property_tax(
    *,
    annual_tax: float | None,
    tax_assessed_value: float | None,
    property_tax_rate: float | None,
    list_price: float | None,
    lat: float | None,
    lng: float | None,
) -> tuple[float | None, str]:
    if annual_tax is not None and annual_tax > 0:
        return float(annual_tax), "Zillow"

    if (
        tax_assessed_value is not None
        and tax_assessed_value > 0
        and property_tax_rate is not None
        and property_tax_rate > 0
    ):
        return float(tax_assessed_value) * float(property_tax_rate), "Zillow assessed × rate"

    basis: float | None = None
    if tax_assessed_value is not None and tax_assessed_value > 0:
        basis = float(tax_assessed_value)
    elif list_price is not None and list_price > 0:
        basis = float(list_price)

    if basis is not None and lat is not None and lng is not None:
        rate = county_effective_property_tax_rate(float(lat), float(lng))
        if rate is not None and rate > 0:
            return basis * rate, "Estimated: ACS county"

    return None, ""
```

- [ ] **Step 5: Run tax tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_property_tax.py -q
```

Expected: PASS.

---

### Task 3: Home insurance table + resolver

**Files:**
- Create: `app/data/home_insurance_rates.json`
- Create: `app/core/home_insurance.py`
- Create: `tests/test_home_insurance.py`
- Ensure `app/data/` is importable via path relative to package (use `Path(__file__).resolve().parents[1] / "data" / ...` from `app/core/`)

**Interfaces:**
- Produces:
  - `resolve_annual_insurance(*, annual_insurance, list_price, state) -> tuple[float | None, str]`
  - Labels: `"Zillow"`, `"Estimated: {ST} avg premium"`, `""`
  - Formula when using table:  
    `avg_premium_usd * (list_price / reference_coverage_usd)`  
    with `reference_coverage_usd` from JSON (default `300000`)

- [ ] **Step 1: Write failing insurance tests**

Create `tests/test_home_insurance.py`:

```python
from app.core.home_insurance import resolve_annual_insurance


def test_prefers_zillow_insurance():
    amount, source = resolve_annual_insurance(
        annual_insurance=2_400,
        list_price=1_000_000,
        state="CA",
    )
    assert amount == 2_400
    assert source == "Zillow"


def test_scales_state_average_premium():
    # CA entry in table: avg_premium_usd=2011, reference=300000
    # → 2011 * (600000/300000) = 4022
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=600_000,
        state="CA",
    )
    assert amount == 4022
    assert "CA" in source


def test_unknown_state_unresolved():
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=600_000,
        state="XX",
    )
    assert amount is None
    assert source == ""


def test_missing_price_unresolved():
    amount, source = resolve_annual_insurance(
        annual_insurance=None,
        list_price=0,
        state="CA",
    )
    assert amount is None
```

- [ ] **Step 2: Run to verify fail**

```powershell
.\.venv\Scripts\pytest.exe tests/test_home_insurance.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create rate table JSON**

Create `app/data/home_insurance_rates.json` with this shape (include **all** 50 states + DC). Values are rounded average annual HO-3 premiums from NAIC / Insurance Information Institute published state averages (data year ~2022–2023 roundups). Document source in `_meta`.

```json
{
  "_meta": {
    "description": "Average annual homeowners (HO-3) premiums by US state, used to scale an estimate for a given home price.",
    "formula": "estimate = avg_premium_usd * (list_price / reference_coverage_usd)",
    "reference_coverage_usd": 300000,
    "sources": [
      "NAIC Dwelling Fire, Homeowners Owner-Occupied Report (recent data year averages as republished by III / consumer roundups)",
      "https://content.naic.org/sites/default/files/publication-hmr-zu-homeowners-report.pdf"
    ],
    "notes": "Not a quote. Scales average premium linearly with price vs reference coverage. Prefer Zillow annualHomeownersInsurance when present."
  },
  "reference_coverage_usd": 300000,
  "avg_premium_usd": {
    "AL": 2651, "AK": 1423, "AZ": 2495, "AR": 3364, "CA": 2011,
    "CO": 3499, "CT": 2140, "DE": 1600, "DC": 1798, "FL": 10968,
    "GA": 2565, "HI": 1410, "ID": 1696, "IL": 2280, "IN": 2018,
    "IA": 1936, "KS": 3430, "KY": 2785, "LA": 8665, "ME": 1405,
    "MD": 1795, "MA": 2190, "MI": 2105, "MN": 2550, "MS": 3435,
    "MO": 2820, "MT": 2320, "NE": 3380, "NV": 1785, "NH": 1490,
    "NJ": 1785, "NM": 2310, "NY": 2105, "NC": 2315, "ND": 2325,
    "OH": 1685, "OK": 4835, "OR": 1455, "PA": 1485, "RI": 2010,
    "SC": 2560, "SD": 2410, "TN": 2655, "TX": 4375, "UT": 1410,
    "VT": 1325, "VA": 1785, "WA": 1585, "WV": 1785, "WI": 1485,
    "WY": 1785
  }
}
```

If a more authoritative extract from the NAIC PDF is available during implementation, replace premiums but keep the same schema and `_meta.sources`.

- [ ] **Step 4: Implement `app/core/home_insurance.py`**

```python
"""Resolve annual homeowners insurance from listing or state premium table."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_TABLE_PATH = Path(__file__).resolve().parents[1] / "data" / "home_insurance_rates.json"


@lru_cache(maxsize=1)
def _load_table() -> dict:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_annual_insurance(
    *,
    annual_insurance: float | None,
    list_price: float | None,
    state: str | None,
) -> tuple[float | None, str]:
    if annual_insurance is not None and annual_insurance > 0:
        return float(annual_insurance), "Zillow"

    price = float(list_price or 0)
    if price <= 0:
        return None, ""

    st = (state or "").strip().upper()
    if len(st) != 2:
        return None, ""

    table = _load_table()
    premiums: dict = table.get("avg_premium_usd") or {}
    avg = premiums.get(st)
    if avg is None:
        return None, ""

    ref = float(table.get("reference_coverage_usd") or 300_000)
    if ref <= 0:
        return None, ""

    estimate = float(avg) * (price / ref)
    return round(estimate), f"Estimated: {st} avg premium"
```

- [ ] **Step 5: Run insurance tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_home_insurance.py -q
```

Expected: PASS (adjust CA assertion if table value differs).

---

### Task 4: Model defaults + sync financial assumptions on add/refresh

**Files:**
- Modify: `app/core/models.py` (`FinancialAssumptions`)
- Modify: `app/core/db.py` (add source columns if missing)
- Modify: `app/core/property_service.py`
- Create: `tests/test_financial_sync.py`

**Interfaces:**
- Consumes: `resolve_annual_property_tax`, `resolve_annual_insurance`, `ListingDetails`
- Produces: `PropertyService._sync_financial_from_listing(prop, details) -> None`
  - Writes: `list_price`, `purchase_price` (keep in sync with list), `monthly_hoa` (when `details.hoa_fee is not None`), `annual_property_tax`, `annual_insurance`, `property_tax_source`, `insurance_source`
  - Never writes loan-term fields / `offer_price`
  - Unresolved tax/insurance → `0.0` and empty source string **when this sync runs**
  - Called from `_apply_listing_details` and again after successful geocode in `add_from_zillow`
  - `refresh_listing_details`: after apply, if coords missing try `ensure_coordinates` (swallow errors), then `_sync_financial_from_listing` again if details were fetched

Model changes:

```python
list_price: Mapped[float] = mapped_column(Float, default=0.0)
purchase_price: Mapped[float] = mapped_column(Float, default=0.0)  # legacy; sync with list
annual_property_tax: Mapped[float] = mapped_column(Float, default=0.0)
annual_insurance: Mapped[float] = mapped_column(Float, default=0.0)
property_tax_source: Mapped[str] = mapped_column(String(64), default="")
insurance_source: Mapped[str] = mapped_column(String(64), default="")
```

(Keep other loan defaults unchanged.)

- [ ] **Step 1: Write failing sync tests**

Create `tests/test_financial_sync.py`:

```python
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
```

Wire imports of resolvers at module level in `property_service` so monkeypatch paths match.

- [ ] **Step 2: Run to verify fail**

```powershell
.\.venv\Scripts\pytest.exe tests/test_financial_sync.py -v
```

Expected: FAIL.

- [ ] **Step 3: Update models + migration**

In `models.py`, change defaults as above; add `property_tax_source` and `insurance_source` (`String(64)`, default `""`).

In `db.py` `_migrate_sqlite`, inside the `fin_cols` block, add:

```python
if "property_tax_source" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN property_tax_source VARCHAR(64) NOT NULL DEFAULT ''"
    )
if "insurance_source" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN insurance_source VARCHAR(64) NOT NULL DEFAULT ''"
    )
```

Do **not** mass-UPDATE existing rows’ tax/insurance to 0 in migration — refresh listing re-seeds. Changing SQLAlchemy defaults only affects **new** `FinancialAssumptions()` rows.

- [ ] **Step 4: Implement sync + call sites**

In `property_service.py`:

```python
from app.core.property_tax import resolve_annual_property_tax
from app.core.home_insurance import resolve_annual_insurance
```

Replace HOA-only financial seed inside `_apply_listing_details` with:

```python
def _apply_listing_details(self, prop: Property, details: ListingDetails) -> None:
    # ... existing property field updates including hoa_fee on Property ...
    if details.hoa_fee is not None:
        prop.hoa_fee = details.hoa_fee
    # remove old "seed financial HOA when still zero" block
    ...
    self._sync_financial_from_listing(prop, details)


def _sync_financial_from_listing(self, prop: Property, details: ListingDetails) -> None:
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
```

In `add_from_zillow`, after successful geocode commit, re-run sync if listing details are available:

```python
        details_for_sync: ListingDetails | None = None
        try:
            html = fetch_listing_html(prop.zillow_url)
            details_for_sync = extract_listing_details(html)
            self._apply_listing_details(prop, details_for_sync)
            ...
        except Exception:
            html = None
            details_for_sync = None

        try:
            lat, lng = geocode_address(prop.address)
            prop.latitude = lat
            prop.longitude = lng
            self.session.commit()
            self.session.refresh(prop)
            if details_for_sync is not None:
                self._sync_financial_from_listing(prop, details_for_sync)
                self.session.commit()
                self.session.refresh(prop)
        except ValueError:
            pass
```

In `refresh_listing_details`:

```python
    def refresh_listing_details(self, property_id: int) -> Property:
        prop = self.get_property(property_id)
        if prop is None:
            raise ValueError("Property not found.")
        details: ListingDetails | None = None
        try:
            details = fetch_listing_details(prop.zillow_url)
            self._apply_listing_details(prop, details)
        except Exception:
            pass
        self._fill_location_from_address(prop)
        if prop.latitude is None or prop.longitude is None:
            try:
                self.ensure_coordinates(property_id)
                prop = self.get_property(property_id) or prop
            except Exception:
                pass
        if details is not None:
            self._sync_financial_from_listing(prop, details)
        self.session.commit()
        self.session.refresh(prop)
        return prop
```

Note: `ensure_coordinates` already commits — re-fetch prop before second sync.

- [ ] **Step 5: Run sync + related tests**

```powershell
.\.venv\Scripts\pytest.exe tests/test_financial_sync.py tests/test_core.py tests/test_gemini_financial.py -q
```

Expected: PASS. Fix seed if anything assumed old $500k defaults without `update_financial` (seed already sets explicit finances).

---

### Task 5: Financials UI captions + docs + full verify

**Files:**
- Modify: `app/modules/financial.py`
- Modify: `.env.example`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/TODO.md` (add TODO-011 Done or extend status for financials autofill)

**Interfaces:**
- Consumes: `fin.property_tax_source`, `fin.insurance_source`
- Produces: caption labels under Ownership tax/insurance inputs

- [ ] **Step 1: Add ownership captions**

In `app/modules/financial.py`, after creating tax/insurance inputs in Ownership section:

```python
                tax = ui.number(
                    "Property tax / year", value=values["annual_property_tax"], format="%.0f"
                ).props("prefix=$ dense outlined").classes("w-full")
                if (fin.property_tax_source or "").strip():
                    ui.label(fin.property_tax_source).classes("text-caption text-grey-6")
                insurance = ui.number(
                    "Insurance / year", value=values["annual_insurance"], format="%.0f"
                ).props("prefix=$ dense outlined").classes("w-full")
                if (fin.insurance_source or "").strip():
                    ui.label(fin.insurance_source).classes("text-caption text-grey-6")
```

Ensure `fin` is in scope (already from `ensure_financial`). If values were loaded via dict only, read sources from the financial object used at render start.

- [ ] **Step 2: Update `.env.example`**

Extend Census comment:

```
# Census Bureau API — Map income choropleth (ACS B19013) AND Financials
# county effective property-tax fallback (ACS B25103 / B25077).
# Free signup: https://api.census.gov/data/key_signup.html
CENSUS_API_KEY=
```

- [ ] **Step 3: Update continuity docs**

In `AGENTS.md` / `README.md`:

- What’s done: Financials autofill from Zillow + ACS county tax + state insurance table on add/refresh
- Product decision: listing-sourced fields overwrite on refresh; loan terms preserved; tax basis assessed→list; sources shown as captions
- Quick verify: add/refresh a home → Financials list price/HOA/tax/insurance match listing or show ACS/state estimate captions; offer/rate untouched

In `docs/TODO.md`, add:

```markdown
| TODO-011 | Done | Financials: autofill list/HOA/tax/insurance from Zillow + ACS/state tables |
```

Plus a short section mirroring other Done items.

- [ ] **Step 4: Full test suite**

```powershell
cd C:\Users\hheaf\Projects\homebuy
.\.venv\Scripts\pytest.exe -q
```

Expected: all PASS.

- [ ] **Step 5: Manual smoke (if app running)**

1. Restart: `.\.venv\Scripts\python.exe -m app.main`
2. Refresh listing on an existing home (or add new Zillow URL)
3. Open Financials: list price ≈ listing; tax/insurance non-placeholder; captions present when sourced; change interest rate, refresh listing again — rate unchanged

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Scrape tax/insurance/assessed/rate | 1 |
| Tax chain explicit → assessed×rate → ACS×assessed → ACS×list | 2 |
| Insurance Zillow → state table scale | 3 |
| Overwrite listing fields on add/refresh; preserve loan terms | 4 |
| Unresolved → 0 after seed attempt | 4 |
| HOA omit keeps previous; explicit 0 overwrites | 4 |
| Defaults not fake $500k/$6k/$1.8k for new rows | 4 |
| Re-sync after geocode for ACS | 4 |
| Light UI source captions | 5 |
| Docs / CENSUS key note | 5 |

## Placeholder / consistency self-review

- No TBD steps; signatures aligned across tasks (`resolve_annual_property_tax` / `resolve_annual_insurance` / `_sync_financial_from_listing`).
- Insurance JSON premiums are approximate NAIC/III roundups — replace with exact PDF extract if desired; schema stable.
- `ensure_coordinates` double-commit on refresh is acceptable; keep implementation careful about refreshed `prop` identity.
