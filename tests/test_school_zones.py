from app.core.school_zones import point_in_polygon, point_in_ring


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
