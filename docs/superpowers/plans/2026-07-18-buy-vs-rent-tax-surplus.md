# Buy vs rent tax + two-way surplus — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or implement directly with TDD).  
> **Goal:** Shared $13k budget surplus on buy and rent paths; mortgage interest + property-tax shield; primary-residence CG tax on buy liquidation.

**Spec:** `docs/superpowers/specs/2026-07-18-buy-vs-rent-tax-surplus-design.md`

## Files

| File | Role |
|------|------|
| `app/core/finance.py` | Rewrite `buy_vs_rent_projection`; helpers for interest-by-year, CG tax |
| `app/core/models.py` / `db.py` | New assumption columns + migrate |
| `app/modules/financial.py` | UI fields + wire kwargs |
| `app/core/property_service.py` | `update_financial` / collect fields if needed |
| `tests/test_buy_vs_rent.py` | TDD coverage |
| `AGENTS.md` / `README.md` | Continuity |

## Tasks

### Task 1: Projection math (TDD)

1. Add failing tests for two-way surplus, tax shield, CG exclusion/tax, buy portfolio in NW.
2. Implement `buy_vs_rent_projection` per spec (new kwargs with defaults).
3. Keep old tests green (update expectations where one-way surplus behavior changed).

### Task 2: Persist + UI

1. Model columns + SQLite migrate.
2. Financials Buy vs rent inputs; save/collect/redraw.
3. Chart caption update.

### Task 3: Docs + full pytest

1. AGENTS.md / README.md decision text.
2. `pytest -q` green.
