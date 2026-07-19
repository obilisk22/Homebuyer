"""Task 4 review fixes: assigned-schools caption copy + long I/O off the event loop."""

import re
from pathlib import Path

from app.modules.neighborhood_reviews import _assigned_schools_caption

ROOT = Path(__file__).resolve().parents[1]


def test_no_pin_caption_matches_design_spec():
    result = {"status": "no_pin", "message": "No coordinates for this property yet."}
    assert (
        _assigned_schools_caption(result, has_keys=False)
        == "Needs a map pin — geocode this home first."
    )


def test_outside_caption_matches_design_spec():
    result = {"status": "outside", "message": "Outside LAUSD attendance boundaries."}
    assert (
        _assigned_schools_caption(result, has_keys=True)
        == "Assigned schools not available for this district yet (SoCal GIS)."
    )


def test_gap_caption_matches_design_spec():
    result = {
        "status": "gap",
        "message": (
            "Inside the LAUSD area but no attendance boundary matched this "
            "point (rare boundary gap)."
        ),
    }
    assert (
        _assigned_schools_caption(result, has_keys=False)
        == "No attendance match for this pin (rare boundary gap)."
    )


def test_error_caption_shows_result_message():
    result = {"status": "error", "message": "LAUSD lookup failed: timeout"}
    assert (
        _assigned_schools_caption(result, has_keys=False)
        == "LAUSD lookup failed: timeout"
    )


def test_error_caption_falls_back_when_message_missing():
    result = {"status": "error"}
    assert (
        _assigned_schools_caption(result, has_keys=False)
        == "Could not load assigned schools."
    )


def test_ok_caption_includes_source_and_schooldigger_suffix_when_keys_present():
    result = {"status": "ok", "source": "LAUSD attendance"}
    assert (
        _assigned_schools_caption(result, has_keys=True)
        == "LAUSD attendance · ratings via SchoolDigger"
    )


def test_ok_caption_prompts_for_keys_when_missing():
    result = {"status": "ok", "source": "LAUSD attendance"}
    caption = _assigned_schools_caption(result, has_keys=False)
    assert caption.startswith("LAUSD attendance")
    assert "SchoolDigger" in caption
    assert "ratings via SchoolDigger" not in caption


def test_neighborhood_module_loads_assigned_schools_off_event_loop():
    src = (
        ROOT / "app" / "modules" / "neighborhood_reviews.py"
    ).read_text(encoding="utf-8")
    assert "resolve_assigned_schools_job" in src
    assert re.search(
        r"await\s+run\.io_bound\(\s*resolve_assigned_schools_job", src
    )
    # The module should no longer call the raw sync resolvers directly —
    # that work now lives in the ui_jobs worker.
    assert "from app.core.school_zones import resolve_assigned" not in src
    assert "enrich_assigned" not in src


def test_ui_jobs_has_resolve_assigned_schools_job():
    src = (ROOT / "app" / "core" / "ui_jobs.py").read_text(encoding="utf-8")
    assert "def resolve_assigned_schools_job(" in src
    assert "resolve_assigned(" in src
    assert "enrich_assigned(" in src
