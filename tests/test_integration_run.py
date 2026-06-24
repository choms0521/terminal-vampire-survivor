"""Headless integration test for the closed Phase 1 loop (Day 6).

This test drives the simulation with NO blessed and NO render: it calls
``new_run`` then ``step`` for a fixed number of ticks under a fixed seed, and
mirrors the loop's level-up drain headlessly (when ``level_up_pending`` is set by
step, it rolls + applies a choice and re-checks, exactly as ``loop.run`` does).

It asserts the full gameplay chain actually closes -- an enemy is killed, an xp
gem drops, the magnet collects it, xp crosses a threshold, and a level-up fires
-- by observing the proxy: starting at level 1, after N ticks the run reaches
``level >= 2`` and ``level_up_pending`` was True at least once. It also asserts
determinism: two same-seed runs produce identical final state.

The render layer is never imported here -- this is the sim+rules headless gate.
"""

from __future__ import annotations

import random

from terminal_vs.rules import leveling
from terminal_vs.sim.state import Intent, new_run
from terminal_vs.sim.step import step

from .conftest import make_config

# Fixed seed and tick cap. The measured tick to reach level >= 2 at this seed is
# ~301 (with the drain mirror), so 400 is a safe upper bound that still proves
# the chain closes well within the run. ``N_TICKS`` is a test budget, not a
# perf-tuning number, so a literal is fine here (tests are not perf-gated).
_SEED = 42
_N_TICKS = 400


def _drain_levelups(state, cfg, rng) -> None:
    """Mirror loop.run's level-up drain headlessly.

    Step only SETS ``level_up_pending``; the loop clears it by consuming every
    banked level (one ``apply_choice`` per level) until pending is false, then
    setting the flag false. This mirror keeps the headless run faithful to the
    interactive loop so the integration result matches play.
    """
    while leveling.level_up_pending(state.level_state, cfg):
        choice = leveling.roll_choices(state.level_state, cfg, rng, n=1)[0]
        state.level_state = leveling.apply_choice(state.level_state, choice, cfg)
    state.level_up_pending = False


def _snapshot(state) -> tuple:
    """A fully comparable snapshot of the run's observable state (for equality)."""
    player = (
        state.player.id,
        round(state.player.x, 9),
        round(state.player.y, 9),
        round(state.player.hp, 9),
    )
    enemies = tuple(
        (e.id, round(e.x, 9), round(e.y, 9), round(e.hp, 9)) for e in state.enemies
    )
    projectiles = tuple(
        (p.id, round(p.x, 9), round(p.y, 9), round(p.ttl, 9))
        for p in state.projectiles
    )
    pickups = tuple(
        (pk.id, round(pk.x, 9), round(pk.y, 9), round(pk.xp, 9))
        for pk in state.pickups
    )
    level = (state.level_state.level, round(state.level_state.xp, 9))
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


def _drive_run(seed: int, n_ticks: int):
    """Run the closed loop headlessly: step + drain each tick. Returns details.

    Returns ``(final_snapshot, saw_pending, ticks_to_level2)``. ``intent`` is a
    stationary Intent(0, 0): the player stays put, enemies walk in and die to
    auto-fire, gems drop and are magnet-collected -- no manual movement needed to
    close the chain (matches tests/test_sim_step's stationary progress check).
    """
    cfg = make_config()
    rng = random.Random(seed)
    state = new_run(cfg, rng)
    saw_pending = False
    ticks_to_level2 = None
    intent = Intent(0, 0)
    for tick in range(n_ticks):
        step(state, intent, cfg, rng)
        if state.level_up_pending:
            saw_pending = True
            _drain_levelups(state, cfg, rng)
        if ticks_to_level2 is None and state.level_state.level >= 2:
            ticks_to_level2 = tick + 1
    return _snapshot(state), saw_pending, ticks_to_level2


def test_closed_loop_reaches_level_two():
    """Starting at level 1, the run levels up at least once within N ticks."""
    snapshot, saw_pending, ticks_to_level2 = _drive_run(_SEED, _N_TICKS)
    # The proxy for "kill -> xp drop -> pickup -> level-up actually happened":
    assert saw_pending is True
    # Final level reflects at least one consumed level-up.
    assert snapshot[4][0] >= 2  # snapshot[4] == (level, xp)
    # And it was reached within the run (sanity on the measured tick count).
    assert ticks_to_level2 is not None
    assert ticks_to_level2 <= _N_TICKS


def test_same_seed_two_runs_identical():
    """Two same-seed headless runs produce byte-identical final state."""
    snap_a, _, _ = _drive_run(_SEED, _N_TICKS)
    snap_b, _, _ = _drive_run(_SEED, _N_TICKS)
    assert snap_a == snap_b


def test_different_seed_diverges():
    """A different seed changes the run -- determinism above is not a constant."""
    snap_a, _, _ = _drive_run(_SEED, _N_TICKS)
    snap_c, _, _ = _drive_run(_SEED + 5, _N_TICKS)
    assert snap_a != snap_c
