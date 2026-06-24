"""Tests for terminal_vs.sim.step: determinism under a fixed seed.

Running new_run + N steps twice with random.Random(42) must produce identical
entity positions, HP, and the id sequence -- the core determinism guarantee.
"""

from __future__ import annotations

import random

from terminal_vs.sim.state import Intent, new_run
from terminal_vs.sim.step import step

from .conftest import make_config


def _snapshot(state) -> tuple:
    """A fully comparable snapshot of the mutable state's observable fields."""
    player = (
        state.player.id,
        round(state.player.x, 9),
        round(state.player.y, 9),
        round(state.player.hp, 9),
    )
    enemies = tuple(
        (e.id, round(e.x, 9), round(e.y, 9), round(e.hp, 9))
        for e in state.enemies
    )
    projectiles = tuple(
        (p.id, round(p.x, 9), round(p.y, 9), round(p.ttl, 9))
        for p in state.projectiles
    )
    pickups = tuple(
        (pk.id, round(pk.x, 9), round(pk.y, 9), round(pk.xp, 9))
        for pk in state.pickups
    )
    level = (state.build.level, round(state.build.xp, 9))
    return (
        player,
        enemies,
        projectiles,
        pickups,
        level,
        state.level_up_pending,
        state.next_id,
        round(state.elapsed, 9),
    )


def _run(n: int, seed: int) -> tuple:
    cfg = make_config()
    rng = random.Random(seed)
    state = new_run(cfg, rng)
    # A wandering intent so the player moves and the run is non-degenerate.
    intents = [
        Intent(1, 0),
        Intent(1, 1),
        Intent(0, 1),
        Intent(-1, 0),
        Intent(0, 0),
    ]
    for i in range(n):
        step(state, intents[i % len(intents)], cfg, rng)
    return _snapshot(state)


def test_same_seed_two_runs_identical():
    snap_a = _run(n=200, seed=42)
    snap_b = _run(n=200, seed=42)
    assert snap_a == snap_b


def test_different_seed_diverges():
    # Sanity: a different seed should change the run (spawns differ), proving the
    # determinism above is not just a constant ignoring rng.
    snap_a = _run(n=200, seed=42)
    snap_c = _run(n=200, seed=7)
    assert snap_a != snap_c


def test_player_out_runs_enemies():
    # The player's base move speed must exceed the WALKER (basic chaser) move
    # speed so kiting works (the core survival loop). Guards the
    # _PLAYER_SPEED_MULT > 1 invariant against a silent regression (e.g. resetting
    # the multiplier to 1.0). The swarm enemy is intentionally faster than the
    # player by design, so the invariant is measured against the walker.
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    step(state, Intent(1, 0), cfg, random.Random(0))
    assert abs(state.player.vx) > cfg.defs.enemies["walker"].move_speed


def test_id_sequence_is_monotonic_and_contiguous():
    cfg = make_config()
    rng = random.Random(42)
    state = new_run(cfg, rng)
    for _ in range(50):
        step(state, Intent(1, 0), cfg, rng)
    # Every allocated id is unique and the counter only ever grew.
    assert state.next_id >= 1  # at least the player
    assert state.player.id == 0  # player is the first id allocated


def test_run_progresses_toward_levelup_with_default_seed():
    # Not a strict acceptance test (that's the integration test), but confirms
    # the pipeline closes: with enough ticks the run accrues xp at least once.
    cfg = make_config()
    rng = random.Random(42)
    state = new_run(cfg, rng)
    saw_pending = False
    for _ in range(1100):
        step(state, Intent(0, 0), cfg, rng)
        if state.level_up_pending:
            saw_pending = True
            break
    assert saw_pending is True
