"""terminal_vs.sim.spawn - off-screen enemy spawner (Day 3).

``maybe_spawn`` adds at most one enemy per tick from a ring just outside the
visible viewport, at a FLAT probability. The time-based difficulty director
(rising spawn rate / enemy escalation) is a PLACEHOLDER here and lands in
Phase 2 -- Phase 1 spawns one enemy type at a constant rate.

Boundary note: this function mutates ``state`` (a sim-owned mutable buffer) in
place. That is the sim side of the section 6 immutability boundary -- all
mutation lives inside sim modules; the rules layer it may call stays pure.

Determinism: spawn timing and ring angle both draw from the injected
``random.Random`` so a fixed seed reproduces the run exactly.
"""

from __future__ import annotations

import math
import random

from ..config import Config
from ..world import visible_bounds
from .state import Enemy, SimState

# Flat per-tick spawn probability and ring placement constants. These are
# gameplay-pacing values, not Phase 0 performance numbers, so they are not
# gated by the no-hardcode perf check. The director curve that would replace the
# flat probability is deferred to Phase 2 (placeholder below).
_FLAT_SPAWN_CHANCE = 0.25
# How far outside the visible bounds (in world units) the spawn ring sits, so
# enemies appear just off-screen rather than popping in view.
_RING_MARGIN = 2.0


def maybe_spawn(state: SimState, cfg: Config, rng: random.Random) -> None:
    """Maybe spawn one enemy from the off-screen ring (flat rate, in place).

    Director difficulty curve: PLACEHOLDER -- the flat ``_FLAT_SPAWN_CHANCE`` is a
    stand-in for the Phase 2 time-based escalation; ``state.elapsed`` is
    available for that future curve but unused here.

    The enemy is placed on a ring just outside ``visible_bounds`` at a random
    angle, so it walks into view. Respects ``cfg.entity_cap``: if the total
    entity count is at the cap, no spawn occurs.
    """
    # deferred (Phase 2): replace the flat chance with a director curve driven by
    # state.elapsed. For now spawning is a constant Bernoulli trial.
    if rng.random() >= _FLAT_SPAWN_CHANCE:
        return

    # Entity-cap guard: count all live entities against the configured cap.
    total = (
        1  # player
        + len(state.enemies)
        + len(state.projectiles)
        + len(state.pickups)
    )
    if total >= cfg.entity_cap:
        return

    bounds = visible_bounds(state.camera, cfg)
    # Ring radius: half the larger visible extent plus a margin, so the spawn
    # sits just outside the viewport on every side.
    half_w = (bounds.max_x - bounds.min_x) / 2.0
    half_h = (bounds.max_y - bounds.min_y) / 2.0
    ring_radius = max(half_w, half_h) + _RING_MARGIN

    angle = rng.random() * 2.0 * math.pi
    spawn_x = state.camera.x + math.cos(angle) * ring_radius
    spawn_y = state.camera.y + math.sin(angle) * ring_radius

    enemy = Enemy(
        entity_id=state.alloc_id(),
        x=spawn_x,
        y=spawn_y,
        hp=cfg.balance.enemy.hp,
    )
    state.enemies.append(enemy)
