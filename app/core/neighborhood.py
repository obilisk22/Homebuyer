"""Neighborhood name resolution helpers and outbound review deep-link builders.

v1 is deep-links only — no scraping of Reddit, City-Data, Niche, etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

# Small map of common US cities → Reddit community slug (fail soft if missing).
CITY_SUBREDDITS: dict[str, str] = {
    "los angeles": "LosAngeles",
    "la": "LosAngeles",
    "seattle": "Seattle",
    "san francisco": "sanfrancisco",
    "sf": "sanfrancisco",
    "new york": "nyc",
    "nyc": "nyc",
    "brooklyn": "brooklyn",
    "chicago": "chicago",
    "austin": "Austin",
    "denver": "denver",
    "portland": "Portland",
    "boston": "boston",
    "miami": "Miami",
    "philadelphia": "philadelphia",
    "philly": "philadelphia",
    "san diego": "sandiego",
    "phoenix": "phoenix",
    "dallas": "Dallas",
    "houston": "houston",
    "atlanta": "Atlanta",
    "washington": "washingtondc",
    "washington dc": "washingtondc",
    "dc": "washingtondc",
    "minneapolis": "Minneapolis",
    "detroit": "Detroit",
    "nashville": "nashville",
    "santa monica": "SantaMonica",
    "oakland": "oakland",
    "sacramento": "Sacramento",
    "san jose": "SanJose",
}

_US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

@dataclass(frozen=True)
class ReviewDeepLinks:
    reddit_search: str
    city_subreddit: str | None
    city_data: str | None
    niche: str | None
    google_site_reddit: str


def effective_neighborhood_name(
    *,
    neighborhood_name: str = "",
    neighborhood_override: str = "",
) -> str:
    """Prefer manual override when set."""
    override = (neighborhood_override or "").strip()
    if override:
        return override
    return (neighborhood_name or "").strip()


def slugify_city_for_subreddit(city: str) -> str | None:
    """Guess a Reddit subreddit slug from a city name (best-effort)."""
    text = (city or "").strip()
    if not text:
        return None
    key = text.casefold()
    if key in CITY_SUBREDDITS:
        return CITY_SUBREDDITS[key]
    # Drop common suffixes, then CamelCase without spaces.
    cleaned = re.sub(r"\s+(city|town|village)$", "", key, flags=re.I).strip()
    if cleaned in CITY_SUBREDDITS:
        return CITY_SUBREDDITS[cleaned]
    parts = re.findall(r"[A-Za-z0-9]+", text)
    if not parts:
        return None
    # e.g. "Santa Monica" → "SantaMonica"
    return "".join(p[:1].upper() + p[1:].lower() for p in parts)


def reddit_search_url(neighborhood: str, city: str = "") -> str:
    name = (neighborhood or "").strip()
    place = (city or "").strip()
    if name and place:
        query = f'"{name}" {place}'
    elif name:
        query = f'"{name}"'
    elif place:
        query = place
    else:
        query = "neighborhood"
    return f"https://www.reddit.com/search/?q={quote_plus(query)}"


def city_subreddit_url(city: str) -> str | None:
    slug = slugify_city_for_subreddit(city)
    if not slug:
        return None
    return f"https://www.reddit.com/r/{slug}/"


def city_data_url(city: str, state: str = "") -> str | None:
    """City-Data city page when we have enough to guess a slug."""
    place = (city or "").strip()
    st = (state or "").strip().upper()
    if not place:
        return None
    state_name = _US_STATE_NAMES.get(st, "")
    if not state_name:
        # Fail soft — City-Data city pages need "City-StateName".
        return f"https://www.city-data.com/search.html?q={quote_plus(place)}"
    slug = f"{place.replace(' ', '-')}-{state_name.replace(' ', '-')}"
    return f"https://www.city-data.com/city/{quote(slug)}.html"


def _niche_slug_part(text: str) -> str:
    """Niche-style slug segment: lowercase, spaces/punct → hyphens."""
    s = (text or "").strip().casefold()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def _state_abbr_lower(state: str) -> str | None:
    """Normalize state to a lowercase 2-letter US abbreviation, or None."""
    st = (state or "").strip()
    if not st:
        return None
    upper = st.upper()
    if upper in _US_STATE_NAMES:
        return upper.lower()
    folded = st.casefold()
    for abbr, name in _US_STATE_NAMES.items():
        if name.casefold() == folded:
            return abbr.lower()
    if len(st) == 2 and st.isalpha():
        return st.lower()
    return None


def niche_search_url(neighborhood: str, city: str = "", state: str = "") -> str:
    """Fallback Niche search when a place slug cannot be built confidently."""
    bits = [b for b in ((neighborhood or "").strip(), (city or "").strip(), (state or "").strip()) if b]
    query = " ".join(bits) or "neighborhood"
    return f"https://www.niche.com/places-to-live/search/best-places-to-live/?q={quote_plus(query)}"


def niche_place_url(neighborhood: str, city: str = "", state: str = "") -> str:
    """Niche places-to-live neighborhood URL, or search fallback if incomplete.

    Shape: ``/places-to-live/n/{neighborhood}-{city}-{state}/``
    e.g. Ocean Park + Santa Monica + CA → ``.../n/ocean-park-santa-monica-ca/``
    """
    hood = _niche_slug_part(neighborhood)
    place = _niche_slug_part(city)
    st = _state_abbr_lower(state)
    if hood and place and st:
        return f"https://www.niche.com/places-to-live/n/{hood}-{place}-{st}/"
    return niche_search_url(neighborhood, city, state)



def google_site_reddit_url(neighborhood: str, city: str = "") -> str:
    name = (neighborhood or "").strip()
    place = (city or "").strip()
    if name and place:
        query = f'site:reddit.com "{name}" {place}'
    elif name:
        query = f'site:reddit.com "{name}"'
    elif place:
        query = f"site:reddit.com {place}"
    else:
        query = "site:reddit.com neighborhood"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def build_review_deep_links(
    neighborhood: str,
    *,
    city: str = "",
    state: str = "",
) -> ReviewDeepLinks:
    return ReviewDeepLinks(
        reddit_search=reddit_search_url(neighborhood, city),
        city_subreddit=city_subreddit_url(city),
        city_data=city_data_url(city, state),
        niche=niche_place_url(neighborhood, city, state),
        google_site_reddit=google_site_reddit_url(neighborhood, city),
    )
