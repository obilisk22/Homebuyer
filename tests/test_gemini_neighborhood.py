from pathlib import Path

from app.core.gemini_neighborhood import (
    OVERVIEW_CACHE_PREFIX,
    THINGS_CACHE_PREFIX,
    build_neighborhood_prompt,
    build_overview_cache_key,
    build_things_to_do_cache_key,
    build_things_to_do_prompt,
)

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_ADDRESS = "1234 Ocean Park Blvd, Santa Monica, CA 90405"


def test_prompt_includes_address_neighborhood_and_city():
    prompt = build_neighborhood_prompt(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    assert SAMPLE_ADDRESS in prompt
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    lower = prompt.lower()
    assert "buying" in lower and "home" in lower
    assert "long-term" in lower or "long term" in lower
    assert "honest" in lower or "direct" in lower
    assert "tradeoff" in lower or "downside" in lower
    assert "address" in lower or "block" in lower


def test_prompt_works_without_state():
    prompt = build_neighborhood_prompt(
        address="100 Main St",
        neighborhood="Ballard",
        city="Seattle",
    )
    assert "100 Main St" in prompt
    assert "Ballard" in prompt
    assert "Seattle" in prompt


def test_things_to_do_prompt_asks_for_nearby_activities():
    prompt = build_things_to_do_prompt(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    assert SAMPLE_ADDRESS in prompt
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    lower = prompt.lower()
    assert "things to do" in lower or "activities" in lower or "walking" in lower
    assert "bullet" in lower or "list" in lower
    assert "walking" in lower or "walkable" in lower
    assert "this address" in lower or "address" in lower
    assert "google.com/maps" in lower
    assert "query=" in lower


def test_things_to_do_prompt_is_separate_from_overview():
    overview = build_neighborhood_prompt(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    things = build_things_to_do_prompt(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    assert overview != things
    assert "long-term" in overview.lower() or "tradeoff" in overview.lower()
    assert "salesy" in things.lower() or "practical" in things.lower()
    assert "maps/search" in things.lower()


def test_cache_keys_include_address_and_v3_prefix():
    overview_key = build_overview_cache_key(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    things_key = build_things_to_do_cache_key(
        address=SAMPLE_ADDRESS,
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    assert overview_key.startswith(f"{OVERVIEW_CACHE_PREFIX}|")
    assert things_key.startswith(f"{THINGS_CACHE_PREFIX}|")
    assert SAMPLE_ADDRESS in overview_key
    assert SAMPLE_ADDRESS in things_key
    assert "Mar Vista" in overview_key
    assert overview_key != things_key
    # Old hood-only keys must not match
    assert not overview_key.startswith("Mar Vista|")
    assert not things_key.startswith("things_v2|")


def test_cache_keys_change_when_address_changes():
    a = build_overview_cache_key(
        address="1 A St",
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    b = build_overview_cache_key(
        address="2 B St",
        neighborhood="Mar Vista",
        city="Los Angeles",
        state="CA",
    )
    assert a != b


def test_neighborhood_tab_has_in_tab_gemini_controls():
    src = (
        ROOT / "app" / "modules" / "neighborhood_reviews.py"
    ).read_text(encoding="utf-8")
    assert "Ask Gemini about this neighborhood" in src
    assert "Ask Gemini: things to do" in src
    assert "ensure_gemini_overview" in src
    assert "ensure_gemini_things_to_do" in src
    assert "hb-page-meta" in src
    assert "hb-page-hint" in src
    assert "hb-empty-state" in src
    assert "text-caption text-grey" not in src
    assert "use Gemini insights in the header" not in src
