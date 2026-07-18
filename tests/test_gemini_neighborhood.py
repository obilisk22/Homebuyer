from pathlib import Path

from app.core.gemini_neighborhood import (
    build_neighborhood_prompt,
    build_things_to_do_prompt,
)

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_includes_neighborhood_and_city():
    prompt = build_neighborhood_prompt(neighborhood="Mar Vista", city="Los Angeles", state="CA")
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    lower = prompt.lower()
    assert "buying a home" in lower or "considering buying" in lower
    assert "long-term" in lower or "long term" in lower
    assert "honest" in lower or "direct" in lower
    assert "tradeoff" in lower or "downside" in lower


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
    assert "long-term" in overview.lower() or "tradeoff" in overview.lower()
    assert "salesy" in things.lower() or "practical" in things.lower()
    assert "maps/search" in things.lower()


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
