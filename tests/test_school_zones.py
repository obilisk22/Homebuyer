from app.core.school_zones import (
    pick_school_in_zone,
    point_in_polygon,
    point_in_ring,
    schools_from_attendance_payloads,
)


def test_point_in_simple_square():
    # square around (0.5, 0.5)
    ring = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert point_in_ring(0.5, 0.5, ring) is True
    assert point_in_ring(1.5, 0.5, ring) is False


def test_point_in_polygon_with_hole():
    outer = [[0.0, 0.0], [3.0, 0.0], [3.0, 3.0], [0.0, 3.0], [0.0, 0.0]]
    hole = [[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0], [1.0, 1.0]]
    assert point_in_polygon(0.5, 0.5, [outer, hole]) is True
    assert point_in_polygon(1.5, 1.5, [outer, hole]) is False


def test_pick_school_in_zone_prefers_inside_point():
    rings = [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]]]
    candidates = [
        {
            "name": "Outside ES",
            "lng": 3.0,
            "lat": 3.0,
            "map_type": "ES",
            "city": "LOS ANGELES",
            "cds_code": "1",
        },
        {
            "name": "Inside ES",
            "lng": 1.0,
            "lat": 1.0,
            "map_type": "ES",
            "city": "LOS ANGELES",
            "cds_code": "2",
        },
    ]
    picked = pick_school_in_zone(
        1.0, 1.0, rings, candidates, map_type="ES"
    )
    assert picked is not None
    assert picked["name"] == "Inside ES"


def test_schools_from_attendance_payloads_maps_levels():
    # Minimal synthetic attendance + school payloads exercised via pure helpers
    attendance = {
        "elementary": {
            "rings": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
            "key": 297,
        },
        "middle": None,
        "high": None,
    }
    school_candidates = {
        "elementary": [
            {
                "name": "Test ES",
                "lng": 1.0,
                "lat": 1.0,
                "map_type": "ES",
                "city": "LOS ANGELES",
                "cds_code": "19647336018048",
            }
        ],
        "middle": [],
        "high": [],
    }
    result = schools_from_attendance_payloads(
        1.0, 1.0, attendance, school_candidates
    )
    assert result["elementary"]["name"] == "Test ES"
    assert result["elementary"]["cds_code"] == "19647336018048"
    assert result["middle"] is None
