"""Headless tests for the PURE render compose path (Day 5/6).

These exercise ``render.frame.compose_cells`` / ``compose_frame`` without blessed
or a TTY: the pure composer takes no ``term``, so the cell-grid build, culling,
draw-priority overdraw, and fixed-width padding are all unit-testable headlessly.
The blessed emitter (``render_frame``) is a thin wrapper over this path; its
compose result is what these tests cover.
"""

from __future__ import annotations

import random

from terminal_vs.render.frame import (
    _identity_colorize,
    compose_cells,
    compose_frame,
)
from terminal_vs.sim.state import Enemy, new_run

from .conftest import make_config


def test_player_lands_at_viewport_center():
    """The camera follows the player, so the player maps to the center cell."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    center_col = cfg.viewport_w // 2
    center_row = cfg.viewport_h // 2
    glyph, color = grid[center_row][center_col]
    assert glyph == state.player.glyph
    assert color == state.player.color


def test_player_overdraws_enemy_sharing_a_cell():
    """An enemy on the player's cell is overwritten by the always-on-top player."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # Place an enemy exactly on the player's world position (shared cell).
    state.enemies.append(
        Enemy(entity_id=state.alloc_id(), x=state.player.x, y=state.player.y, hp=1.0)
    )
    grid = compose_cells(state, state.camera, cfg)
    center_col = cfg.viewport_w // 2
    center_row = cfg.viewport_h // 2
    glyph, _ = grid[center_row][center_col]
    assert glyph == state.player.glyph  # player wins the shared cell


def test_offscreen_entity_is_culled():
    """An entity far outside the viewport never appears in the grid."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    far = state.player.x + cfg.viewport_w * 1000.0
    state.enemies.append(
        Enemy(entity_id=state.alloc_id(), x=far, y=state.player.y, hp=1.0)
    )
    grid = compose_cells(state, state.camera, cfg)
    glyphs = {glyph for row in grid for glyph, _ in row}
    assert "z" not in glyphs  # the off-screen enemy glyph is absent


def test_grid_dimensions_are_fixed():
    """The grid is exactly viewport_h rows of viewport_w cells."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    assert len(grid) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in grid)


def test_compose_frame_rows_padded_to_fixed_width():
    """Every emitted row is exactly viewport_w wide (fixed-width erases ghosts)."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)


def test_compose_frame_includes_hud_overlay():
    """The HUD lines overlay the top rows of the frame."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    first_row = frame.split("\n")[0]
    assert first_row.startswith("HP ")  # HP bar is the first HUD line


def test_compose_frame_is_nonempty():
    """The pure compose path yields a non-empty multi-row string."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    assert len(frame) > 0
    assert "\n" in frame
