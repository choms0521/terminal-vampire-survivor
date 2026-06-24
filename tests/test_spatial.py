"""Tests for terminal_vs.sim.spatial: query_near equals brute-force all-pairs.

The spatial hash is an optimization, so its query result must exactly match a
naive Euclidean all-pairs scan with the same metric. Verified over 100
randomly-seeded entities for several query points/radii.
"""

from __future__ import annotations

import random

from terminal_vs.sim.spatial import SpatialHash


class _Pt:
    """Minimal entity for spatial tests (id + x/y)."""

    def __init__(self, entity_id: int, x: float, y: float) -> None:
        self.id = entity_id
        self.x = x
        self.y = y


def _brute_force(entities, x: float, y: float, radius: float) -> list[int]:
    """Naive in-radius ids (sorted), the ground truth for query_near."""
    r2 = radius * radius
    ids = [
        e.id
        for e in entities
        if (e.x - x) ** 2 + (e.y - y) ** 2 <= r2
    ]
    return sorted(ids)


def test_query_near_matches_brute_force_over_random_entities():
    rng = random.Random(2026)
    entities = [
        _Pt(i, rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0))
        for i in range(100)
    ]
    grid = SpatialHash.build(entities, cell_size=4.0)

    # Several query points and radii, including ones that span many buckets.
    for _ in range(50):
        qx = rng.uniform(-55.0, 55.0)
        qy = rng.uniform(-55.0, 55.0)
        radius = rng.uniform(0.0, 20.0)
        got = grid.query_near(qx, qy, radius)
        expected = _brute_force(entities, qx, qy, radius)
        assert got == expected, (qx, qy, radius)


def test_query_near_radius_zero_returns_only_exact_point():
    entities = [_Pt(0, 0.0, 0.0), _Pt(1, 0.0, 0.0), _Pt(2, 1.0, 0.0)]
    grid = SpatialHash.build(entities, cell_size=2.0)
    # Radius 0 includes only entities exactly at the query point.
    assert grid.query_near(0.0, 0.0, 0.0) == [0, 1]


def test_query_near_empty_grid_returns_empty():
    grid = SpatialHash.build([], cell_size=3.0)
    assert grid.query_near(0.0, 0.0, 10.0) == []


def test_query_near_returns_sorted_ids():
    # Ids deliberately out of spatial order to confirm sorting.
    entities = [_Pt(9, 0.0, 0.0), _Pt(2, 0.1, 0.1), _Pt(5, -0.1, -0.1)]
    grid = SpatialHash.build(entities, cell_size=2.0)
    got = grid.query_near(0.0, 0.0, 5.0)
    assert got == sorted(got)
    assert got == [2, 5, 9]
