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
    is the ordered ``(name, weight)`` table of REGULAR enemies the weighted kind
    pick draws from. ``boss_due`` is True on the tick that crosses a boss spawn
    mark; ``boss_weights`` is the ordered boss-only subset drawn from then.
    """

    spawn_interval: float
    concurrent: int
    enemy_weights: tuple[tuple[str, float], ...]
    boss_due: bool = False
    boss_weights: tuple[tuple[str, float], ...] = ()


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


def director_params(
    elapsed_sec: float, defs: BalanceDefs, prev_elapsed: float = 0.0
) -> SpawnParams:
    """Map elapsed survival time to the current :class:`SpawnParams` (pure).

    The active per-minute reinforce step scales the base spawn interval down
    (bounded below by ``min_spawn_interval``) and sets the concurrent count, so
    the spawn rate rises over time. Pure: ``defs`` is read-only and the result
    depends only on ``elapsed_sec``, ``prev_elapsed``, and ``defs``.

    The enemy table is PARTITIONED: ``enemy_weights`` holds only the regular
    (non-boss) enemies the per-wave weighted pick draws from, while ``boss_weights``
    holds the boss-flagged subset drawn from only when ``boss_due`` fires.
    ``boss_due`` is True on the single tick whose (``prev_elapsed``, ``elapsed_sec``]
    window contains a ``director.boss_spawn_times`` mark -- and only when boss
    enemies exist, so a boss-free balance never trips it (``prev_elapsed`` defaults
    to 0.0, preserving the Phase 2 two-argument call sites).
    """
    director = defs.director
    step = _current_reinforce_step(elapsed_sec, director)
    interval = max(
        director.min_spawn_interval,
        director.base_spawn_interval * step.interval_mult,
    )
    # Partition the enemy table into the regular weighted pool and the boss subset.
    # Both are sorted by name so the cumulative-weight walk in _weighted_pick is
    # deterministic (independent of dict insertion order) -- load-bearing.
    regular = tuple(
        sorted(
            (
                (name, edef.spawn_weight)
                for name, edef in defs.enemies.items()
                if not edef.boss
            ),
            key=lambda nw: nw[0],
        )
    )
    bosses = tuple(
        sorted(
            (
                (name, edef.spawn_weight)
                for name, edef in defs.enemies.items()
                if edef.boss
            ),
            key=lambda nw: nw[0],
        )
    )
    boss_due = bool(bosses) and any(
        prev_elapsed < t <= elapsed_sec for t in director.boss_spawn_times
    )
    return SpawnParams(
        spawn_interval=interval,
        concurrent=step.concurrent,
        enemy_weights=regular,
        boss_due=boss_due,
        boss_weights=bosses,
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


def _ring_spawn_xy(
    state: SimState, cfg: Config, rng: random.Random
) -> tuple[float, float]:
    """A random point on the off-screen spawn ring (just outside the viewport).

    The ring radius is half the larger visible extent plus ``_RING_MARGIN`` so the
    point sits just off-screen on every side; the angle draws once from ``rng``, so
    a caller that picks a kind first keeps a fixed (kind, angle) rng draw order.
    """
    bounds = visible_bounds(state.camera, cfg)
    half_w = (bounds.max_x - bounds.min_x) / 2.0
    half_h = (bounds.max_y - bounds.min_y) / 2.0
    ring_radius = max(half_w, half_h) + _RING_MARGIN
    angle = rng.random() * 2.0 * math.pi
    return (
        state.camera.x + math.cos(angle) * ring_radius,
        state.camera.y + math.sin(angle) * ring_radius,
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
    # Non-positive total weight: nothing to draw from. config validates each
    # spawn_weight > 0, but a directly-built BalanceDefs (e.g. a test) could carry
    # zero/negative weights, so guard here to match the documented behavior rather
    # than let the weighted pick run on a zero-total table.
    if sum(weight for _, weight in params.enemy_weights) <= 0:
        return

    for _ in range(params.concurrent):
        if _total_entities(state) >= cfg.entity_cap:
            return
        kind = _weighted_pick(params.enemy_weights, rng)
        enemy_def = cfg.defs.enemies.get(kind)
        if enemy_def is None:
            continue
        spawn_x, spawn_y = _ring_spawn_xy(state, cfg, rng)
        state.enemies.append(
            make_enemy(state.alloc_id(), spawn_x, spawn_y, enemy_def)
        )


def _boss_alive(state: SimState, defs: BalanceDefs) -> bool:
    """True if a boss-flagged enemy is currently alive in the buffer.

    The director keeps at most one boss alive at a time: this guard makes a second
    boss_due crossing a no-op while the first boss still lives.
    """
    for enemy in state.enemies:
        edef = defs.enemies.get(enemy.kind)
        if edef is not None and edef.boss:
            return True
    return False


def _spawn_boss(
    state: SimState, params: SpawnParams, cfg: Config, rng: random.Random
) -> None:
    """Spawn one boss on the off-screen ring (in place), kind chosen by weighted
    pick over the boss subset. Respects ``cfg.entity_cap``. Deterministic: the kind
    then the ring angle draw from ``rng`` in that order.
    """
    if not params.boss_weights:
        return
    if _total_entities(state) >= cfg.entity_cap:
        return
    kind = _weighted_pick(params.boss_weights, rng)
    enemy_def = cfg.defs.enemies.get(kind)
    if enemy_def is None:
        return
    spawn_x, spawn_y = _ring_spawn_xy(state, cfg, rng)
    state.enemies.append(make_enemy(state.alloc_id(), spawn_x, spawn_y, enemy_def))


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
    params = director_params(state.elapsed, cfg.defs, prev_elapsed=state.elapsed - dt)
    state.spawn_accumulator += dt
    while state.spawn_accumulator >= params.spawn_interval:
        state.spawn_accumulator -= params.spawn_interval
        spawn_enemies(state, params, cfg, rng)
    # Boss spawn is OFF the wave accumulator: evaluated once per tick on the
    # (prev, now] crossing of a boss_spawn_times mark, guarded so only one boss
    # lives at a time. Drawn AFTER the regular waves so a boss-free balance
    # (boss_due always False -> no boss rng draw) leaves the existing seeded spawn
    # stream unchanged.
    if params.boss_due and not _boss_alive(state, cfg.defs):
        _spawn_boss(state, params, cfg, rng)
