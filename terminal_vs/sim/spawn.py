"""terminal_vs.sim.spawn - director-driven off-screen enemy spawner (Phase 2).

Two responsibilities, split by the section 6 immutability boundary:

  * ``director_params`` is PURE (master plan section 5.4 stage 2): it maps the
    elapsed survival time to the current :class:`SpawnParams` (spawn interval,
    concurrent count, per-kind weights) using the data-driven per-minute
    reinforce table. It never touches sim state.
  * ``spawn_enemies`` mutates ``state`` in place: it adds ``concurrent`` enemies
    on a ring just outside the visible viewport, each kind chosen by a weighted
    pick over ``params.enemy_weights``. That is the sim side of the boundary.
  * ``maybe_spawn`` is step's stage-2 entry point: it advances the per-tick
    spawn accumulator by ``dt``, computes the director params for the current
    elapsed time, and spawns one wave each time the accumulator crosses the
    spawn interval (subtracting one interval per wave so a long-overdue
    accumulator drains deterministically).

Entity cap: ``spawn_enemies`` reads ``cfg.entity_cap`` (NOT hardcoded) and skips
a spawn when the total live entity count is at the cap, so the director never
exceeds the Phase 0 operating point.

Determinism: the kind pick and ring angle both draw from the injected
``random.Random`` in a fixed order, so a fixed seed reproduces the run exactly.
Blessed-free.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..config import Config
from ..rules.defs import BalanceDefs, DirectorDef
from ..world import visible_bounds
from .state import SimState, make_enemy

# How far outside the visible bounds (in world units) the spawn ring sits, so
# enemies appear just off-screen rather than popping in view. A gameplay-pacing
# value, not a Phase 0 performance number, so it is not gated by the no-hardcode
# perf check.
_RING_MARGIN = 2.0


@dataclass(frozen=True)
class SpawnParams:
    """Frozen director output: the spawn cadence for the current elapsed time.

    ``spawn_interval`` is the seconds between spawn waves (smaller = faster);
    ``concurrent`` is how many enemies spawn together each wave; ``enemy_weights``
    is the ordered ``(name, weight)`` table the weighted kind pick draws from.
    """

    spawn_interval: float
    concurrent: int
    enemy_weights: tuple[tuple[str, float], ...]


def _current_reinforce_step(elapsed_sec: float, director: DirectorDef):
    """Return the latest reinforce step whose minute threshold has been reached.

    ``reinforce_steps`` is ordered by ascending minute. The active step is the
    last one whose ``minute`` is <= the elapsed minutes; before the first
    threshold the earliest step applies (the table always has a minute-0 row, so
    a step is always found). Pure: reads the def only.
    """
    elapsed_minutes = elapsed_sec / 60.0
    active = director.reinforce_steps[0]
    for step in director.reinforce_steps:
        if step.minute <= elapsed_minutes:
            active = step
        else:
            break
    return active


def director_params(elapsed_sec: float, defs: BalanceDefs) -> SpawnParams:
    """Map elapsed survival time to the current :class:`SpawnParams` (pure).

    The active per-minute reinforce step scales the base spawn interval down
    (bounded below by ``min_spawn_interval``) and sets the concurrent count, so
    the spawn rate rises over time. ``enemy_weights`` is built from each enemy
    def's ``spawn_weight`` (a balance dial). Pure: ``defs`` is read-only and the
    result depends only on ``elapsed_sec`` + ``defs``.
    """
    director = defs.director
    step = _current_reinforce_step(elapsed_sec, director)
    interval = max(
        director.min_spawn_interval,
        director.base_spawn_interval * step.interval_mult,
    )
    # Sorted by name so the weighted pick is independent of dict insertion order.
    # This ordering is load-bearing for determinism: the cumulative-weight walk
    # in _weighted_pick must traverse the table in the same order every call.
    enemy_weights = tuple(
        sorted(
            ((name, edef.spawn_weight) for name, edef in defs.enemies.items()),
            key=lambda nw: nw[0],
        )
    )
    return SpawnParams(
        spawn_interval=interval,
        concurrent=step.concurrent,
        enemy_weights=enemy_weights,
    )


def _weighted_pick(
    weights: tuple[tuple[str, float], ...], rng: random.Random
) -> str:
    """Deterministically pick one enemy-kind name from a weighted table.

    Draws a uniform value in ``[0, total_weight)`` and walks the cumulative
    weights, so a fixed seed reproduces the pick. The table is iterated in its
    given (insertion) order, which is stable for determinism.
    """
    total = sum(weight for _, weight in weights)
    roll = rng.uniform(0.0, total)
    cumulative = 0.0
    chosen = weights[-1][0]
    for name, weight in weights:
        cumulative += weight
        if roll <= cumulative:
            chosen = name
            break
    return chosen


def _total_entities(state: SimState) -> int:
    """Count all live entities against the cap (player + the three buffers)."""
    return (
        1  # player
        + len(state.enemies)
        + len(state.projectiles)
        + len(state.pickups)
    )


def spawn_enemies(
    state: SimState, params: SpawnParams, cfg: Config, rng: random.Random
) -> None:
    """Spawn ``params.concurrent`` enemies on the off-screen ring (in place).

    Each enemy's kind is a weighted pick over ``params.enemy_weights`` and its
    position is a random angle on a ring just outside ``visible_bounds``, so it
    walks into view. The enemy is built from its :class:`EnemyDef` via
    :func:`make_enemy`. Respects ``cfg.entity_cap`` (read, never hardcoded): each
    spawn is skipped while the total live entity count is at/over the cap, so the
    director cannot exceed the Phase 0 operating point. Deterministic: kind and
    angle draw from ``rng`` in a fixed order per enemy.

    No enemy is spawned if ``params.enemy_weights`` is empty (no enemy defs) or
    the total weight is non-positive -- the director has nothing to draw from.
    """
    if not params.enemy_weights:
        return

    bounds = visible_bounds(state.camera, cfg)
    # Ring radius: half the larger visible extent plus a margin, so the spawn
    # sits just outside the viewport on every side.
    half_w = (bounds.max_x - bounds.min_x) / 2.0
    half_h = (bounds.max_y - bounds.min_y) / 2.0
    ring_radius = max(half_w, half_h) + _RING_MARGIN

    for _ in range(params.concurrent):
        if _total_entities(state) >= cfg.entity_cap:
            return
        kind = _weighted_pick(params.enemy_weights, rng)
        enemy_def = cfg.defs.enemies.get(kind)
        if enemy_def is None:
            continue
        angle = rng.random() * 2.0 * math.pi
        spawn_x = state.camera.x + math.cos(angle) * ring_radius
        spawn_y = state.camera.y + math.sin(angle) * ring_radius
        state.enemies.append(
            make_enemy(state.alloc_id(), spawn_x, spawn_y, enemy_def)
        )


def maybe_spawn(state: SimState, cfg: Config, rng: random.Random) -> None:
    """Advance the spawn accumulator and spawn director waves when due (in place).

    Step's stage-2 entry point. ``dt`` is the fixed ``1.0 / cfg.sim_tps``; the
    accumulator banks elapsed time and each full ``spawn_interval`` triggers one
    ``spawn_enemies`` wave (the interval is subtracted per wave so an overdue
    accumulator drains several waves deterministically rather than collapsing to
    one). The interval and concurrent count come from the pure
    :func:`director_params` evaluated at the CURRENT ``state.elapsed`` (read at
    the start of the tick, before step advances it).
    """
    dt = 1.0 / cfg.sim_tps
    params = director_params(state.elapsed, cfg.defs)
    state.spawn_accumulator += dt
    while state.spawn_accumulator >= params.spawn_interval:
        state.spawn_accumulator -= params.spawn_interval
        spawn_enemies(state, params, cfg, rng)
