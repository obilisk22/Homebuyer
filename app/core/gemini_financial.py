from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Sequence

from dotenv import load_dotenv

load_dotenv()

# Financials uses URL context + Google Search. On the free tier those tools are
# more reliably available on 2.5 Flash-Lite than on Gemini 3.x (Search grounding
# is paid-only for 3.1 Flash-Lite). Override with GEMINI_FINANCIAL_MODEL or GEMINI_MODEL.
DEFAULT_MODEL = "gemini-2.5-flash-lite"
# fin_v4: Zillow URL context only — Gemini fetches listings; no app calculator dump
FINANCIAL_PROMPT_VERSION = "fin_v4"


@dataclass(frozen=True)
class ZillowListingRef:
    """A library home identified by its Zillow URL (Gemini fetches the page)."""

    property_id: int
    zillow_url: str
    label: str = ""  # short address for human orientation only


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def zillow_urls_digest(
    subject_url: str,
    peers: Sequence[ZillowListingRef] = (),
) -> str:
    """Stable fingerprint from Zillow URLs only."""
    urls = [_normalize_url(subject_url)]
    for p in sorted(peers, key=lambda x: x.property_id):
        u = _normalize_url(p.zillow_url)
        if u:
            urls.append(u)
    joined = "\n".join(u for u in urls if u)
    if not joined:
        return "empty"
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def build_financial_fingerprint(
    *,
    subject_zillow_url: str = "",
    peer_refs: Sequence[ZillowListingRef] = (),
    # Legacy kwargs ignored (kept so old call sites fail loudly if mis-used)
    **_ignored: object,
) -> str:
    """Cache key: prompt version + hash of subject + peer Zillow URLs."""
    digest = zillow_urls_digest(subject_zillow_url, peer_refs)
    return f"{FINANCIAL_PROMPT_VERSION}|{digest}"


def build_financial_prompt(
    *,
    subject_zillow_url: str,
    subject_label: str = "",
    peer_refs: Sequence[ZillowListingRef] = (),
) -> str:
    """Prompt that points Gemini at Zillow URLs — no app-sourced numbers."""
    subject = _normalize_url(subject_zillow_url)
    if not subject:
        raise ValueError("Subject Zillow URL is required.")

    label = (subject_label or "").strip() or "subject listing"
    peer_lines: list[str] = []
    for p in peer_refs:
        url = _normalize_url(p.zillow_url)
        if not url:
            continue
        name = (p.label or "").strip() or f"library home #{p.property_id}"
        peer_lines.append(f"- {name}: {url}")

    if peer_lines:
        peers_block = (
            "Other Zillow listings this buyer is also researching "
            "(open each URL with the URL context tool):\n"
            + "\n".join(peer_lines)
        )
    else:
        peers_block = (
            "Other library Zillow listings: (none — research the subject listing "
            "and its area only)."
        )

    return (
        "You are a candid buy-side housing research analyst. The buyer already has "
        "their own mortgage calculator in another app — do NOT invent or dump a full "
        "PITI spreadsheet. Your job is interpretation from live Zillow pages.\n\n"
        "Tools: Use the URL context tool to open every Zillow URL listed below. "
        "Read asking price, Zestimate, rent Zestimate, tax history, HOA, beds/baths/"
        "sqft, neighborhood, and any market/price-history signals on those pages. "
        "You may also use Google Search for broader market context for that city/"
        "neighborhood, but prioritize the Zillow listing pages.\n\n"
        "Hard rules:\n"
        "- Do not invent listing facts that are not on the pages you retrieved.\n"
        "- If a Zillow URL fails to load, say so and work from what you could fetch.\n"
        "- Avoid absolute \"too expensive / unaffordable\" in a vacuum; stay relative "
        "to the peer Zillow listings and the local market.\n"
        "- Do not restate every number as a table — explain meaning and tradeoffs.\n\n"
        f"Subject listing ({label}):\n{subject}\n\n"
        f"{peers_block}\n\n"
        "Write markdown with exactly three sections:\n\n"
        "## Why the numbers look like this\n"
        "Explain what drives price / $/sqft / HOA / tax / rent signals on the subject "
        "Zillow page versus the peer Zillow listings (size, type, location, history).\n\n"
        "## Market & location take\n"
        "What the market and neighborhood appear to imply for this buy, grounded in "
        "the Zillow pages (and light search if needed). No fake comps outside those URLs.\n\n"
        "## Buy vs rent\n"
        "Using Zillow rent Zestimate / price history when present on the pages, argue "
        "when buying may beat renting (or not) for a typical buyer of this home — "
        "horizon, cash drag, appreciation risk, lifestyle. Be practical, not salesy.\n\n"
        "This is research commentary only, not financial advice."
    )


def _call_gemini_with_web_tools(prompt: str) -> str:
    """Gemini generateContent with URL context (+ Google Search) enabled."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the app."
        )

    model = (
        (os.getenv("GEMINI_FINANCIAL_MODEL") or "").strip()
        or (os.getenv("GEMINI_MODEL") or "").strip()
        or DEFAULT_MODEL
    )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ValueError("google-genai is not installed. Run: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    tools = [
        types.Tool(url_context=types.UrlContext()),
        types.Tool(google_search=types.GoogleSearch()),
    ]
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=tools),
    )
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ValueError(
            "Gemini returned an empty response "
            "(Zillow pages may have blocked URL fetch — try again or check the links)."
        )
    return text


def generate_financial_commentary(
    *,
    subject_zillow_url: str,
    subject_label: str = "",
    peer_refs: Sequence[ZillowListingRef] = (),
) -> str:
    """Ask Gemini to research Zillow URLs and return opinion markdown."""
    url = _normalize_url(subject_zillow_url)
    if not url:
        raise ValueError("This home needs a Zillow URL before asking Gemini about finances.")

    prompt = build_financial_prompt(
        subject_zillow_url=url,
        subject_label=subject_label,
        peer_refs=peer_refs,
    )
    return _call_gemini_with_web_tools(prompt)


# --- Back-compat aliases (older imports / tests migrating) ---
LibraryCompSnapshot = ZillowListingRef  # type: ignore[misc,assignment]


def library_comps_digest(comps: Sequence[ZillowListingRef]) -> str:
    """Deprecated name — digest peers only (no subject). Prefer zillow_urls_digest."""
    return zillow_urls_digest("", comps)


def format_buy_vs_rent_notes(*_a: object, **_k: object) -> str:
    """Deprecated — buy-vs-rent now comes from Zillow rent Zestimate via URL context."""
    return ""
