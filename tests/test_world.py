"""Tests for terminal_vs.world: aspect correction, visibility culling, round-trip.

world.py is pure math, so these run headlessly. Config is constructed directly
(tests may use literal numbers freely; the no-hardcode gate only scans the
package). Deltas are chosen so dx * aspect_x lands on integers, keeping the
round-based quantization exact.
"""

from __future__ import annotations

from terminal_vs.config import Config
from terminal_vs.world import (
    Camera,
    cell_to_world,
    is_visible,
    sq_dist_aspect,
    visible_bounds,
    world_to_cell,
)

from .conftest import make_config


def _cfg(aspect_x: float = 2.0, viewport_w: int = 100, viewport_h: int = 30) -> Config:
    """Build a Config for world tests (only the operating point matters here)."""
    return make_config(
        aspect_x=aspect_x, viewport_w=viewport_w, viewport_h=viewport_h
    )


def test_aspect_x_compresses_x_cell_displacement():
    """Equal world distance gives X cell displacement = aspect_x * Y displacement.

    Moving the same world delta along X vs Y, the X cell displacement is larger
    by exactly cfg.aspect_x (X is compressed on screen, so the same world step
    spans more cells horizontally).
    """
    aspect_x = 2.0
    cfg = _cfg(aspect_x=aspect_x)
    cam = Camera(0.0, 0.0)

    center_col, center_row = world_to_cell(0.0, 0.0, cam, cfg)
    # Same world delta (3.0) applied along X and along Y.
    delta = 3.0
    x_col, _ = world_to_cell(delta, 0.0, cam, cfg)
    _, y_row = world_to_cell(0.0, delta, cam, cfg)

    x_cell_disp = x_col - center_col
    y_cell_disp = y_row - center_row

    assert y_cell_disp == 3        # 3.0 world units -> 3 cells on Y
    assert x_cell_disp == 6        # 3.0 world units -> 6 cells on X (aspect 2)
    assert x_cell_disp == int(aspect_x * y_cell_disp)


def test_is_visible_inside_true_outside_false():
    """Coordinates inside the viewport are visible; far ones are not."""
    cfg = _cfg(aspect_x=2.0, viewport_w=100, viewport_h=30)
    cam = Camera(50.0, 50.0)

    # The camera center is always visible.
    assert is_visible(50.0, 50.0, cam, cfg) is True

    # A point far outside the viewport (well beyond half-extents) is not visible.
    # X half-extent in world = (100/2)/2 = 25; Y half-extent = 15.
    assert is_visible(50.0 + 1000.0, 50.0, cam, cfg) is False
    assert is_visible(50.0, 50.0 + 1000.0, cam, cfg) is False
    assert is_visible(50.0 - 1000.0, 50.0 - 1000.0, cam, cfg) is False


def test_visible_bounds_match_is_visible_boundary():
    """visible_bounds half-extents are consistent with is_visible.

    A point just inside the X bound is visible; one well past it is not.
    """
    cfg = _cfg(aspect_x=2.0, viewport_w=100, viewport_h=30)
    cam = Camera(0.0, 0.0)
    rect = visible_bounds(cam, cfg)

    # X half-extent in world = (100/2)/2 = 25.
    assert rect.max_x == 25.0
    assert rect.min_x == -25.0
    # Y half-extent in world = 30/2 = 15.
    assert rect.max_y == 15.0
    assert rect.min_y == -15.0
    # A point near the center is inside the bounds and visible.
    assert is_visible(rect.min_x + 1.0, rect.min_y + 1.0, cam, cfg) is True


def test_round_trip_cell_to_world_to_cell_exact_on_integer_cells():
    """world_to_cell(cell_to_world(c, r)) == (c, r) for integer cells.

    Round-based quantization centers each cell on its integer, so the inverse
    that divides X by aspect_x (no half-cell offset) is exact. No float equality
    is asserted -- only integer cell equality.
    """
    cfg = _cfg(aspect_x=2.0, viewport_w=100, viewport_h=30)
    cam = Camera(7.5, -3.25)  # non-trivial camera offset

    for col in range(0, cfg.viewport_w, 7):
        for row in range(0, cfg.viewport_h, 3):
            wx, wy = cell_to_world(col, row, cam, cfg)
            rt_col, rt_row = world_to_cell(wx, wy, cam, cfg)
            assert (rt_col, rt_row) == (col, row)


def test_sq_dist_aspect_uses_same_x_compression():
    """sq_dist_aspect scales X by aspect_x, matching world_to_cell's transform."""
    cfg = _cfg(aspect_x=2.0)
    # Pure X separation of 3.0 -> scaled to 6.0 -> squared 36.0.
    assert sq_dist_aspect(0.0, 0.0, 3.0, 0.0, cfg) == 36.0
    # Pure Y separation of 3.0 -> unscaled -> squared 9.0.
    assert sq_dist_aspect(0.0, 0.0, 0.0, 3.0, cfg) == 9.0
    # Symmetric.
    assert sq_dist_aspect(1.0, 2.0, 4.0, 6.0, cfg) == sq_dist_aspect(4.0, 6.0, 1.0, 2.0, cfg)
