from app.core.schooldigger import normalize_enrichment, pick_search_match


def test_pick_search_match_prefers_city():
    school_list = [
        {
            "schoolid": "1",
            "schoolName": "Mar Vista Elementary School",
            "address": {"city": "San Diego", "state": "CA"},
            "url": "https://example.com/a",
            "rankHistory": [{"rankStars": 2, "year": 2025}],
        },
        {
            "schoolid": "2",
            "schoolName": "Mar Vista Elementary School",
            "address": {"city": "Los Angeles", "state": "CA"},
            "url": "https://example.com/b",
            "rankHistory": [{"rankStars": 4, "year": 2025}],
        },
    ]
    picked = pick_search_match(
        school_list, name="Mar Vista Elementary School", city="LOS ANGELES"
    )
    assert picked["schoolid"] == "2"


def test_normalize_enrichment_reviews():
    detail = {
        "schoolid": "2",
        "urlSchoolDigger": "https://example.com/b",
        "rankHistory": [{"rankStars": 4, "year": 2025}],
        "reviews": [
            {
                "submitDate": "1/1/2020",
                "numberOfStars": 5,
                "comment": "Great teachers and community.",
                "submittedBy": "parent",
            },
            {
                "submitDate": "1/2/2020",
                "numberOfStars": 3,
                "comment": "ok",
                "submittedBy": "citizen",
            },
        ],
    }
    out = normalize_enrichment(detail)
    assert out["rating_stars"] == 4
    assert out["review_count"] == 1  # parent-only preferred
    assert out["review_avg"] == 5.0
    assert "Great teachers" in (out["review_quote"] or "")
    assert out["schooldigger_url"] == "https://example.com/b"
