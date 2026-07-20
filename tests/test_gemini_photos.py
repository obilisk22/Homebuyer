"""Tests for Photos-tab Gemini fingerprint / prompt (TODO-053)."""

from app.core.gemini_photos import (
    PHOTOS_PROMPT_VERSION,
    build_photos_fingerprint,
    build_photos_prompt,
)


def test_photos_fingerprint_url_based():
    a = build_photos_fingerprint(
        subject_zillow_url="https://www.zillow.com/homedetails/a_1_zpid/",
        address="123 Main St",
    )
    assert a.startswith(f"{PHOTOS_PROMPT_VERSION}|")
    b = build_photos_fingerprint(
        subject_zillow_url="https://www.zillow.com/homedetails/b_2_zpid/",
        address="123 Main St",
    )
    assert a != b
    c = build_photos_fingerprint(
        subject_zillow_url="https://www.zillow.com/homedetails/a_1_zpid/",
        address="123 Main St",
    )
    assert a == c


def test_photos_prompt_mentions_url_and_short_paragraph():
    prompt = build_photos_prompt(
        subject_zillow_url="https://www.zillow.com/homedetails/a_1_zpid/",
        subject_label="123 Main St",
    )
    assert "https://www.zillow.com/homedetails/a_1_zpid/" in prompt
    assert "123 Main St" in prompt
    assert "URL context" in prompt
    assert "paragraph" in prompt.casefold()
