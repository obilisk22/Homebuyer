# Financials primary inputs + down payment dollars — Design Spec

**Date:** 2026-07-18  
**Status:** Approved for implementation  
**Product:** Homebuy Financials tab

## Decisions

| Decision | Choice |
|----------|--------|
| Primary fields | Offer price + Down payment ($) only |
| Secondary | Always visible, quieter below primary |
| Down storage | Keep `down_payment_pct` in DB; UI edits dollars |
| Down vs price | Dollar amount is sticky when list/offer change; % recalculated |
| Warning | Amber icon when down &lt; 20% of effective price (PMI may apply) |

## Layout

1. Hero metrics (unchanged)
2. **Your deal** — Offer $, Down $ + amber warning if &lt;20% + muted `≈ N% of offer/list`
3. **Assumptions** (quieter) — List, Rate, Term, Closing %, Tax, Insurance, HOA (+ source captions)
4. Charts + Gemini unchanged

## Conversion

- Load: `dollars = effective_price × pct / 100`
- Save/collect: `pct = dollars / effective_price × 100` (0 if no price)
- Effective price = offer if &gt; 0 else list (same as mortgage math)
