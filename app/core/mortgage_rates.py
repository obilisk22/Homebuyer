"""U.S. average fixed mortgage rates (Freddie Mac PMMS) by common loan term."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import requests

from app.core.overlay_cache import read_json, write_json

PMMS_URL = "https://www.freddiemac.com/pmms"
FRED_30_URL = "https://fred.stlouisfed.org/data/MORTGAGE30US"
FRED_15_URL = "https://fred.stlouisfed.org/data/MORTGAGE15US"

CACHE_NAMESPACE = "mortgage_rates"
CACHE_KEY = "pmms_latest"
CACHE_TTL_S = 6 * 60 * 60  # refresh a few times a day; PMMS itself is weekly
REQUEST_TIMEOUT_S = 20

# Stock FinancialAssumptions default — treat as "not customized yet".
DEFAULT_INTEREST_RATE_PCT = 6.5


@dataclass(frozen=True)
class MortgageRateSnapshot:
    rate_30y: float
    rate_15y: float
    as_of: str  # YYYY-MM-DD when known, else empty

    def rate_for_term(self, term_years: int) -> float:
        years = max(int(term_years or 30), 1)
        # PMMS only publishes 15- and 30-year fixed averages; pick the closer one.
        if abs(years - 15) <= abs(years - 30):
            return self.rate_15y
        return self.rate_30y

    def product_label(self, term_years: int) -> str:
        years = max(int(term_years or 30), 1)
        if abs(years - 15) <= abs(years - 30):
            return "15-yr FRM"
        return "30-yr FRM"

    def source_caption(self, term_years: int) -> str:
        product = self.product_label(term_years)
        if self.as_of:
            return f"Freddie Mac PMMS {product} · {self.as_of}"
        return f"Freddie Mac PMMS {product}"


def _parse_pct(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0 or value >= 30:
        return None
    return round(value, 3)


def _parse_pmms_html(html: str) -> MortgageRateSnapshot | None:
    """Parse the public PMMS landing page for the latest 15/30 averages."""
    as_of = ""
    as_of_match = re.search(
        r"as of\s+(\d{1,2}/\d{1,2}/\d{4})",
        html,
        flags=re.IGNORECASE,
    )
    if as_of_match:
        try:
            as_of = datetime.strptime(as_of_match.group(1), "%m/%d/%Y").date().isoformat()
        except ValueError:
            as_of = ""

    # Prefer labeled blocks near "30-year" / "15-year" headings.
    rate_30 = None
    rate_15 = None
    m30 = re.search(
        r"30[\-\u2011\u2013\u2014]?year[^%]{0,120}?(\d+\.\d{1,3})\s*%",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    m15 = re.search(
        r"15[\-\u2011\u2013\u2014]?year[^%]{0,120}?(\d+\.\d{1,3})\s*%",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m30:
        rate_30 = _parse_pct(m30.group(1))
    if m15:
        rate_15 = _parse_pct(m15.group(1))
    if rate_30 is None or rate_15 is None:
        return None
    return MortgageRateSnapshot(rate_30y=rate_30, rate_15y=rate_15, as_of=as_of)


def _parse_fred_data_page(text: str) -> tuple[str, float] | None:
    """Last observation from FRED's plain data table page."""
    rows = re.findall(
        r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d+\.\d+)\s*\|",
        text,
    )
    if not rows:
        # Fallback: DATE VALUE lines
        rows = re.findall(r"(?m)^(\d{4}-\d{2}-\d{2})\s+(\d+\.\d+)\s*$", text)
    if not rows:
        return None
    day, raw = rows[-1]
    rate = _parse_pct(raw)
    if rate is None:
        return None
    return day, rate


def _fetch_from_pmms() -> MortgageRateSnapshot | None:
    try:
        resp = requests.get(
            PMMS_URL,
            timeout=REQUEST_TIMEOUT_S,
            headers={"User-Agent": "Homebuy/1.0 (personal research)"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return _parse_pmms_html(resp.text)


def _fetch_from_fred() -> MortgageRateSnapshot | None:
    headers = {"User-Agent": "Homebuy/1.0 (personal research)"}
    try:
        r30 = requests.get(FRED_30_URL, timeout=REQUEST_TIMEOUT_S, headers=headers)
        r15 = requests.get(FRED_15_URL, timeout=REQUEST_TIMEOUT_S, headers=headers)
        r30.raise_for_status()
        r15.raise_for_status()
    except requests.RequestException:
        return None
    p30 = _parse_fred_data_page(r30.text)
    p15 = _parse_fred_data_page(r15.text)
    if p30 is None or p15 is None:
        return None
    as_of = max(p30[0], p15[0])
    return MortgageRateSnapshot(rate_30y=p30[1], rate_15y=p15[1], as_of=as_of)


def fetch_mortgage_rates(*, force_refresh: bool = False) -> MortgageRateSnapshot | None:
    if not force_refresh:
        cached = read_json(CACHE_NAMESPACE, CACHE_KEY, max_age_s=CACHE_TTL_S)
        if isinstance(cached, dict):
            try:
                return MortgageRateSnapshot(
                    rate_30y=float(cached["rate_30y"]),
                    rate_15y=float(cached["rate_15y"]),
                    as_of=str(cached.get("as_of") or ""),
                )
            except (KeyError, TypeError, ValueError):
                pass

    snap = _fetch_from_pmms() or _fetch_from_fred()
    if snap is None:
        # Stale cache is better than nothing when the network is down.
        stale = read_json(CACHE_NAMESPACE, CACHE_KEY, max_age_s=None)
        if isinstance(stale, dict):
            try:
                return MortgageRateSnapshot(
                    rate_30y=float(stale["rate_30y"]),
                    rate_15y=float(stale["rate_15y"]),
                    as_of=str(stale.get("as_of") or ""),
                )
            except (KeyError, TypeError, ValueError):
                return None
        return None

    write_json(
        CACHE_NAMESPACE,
        CACHE_KEY,
        {
            "rate_30y": snap.rate_30y,
            "rate_15y": snap.rate_15y,
            "as_of": snap.as_of,
            "fetched": date.today().isoformat(),
        },
    )
    return snap


def resolve_interest_rate(
    term_years: int,
    *,
    force_refresh: bool = False,
) -> tuple[float | None, str]:
    snap = fetch_mortgage_rates(force_refresh=force_refresh)
    if snap is None:
        return None, ""
    return snap.rate_for_term(term_years), snap.source_caption(term_years)


def should_autofill_interest_rate(source: str | None) -> bool:
    """Autofill unless the user explicitly overrode the rate."""
    src = (source or "").strip()
    if not src:
        return True
    if src == "Manual":
        return False
    return src.startswith("Freddie Mac")
