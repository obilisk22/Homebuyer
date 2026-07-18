from app.core.gemini_neighborhood import build_neighborhood_prompt


def test_prompt_includes_neighborhood_and_city():
    prompt = build_neighborhood_prompt(neighborhood="Mar Vista", city="Los Angeles", state="CA")
    assert "Mar Vista" in prompt
    assert "Los Angeles" in prompt
    assert "buying a home" in prompt.lower()


def test_prompt_works_without_state():
    prompt = build_neighborhood_prompt(neighborhood="Ballard", city="Seattle")
    assert "Ballard" in prompt
    assert "Seattle" in prompt
