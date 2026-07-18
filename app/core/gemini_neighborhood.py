from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"

PROMPT_TEMPLATE = (
    "I am thinking of buying a home in the {neighborhood} neighborhood in {city}. "
    "Write one clear paragraph (about 120–180 words) about the area: how it feels to live there, "
    "vibe and character, and some local things to do nearby. "
    "Be practical and balanced — not salesy. Do not use bullet points or headings."
)


def build_neighborhood_prompt(*, neighborhood: str, city: str, state: str = "") -> str:
    place_city = (city or "").strip() or "the local city"
    if state and state.strip() and state.strip().upper() not in place_city.upper():
        place_city = f"{place_city}, {state.strip().upper()}"
    return PROMPT_TEMPLATE.format(
        neighborhood=(neighborhood or "").strip() or "this",
        city=place_city,
    )


def generate_neighborhood_overview(
    *,
    neighborhood: str,
    city: str,
    state: str = "",
) -> str:
    """Call Gemini and return a single overview paragraph."""
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the app."
        )

    name = (neighborhood or "").strip()
    if not name:
        raise ValueError("Neighborhood name is required before asking Gemini.")

    model = (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    prompt = build_neighborhood_prompt(neighborhood=name, city=city, state=state)

    try:
        from google import genai
    except ImportError as exc:
        raise ValueError("google-genai is not installed. Run: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text
