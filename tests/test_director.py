"""Tests for terminal_vs.sim.spawn: the director curve + spawn behavior (Phase 2).

The director is split into a PURE time->params mapping (``director_params``) and
an in-place spawner (``spawn_enemies`` / ``maybe_spawn``). These tests verify the
curve rises over time, the per-minute reinforce step changes at the minute
boundary, the params mapping is pure (deepcopy-stable inputs), and the spawner
honors the injected entity cap. Headless, deterministic, blessed-free.
"""

from __future__ import annotations

import copy
import random

from terminal_vs.rules.defs import DirectorDef, ReinforceStep
from terminal_vs.sim.spawn import (
    SpawnParams,
    director_params,
    maybe_spawn,
    spawn_enemies,
)
from terminal_vs.sim.state import new_run

from .conftest import make_config, make_defs


def test_spawn_rate_increases_with_time():
    """A later elapsed time yields a smaller spawn interval (spawn rate rises)."""
    defs = make_defs()
    early = director_params(0.0, defs)
    late = director_params(300.0, defs)  # 5 minutes in
    assert late.spawn_interval < early.spawn_interval


def test_reinforce_step_at_minute_boundary():
    """Crossing the 1-minute boundary switches to the next reinforce step.

    At 59s the minute-0 step applies; at 60s the minute-1 step applies, changing
    both the interval and the concurrent count.
    """
    defs = make_defs()
    before = director_params(59.0, defs)
    after = director_params(60.0, defs)
    # minute-0: interval_mult 1.0, concurrent 1; minute-1: 0.8, concurrent 2.
    assert before.concurrent == 1
    assert after.concurrent == 2
    assert after.spawn_interval < before.spawn_interval


def test_min_spawn_interval_is_a_floor():
    """The spawn interval never drops below the configured minimum.

    A director whose reinforce multiplier would push the interval below the floor
    is clamped to ``min_spawn_interval``.
    """
    defs = make_defs(
        director=DirectorDef(
            base_spawn_interval=2.0,
            min_spawn_interval=0.5,
            reinforce_steps=(
                ReinforceStep(0, 1.0, 1),
                ReinforceStep(1, 0.1, 5),  # 2.0 * 0.1 = 0.2 < 0.5 floor
            ),
        )
    )
    params = director_params(120.0, defs)
    assert params.spawn_interval == 0.5  # clamped to the floor, not 0.2


def test_director_params_pure():
    """Same input twice yields equal params and never mutates the input defs."""
    defs = make_defs()
    defs_copy = copy.deepcopy(defs)
    a = director_params(90.0, defs)
    b = director_params(90.0, defs)
    assert a == b
    assert defs == defs_copy  # input was not mutated


def test_enemy_weights_come_from_defs():
    """The params' enemy weights mirror each enemy def's spawn_weight."""
    defs = make_defs()
    params = director_params(0.0, defs)
    weights = dict(params.enemy_weights)
    assert weights["walker"] == defs.enemies["walker"].spawn_weight
    assert weights["swarm"] == defs.enemies["swarm"].spawn_weight


def test_spawn_enemies_respects_cap():
    """spawn_enemies never grows the buffer past the injected entity cap.

    A tiny cap is injected via the test Config; a high-concurrent director wave
    is requested, but the spawner stops at the cap (no enemy beyond it).
    """
    cfg = make_config(entity_cap=3)  # player + room for only 2 enemies
    state = new_run(cfg, random.Random(0))
    params = director_params(180.0, cfg.defs)  # minute-3 step: concurrent 4
    assert params.concurrent >= 4
    spawn_enemies(state, params, cfg, random.Random(0))
    total = 1 + len(state.enemies) + len(state.projectiles) + len(state.pickups)
    assert total <= cfg.entity_cap
    assert len(state.enemies) == cfg.entity_cap - 1  # filled exactly to the cap


def test_spawn_enemies_skips_on_non_positive_total_weight():
    """spawn_enemies adds nothing when the total spawn weight is non-positive.

    config validates each spawn_weight > 0, but a directly-built SpawnParams (which
    bypasses that validation) with all-zero weights must spawn no enemy rather than
    run the weighted pick on a zero-total table -- the documented behavior.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    params = SpawnParams(
        spawn_interval=2.0,
        concurrent=5,
        enemy_weights=(("walker", 0.0), ("swarm", 0.0)),
    )
    spawn_enemies(state, params, cfg, random.Random(0))
    assert len(state.enemies) == 0


def test_maybe_spawn_accumulates_and_spawns():
    """maybe_spawn spawns a wave once the accumulator crosses the interval."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # One tick is far shorter than the 2.0s minute-0 interval, so a single call
    # banks time but does not yet spawn.
    maybe_spawn(state, cfg, random.Random(0))
    assert len(state.enemies) == 0
    # Drive enough ticks to cross the interval; at least one enemy must appear.
    for _ in range(int(cfg.sim_tps * 3)):  # ~3 seconds of ticks
        maybe_spawn(state, cfg, random.Random(0))
    assert len(state.enemies) >= 1


def test_maybe_spawn_deterministic():
    """Same seed + same tick sequence yields the same spawned enemy set."""
    def _run() -> list[tuple[str, float, float]]:
        cfg = make_config()
        state = new_run(cfg, random.Random(0))
        rng = random.Random(123)
        for _ in range(int(cfg.sim_tps * 6)):
            maybe_spawn(state, cfg, rng)
        return [(e.kind, round(e.x, 9), round(e.y, 9)) for e in state.enemies]

    assert _run() == _run()
