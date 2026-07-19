"""SchoolDigger enrichment (stars + parent reviews) for assigned schools."""

from __future__ import annotations

import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

from app.core.overlay_cache import cache_key, read_json, write_json

load_dotenv()

REQUEST_TIMEOUT_S = 20
CACHE_NS = "schooldigger"
CACHE_REV = "v1"
CACHE_MAX_AGE_S = 7 * 24 * 3600

API_BASE = "https://api.schooldigger.com/v2.4"

LEVEL_TO_QUERY: dict[str, str] = {
    "elementary": "Elementary",
    "middle": "Middle",
    "high": "High",
}

QUOTE_MAX_CHARS = 160


def has_schooldigger_keys() -> bool:
    app_id = (os.environ.get("SCHOOLDIGGER_APP_ID") or "").strip()
    app_key = (os.environ.get("SCHOOLDIGGER_APP_KEY") or "").strip()
    return bool(app_id and app_key)


def _normalize_name(name: str) -> str:
    normalized = (name or "").strip().casefold()
    normalized = re.sub(r"\bschool\b", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalized.strip()


def pick_search_match(
    school_list: list[dict[str, Any]], *, name: str, city: str = ""
) -> dict[str, Any] | None:
    """Pick the best SchoolDigger search hit: name match first, then city match."""
    if not school_list:
        return None

    target = _normalize_name(name)
    name_matches = [
        s
        for s in school_list
        if _normalize_name(s.get("schoolName") or s.get("name") or "") == target
    ]
    pool = name_matches or list(school_list)

    city_norm = (city or "").strip().casefold()
    if city_norm:
        city_matches = [
            s
            for s in pool
            if ((s.get("address") or {}).get("city") or "").strip().casefold()
            == city_norm
        ]
        if city_matches:
            pool = city_matches

    return pool[0] if pool else None


def _truncate_quote(text: str | None, limit: int = QUOTE_MAX_CHARS) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def normalize_enrichment(detail: dict[str, Any]) -> dict[str, Any]:
    """Map a SchoolDigger school-detail payload onto our enrichment fields."""
    rank_history = detail.get("rankHistory") or []
    latest_rank = rank_history[0] if rank_history else {}
    rating_stars = latest_rank.get("rankStars")
    rating_year = latest_rank.get("year")

    reviews = detail.get("reviews") or []
    parent_reviews = [
        r for r in reviews if (r.get("submittedBy") or "").strip().casefold() == "parent"
    ]
    chosen_reviews = parent_reviews or reviews

    stars = [
        r.get("numberOfStars")
        for r in chosen_reviews
        if isinstance(r.get("numberOfStars"), (int, float))
    ]
    review_avg = round(sum(stars) / len(stars), 2) if stars else None
    review_count = len(chosen_reviews)
    review_quote = _truncate_quote(chosen_reviews[0].get("comment")) if chosen_reviews else None

    return {
        "rating_stars": rating_stars,
        "rating_year": rating_year,
        "review_avg": review_avg,
        "review_count": review_count,
        "review_quote": review_quote,
        "schooldigger_url": detail.get("url") or detail.get("urlSchoolDigger"),
        "schooldigger_id": detail.get("schoolid"),
    }


def _search_schooldigger(
    name: str, level: str, app_id: str, app_key: str
) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{API_BASE}/schools",
        params={
            "st": "CA",
            "q": name,
            "qSearchSchoolNameOnly": "true",
            "level": level,
            "appID": app_id,
            "appKey": app_key,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("schoolList") or []


def _fetch_school_detail(schoolid: str, app_id: str, app_key: str) -> dict[str, Any]:
    resp = requests.get(
        f"{API_BASE}/schools/{schoolid}",
        params={"appID": app_id, "appKey": app_key},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def enrich_school(school: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``school`` merged with SchoolDigger rating/review fields.

    Best-effort: any missing keys, lookup failure, or no-match leaves the
    school unchanged (never raises).
    """
    out = dict(school)
    if not has_schooldigger_keys():
        return out

    name = (school.get("name") or "").strip()
    api_level = LEVEL_TO_QUERY.get((school.get("level") or "").strip().lower())
    if not name or not api_level:
        return out

    app_id = (os.environ.get("SCHOOLDIGGER_APP_ID") or "").strip()
    app_key = (os.environ.get("SCHOOLDIGGER_APP_KEY") or "").strip()
    cache_id = school.get("cds_code") or _normalize_name(name)
    key = cache_key(CACHE_REV, str(cache_id), api_level)

    cached = read_json(CACHE_NS, key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict):
        out.update(cached)
        return out

    try:
        search_results = _search_schooldigger(name, api_level, app_id, app_key)
        match = pick_search_match(search_results, name=name, city=school.get("city") or "")
        if not match:
            return out
        schoolid = match.get("schoolid")
        detail = _fetch_school_detail(schoolid, app_id, app_key) if schoolid else match
        enrichment = normalize_enrichment(detail)
    except Exception:  # noqa: BLE001 - best-effort enrichment, never raise
        return out

    write_json(CACHE_NS, key, enrichment)
    out.update(enrichment)
    return out


def enrich_assigned(result: dict[str, Any]) -> dict[str, Any]:
    """Enrich each non-None school level in a Task 2 ``resolve_assigned`` result."""
    out = dict(result)
    schools = result.get("schools") or {}
    out["schools"] = {
        level: (enrich_school(school) if school else school)
        for level, school in schools.items()
    }
    return out
