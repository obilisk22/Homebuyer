# Buy vs Rent + Invest Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Financials Plotly chart comparing buy net worth (appreciating home, sell @ 6%) vs rent + invest leftover at 10%, using blended FHFA ZIP + Zillow decade appreciation and rentZestimate prefill.

**Architecture:** Pure projection math in `finance.py`; FHFA ZIP5 HPI download/cache in `fhfa_hpi.py`; Zillow rent + decade % via `zillow_listing`; sync onto new `FinancialAssumptions` columns in `property_service`; dual-line chart + rent/appreciation inputs in `financial.py`.

**Tech Stack:** Python 3.12, NiceGUI, Plotly, SQLAlchemy/SQLite, `requests` + `openpyxl` (FHFA XLSX), existing `curl_cffi` Zillow fetch, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-buy-vs-rent-chart-design.md`

## Global Constraints

- Windows: run tests with `.\.venv\Scripts\pytest.exe` (not bare `pytest`).
- Do not touch loan-term fields on listing sync (down/rate/term/closing).
- Invest return fixed **10%**; selling cost fixed **6%** (captioned, not editable).
- Default appreciation **3%** when both FHFA and Zillow missing; source `Default`.
- No live FHFA/Zillow network in CI — fixtures and mocks only.
- Chart cyan = buy, magenta = rent+invest; reuse `_CHART` / `_chart_layout`.
- After user-facing work: update `AGENTS.md` + `README.md` in the same turn as the docs task.
- Do not commit unless the user asks (plan commit steps are optional checkpoints).

## File structure

| File | Responsibility |
|------|----------------|
| `app/core/finance.py` | `blend_appreciation_rates`, `BuyVsRentYear`, `buy_vs_rent_projection` |
| `app/core/fhfa_hpi.py` | Download/cache ZIP5 HPI; CAGR for a ZIP |
| `app/core/zillow_listing.py` | Extract `rent_zestimate`, `appreciation_decade_pct` |
| `app/core/models.py` + `db.py` | New financial columns + migrate |
| `app/core/property_service.py` | Sync rent/appreciation on listing refresh |
| `app/modules/financial.py` | Rent + appreciation inputs; new Plotly chart |
| `tests/test_buy_vs_rent.py` | Math + blend + FHFA CAGR unit tests |
| `tests/test_listing_filters.py` | Rent/appreciation extract fixtures |
| `requirements.txt` | Add `openpyxl` |
| `AGENTS.md`, `README.md` | Continuity / user docs |

---

### Task 1: Projection math + blend helper

**Files:**
- Modify: `app/core/finance.py`
- Create: `tests/test_buy_vs_rent.py`

**Interfaces:**
- Produces:
  - `blend_appreciation_rates(fhfa_pct: float | None, zillow_pct: float | None, *, default: float = 3.0) -> tuple[float, str]`
  - `@dataclass(frozen=True) class BuyVsRentYear: year: int; buy_net_worth: float; rent_invest_net_worth: float; home_value: float; loan_balance: float`
  - `buy_vs_rent_projection(*, summary: MortgageSummary, appreciation_pct: float, monthly_rent: float, invest_return_pct: float = 10.0, selling_cost_pct: float = 6.0) -> list[BuyVsRentYear]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_buy_vs_rent.py`:

```python
from app.core.finance import (
    blend_appreciation_rates,
    buy_vs_rent_projection,
    summarize,
)


def test_blend_both_sources():
    rate, src = blend_appreciation_rates(4.0, 6.0)
    assert rate == 5.0
    assert src == "FHFA+Zillow"


def test_blend_fhfa_only():
    rate, src = blend_appreciation_rates(4.0, None)
    assert rate == 4.0
    assert src == "FHFA"


def test_blend_zillow_only():
    rate, src = blend_appreciation_rates(None, 6.0)
    assert rate == 6.0
    assert src == "Zillow"


def test_blend_default():
    rate, src = blend_appreciation_rates(None, None)
    assert rate == 3.0
    assert src == "Default"


def test_buy_vs_rent_year_zero():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=summary.monthly_total,
        invest_return_pct=10.0,
        selling_cost_pct=6.0,
    )
    assert rows[0].year == 0
    # Buy: 500k - 400k - 6%*500k = 70_000
    assert abs(rows[0].buy_net_worth - 70_000) < 1.0
    # Rent portfolio starts at cash_to_close = 100_000
    assert abs(rows[0].rent_invest_net_worth - 100_000) < 1.0
    assert len(rows) == 31  # years 0..30


def test_buy_vs_rent_invests_surplus_when_rent_below_piti():
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
    # Zero rate → P&I = 400_000 / 360; rent half of that → positive monthly invest
    rent = summary.monthly_total / 2.0
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=rent,
        invest_return_pct=0.0,  # isolate contribution sum
        selling_cost_pct=6.0,
    )
    # After 12 months with 0% return: start 100k + 12 * (piti - rent)
    expected = 100_000 + 12 * (summary.monthly_total - rent)
    assert abs(rows[1].rent_invest_net_worth - expected) < 1.0


def test_buy_vs_rent_no_negative_contribution():
    summary = summarize(
        list_price=500_000,
        offer_price=500_000,
        down_payment_pct=20,
        interest_rate_pct=6.0,
        loan_term_years=30,
        annual_property_tax=0,
        annual_insurance=0,
        monthly_hoa=0,
        closing_cost_pct=0,
    )
    rows = buy_vs_rent_projection(
        summary=summary,
        appreciation_pct=0.0,
        monthly_rent=summary.monthly_total + 5_000,
        invest_return_pct=0.0,
        selling_cost_pct=6.0,
    )
    # Portfolio stays at cash_to_close when rent > PITI and 0% return
    assert abs(rows[5].rent_invest_net_worth - 100_000) < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py -v`

Expected: FAIL with `ImportError` / not defined.

- [ ] **Step 3: Implement math in `app/core/finance.py`**

Append (keep existing helpers unchanged):

```python
@dataclass(frozen=True)
class BuyVsRentYear:
    year: int
    buy_net_worth: float
    rent_invest_net_worth: float
    home_value: float
    loan_balance: float


def blend_appreciation_rates(
    fhfa_pct: float | None,
    zillow_pct: float | None,
    *,
    default: float = 3.0,
) -> tuple[float, str]:
    rates: list[float] = []
    if fhfa_pct is not None:
        rates.append(float(fhfa_pct))
    if zillow_pct is not None:
        rates.append(float(zillow_pct))
    if not rates:
        return float(default), "Default"
    blended = sum(rates) / len(rates)
    if fhfa_pct is not None and zillow_pct is not None:
        return blended, "FHFA+Zillow"
    if fhfa_pct is not None:
        return blended, "FHFA"
    return blended, "Zillow"


def buy_vs_rent_projection(
    *,
    summary: MortgageSummary,
    appreciation_pct: float,
    monthly_rent: float,
    invest_return_pct: float = 10.0,
    selling_cost_pct: float = 6.0,
) -> list[BuyVsRentYear]:
    # Infer horizon from amortization length (cash / empty schedule → year 0 only)
    term_years = max(len(summary.schedule) // 12, 0)

    price0 = float(summary.effective_price)
    loan0 = float(summary.loan_amount)
    sell = float(selling_cost_pct) / 100.0
    appr = float(appreciation_pct) / 100.0
    r_month = (float(invest_return_pct) / 100.0) / 12.0
    piti = float(summary.monthly_total)
    rent = float(monthly_rent or 0)
    contrib = max(0.0, piti - rent)

    # Balance lookup by month (1-indexed in schedule)
    bal_by_month = {int(row["month"]): float(row["balance"]) for row in summary.schedule}

    portfolio = float(summary.cash_to_close)
    rows: list[BuyVsRentYear] = []

    for year in range(0, term_years + 1):
        home = price0 * ((1.0 + appr) ** year)
        if year == 0:
            bal = loan0
        else:
            bal = bal_by_month.get(year * 12, 0.0)
        buy_nw = home - bal - sell * home
        rows.append(
            BuyVsRentYear(
                year=year,
                buy_net_worth=round(buy_nw, 2),
                rent_invest_net_worth=round(portfolio, 2),
                home_value=round(home, 2),
                loan_balance=round(bal, 2),
            )
        )
        if year == term_years:
            break
        # Advance 12 months of rent-path contributions + compounding
        for _ in range(12):
            portfolio = portfolio * (1.0 + r_month) + contrib

    return rows
```

Notes for implementer:
- Year 0 rent NW is cash-to-close **before** month-1 contribution (matches spec).
- Year `t` rent NW is portfolio **after** `12*t` months of contrib+compound.
- If `schedule` empty and `loan_amount == 0` (cash deal), use `loan_term_years` is not on `MortgageSummary` — derive from `len(schedule)//12` or if schedule empty treat term as 0 and return only year 0. For cash purchases, `summarize` still builds a schedule when loan>0; when loan is 0, schedule is empty — return `[year 0]` only, or optionally accept `horizon_years` later. For v1: if `term_years == 0`, still emit year 0 only (cash / no loan). Tests above use 30-year loans.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py -v`

Expected: PASS

- [ ] **Step 5: Commit (only if user asked)**

```bash
git add app/core/finance.py tests/test_buy_vs_rent.py
git commit -m "feat: add buy vs rent net-worth projection math"
```

---

### Task 2: FHFA ZIP CAGR helper

**Files:**
- Create: `app/core/fhfa_hpi.py`
- Modify: `requirements.txt` (add `openpyxl`)
- Modify: `tests/test_buy_vs_rent.py` (append FHFA tests)

**Interfaces:**
- Consumes: `requests`, `openpyxl`, `app.core.overlay_cache.cache_dir` pattern (or local `data/cache/fhfa/`)
- Produces:
  - `cagr_from_index_series(points: list[tuple[int, float]], *, span_years: int = 10) -> float | None`
  - `zip5_cagr(zip_code: str, *, span_years: int = 10) -> float | None` (loads cached workbook; `None` on miss/error)
  - Constants: `FHFA_ZIP5_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx"`, `CACHE_TTL_S = 30 * 24 * 3600`

- [ ] **Step 1: Add openpyxl**

Append to `requirements.txt`:

```
openpyxl==3.1.5
```

Run: `.\.venv\Scripts\pip.exe install openpyxl==3.1.5`

- [ ] **Step 2: Write failing CAGR unit tests**

Append to `tests/test_buy_vs_rent.py`:

```python
from app.core.fhfa_hpi import cagr_from_index_series


def test_cagr_from_index_series_decade():
    # index doubles over 10 years → CAGR = 2**(1/10) - 1 ≈ 7.177%
    points = [(2014, 100.0), (2024, 200.0)]
    rate = cagr_from_index_series(points, span_years=10)
    assert rate is not None
    assert abs(rate - (((200 / 100) ** (1 / 10) - 1) * 100)) < 0.01


def test_cagr_insufficient_history():
    assert cagr_from_index_series([(2024, 100.0)], span_years=10) is None
```

- [ ] **Step 3: Run to verify fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py::test_cagr_from_index_series_decade -v`

Expected: FAIL import / not defined.

- [ ] **Step 4: Implement `app/core/fhfa_hpi.py`**

```python
"""FHFA ZIP5 annual HPI download + decade CAGR."""

from __future__ import annotations

import time
from pathlib import Path

import requests
from openpyxl import load_workbook

from app.core.overlay_cache import cache_dir

FHFA_ZIP5_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx"
CACHE_TTL_S = 30 * 24 * 3600
REQUEST_TIMEOUT_S = 60
_NAMESPACE = "fhfa"


def cagr_from_index_series(
    points: list[tuple[int, float]], *, span_years: int = 10
) -> float | None:
    if not points or span_years <= 0:
        return None
    by_year = {int(y): float(idx) for y, idx in points if idx and float(idx) > 0}
    if not by_year:
        return None
    end_year = max(by_year)
    start_year = end_year - span_years
    if start_year not in by_year or end_year not in by_year:
        # nearest available start within +2 years if exact miss
        candidates = [y for y in by_year if y <= start_year]
        if not candidates:
            return None
        start_year = max(candidates)
        actual_span = end_year - start_year
        if actual_span <= 0:
            return None
    else:
        actual_span = span_years
    start_idx = by_year[start_year]
    end_idx = by_year[end_year]
    if start_idx <= 0 or end_idx <= 0:
        return None
    return ((end_idx / start_idx) ** (1.0 / actual_span) - 1.0) * 100.0


def _cached_xlsx_path() -> Path:
    return cache_dir(_NAMESPACE) / "hpi_at_zip5.xlsx"


def ensure_zip5_workbook() -> Path | None:
    path = _cached_xlsx_path()
    if path.is_file():
        age = time.time() - path.stat().st_mtime
        if age <= CACHE_TTL_S:
            return path
    try:
        resp = requests.get(FHFA_ZIP5_URL, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return path
    except (OSError, requests.RequestException):
        return path if path.is_file() else None


def _load_zip_series(zip_code: str) -> list[tuple[int, float]]:
    path = ensure_zip5_workbook()
    if path is None:
        return []
    zip5 = "".join(c for c in str(zip_code) if c.isdigit())[:5]
    if len(zip5) < 5:
        return []
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return []
        # Normalize header names
        cols = {str(h).strip().lower(): i for i, h in enumerate(header) if h is not None}
        # FHFA columns vary; accept common labels
        zip_i = next((cols[k] for k in cols if "zip" in k), None)
        year_i = next((cols[k] for k in cols if k == "year" or "year" in k), None)
        # Prefer index / hpi level column over annual % change
        idx_i = next(
            (
                cols[k]
                for k in cols
                if k in ("index", "hpi", "annual house price index")
                or (k.startswith("index") or k == "hpi")
            ),
            None,
        )
        if zip_i is None or year_i is None or idx_i is None:
            return []
        out: list[tuple[int, float]] = []
        for row in rows:
            if not row or row[zip_i] is None:
                continue
            z = "".join(c for c in str(row[zip_i]) if c.isdigit())
            if z != zip5 and z.zfill(5) != zip5:
                continue
            try:
                year = int(row[year_i])
                idx = float(row[idx_i])
            except (TypeError, ValueError):
                continue
            out.append((year, idx))
        return out
    finally:
        wb.close()


def zip5_cagr(zip_code: str, *, span_years: int = 10) -> float | None:
    try:
        return cagr_from_index_series(_load_zip_series(zip_code), span_years=span_years)
    except Exception:
        return None
```

Implementer note: After first real download (manual smoke, not CI), inspect header row and adjust column matching if needed. Unit tests only cover `cagr_from_index_series`.

- [ ] **Step 5: Run unit tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_buy_vs_rent.py -v`

Expected: PASS

- [ ] **Step 6: Commit (only if user asked)**

```bash
git add app/core/fhfa_hpi.py requirements.txt tests/test_buy_vs_rent.py
git commit -m "feat: FHFA ZIP5 HPI decade CAGR helper"
```

---

### Task 3: Zillow rentZestimate + decade appreciation extract

**Files:**
- Modify: `app/core/zillow_listing.py`
- Modify: `tests/test_listing_filters.py`

**Interfaces:**
- Produces on `ListingDetails`: `rent_zestimate: float | None = None`, `appreciation_decade_pct: float | None = None`
- Update `any_present()` to include both

- [ ] **Step 1: Probe one real listing blob (manual, once)**

Using an existing cached file under `data/_zillow_*.json` / HTML or a fresh fetch, search for `rentZestimate`, `rent_zestimate`, and decade / 10-year appreciation strings. Record the winning JSON keys or regex in the test fixtures below. Prefer structured JSON keys over UI copy.

If decade appreciation is only available as a 1-year or 5-year rate on the page, **do not invent a decade rate** — leave `appreciation_decade_pct = None` unless a ~10y figure (or explicit annualized 10y) is present. Document the chosen key in a one-line comment above the extractor.

- [ ] **Step 2: Write failing extract tests**

Append fixtures to `tests/test_listing_filters.py` (replace KEY/VALUE with whatever probe found):

```python
SAMPLE_RENT_ZESTIMATE = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"property\":{\"zpid\":1,\"rentZestimate\":4200}}"}}}}
</script>
"""

SAMPLE_APPRECIATION_DECADE = r"""
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"componentProps":{"gdpClientCache":"{\"property\":{\"zpid\":1,\"annualHomeValueAppreciation\":3.5}}"}}}}
</script>
"""


def test_extract_rent_zestimate():
    details = extract_listing_details(SAMPLE_RENT_ZESTIMATE)
    assert details.rent_zestimate == 4200.0


def test_extract_appreciation_decade_pct():
    details = extract_listing_details(SAMPLE_APPRECIATION_DECADE)
    assert details.appreciation_decade_pct == 3.5
```

Adjust fixture field names to match the probe in Step 1 — tests must reflect real keys.

- [ ] **Step 3: Run to verify fail**

Run: `.\.venv\Scripts\pytest.exe tests/test_listing_filters.py::test_extract_rent_zestimate tests/test_listing_filters.py::test_extract_appreciation_decade_pct -v`

Expected: FAIL (attribute missing / None).

- [ ] **Step 4: Extend `ListingDetails` + extractors**

In `zillow_listing.py`:

1. Add fields to `ListingDetails`.
2. Extend `any_present()`.
3. When walking property JSON (same path as tax/price), read `rentZestimate` / `rent_zestimate`.
4. Read the probed appreciation key; store as annual % (if Zillow gives a 10-year total change instead of annualized, convert: `((1 + total/100) ** (1/10) - 1) * 100` and comment that conversion).
5. Also add regex fallbacks on HTML if JSON path is flaky (follow existing listing regex style).

- [ ] **Step 5: Run listing tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_listing_filters.py -v`

Expected: PASS

- [ ] **Step 6: Commit (only if user asked)**

```bash
git add app/core/zillow_listing.py tests/test_listing_filters.py
git commit -m "feat: scrape Zillow rentZestimate and decade appreciation"
```

---

### Task 4: Models, migrate, listing sync

**Files:**
- Modify: `app/core/models.py` (`FinancialAssumptions`)
- Modify: `app/core/db.py` (`_migrate_sqlite`)
- Modify: `app/core/property_service.py` (`_sync_financial_from_listing`, `update_financial`)

**Interfaces:**
- New columns per spec: `monthly_rent`, `rent_source`, `appreciation_pct`, `appreciation_source`, `appreciation_fhfa_pct`, `appreciation_zillow_pct`
- Sync calls `zip5_cagr(prop.zip_code)` and `blend_appreciation_rates`

- [ ] **Step 1: Add model columns**

On `FinancialAssumptions` in `models.py`:

```python
monthly_rent: Mapped[float] = mapped_column(Float, default=0.0)
rent_source: Mapped[str] = mapped_column(String(64), default="")
appreciation_pct: Mapped[float] = mapped_column(Float, default=3.0)
appreciation_source: Mapped[str] = mapped_column(String(64), default="")
appreciation_fhfa_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
appreciation_zillow_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Migrate in `_migrate_sqlite`**

Inside the `if fin_cols:` block in `db.py`, add ALTERs matching other financial columns:

```python
if "monthly_rent" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN monthly_rent FLOAT NOT NULL DEFAULT 0"
    )
if "rent_source" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN rent_source VARCHAR(64) NOT NULL DEFAULT ''"
    )
if "appreciation_pct" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN appreciation_pct FLOAT NOT NULL DEFAULT 3"
    )
if "appreciation_source" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN appreciation_source VARCHAR(64) NOT NULL DEFAULT ''"
    )
if "appreciation_fhfa_pct" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN appreciation_fhfa_pct FLOAT"
    )
if "appreciation_zillow_pct" not in fin_cols:
    conn.exec_driver_sql(
        "ALTER TABLE financial_assumptions ADD COLUMN appreciation_zillow_pct FLOAT"
    )
```

- [ ] **Step 3: Extend `_sync_financial_from_listing`**

After insurance sync in `property_service.py`:

```python
from app.core.finance import blend_appreciation_rates
from app.core.fhfa_hpi import zip5_cagr

# Rent
if details.rent_zestimate is not None and details.rent_zestimate > 0:
    if (fin.rent_source or "").strip() in ("", "Zillow"):
        fin.monthly_rent = float(details.rent_zestimate)
        fin.rent_source = "Zillow"

# Appreciation components
fhfa = None
try:
    z = (prop.zip_code or details.zip_code or "").strip()
    if z:
        fhfa = zip5_cagr(z)
except Exception:
    fhfa = None
if fhfa is not None:
    fin.appreciation_fhfa_pct = float(fhfa)

if details.appreciation_decade_pct is not None:
    fin.appreciation_zillow_pct = float(details.appreciation_decade_pct)

if (fin.appreciation_source or "").strip() != "Manual":
    blended, src = blend_appreciation_rates(
        fin.appreciation_fhfa_pct, fin.appreciation_zillow_pct
    )
    fin.appreciation_pct = float(blended)
    fin.appreciation_source = src
```

Wrap FHFA in try/except so listing refresh never fails hard.

- [ ] **Step 4: Extend `update_financial` for Manual sources**

Mirror tax/insurance clearing:

```python
prev_rent = float(fin.monthly_rent or 0)
prev_appr = float(fin.appreciation_pct or 0)
# ... setattr loop ...
if "monthly_rent" in fields and float(fields["monthly_rent"]) != prev_rent:
    fin.rent_source = "Manual"
if "appreciation_pct" in fields and float(fields["appreciation_pct"]) != prev_appr:
    fin.appreciation_source = "Manual"
```

Widen `**fields` type hint to allow the new floats.

- [ ] **Step 5: Smoke migrate**

Run: `.\.venv\Scripts\python.exe -c "from app.core.db import init_db; init_db(); print('ok')"`

Expected: `ok` (no exception).

- [ ] **Step 6: Commit (only if user asked)**

```bash
git add app/core/models.py app/core/db.py app/core/property_service.py
git commit -m "feat: persist rent and appreciation assumptions from listing sync"
```

---

### Task 5: Financials UI — inputs + chart

**Files:**
- Modify: `app/modules/financial.py`

**Interfaces:**
- Consumes: `buy_vs_rent_projection`, `summarize`, fin columns
- UI: section **Buy vs rent** with Monthly rent + Appreciation %; captions from sources; new Plotly dual-line after existing charts

- [ ] **Step 1: Load new values into `values` / `collect` / save**

In `render()`:
- Initialize `values["monthly_rent"]` and `values["appreciation_pct"]` from `fin`.
- Add inputs under Ownership (or new `_section("Buy vs rent", quiet=True)`):
  - `rent_in = ui.number("Comparable rent / month", ...)`
  - caption: `fin.rent_source` if set
  - `appr_in = ui.number("Appreciation", ..., format="%.2f")` suffix `%/yr`
  - caption: build from `appreciation_source` + optional `FHFA x% · Zillow y%`
- Include both in `collect()` and pass through `update_financial` on Save.
- Add both to Enter-key redraw list.

- [ ] **Step 2: Draw chart in `redraw()`**

After the cumulative principal/interest chart block, when `result.effective_price > 0`:

```python
from app.core.finance import buy_vs_rent_projection

proj = buy_vs_rent_projection(
    summary=result,
    appreciation_pct=float(appr_in.value or 0),
    monthly_rent=float(rent_in.value or 0),
)
years = [r.year for r in proj]
buy_y = [r.buy_net_worth for r in proj]
rent_y = [r.rent_invest_net_worth for r in proj]

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=years,
        y=buy_y,
        name="Buy (sell net)",
        line=dict(color=_CHART["pi"], width=2.5),
        hovertemplate="Year %{x}<br>Buy $%{y:,.0f}<extra></extra>",
    )
)
fig.add_trace(
    go.Scatter(
        x=years,
        y=rent_y,
        name="Rent + invest 10%",
        line=dict(color=_CHART["interest"], width=2.5),
        hovertemplate="Year %{x}<br>Rent+invest $%{y:,.0f}<extra></extra>",
    )
)
fig.update_layout(
    **_chart_layout(
        title=dict(
            text="Buy vs rent + invest (net worth)",
            x=0,
            xanchor="left",
            font=dict(color=_CHART["text"]),
        ),
        height=360,
        xaxis=_axis_style(title="Year", showgrid=False),
        yaxis=_axis_style(title="", tickformat="$,.0s"),
    )
)
ui.plotly(fig).classes("w-full")

# Caption
bits = [
    f"Appreciation {float(appr_in.value or 0):.2f}%/yr",
    f"source {fin.appreciation_source or '—'}",
]
if fin.appreciation_fhfa_pct is not None:
    bits.append(f"FHFA {fin.appreciation_fhfa_pct:.2f}%")
if fin.appreciation_zillow_pct is not None:
    bits.append(f"Zillow {fin.appreciation_zillow_pct:.2f}%")
bits.append("sell cost 6%")
bits.append("invest return 10%")
if float(rent_in.value or 0) <= 0:
    bits.append("set rent for a fair compare")
ui.label(" · ".join(bits)).classes("hb-page-meta")
```

Reload `fin` source captions carefully: after Save, sources may be Manual — either re-fetch property in `save()` or keep caption labels as reactive `ui.label` updated in `redraw` from local state set on save. Simplest v1: captions are static from initial `fin` load; after Save + page refresh they update. Better: store `rent_source_label` / `appr_source_label` in a dict mutated in `save()` after `update_financial` returns.

If `result.effective_price <= 0`, skip chart and show quiet empty hint.

- [ ] **Step 3: Manual UI verify**

Restart app:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Open a property → Financials: rent/appreciation fields appear; Recalculate draws fourth chart; change rent and see rent line move.

- [ ] **Step 4: Run full test suite**

Run: `.\.venv\Scripts\pytest.exe -q`

Expected: all pass.

- [ ] **Step 5: Commit (only if user asked)**

```bash
git add app/modules/financial.py
git commit -m "feat: Buy vs rent net-worth chart on Financials"
```

---

### Task 6: Docs continuity

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Update AGENTS.md**

- Add to What’s done: Buy vs rent + invest chart (FHFA ZIP + Zillow decade blend, rentZestimate).
- Add product decision bullet: appreciation = mean(FHFA ZIP10y, Zillow decade) with Manual override; rent from rentZestimate; buy NW assumes 6% sell; rent path 10% compound; fixed constants v1.
- Key files table: mention `fhfa_hpi.py`.
- FinancialAssumptions field list: new columns.
- Quick verify: Financials shows fourth chart; Refresh listing fills rent/appreciation when available.

- [ ] **Step 2: Update README.md**

In Financials section: describe the buy-vs-rent chart, rent + appreciation inputs, FHFA cache under `data/cache/fhfa/`, no extra API key.

- [ ] **Step 3: Commit (only if user asked)**

```bash
git add AGENTS.md README.md
git commit -m "docs: document Financials buy vs rent chart"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Buy NW = HV − bal − 6% HV | Task 1 |
| Rent path cash-to-close + (PITI−rent) @ 10% | Task 1 |
| Blend FHFA + Zillow; default 3% | Task 1 + 2 + 4 |
| FHFA ZIP5 cache ~30d | Task 2 |
| rentZestimate + decade % scrape | Task 3 |
| Persist columns + Manual override | Task 4 |
| UI fields + Plotly dual line + caption | Task 5 |
| AGENTS + README | Task 6 |
| No Gemini fingerprint change | (explicit non-goal; no task) |
| No live network in CI | Tasks 1–3 use fixtures |

No TBD placeholders. Signatures consistent across tasks (`buy_vs_rent_projection`, `blend_appreciation_rates`, `zip5_cagr`).
