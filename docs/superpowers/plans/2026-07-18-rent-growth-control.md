# Rent Growth + Rent Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Buy vs rent rent grow over time — 2%/yr when Rent control is checked, otherwise ACS county median-rent ~5y CAGR — with PITI still flat.

**Architecture:** Pure CAGR + projection math in `finance.py`; ACS county `B25064` dual-year fetch in `census_acs.py`; persist `rent_control` / `rent_growth_pct` / `rent_growth_source` on FinancialAssumptions; sync from listing refresh + UI toggle; Financials checkbox + captions.

**Tech Stack:** Python 3.12, NiceGUI, SQLAlchemy/SQLite, Census ACS API (`CENSUS_API_KEY`), existing overlay cache, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-rent-growth-control-design.md`

## Global Constraints

- Rent control on → growth exactly **2%/yr**, source `Rent control 2%`.
- Rent control off → ACS county **B25064** CAGR over **5** years (`ACS_YEAR` vs `ACS_YEAR - 5`); source `ACS county ~5y CAGR`.
- ACS fail / no key / no coords → growth **3%**, source `Default`.
- Owner **PITI stays flat** for the whole horizon.
- Geography = **county** via FCC FIPS (not city).
- Negative ACS CAGR allowed.
- No live Census in CI — fixtures/mocks only.
- Do not change Gemini fingerprint; exclude new fields from `summarize()` inputs.
- Windows: `.\.venv\Scripts\pytest.exe`.
- Do not commit unless the user asks (plan commit steps are optional).

## File structure

| File | Responsibility |
|------|----------------|
| `app/core/finance.py` | `rent_cagr_pct`, `buy_vs_rent_projection(..., rent_growth_pct=)` |
| `app/core/census_acs.py` | `county_median_rent_cagr(lat, lng) -> float \| None` |
| `app/core/models.py` + `db.py` | New columns + migrate |
| `app/core/property_service.py` | Resolve growth on sync / helpers |
| `app/modules/financial.py` | Checkbox, growth caption, pass growth into projection |
| `tests/test_buy_vs_rent.py` | Growth projection + CAGR math |
| `tests/test_rent_growth.py` | ACS helper + sync rules (mocked) |
| `AGENTS.md`, `README.md` | Continuity |

---

### Task 1: Projection math + pure CAGR helper

**Files:**
- Modify: `app/core/finance.py`
- Modify: `tests/test_buy_vs_rent.py`

**Interfaces:**
- Produces:
  - `rent_cagr_pct(rent_start: float, rent_end: float, *, years: int = 5) -> float | None`
  - `buy_vs_rent_projection(..., rent_growth_pct: float = 0.0)` — yearly `rent(t) = rent0 * (1+g)^t`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_buy_vs_rent.py`:

```python
from app.core.finance import rent_cagr_pct


def test_rent_cagr_pct_five_years():
    # doubles over 5 years → (2**(1/5)-1)*100
    rate = rent_cagr_pct(1000.0, 2000.0, years=5)
    assert rate is not None
    assert abs(rate - ((2.0 ** (1 / 5) - 1.0) * 100.0)) < 0.01


def test_rent_cagr_pct_invalid():
    assert rent_cagr_pct(0, 2000.0) is None
    assert rent_cagr_pct(1000.0, 0) is None
    assert rent_cagr_pct(-1, 2000) is None


def test_buy_vs_rent_applies_rent_growth_year_one():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=0.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rent0 = summary.monthly_total / 2.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent0,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
        rent_growth_pct=10.0,  # easy math
    )
    # Year 0 portfolio = cash_to_close; after year 1: 12 months at rent0*(1.1)
    rent_y1 = rent0 * 1.10
    contrib_y1 = summary.monthly_total - rent_y1
    expected = 100_000 + 12 * contrib_y1
    assert abs(rows[1].rent_invest_net_worth - expected) < 1.0
```

- [ ] **Step 2: Run to verify fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py::test_rent_cagr_pct_five_years tests/test_buy_vs_rent.py::test_buy_vs_rent_applies_rent_growth_year_one -v`

Expected: FAIL (import / unexpected TypeError on unknown kwarg).

- [ ] **Step 3: Implement**

In `finance.py`:

```python
def rent_cagr_pct(
    rent_start: float, rent_end: float, *, years: int = 5
) -> float | None:
    if years <= 0:
        return None
    try:
        start = float(rent_start)
        end = float(rent_end)
    except (TypeError, ValueError):
        return None
    if start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0
```

Update `buy_vs_rent_projection` signature to add `rent_growth_pct: float = 0.0`. Replace the flat `contrib` with per-year rent:

```python
    g = float(rent_growth_pct or 0) / 100.0
    rent0 = float(monthly_rent or 0)
    ...
    for year in range(0, term_years + 1):
        ...
        # existing buy_nw / append row using current portfolio
        ...
        if year == term_years:
            break
        rent_year = rent0 * ((1.0 + g) ** (year + 1))  # growth applies to next 12 months
        contrib = max(0.0, piti - rent_year)
        for _ in range(12):
            portfolio = portfolio * (1.0 + r_month) + contrib
```

Note: Year 0 row uses portfolio before contributions. Months after year 0 use `rent0 * (1+g)^1`; after year 1 use `(1+g)^2`, matching spec `rent(t)` for year \(t\) where \(t\) is the year index of the upcoming block. Spec says year \(t\) months use `rent0*(1+g)^t` with year 0 using `rent0`. So after writing year-0 row, advance with `rent(1)=rent0*(1+g)^1`; after year-1 row, advance with `rent(2)`, etc. Use `((1.0 + g) ** (year + 1))` as above.

Keep default `rent_growth_pct=0.0` so existing tests that omit it stay flat-rent.

- [ ] **Step 4: Run tests pass**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py -q`

Expected: PASS

- [ ] **Step 5: Commit (only if user asked)**

```bash
git add app/core/finance.py tests/test_buy_vs_rent.py
git commit -m "feat: apply annual rent growth in buy vs rent projection"
```

---

### Task 2: ACS county median rent CAGR

**Files:**
- Modify: `app/core/census_acs.py`
- Create: `tests/test_rent_growth.py`

**Interfaces:**
- Consumes: `has_census_key`, `_fcc_fips`, `ACS_YEAR`, `ACS_DATASET`, `cache_key` / `read_json` / `write_json`, `requests`
- Produces: `county_median_rent_cagr(lat: float, lng: float) -> float | None`
- Also export pure parser for tests: `cagr_from_county_rent_rows(end_rows, start_rows) -> float | None` OR call `rent_cagr_pct` after extracting medians from mocked JSON

- [ ] **Step 1: Write failing tests**

Create `tests/test_rent_growth.py`:

```python
from unittest.mock import patch

from app.core.census_acs import county_median_rent_cagr
from app.core.finance import rent_cagr_pct


def test_county_median_rent_cagr_from_mocked_acs():
    end_payload = [
        ["NAME", "B25064_001E", "state", "county"],
        ["X County", "2000", "06", "037"],
    ]
    start_payload = [
        ["NAME", "B25064_001E", "state", "county"],
        ["X County", "1000", "06", "037"],
    ]

    def fake_get(url, params=None, timeout=None):
        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                # year is in url path .../2023/acs/... vs .../2018/...
                if "/2018/" in url:
                    return start_payload
                return end_payload

        return Resp()

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


def test_county_median_rent_cagr_no_key():
    with patch("app.core.census_acs.has_census_key", return_value=False):
        assert county_median_rent_cagr(34.0, -118.0) is None
```

Adjust URL year checks to match how you build the dataset string (`f"{year}/acs/acs5"`).

- [ ] **Step 2: Run to fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_rent_growth.py -v`

Expected: FAIL (function missing).

- [ ] **Step 3: Implement `county_median_rent_cagr`**

Mirror `county_effective_property_tax_rate` in `census_acs.py`:

```python
def _county_median_gross_rent(state_fips: str, county_fips: str, year: int) -> float | None:
    key = cache_key("acs", year, state_fips, county_fips, "B25064_county")
    cached = read_json("acs_county_rent", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and "rent" in cached:
        rent = cached.get("rent")
        return float(rent) if rent is not None else None

    dataset = f"{year}/acs/acs5"
    url = f"https://api.census.gov/data/{dataset}"
    params = {
        "get": "NAME,B25064_001E",
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
        rent_i = header.index("B25064_001E")
    except ValueError:
        return None
    rent = _parse_acs_missing(data[rent_i])
    write_json("acs_county_rent", key, {"rent": rent, "name": data[0] if data else ""})
    return rent


def county_median_rent_cagr(lat: float, lng: float) -> float | None:
    """~5y CAGR of county median gross rent (ACS B25064)."""
    from app.core.finance import rent_cagr_pct

    if not has_census_key():
        return None
    try:
        state_fips, county_fips = _fcc_fips(lat, lng)
    except Exception:
        return None
    end = _county_median_gross_rent(state_fips, county_fips, ACS_YEAR)
    start = _county_median_gross_rent(state_fips, county_fips, ACS_YEAR - 5)
    if end is None or start is None:
        return None
    return rent_cagr_pct(start, end, years=5)
```

- [ ] **Step 4: Tests pass**

Run: `.\.venv\Scripts\pytest.exe tests/test_rent_growth.py -q`

Expected: PASS

- [ ] **Step 5: Commit (only if user asked)**

```bash
git add app/core/census_acs.py tests/test_rent_growth.py
git commit -m "feat: ACS county median rent CAGR for buy vs rent"
```

---

### Task 3: Models, migrate, resolve growth sync

**Files:**
- Modify: `app/core/models.py`, `app/core/db.py`, `app/core/property_service.py`
- Modify: `tests/test_rent_growth.py` (sync tests)

**Interfaces:**
- Columns: `rent_control: bool = False`, `rent_growth_pct: float = 3.0`, `rent_growth_source: str = ""`
- `PropertyService.resolve_rent_growth(fin, prop) -> None` mutates fin per spec rules
- Call from `_sync_financial_from_listing` after rent zestimate sync

- [ ] **Step 1: Add model columns + migrate ALTERs**

`models.py`:

```python
rent_control: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
rent_growth_pct: Mapped[float] = mapped_column(Float, default=3.0)
rent_growth_source: Mapped[str] = mapped_column(String(64), default="")
```

`db.py` inside `if fin_cols:`:

```python
if "rent_control" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN rent_control BOOLEAN NOT NULL DEFAULT 0"
    )
if "rent_growth_pct" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN rent_growth_pct FLOAT NOT NULL DEFAULT 3"
    )
if "rent_growth_source" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN rent_growth_source VARCHAR(64) NOT NULL DEFAULT ''"
    )
```

- [ ] **Step 2: Implement resolve helper + wire sync**

In `property_service.py`:

```python
def _resolve_rent_growth(self, prop: Property, fin: FinancialAssumptions) -> None:
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
    except Exception:
        cagr = None
    if cagr is not None:
        fin.rent_growth_pct = float(cagr)
        fin.rent_growth_source = "ACS county ~5y CAGR"
    else:
        fin.rent_growth_pct = 3.0
        fin.rent_growth_source = "Default"
```

Call `self._resolve_rent_growth(prop, fin)` at end of `_sync_financial_from_listing`.

Extend `update_financial` to accept bool for `rent_control` and:

```python
if "rent_control" in fields and bool(fields["rent_control"]):
    fin.rent_control = True
    fin.rent_growth_pct = 2.0
    fin.rent_growth_source = "Rent control 2%"
elif "rent_growth_pct" in fields and float(fields["rent_growth_pct"]) != prev_growth:
    fin.rent_growth_source = "Manual"
    fin.rent_control = False
```

When UI unchecks control and saves with `rent_control=False`, call resolve (or let Save pass growth from UI after ACS refresh — see Task 4). Prefer: `update_financial` if `rent_control` flips from True→False, call `_resolve_rent_growth`.

- [ ] **Step 3: Sync unit tests with mocks**

```python
def test_resolve_rent_growth_control_forces_two_percent():
    # build fin+prop in-memory or via existing sync test fixtures
    ...

def test_resolve_rent_growth_acs_when_unchecked(monkeypatch):
    monkeypatch.setattr(
        "app.core.census_acs.county_median_rent_cagr", lambda lat, lng: 4.25
    )
    ...
    assert fin.rent_growth_pct == 4.25
    assert fin.rent_growth_source == "ACS county ~5y CAGR"
```

- [ ] **Step 4: Smoke migrate + tests**

Run: `.\.venv\Scripts\python.exe -c "from app.core.db import init_db; init_db(); print('ok')"`  
Run: `.\.venv\Scripts\pytest.exe tests/test_rent_growth.py tests/test_financial_sync.py -q`

Expected: ok / PASS

- [ ] **Step 5: Commit (only if user asked)**

```bash
git add app/core/models.py app/core/db.py app/core/property_service.py tests/test_rent_growth.py
git commit -m "feat: persist rent control and ACS rent growth assumptions"
```

---

### Task 4: Financials UI — checkbox + wire projection

**Files:**
- Modify: `app/modules/financial.py`

**Interfaces:**
- Consumes: fin fields + `buy_vs_rent_projection(..., rent_growth_pct=)`
- UI: checkbox `Rent control` beside rent; growth caption; Save includes fields

- [ ] **Step 1: Add controls**

In Buy vs rent section:

```python
with ui.row().classes("w-full items-end gap-2 no-wrap"):
    rent_in = ui.number(...).classes("col")
    rent_control = ui.checkbox("Rent control", value=bool(fin.rent_control)).props("dense")

growth_caption = ui.label("").classes("hb-page-meta")

def refresh_growth_caption() -> None:
    g = float(growth_in.value if 'growth_in' in dir() else fin.rent_growth_pct or 0)
    # Prefer: store growth in a number field OR derive from checkbox
    ...
```

Preferred UX per spec (caption, not free-edit unless Manual path from Save):

- On checkbox change:
  - checked → set local growth 2 / source Rent control; redraw
  - unchecked → call session `PropertyService` to resolve ACS for this property (or optimistic Default then Save), update caption, redraw
- Include in `collect()`: `rent_control`, `rent_growth_pct` (from fin state dict updated by toggle)
- Pass `rent_growth_pct` into `buy_vs_rent_projection`
- Chart caption append `rent growth X%/yr · {source}`

Keep a mutable `growth_state = {"pct": fin.rent_growth_pct, "source": fin.rent_growth_source, "control": bool(fin.rent_control)}` updated by checkbox and Save.

Minimal checkbox handler:

```python
def on_rent_control(e) -> None:
    checked = bool(rent_control.value)
    growth_state["control"] = checked
    if checked:
        growth_state["pct"] = 2.0
        growth_state["source"] = "Rent control 2%"
        refresh_growth_caption()
        redraw()
        return
    with get_session() as session:
        svc = PropertyService(session)
        prop = svc.get_property(property_id)
        fin_row = svc.ensure_financial(prop)
        fin_row.rent_control = False
        if (fin_row.rent_growth_source or "") == "Manual":
            fin_row.rent_growth_source = ""  # allow ACS refresh
        svc._resolve_rent_growth(prop, fin_row)
        session.commit()
        growth_state["pct"] = float(fin_row.rent_growth_pct or 3)
        growth_state["source"] = fin_row.rent_growth_source or "Default"
    refresh_growth_caption()
    redraw()
```

Avoid calling private `_resolve_rent_growth` if possible — expose `ensure_rent_growth(property_id, *, rent_control: bool)` public method instead.

- [ ] **Step 2: Wire projection**

```python
projection = buy_vs_rent_projection(
    summary=result,
    appreciation_pct=float(appr_in.value or 0),
    monthly_rent=float(rent_in.value or 0),
    rent_growth_pct=float(growth_state["pct"] or 0),
)
```

- [ ] **Step 3: Manual smoke + full suite**

Restart app; toggle Rent control; confirm caption 2% vs ACS/Default; Recalculate moves rent line.

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: all pass.

- [ ] **Step 4: Commit (only if user asked)**

```bash
git add app/modules/financial.py
git commit -m "feat: Rent control checkbox and growing rent on Financials chart"
```

---

### Task 5: Docs

**Files:** `AGENTS.md`, `README.md`

- [ ] **Step 1:** Update decision 6d / Financials: rent control 2%, ACS county CAGR, default 3%, PITI flat, checkbox UI.
- [ ] **Step 2:** README Financials paragraph for rent growth.
- [ ] **Step 3:** Commit only if user asked.

---

## Self-review (plan vs spec)

| Spec item | Task |
|-----------|------|
| Yearly rent growth in projection | Task 1 |
| `rent_cagr_pct` / ACS 5y B25064 | Task 1–2 |
| Persist columns + sync rules | Task 3 |
| Checkbox UI + captions + chart | Task 4 |
| AGENTS + README | Task 5 |
| PITI flat; no Gemini fingerprint change | Tasks 1 & 4 (`mortgage_data` exclusion) |
| No live Census in CI | Task 2 mocks |

No TBD placeholders. Signatures: `rent_growth_pct` on projection; `county_median_rent_cagr(lat,lng)`.
