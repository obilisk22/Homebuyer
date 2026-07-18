from app.core.gemini_neighborhood import (
    build_neighborhood_prompt,
    build_things_to_do_prompt,
)


def test_prompt_includes_neighborhood_and_city():
    prompt = build_neighborhood_prompt(neighborhood="Mar Vista", city="Los Angeles", state="CA")
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    assert "buying a home" in prompt.lower()


def test_prompt_works_without_state():
    prompt = build_neighborhood_prompt(neighborhood="Ballard", city="Seattle")
    assert "Ballard" in prompt
    assert "Seattle" in prompt


def test_things_to_do_prompt_asks_for_nearby_activities():
    prompt = build_things_to_do_prompt(
        neighborhood="Mar Vista", city="Los Angeles", state="CA"
    )
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    lower = prompt.lower()
    assert "things to do" in lower or "activities" in lower or "walking" in lower
    assert "bullet" in lower or "list" in lower
    assert "walking" in lower or "walkable" in lower
    assert "google.com/maps" in lower
    assert "query=" in lower


def test_things_to_do_prompt_is_separate_from_overview():
    overview = build_neighborhood_prompt(
        neighborhood="Mar Vista", city="Los Angeles", state="CA"
    )
    things = build_things_to_do_prompt(
        neighborhood="Mar Vista", city="Los Angeles", state="CA"
    )
    assert overview != things
    assert "vibe" in overview.lower() or "feel" in overview.lower()
    assert "salesy" in things.lower() or "practical" in things.lower()
    assert "maps/search" in things.lower()
