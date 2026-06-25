"""Headless full-run regression: a run reaches game over, deterministically.

This is the objective proxy for the master plan's "one full run is playable"
exit (Phase 3 Day 4 / AC4-AC5). "Reaches game over" becomes ``hp <= 0`` and
"deterministic" becomes "same cfg + seed + input script => identical end tick and
kill count" -- no subjective "is it fun" claim.

A deliberately deadly balance guarantees the player is overwhelmed within a
bounded, reproducible number of ticks:

  * a slow ``walker`` (the player-speed reference kind, so the player's base
    speed stays low and it cannot simply out-run everything), and
  * a fast, tanky ``brute`` the starter dagger can never clear (so it survives
    to reach the player) that is far faster than the player (so even a drifting
    player is caught).

Both are spawned aggressively into a small viewport, so contact damage grinds
the player down in tens of ticks. The driver (tests/support/sim_driver.py) is
blessed-free and only steps the sim; any exception before game over would
surface here as a test error (criterion (b): no exception before game over).
"""

from __future__ import annotations

import random
import time

from terminal_vs.rules.defs import DirectorDef, EnemyDef, ReinforceStep
from terminal_vs.sim.state import Intent

from .conftest import make_config, make_defs
from .support.sim_driver import run_until_gameover

# Regression-guard safety bound (NOT a performance number): a run must end well
# inside this many seconds of SIMULATED time, or the balance is too easy. It is
# converted to a tick cap from cfg.sim_tps so no tick count is hardcoded.
_SAFETY_SECONDS = 120


def _deadly_defs():
    """Balance that reliably overwhelms the player, fast and deterministically.

    Both kinds carry hp far above what the dagger (6 dmg) can clear, so they
    survive to reach the player. ``walker`` is slow and is the speed reference
    (keeping the player's base speed low); ``brute`` is much faster than the
    player, so it catches even a moving player. The director spawns several per
    wave from t=0.
    """
    tanky_hp = 100000.0
    return make_defs(
        enemies={
            "walker": EnemyDef(
                name="walker",
                hp=tanky_hp,
                move_speed=2.5,
                spawn_weight=1.0,
                glyph="z",
                color="red",
            ),
            "brute": EnemyDef(
                name="brute",
                hp=tanky_hp,
                move_speed=40.0,
                spawn_weight=5.0,
                glyph="B",
                color="red",
            ),
        },
        director=DirectorDef(
            base_spawn_interval=0.1,
            min_spawn_interval=0.05,
            reinforce_steps=(ReinforceStep(0, 1.0, 5),),
        ),
    )


def _deadly_config():
    """Small-viewport config with the deadly balance (close, fast spawns)."""
    return make_config(viewport_w=20, viewport_h=10, defs=_deadly_defs())


def _max_ticks(cfg) -> int:
    """Regression-guard tick cap derived from cfg (never a hardcoded tick count)."""
    return int(cfg.sim_tps * _SAFETY_SECONDS)


def test_full_run_reaches_gameover():
    """A stationary player is overwhelmed: hp falls to <= 0 before the cap."""
    cfg = _deadly_config()
    cap = _max_ticks(cfg)
    result = run_until_gameover(cfg, random.Random(1234), None, cap)
    assert result["reached_gameover"] is True  # player hp fell to <= 0
    assert result["ticks"] < cap               # died before the safety cap


def test_full_run_reaches_gameover_while_moving():
    """A drifting player is faster than the walker but not the brute, so it dies."""
    cfg = _deadly_config()
    cap = _max_ticks(cfg)
    drift = (Intent(1, 0),)  # hold east; brutes (40) outrun the player, no escape
    result = run_until_gameover(cfg, random.Random(7), drift, cap)
    assert result["reached_gameover"] is True
    assert result["ticks"] < cap


def test_full_run_is_deterministic():
    """Same cfg + seed + input script => identical end tick and kill count."""
    cfg = _deadly_config()
    cap = _max_ticks(cfg)
    a = run_until_gameover(cfg, random.Random(1234), None, cap)
    b = run_until_gameover(cfg, random.Random(1234), None, cap)
    assert a["ticks"] == b["ticks"]  # same seed -> same end tick
    assert a["kills"] == b["kills"]
    assert a == b


def test_full_run_completes_within_wall_clock_budget():
    """The full-run regression finishes well under the 10s wall-clock budget."""
    cfg = _deadly_config()
    cap = _max_ticks(cfg)
    start = time.perf_counter()
    run_until_gameover(cfg, random.Random(1234), None, cap)
    assert time.perf_counter() - start < 10.0
