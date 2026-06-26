"""Pure layer-composition tests (Phase 3 Day 5).

The frame composer is render-free: ``compose_cells`` builds the (glyph, color)
grid in draw-priority order (floor < pickup < enemy < projectile < player) with
the player ALWAYS drawn on top (master 3.4), and ``compose_frame`` draws the
loop mode's modal panel over the HUD. These tests assert the priority / overlap
invariant and that each mode's overlay lands in the composed frame -- all without
a terminal or TTY.
"""

from __future__ import annotations

import random

from terminal_vs.render.frame import (
    _identity_colorize,
    compose_cells,
    compose_frame,
)
from terminal_vs.rules.leveling import Choice
from terminal_vs.sim.state import Effect, Enemy, Pickup, Projectile, new_run
from terminal_vs.world import world_to_cell

from .conftest import make_config


def test_player_is_top_priority_over_enemy_and_projectile_overlap():
    """Player + enemy + projectile share a cell -> the player glyph wins on top.

    The draw-priority overlap invariant (master 3.4): whatever entities pile onto
    the player's cell, the always-on-top player must remain visible. Guards
    against a layer-order regression that would hide the player in a crowd.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    px, py = state.player.x, state.player.y
    state.enemies.append(Enemy(state.alloc_id(), px, py, hp=5.0))
    state.projectiles.append(
        Projectile(state.alloc_id(), px, py, vx=0.0, vy=0.0, damage=1.0, ttl=1.0)
    )

    grid = compose_cells(state, state.camera, cfg)
    col = cfg.viewport_w // 2
    row = cfg.viewport_h // 2
    glyph, _ = grid[row][col]
    assert glyph == state.player.glyph  # player drawn on top of the overlap


def test_draw_priority_projectile_over_enemy_over_pickup():
    """At a shared non-player cell, draw priority is pickup < enemy < projectile.

    The highest layer present wins the cell; with a projectile, enemy, and pickup
    stacked, the projectile glyph is what shows.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # A cell offset from the player so the player layer does not mask the result.
    wx, wy = state.player.x + 3.0, state.player.y
    pickup = Pickup(state.alloc_id(), wx, wy, xp=1.0)
    enemy = Enemy(state.alloc_id(), wx, wy, hp=5.0)
    proj = Projectile(state.alloc_id(), wx, wy, vx=0.0, vy=0.0, damage=1.0, ttl=1.0)
    state.pickups.append(pickup)
    state.enemies.append(enemy)
    state.projectiles.append(proj)

    grid = compose_cells(state, state.camera, cfg)
    col, row = world_to_cell(wx, wy, state.camera, cfg)
    glyph, _ = grid[row][col]
    assert glyph == proj.glyph        # projectile is the top non-player layer
    assert glyph != enemy.glyph
    assert glyph != pickup.glyph


def test_effect_draws_over_entities_but_under_player():
    """A visual effect overdraws an entity it shares a cell with (it is above the
    entity layers), yet the always-on-top player still wins its own cell -- draw
    priority pickup < enemy < projectile < effect < player (master 3.4)."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # A non-player cell holding an enemy + an effect: the effect draws on top.
    wx, wy = state.player.x + 3.0, state.player.y
    state.enemies.append(Enemy(state.alloc_id(), wx, wy, hp=5.0))
    state.effects.append(Effect(wx, wy, glyph=")", color="red", ttl=0.1))
    grid = compose_cells(state, state.camera, cfg)
    col, row = world_to_cell(wx, wy, state.camera, cfg)
    assert grid[row][col][0] == ")"  # effect over the enemy

    # An effect on the player's own cell loses to the always-on-top player.
    state.effects.append(
        Effect(state.player.x, state.player.y, glyph=")", color="red", ttl=0.1)
    )
    grid2 = compose_cells(state, state.camera, cfg)
    pcol, prow = cfg.viewport_w // 2, cfg.viewport_h // 2
    assert grid2[prow][pcol][0] == state.player.glyph  # player over the effect


def test_compose_frame_shows_pause_overlay_in_pause_mode():
    """mode='pause' draws the pause panel into the composed frame."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(
        state, state.camera, cfg, _identity_colorize, 100.0, mode="pause"
    )
    assert "== PAUSED ==" in frame


def test_compose_frame_shows_gameover_overlay_in_gameover_mode():
    """mode='gameover' draws the run-summary panel (with kills) into the frame."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.kills = 12
    frame = compose_frame(
        state, state.camera, cfg, _identity_colorize, 100.0, mode="gameover"
    )
    assert "== GAME OVER ==" in frame
    assert "kills 12" in frame


def test_compose_frame_play_mode_has_no_modal_panel():
    """mode='play' (no pending draft) draws no pause/gameover/levelup panel."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(
        state, state.camera, cfg, _identity_colorize, 100.0, mode="play"
    )
    assert "PAUSED" not in frame
    assert "GAME OVER" not in frame
    assert "LEVEL UP" not in frame


def test_compose_frame_draft_shows_in_play_mode_backward_compat():
    """Backward-compat seam: a pending draft shows even when mode is left 'play'.

    Callers that drive the level-up draft purely via ``state.pending_choices``
    (the pre-mode behavior) must still get the overlay when ``mode`` is its
    default. Locks the fallback in compose_frame so it cannot silently regress --
    the render-overlay wire-test lesson applied to the new mode-threaded path.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
    )
    frame = compose_frame(
        state, state.camera, cfg, _identity_colorize, 100.0, mode="play"
    )
    assert "LEVEL UP" in frame       # draft still drawn at the default mode
    assert "1) dagger Lv2" in frame


def test_compose_frame_overlay_keeps_fixed_width():
    """A modal overlay never changes the frame's fixed dimensions (no overflow)."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.kills = 3
    frame = compose_frame(
        state, state.camera, cfg, _identity_colorize, 100.0, mode="gameover"
    )
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)
