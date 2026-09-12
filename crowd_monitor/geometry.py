from __future__ import annotations

from collections.abc import Iterable
import math

import numpy as np

PointNorm = tuple[float, float]
PointPx = tuple[int, int]


def normalized_to_pixels(
    points: Iterable[PointNorm], width: int, height: int
) -> np.ndarray:
    return np.array(
        [
            (
                min(width - 1, max(0, round(x * (width - 1)))),
                min(height - 1, max(0, round(y * (height - 1)))),
            )
            for x, y in points
        ],
        dtype=np.int32,
    )


def normalized_line_to_pixels(
    line: tuple[PointNorm, PointNorm], width: int, height: int
) -> tuple[PointPx, PointPx]:
    pixels = normalized_to_pixels(line, width, height)
    return (int(pixels[0][0]), int(pixels[0][1])), (
        int(pixels[1][0]),
        int(pixels[1][1]),
    )


def point_in_polygon(point: PointPx, polygon: np.ndarray) -> bool:
    if polygon.size == 0:
        return True
    x, y = float(point[0]), float(point[1])
    vertices = [(float(item[0]), float(item[1])) for item in polygon]
    inside = False
    for index, (x1, y1) in enumerate(vertices):
        x2, y2 = vertices[(index + 1) % len(vertices)]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-9
            and min(x1, x2) <= x <= max(x1, x2)
            and min(y1, y2) <= y <= max(y1, y2)
        ):
            return True
        if (y1 > y) != (y2 > y):
            x_intersection = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersection:
                inside = not inside
    return inside


def euclidean_distance(a: PointPx, b: PointPx) -> float:
    return math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))


def signed_distance_to_line(
    point: PointPx,
    line_start: PointPx,
    line_end: PointPx,
) -> float:
    """Signed perpendicular distance in pixels from a point to an oriented line."""
    x1, y1 = line_start
    x2, y2 = line_end
    px, py = point
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    return (dx * (py - y1) - dy * (px - x1)) / length


def _orientation(a: PointPx, b: PointPx, c: PointPx) -> int:
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (
        c[1] - b[1]
    )
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def _on_segment(a: PointPx, b: PointPx, c: PointPx) -> bool:
    return (
        min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
        and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
    )


def segments_intersect(
    first_start: PointPx,
    first_end: PointPx,
    second_start: PointPx,
    second_end: PointPx,
) -> bool:
    """Return True when two finite 2-D segments intersect."""
    o1 = _orientation(first_start, first_end, second_start)
    o2 = _orientation(first_start, first_end, second_end)
    o3 = _orientation(second_start, second_end, first_start)
    o4 = _orientation(second_start, second_end, first_end)

    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(first_start, second_start, first_end):
        return True
    if o2 == 0 and _on_segment(first_start, second_end, first_end):
        return True
    if o3 == 0 and _on_segment(second_start, first_start, second_end):
        return True
    if o4 == 0 and _on_segment(second_start, first_end, second_end):
        return True
    return False
