"""Photos-tab Gemini overall property blurb via Zillow URL context (TODO-053)."""

from __future__ import annotations

import hashlib
import os

from dotenv import load_dotenv

load_dotenv()

# Same URL-context + Search stack as Financials Gemini (2.5 Flash-Lite default).
DEFAULT_MODEL = "gemini-2.5-flash-lite"
PHOTOS_PROMPT_VERSION = "photos_v1"


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def build_photos_fingerprint(
    *,
    subject_zillow_url: str = "",
    address: str = "",
) -> str:
    """Cache key: prompt version + hash of subject Zillow URL (+ address salt)."""
    url = _normalize_url(subject_zillow_url)
    addr = (address or "").strip()
    if not url:
        return f"{PHOTOS_PROMPT_VERSION}|empty"
    digest = hashlib.sha256(f"{url}\n{addr}".encode("utf-8")).hexdigest()[:16]
    return f"{PHOTOS_PROMPT_VERSION}|{digest}"


def build_photos_prompt(*, subject_zillow_url: str, subject_label: str = "") -> str:
    subject = _normalize_url(subject_zillow_url)
    if not subject:
        raise ValueError("Subject Zillow URL is required.")
    label = (subject_label or "").strip() or "this listing"
    return (
        "You are a candid buy-side housing research analyst helping someone browse "
        "listing photos. Write a short overall take on the property — not a deal "
        "spreadsheet and not a neighborhood essay.\n\n"
        "Tools: Use the URL context tool to open the Zillow URL below. Read the "
        "listing description, beds/baths/sqft, photos captions when present, and "
        "notable pros/cons. You may use Google Search lightly for context, but "
        "prioritize the Zillow page.\n\n"
        "Hard rules:\n"
        "- Do not invent facts that are not on the page you retrieved.\n"
        "- If the URL fails to load, say so briefly.\n"
        "- Keep it to one compact paragraph (roughly 80–140 words). No markdown "
        "headers, no bullet lists, no PITI tables.\n"
        "- Cover: what kind of home it is, standout condition/layout/finish cues "
        "from the listing, and one practical watch-out if any.\n\n"
        f"Subject ({label}):\n{subject}\n\n"
        "Write the paragraph now. Research commentary only, not advice."
    )


def _call_gemini_with_web_tools(prompt: str) -> str:
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
        raise ValueError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from exc

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
            "(Zillow pages may have blocked URL fetch — try again or check the link)."
        )
    return text


def generate_photos_commentary(
    *,
    subject_zillow_url: str,
    subject_label: str = "",
) -> str:
    """Ask Gemini for a short overall property blurb from the Zillow listing URL."""
    url = _normalize_url(subject_zillow_url)
    if not url:
        raise ValueError(
            "This home needs a Zillow URL before asking Gemini about the property."
        )
    prompt = build_photos_prompt(
        subject_zillow_url=url,
        subject_label=subject_label,
    )
    return _call_gemini_with_web_tools(prompt)
