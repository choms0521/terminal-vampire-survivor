"""Headless full-run driver (Phase 3 Day 4) -- render-free, no terminal.

Drives ``sim/step.py`` with a scripted input sequence and an injected
``random.Random`` until the player dies (hp <= 0) or a regression-guard tick cap
is reached. It imports NOTHING from the render/terminal layer: it exercises only
the rules + simulation boundary and observes the sim state read-only (the
section-6 immutability boundary keeps mutation inside ``step``).

This is the objective measurement proxy for the master plan's "one full run is
playable" exit (Phase 3): "reaches game over" becomes ``sim.player.hp <= 0`` and
"deterministic" becomes "same cfg + seed + input script => identical end tick and
kill count".

The driver does NOT consume level-ups (the interactive loop owns the draft); a
pending level-up simply sits unconsumed while the run continues, which is the
correct passive-player model for a death-reaching regression.
"""

from __future__ import annotations

import random
from collections.abc import Iterable

from terminal_vs.config import Config
from terminal_vs.sim.state import NEUTRAL_INTENT, Intent, new_run
from terminal_vs.sim.step import step


def _iter_inputs(input_script: Iterable[Intent] | None, max_ticks: int):
    """Yield exactly ``max_ticks`` Intents, cycling a non-empty script.

    ``input_script`` is a sequence of Intents applied one per tick and cycled if
    shorter than ``max_ticks`` (so a one-element script is "hold this intent").
    An empty or absent script means a stationary player (the neutral intent),
    the most passive death-reaching scenario.
    """
    script = tuple(input_script) if input_script else (NEUTRAL_INTENT,)
    n = len(script)
    for tick in range(max_ticks):
        yield script[tick % n]


def run_until_gameover(
    cfg: Config,
    rng: random.Random,
    input_script: Iterable[Intent] | None,
    max_ticks: int,
) -> dict:
    """Step a fresh run until the player dies or ``max_ticks`` is hit.

    Returns a read-only summary dict:
      * ``reached_gameover``: True iff the player's hp fell to <= 0.
      * ``ticks``: how many ticks were simulated (the end tick on death).
      * ``kills``: cumulative enemy kills at the end of the run.

    ``max_ticks`` is a regression guard against an unbounded run (a too-easy
    balance that never kills the player), NOT a performance number; callers
    derive it from ``cfg`` (e.g. ``sim_tps`` * a safety duration).
    """
    sim = new_run(cfg, rng)
    ticks = 0
    for intent in _iter_inputs(input_script, max_ticks):
        step(sim, intent, cfg, rng)
        ticks += 1
        if sim.player.hp <= 0.0:
            break
    return {
        "reached_gameover": sim.player.hp <= 0.0,
        "ticks": ticks,
        "kills": sim.kills,
    }
