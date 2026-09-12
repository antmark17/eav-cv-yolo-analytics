from crowd_monitor.geometry import (
    normalized_to_pixels,
    point_in_polygon,
    segments_intersect,
    signed_distance_to_line,
)


def test_normalized_polygon_and_point_membership():
    polygon = normalized_to_pixels(
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        width=100,
        height=50,
    )
    assert point_in_polygon((50, 25), polygon)
    assert not point_in_polygon((120, 25), polygon)


def test_line_geometry():
    assert segments_intersect((10, 50), (90, 50), (50, 0), (50, 100))
    assert not segments_intersect((10, 10), (20, 10), (50, 0), (50, 100))
    assert signed_distance_to_line((25, 50), (50, 0), (50, 100)) > 0
    assert signed_distance_to_line((75, 50), (50, 0), (50, 100)) < 0
