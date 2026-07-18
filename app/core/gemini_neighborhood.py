from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.1-flash-lite"

PROMPT_TEMPLATE = (
    "I am seriously considering buying a home in the {neighborhood} neighborhood in {city}. "
    "Help me decide whether this is a good place to live long-term — be honest and direct, "
    "not a travel brochure or realtor pitch. Write 2 short paragraphs (about 160–220 words total).\n\n"
    "Cover what I would actually want to know after living there for years: daily quality of life; "
    "noise, traffic, parking, density; walkability and practical errands; schools/family fit if relevant; "
    "safety and street feel (with nuance, not fear-mongering); housing stock and whether costs/HOA or "
    "maintenance pressures are common; flood/heat/climate or wildfire exposure if relevant to the area; "
    "and who the neighborhood tends to suit vs who may be unhappy there. "
    "Call out real tradeoffs and downsides alongside upsides. "
    "If you are unsure about something, say so rather than inventing certainty. "
    "No bullet points, no headings, no closing pep talk."
)

THINGS_TO_DO_PROMPT_TEMPLATE = (
    "I am researching the {neighborhood} neighborhood in {city} as a possible place to live. "
    "List cool, practical things to do nearby. "
    "Prioritize places and activities within comfortable walking distance of the neighborhood "
    "(roughly under ~20 minutes on foot) first; only after those, add a few slightly farther "
    "worth-the-short-trip options and mark those as a short drive/transit. "
    "Prefer specific place names (cafes, parks, trails, markets, beaches, venues) over vague hype. "
    "Keep it practical, not salesy.\n\n"
    "Format as a markdown bullet list of 8–12 items. For each item use this pattern exactly:\n"
    "- [Place Name](https://www.google.com/maps/search/?api=1&query=URL_ENCODED_PLACE_AND_CITY) "
    "— one short clause (note if walkable). "
    "Encode spaces in the query as + or %20; include the neighborhood or city in the query "
    "so Maps finds the right place (e.g. query=Fritto+Misto+Santa+Monica+CA). "
    "No intro paragraph, no headings, no closing pitch."
)


def _place_city(city: str, state: str = "") -> str:
    place_city = (city or "").strip() or "the local city"
    if state and state.strip() and state.strip().upper() not in place_city.upper():
        place_city = f"{place_city}, {state.strip().upper()}"
    return place_city


def build_neighborhood_prompt(*, neighborhood: str, city: str, state: str = "") -> str:
    return PROMPT_TEMPLATE.format(
        neighborhood=(neighborhood or "").strip() or "this",
        city=_place_city(city, state),
    )


def build_things_to_do_prompt(*, neighborhood: str, city: str, state: str = "") -> str:
    return THINGS_TO_DO_PROMPT_TEMPLATE.format(
        neighborhood=(neighborhood or "").strip() or "this",
        city=_place_city(city, state),
    )


def _call_gemini(prompt: str) -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file and restart the app."
        )

    model = (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

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


def generate_neighborhood_overview(
    *,
    neighborhood: str,
    city: str,
    state: str = "",
) -> str:
    """Call Gemini and return a single overview paragraph."""
    name = (neighborhood or "").strip()
    if not name:
        raise ValueError("Neighborhood name is required before asking Gemini.")

    prompt = build_neighborhood_prompt(neighborhood=name, city=city, state=state)
    return _call_gemini(prompt)


def generate_things_to_do(
    *,
    neighborhood: str,
    city: str,
    state: str = "",
) -> str:
    """Call Gemini and return a practical nearby things-to-do list."""
    name = (neighborhood or "").strip()
    if not name:
        raise ValueError("Neighborhood name is required before asking Gemini.")

    prompt = build_things_to_do_prompt(neighborhood=name, city=city, state=state)
    return _call_gemini(prompt)
