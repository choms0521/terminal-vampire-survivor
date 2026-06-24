"""terminal_vs.sim.spatial - uniform-grid spatial hash (Day 3).

A uniform grid that buckets entities by integer cell so neighbor queries only
scan nearby buckets instead of every entity (master section 5.3, O(n) average vs
O(n^2) brute force). The grid is built once per tick from the current entity
list and queried during collision resolution.

Distance convention: this is PHYSICAL collision space, so distances are plain
Euclidean world distance -- NOT the aspect-corrected on-screen distance used by
targeting/rendering. ``query_near`` returns exactly the ids whose entities lie
within ``radius`` (true distance filter), so its result set equals a brute-force
all-pairs scan with the same metric (verified in tests/test_spatial.py).

Pure data structure, blessed-free.
"""

from __future__ import annotations

from math import ceil, floor


class SpatialHash:
    """Uniform grid mapping (cell_x, cell_y) -> list of (id, x, y).

    ``cell_size`` is the world width/height of one bucket. Build it from an
    entity iterable, then call ``query_near`` to get the ids within a radius of a
    point. Buckets store coordinates so the exact-distance filter needs no
    second lookup into the entity list.
    """

    def __init__(self, cell_size: float) -> None:
        if cell_size <= 0.0:
            raise ValueError(f"cell_size must be > 0, got {cell_size!r}")
        self.cell_size: float = cell_size
        self.buckets: dict[tuple[int, int], list[tuple[int, float, float]]] = {}

    def _cell_of(self, x: float, y: float) -> tuple[int, int]:
        """Return the integer bucket coordinate containing world point (x, y)."""
        return (floor(x / self.cell_size), floor(y / self.cell_size))

    @classmethod
    def build(cls, entities, cell_size: float) -> "SpatialHash":
        """Build a grid from ``entities`` (each exposing int ``id`` and float x/y).

        Entities are inserted in iteration order; bucket lists therefore preserve
        that order, which keeps downstream iteration deterministic.
        """
        grid = cls(cell_size)
        for entity in entities:
            key = grid._cell_of(entity.x, entity.y)
            grid.buckets.setdefault(key, []).append((entity.id, entity.x, entity.y))
        return grid

    def query_near(self, x: float, y: float, radius: float) -> list[int]:
        """Return the ids of entities within ``radius`` (Euclidean) of (x, y).

        Only the buckets overlapping the query disc are scanned: the bucket span
        is ``ceil(radius / cell_size)`` in each direction, which covers any
        entity that could be within ``radius`` regardless of how the disc lines
        up with cell boundaries. Each candidate is then filtered by its true
        squared distance, so the result is exactly the in-radius set (no false
        positives). Ids are returned sorted ascending for deterministic
        downstream processing.
        """
        if radius < 0.0:
            return []
        cx, cy = self._cell_of(x, y)
        span = ceil(radius / self.cell_size)
        r2 = radius * radius
        found: list[int] = []
        for gx in range(cx - span, cx + span + 1):
            for gy in range(cy - span, cy + span + 1):
                bucket = self.buckets.get((gx, gy))
                if bucket is None:
                    continue
                for entity_id, ex, ey in bucket:
                    dx = ex - x
                    dy = ey - y
                    if dx * dx + dy * dy <= r2:
                        found.append(entity_id)
        found.sort()
        return found
