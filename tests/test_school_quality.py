from app.core import school_quality
from app.core.school_quality import (
    dashboard_url,
    enrich_assigned,
    enrich_school,
    has_quality_data,
    niche_school_url,
    normalize_cds,
    parse_dashboard_rows,
)


def test_normalize_cds_zero_pads_short_codes():
    assert normalize_cds("1964733") == "00000001964733"
    assert normalize_cds(1964733) == "00000001964733"


def test_normalize_cds_keeps_full_length_codes():
    assert normalize_cds("19647336018048") == "19647336018048"


def test_normalize_cds_strips_non_digits_and_truncates_overlong():
    assert normalize_cds("CDS: 19-6473-36018048!") == "19647336018048"


def test_normalize_cds_empty_for_blank_or_none():
    assert normalize_cds(None) == ""
    assert normalize_cds("") == ""
    assert normalize_cds("no digits here") == ""


def test_niche_school_url_includes_name_city_state():
    url = niche_school_url("Mar Vista Elementary School", "Los Angeles", "CA")
    assert url.startswith("https://www.niche.com/k12/search/best-schools/?q=")
    assert "Mar+Vista" in url or "Mar%20Vista" in url


def test_niche_school_url_falls_back_when_no_name():
    url = niche_school_url("", "", "")
    assert "school" in url


def test_dashboard_url_uses_normalized_cds_and_year():
    url = dashboard_url("19647336018048", year=2025)
    assert url == "https://www.caschooldashboard.org/reports/19647336018048/2025"


def test_dashboard_url_pads_short_cds():
    url = dashboard_url("1964733", year=2025)
    assert url == "https://www.caschooldashboard.org/reports/00000001964733/2025"


def test_parse_dashboard_rows_keeps_school_all_students_with_color():
    rows = [
        {
            "cds": "00000000000000",
            "rtype": "X",
            "studentgroup": "ALL",
            "color": "4",
            "statuslevel": "4",
            "reportingyear": "2025",
        },
        {
            "cds": "19647336018048",
            "rtype": "S",
            "studentgroup": "AA",
            "color": "3",
            "statuslevel": "3",
            "reportingyear": "2025",
        },
        {
            "cds": "19647336018048",
            "rtype": "S",
            "studentgroup": "ALL",
            "color": "4",
            "statuslevel": "4",
            "reportingyear": "2025",
        },
        {
            "cds": "19647336099999",
            "rtype": "S",
            "studentgroup": "ALL",
            "color": "0",
            "statuslevel": "",
            "reportingyear": "2025",
        },
    ]
    out = parse_dashboard_rows(rows)
    # State (X) and non-ALL (AA) rows are excluded; School+ALL with a
    # recognized color is kept.
    assert set(out.keys()) == {"19647336018048", "19647336099999"}
    assert out["19647336018048"] == {"color": "Green", "status": "High", "year": "2025"}
    assert out["19647336099999"]["color"] == "No Color"


def test_parse_dashboard_rows_skips_malformed_rows():
    assert parse_dashboard_rows([{"rtype": "S"}]) == {}
    assert parse_dashboard_rows([None, {}]) == {}


def test_enrich_school_always_adds_niche_url(monkeypatch):
    monkeypatch.setattr(school_quality, "lookup_dashboard_status", lambda cds: None)
    school = {"name": "Test Elementary", "city": "Los Angeles", "cds_code": ""}
    out = enrich_school(school)
    assert out["niche_url"].startswith("https://www.niche.com/k12/search/")
    # No cds_code -> no dashboard fields at all.
    assert "dashboard_url" not in out
    assert "dashboard_color" not in out


def test_enrich_school_adds_dashboard_fields_when_cds_present_and_matched(monkeypatch):
    monkeypatch.setattr(
        school_quality,
        "lookup_dashboard_status",
        lambda cds: {"color": "Green", "status": "High", "year": "2025", "source": "x"},
    )
    school = {"name": "Test ES", "city": "Los Angeles", "cds_code": "19647336018048"}
    out = enrich_school(school)
    assert out["dashboard_color"] == "Green"
    assert out["dashboard_status"] == "High"
    assert out["dashboard_url"] == (
        "https://www.caschooldashboard.org/reports/19647336018048/2025"
    )


def test_enrich_school_has_dashboard_url_without_color_on_lookup_miss(monkeypatch):
    monkeypatch.setattr(school_quality, "lookup_dashboard_status", lambda cds: None)
    school = {"name": "Test ES", "city": "Los Angeles", "cds_code": "19647336018048"}
    out = enrich_school(school)
    assert out["dashboard_url"]
    assert "dashboard_color" not in out


def test_enrich_assigned_enriches_every_present_school_no_key_gate(monkeypatch):
    monkeypatch.setattr(school_quality, "lookup_dashboard_status", lambda cds: None)
    result = {
        "status": "ok",
        "schools": {
            "elementary": {"name": "A ES", "city": "LA", "cds_code": "1"},
            "middle": None,
            "high": {"name": "A HS", "city": "LA", "cds_code": "2"},
        },
    }
    out = enrich_assigned(result)
    assert out["schools"]["elementary"]["niche_url"]
    assert out["schools"]["middle"] is None
    assert out["schools"]["high"]["niche_url"]


def test_has_quality_data_is_always_true():
    assert has_quality_data() is True
