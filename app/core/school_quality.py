"""Free CA School Dashboard quality badge + Niche parent-review deep link.

Replaces the paid SchoolDigger API with two free, no-key sources:

- **California School Dashboard** performance-level color (Blue/Green/Yellow/
  Orange/Red), looked up by 14-digit CDS code from the free CDE Academic
  Indicator downloadable data (ELA, ``All Students`` group, school-level
  rows). The national/state TXT file is large, so it is downloaded once and
  a slim ``cds -> {color, status, year}`` map is cached under
  ``data/cache/ca_dashboard/`` (~30 day TTL) — same one-time-ingest pattern
  as the Redfin ZIP median tracker (`app/core/redfin_sales.py`).
- **Niche** deep link (search only, no scrape) for parent reviews, plus a
  direct link to the school's CA Dashboard report page.

No API key of any kind is required. If the CDE file can't be downloaded or
parsed (network hiccup, layout change), `enrich_school` still returns the
Niche + Dashboard links — it just omits the color/status fields.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import quote_plus

import requests

from app.core.overlay_cache import cache_dir, read_json, write_json

REQUEST_TIMEOUT_S = 120
CACHE_NS = "ca_dashboard"
CACHE_KEY = "ela_all_students_school_v1"
CACHE_MAX_AGE_S = 30 * 24 * 3600

# CDE publishes one Academic Indicator TXT file per reporting year at a
# stable, predictable URL (confirmed against the ELPI/ELA-participation
# siblings, e.g. .../cadashboard/elpidownload2022.txt,
# .../cadashboard/elapratedownload2019.txt): {indicator}download{year}.txt.
DASHBOARD_YEAR = 2025
ELA_DASHBOARD_TXT_URL = (
    "https://www3.cde.ca.gov/researchfiles/cadashboard/"
    f"eladownload{DASHBOARD_YEAR}.txt"
)

# Performance Level Color per the CDE record layout (field "color"):
# numeric 1-5, 0 = No Color (usually small n-size / DASS-only schools).
_COLOR_NAMES: dict[str, str] = {
    "1": "Red",
    "2": "Orange",
    "3": "Yellow",
    "4": "Green",
    "5": "Blue",
    "0": "No Color",
}

# Status Level (field "statuslevel") — separate from Color; combines with
# Change in the 5x5 grid that produces Color. Shown as a secondary human
# label when present.
_STATUS_LEVEL_NAMES: dict[str, str] = {
    "1": "Very Low",
    "2": "Low",
    "3": "Medium",
    "4": "High",
    "5": "Very High",
}

_DIGITS_RE = re.compile(r"\d+")


def normalize_cds(cds: str | int | None) -> str:
    """Zero-pad to the canonical 14-digit CDS code, or ``""`` if unusable."""
    if cds is None:
        return ""
    digits = "".join(_DIGITS_RE.findall(str(cds)))
    if not digits:
        return ""
    if len(digits) > 14:
        digits = digits[-14:]
    return digits.zfill(14)


def niche_school_url(name: str, city: str = "", state: str = "CA") -> str:
    """Niche K-12 school-search deep link (no scrape) for parent reviews."""
    bits = [
        b
        for b in ((name or "").strip(), (city or "").strip(), (state or "").strip())
        if b
    ]
    query = " ".join(bits) or "school"
    return f"https://www.niche.com/k12/search/best-schools/?q={quote_plus(query)}"


def dashboard_url(cds_code: str | int | None, year: int = DASHBOARD_YEAR) -> str:
    """CA School Dashboard report-page deep link for a CDS code."""
    cds = normalize_cds(cds_code) or str(cds_code or "").strip()
    return f"https://www.caschooldashboard.org/reports/{cds}/{year}"


def _color_name(raw: str | None) -> str | None:
    return _COLOR_NAMES.get((raw or "").strip())


def _status_level_name(raw: str | None) -> str | None:
    return _STATUS_LEVEL_NAMES.get((raw or "").strip())


def parse_dashboard_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Pure parse: school-level ``All Students`` rows -> ``{cds: {color, status, year}}``.

    Keeps only ``rtype == "S"`` (school) and ``studentgroup == "ALL"`` rows,
    and only rows with a recognized ``color`` code — this is the slim map we
    cache to disk. Never raises on malformed rows; they're skipped.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        lowered = {(k or "").strip().lower(): v for k, v in row.items()}
        if (lowered.get("rtype") or "").strip().upper() != "S":
            continue
        if (lowered.get("studentgroup") or "").strip().upper() != "ALL":
            continue
        cds = normalize_cds(lowered.get("cds"))
        if not cds:
            continue
        color = _color_name(lowered.get("color"))
        if not color:
            continue
        out[cds] = {
            "color": color,
            "status": _status_level_name(lowered.get("statuslevel")),
            "year": (lowered.get("reportingyear") or "").strip() or str(DASHBOARD_YEAR),
        }
    return out


def _download_dashboard_rows() -> list[dict[str, str]]:
    """Network I/O only — kept separate so parsing stays fixture-testable."""
    resp = requests.get(ELA_DASHBOARD_TXT_URL, timeout=REQUEST_TIMEOUT_S, stream=True)
    resp.raise_for_status()
    raw = resp.content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    return list(reader)


def _ingest_dashboard_map() -> dict[str, dict[str, Any]]:
    """Download once (cached ~30d) + slim-parse the CDE ELA Academic Indicator file."""
    cached = read_json(CACHE_NS, CACHE_KEY, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and isinstance(cached.get("cds"), dict) and cached["cds"]:
        return {str(k): dict(v) for k, v in cached["cds"].items()}

    cache_dir(CACHE_NS)
    rows = _download_dashboard_rows()
    slim = parse_dashboard_rows(rows)
    if not slim:
        raise RuntimeError("CDE Academic Indicator file returned no usable rows")

    write_json(
        CACHE_NS,
        CACHE_KEY,
        {"cds": slim, "source": ELA_DASHBOARD_TXT_URL, "count": len(slim)},
    )
    return slim


def lookup_dashboard_status(cds: str | int | None) -> dict[str, Any] | None:
    """CDS -> ``{color, status, year, source}``, or ``None`` on no-match/failure.

    Fixture-friendly: the actual parsing (`parse_dashboard_rows`) is pure; this
    function owns the cached network download and never raises — a download
    or parse failure just means no color badge (Niche/Dashboard links still work).
    """
    key = normalize_cds(cds)
    if not key:
        return None
    try:
        table = _ingest_dashboard_map()
    except Exception:  # noqa: BLE001 - best-effort enrichment, never raise
        return None
    hit = table.get(key)
    if not hit:
        return None
    return {
        "color": hit.get("color"),
        "status": hit.get("status"),
        "year": hit.get("year") or str(DASHBOARD_YEAR),
        "source": "CA School Dashboard (CDE Academic Indicator, ELA · All Students)",
    }


def enrich_school(school: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``school`` merged with a Dashboard color + Niche/Dashboard links.

    Always adds ``niche_url``. Adds ``dashboard_url`` when a CDS code is
    present, and ``dashboard_color`` / ``dashboard_status`` / ``dashboard_year``
    when the CDE lookup finds a match. Never raises.
    """
    out = dict(school)
    name = (school.get("name") or "").strip()
    city = (school.get("city") or "").strip()
    out["niche_url"] = niche_school_url(name, city)

    cds = normalize_cds(school.get("cds_code"))
    if cds:
        out["dashboard_url"] = dashboard_url(cds)
        status = lookup_dashboard_status(cds)
        if status:
            out["dashboard_color"] = status.get("color")
            out["dashboard_status"] = status.get("status")
            out["dashboard_year"] = status.get("year")
    return out


def enrich_assigned(result: dict[str, Any]) -> dict[str, Any]:
    """Enrich each non-None school level in a ``resolve_assigned()`` result.

    Always enriches (no API-key gate) — Niche + Dashboard links never need
    network access or a key; only the color badge depends on the cached CDE
    download succeeding.
    """
    out = dict(result)
    schools = result.get("schools") or {}
    out["schools"] = {
        level: (enrich_school(school) if school else school)
        for level, school in schools.items()
    }
    return out


def has_quality_data() -> bool:
    """Always True — this feature needs no API keys."""
    return True
