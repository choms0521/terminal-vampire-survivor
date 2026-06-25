"""Balance sensitivity: config edits alone change the outcome (Phase 3 Day 6).

The master plan's data-driven-balance contract (sections 5.5, 12) says difficulty
is tuned by editing balance values, NOT code. These tests prove it: the same
seed + same scripted input is run through the headless driver twice, with two
configs that differ in exactly ONE balance value (enemy hp, then spawn cadence).
No ``terminal_vs/rules`` or ``terminal_vs/sim`` source is touched -- only injected
config objects differ -- yet the run outcome (kills / survival ticks) changes.

Determinism is the control: re-running the same config + seed reproduces the
result exactly, so the measured difference is attributable to the balance change,
not to noise.
"""

from __future__ import annotations

import random

from terminal_vs.rules.defs import DirectorDef, EnemyDef, ReinforceStep

from .conftest import make_config, make_defs
from .support.sim_driver import run_until_gameover

# A lethal-but-killable scenario: a stationary player auto-fires the dagger and
# clears some incoming enemies, but the director out-paces it and the player is
# ground down within a bounded number of ticks. Tuning the enemy hp changes how
# many the dagger clears before dying -- a measurable, deterministic outcome.
_SAFETY_SECONDS = 120
_SEED = 42
_BASE_ENEMY_HP = 4.0


def _config(*, enemy_hp: float, spawn_concurrent: int = 3) -> object:
    """A config that varies ONLY enemy hp (and optionally the spawn concurrency).

    Everything else -- weapons, viewport, director cadence, seed handling -- is
    held fixed, so any outcome change is attributable to the one varied dial.
    """
    defs = make_defs(
        enemies={
            "walker": EnemyDef(
                name="walker",
                hp=enemy_hp,
                move_speed=4.0,
                spawn_weight=1.0,
                glyph="z",
                color="red",
            ),
        },
        director=DirectorDef(
            base_spawn_interval=0.4,
            min_spawn_interval=0.15,
            reinforce_steps=(ReinforceStep(0, 1.0, spawn_concurrent),),
        ),
    )
    return make_config(viewport_w=60, viewport_h=24, defs=defs)


def _run(cfg) -> dict:
    cap = int(cfg.sim_tps * _SAFETY_SECONDS)
    return run_until_gameover(cfg, random.Random(_SEED), None, cap)


def test_tougher_enemies_reduce_kills_same_seed():
    """Doubling enemy hp (config only) lowers the kill count at a fixed seed.

    The starter dagger clears fewer of the tankier enemies before the player is
    overwhelmed, so the same seed + input yields strictly fewer kills -- proven
    purely by injecting a different enemy-hp config, with no source change.
    """
    base = _run(_config(enemy_hp=_BASE_ENEMY_HP))
    tough = _run(_config(enemy_hp=_BASE_ENEMY_HP * 2.0))

    assert base["reached_gameover"] is True   # both runs are bounded (end in death)
    assert tough["reached_gameover"] is True
    assert base["kills"] > tough["kills"]     # tougher enemies -> fewer kills


def test_spawn_rate_change_alters_outcome_same_seed():
    """Changing only the director's concurrency changes the run outcome.

    A second balance dial (spawn concurrency) is varied in isolation; the kill
    count or survival ticks must differ from the baseline at the same seed.
    """
    base = _run(_config(enemy_hp=_BASE_ENEMY_HP, spawn_concurrent=3))
    swarmier = _run(_config(enemy_hp=_BASE_ENEMY_HP, spawn_concurrent=6))

    assert base["reached_gameover"] is True
    assert swarmier["reached_gameover"] is True
    assert (base["kills"], base["ticks"]) != (swarmier["kills"], swarmier["ticks"])


def test_balance_outcome_is_deterministic():
    """Same config + seed + input reproduces the outcome exactly (the control).

    Without this, a measured difference could be noise; with it, the difference in
    the tests above is attributable to the balance change.
    """
    cfg = _config(enemy_hp=_BASE_ENEMY_HP)
    first = _run(cfg)
    second = _run(cfg)
    assert first == second
