"""Phase 4C: boss spawning + large-XP drop.

Commit 1 (infra, this file's first tests): a boss-flagged enemy is excluded from
the regular weighted spawn pool and spawned ONLY when the director's
``boss_spawn_times`` threshold is crossed (once, guarded by ``_boss_alive``);
killing it drops a large xp gem driven by ``EnemyDef.xp_value`` (data-driven,
replacing the previously hardcoded ``_XP_GEM_VALUE``). Headless / deterministic.

Commit 2 will add the caster boss + the enemy-projectile collision direction in
this same file.
"""

from __future__ import annotations

import random

from terminal_vs.rules.defs import DirectorDef, EnemyDef, ReinforceStep
from terminal_vs.sim.spawn import director_params, maybe_spawn
from terminal_vs.sim.state import make_enemy, new_run
from terminal_vs.sim.step import _drop_xp_on_death

from .conftest import make_config, make_defs


def _defs_with_boss(*, boss_times=(60.0,), boss_xp=50.0, boss_hp=500.0):
    """A BalanceDefs whose enemy table has a regular walker/swarm pair plus one
    boss-flagged tank, and a director with a boss spawn time."""
    return make_defs(
        enemies={
            "walker": EnemyDef("walker", 10.0, 2.5, 70.0, "z", "red"),
            "swarm": EnemyDef("swarm", 4.0, 5.0, 30.0, "x", "magenta"),
            "boss_tank": EnemyDef(
                "boss_tank",
                boss_hp,
                1.0,
                1.0,
                "M",
                "red",
                boss=True,
                xp_value=boss_xp,
            ),
        },
        director=DirectorDef(
            base_spawn_interval=2.0,
            min_spawn_interval=0.4,
            reinforce_steps=(ReinforceStep(0, 1.0, 1),),
            boss_spawn_times=boss_times,
        ),
    )


def test_boss_excluded_from_regular_weighted_spawn_pool():
    """A boss-flagged enemy never appears in the regular weighted spawn table, so
    the director's per-wave weighted pick can never roll it as cannon fodder."""
    defs = _defs_with_boss()
    params = director_params(0.0, defs)
    regular = {name for name, _ in params.enemy_weights}
    assert "walker" in regular
    assert "swarm" in regular
    assert "boss_tank" not in regular  # boss is partitioned out of the regular pool


def test_boss_due_only_on_the_threshold_crossing():
    """``boss_due`` is True only on the tick whose (prev, now] window contains a
    boss_spawn_time -- not before, not on a later already-past tick."""
    defs = _defs_with_boss(boss_times=(60.0,))
    assert director_params(59.0, defs, prev_elapsed=58.9).boss_due is False
    assert director_params(60.0, defs, prev_elapsed=59.9).boss_due is True
    assert director_params(61.0, defs, prev_elapsed=60.9).boss_due is False


def test_boss_spawns_exactly_once_on_due_and_not_while_alive():
    """maybe_spawn adds exactly one boss when due, and does not add a second while
    one is still alive (the ``_boss_alive`` guard)."""
    cfg = make_config(defs=_defs_with_boss(boss_times=(0.05,)))
    rng = random.Random(0)
    state = new_run(cfg, rng)
    dt = 1.0 / cfg.sim_tps

    state.elapsed = 0.05  # park elapsed on the crossing window
    maybe_spawn(state, cfg, rng)
    bosses = [e for e in state.enemies if e.kind == "boss_tank"]
    assert len(bosses) == 1

    state.elapsed += dt  # a later tick, boss still alive
    maybe_spawn(state, cfg, rng)
    bosses = [e for e in state.enemies if e.kind == "boss_tank"]
    assert len(bosses) == 1  # the alive guard prevents a second spawn


def test_boss_kill_drops_large_xp_gem():
    """Killing a boss drops a pickup carrying the boss's data-driven ``xp_value``
    (much larger than a regular enemy's), via step stage 7."""
    cfg = make_config(defs=_defs_with_boss(boss_xp=50.0))
    rng = random.Random(0)
    state = new_run(cfg, rng)
    boss = make_enemy(state.alloc_id(), 0.0, 0.0, cfg.defs.enemies["boss_tank"])
    boss.hp = 0.0
    state.enemies.append(boss)

    _drop_xp_on_death(state, rng)

    assert len(state.pickups) == 1
    assert state.pickups[0].xp == 50.0  # the boss's xp_value, not the 1.0 default


def test_regular_enemy_keeps_default_xp_value():
    """A regular enemy without an explicit ``xp_value`` drops the 1.0 default gem,
    so externalizing the boss reward does not alter existing enemy rewards."""
    cfg = make_config(defs=_defs_with_boss())
    rng = random.Random(0)
    state = new_run(cfg, rng)
    walker = make_enemy(state.alloc_id(), 0.0, 0.0, cfg.defs.enemies["walker"])
    walker.hp = 0.0
    state.enemies.append(walker)

    _drop_xp_on_death(state, rng)

    assert state.pickups[0].xp == 1.0
