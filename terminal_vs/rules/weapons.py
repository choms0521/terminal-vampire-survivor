"""terminal_vs.rules.weapons - pure weapon firing logic (Phase 2, master 5.4 stage 4).

Each owned weapon ticks once per sim step. ``tick_weapon`` is a PURE function: it
reads a read-only :class:`FireContext` snapshot (player position/facing, enemy
positions, the weapon def, the passive-scaled attack-speed multiplier, dt, and
the operating-point ``aspect_x``) plus an injected ``random.Random``, and returns
a :class:`WeaponFireResult` value -- the projectiles or instant hits to spawn and
the updated cooldown. It never mutates its inputs and never touches buffers; the
sim layer (Chunk 2) applies the result in place.

Three targeting strategies (selected by ``weapon_def.targeting``):

  * ``"nearest"``            - one projectile salvo aimed at the nearest enemy.
  * ``"nearest_or_random"``  - aim at the nearest enemy; distance ties are broken
                               by an injected-RNG pick among the tied enemies
                               (deterministic for a fixed seed).
  * ``"forward_arc"``        - melee: instant hits on every enemy inside a forward
                               arc in front of the player's facing direction.

Determinism: aspect distance uses :func:`terminal_vs.world.sq_dist_aspect_x` (the
single on-screen-distance definition) with ``ctx.aspect_x``, and the "nearest"
tie-break falls to the LOWEST enemy id, so target selection is reproducible. No
blessed, no global state, no Chinese characters.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from random import Random

from ..world import sq_dist_aspect_x
from .defs import WeaponDef

# Cooldown written back when the weapon is ready but had no valid target this
# tick. Zero means "retry next tick" (ready but idle). Not a balance dial -- it
# is a control-flow sentinel, kept named so the no-hardcode balance gate has no
# bare zero literal to flag here.
_READY_IDLE_COOLDOWN: float = 0.0


@dataclass(frozen=True)
class ProjectileSpec:
    """Frozen launch spec for one projectile (the pure result of a fire).

    Velocity is already aimed at the target and scaled to the weapon's
    projectile speed; ``damage`` and ``ttl`` come from the weapon def. ``pierce``
    is how many enemies the projectile passes through before despawning (0 = stop
    on first hit). The sim layer reads this to build a mutable Projectile entity;
    the value itself is immutable and crosses the rules/sim boundary read-only.
    """

    vx: float
    vy: float
    damage: float
    ttl: float
    pierce: int = 0


@dataclass(frozen=True)
class InstantHitSpec:
    """Frozen instant-hit spec for a melee (forward_arc) strike.

    ``target_id`` names the enemy struck this fire; ``damage`` is applied by the
    sim layer directly (no projectile travels). One spec is produced per enemy
    inside the arc.
    """

    target_id: int
    damage: float


@dataclass(frozen=True)
class FireContext:
    """Read-only snapshot a weapon needs to decide a fire (master 5.4 stage 4).

    All fields are immutable values copied out of the mutable sim buffers, so
    ``tick_weapon`` can stay pure. ``enemy_positions`` carries the entity id
    alongside the coordinates so nearest targeting can tie-break to the lowest id
    and forward-arc hits can name which enemies were struck. ``aspect_x`` is the
    operating-point aspect factor (passed as a scalar rather than the whole
    Config, keeping the rules layer config-free).
    """

    player_pos: tuple[float, float]
    player_facing: tuple[float, float]                # last non-zero move dir
    enemy_positions: tuple[tuple[int, float, float], ...]  # (id, x, y) snapshot
    weapon_def: WeaponDef
    attack_speed_mult: float                          # passive-scaled cooldown factor
    dt: float                                         # fixed sim timestep (seconds)
    aspect_x: float                                   # operating-point aspect factor


@dataclass(frozen=True)
class WeaponFireResult:
    """Frozen result of one weapon tick (master 5.4 stage 4, ADR-001 boundary).

    ``new_cooldown`` is the cooldown the sim writes back for this weapon. When
    the weapon did not fire because no target was in range, ``new_cooldown`` is
    ``0.0`` so the weapon retries next tick (it is "ready but idle"). When still
    on cooldown, ``new_cooldown`` is the decremented remaining time.
    """

    fired: bool
    new_cooldown: float
    projectiles: tuple[ProjectileSpec, ...] = ()
    instant_hits: tuple[InstantHitSpec, ...] = ()


def _select_target(ctx: FireContext, rng: Random) -> tuple[int, float, float] | None:
    """Return the (id, x, y) of the enemy this weapon should aim at, or None.

    Nearest is measured with aspect-corrected distance so it matches what the
    player sees. For ``"nearest"`` a distance tie breaks to the LOWEST enemy id
    (deterministic regardless of iteration order). For ``"nearest_or_random"`` a
    distance tie is broken by an injected-RNG pick among the tied enemies, so the
    choice is deterministic for a fixed seed but spreads fire across equidistant
    targets.
    """
    if not ctx.enemy_positions:
        return None

    px, py = ctx.player_pos
    best_d2: float | None = None
    tied: list[tuple[int, float, float]] = []
    for enemy in ctx.enemy_positions:
        _eid, ex, ey = enemy
        d2 = sq_dist_aspect_x(px, py, ex, ey, ctx.aspect_x)
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            tied = [enemy]
        elif d2 == best_d2:
            tied.append(enemy)

    if len(tied) == 1:
        return tied[0]
    if ctx.weapon_def.targeting == "nearest_or_random":
        # Sort by id before rng.choice so the pick is independent of the caller's
        # buffer order (Chunk 2 may swap-remove enemies, changing iteration order).
        tied.sort(key=lambda e: e[0])
        return rng.choice(tied)
    # "nearest": tie-break to the lowest id.
    return min(tied, key=lambda e: e[0])


def _make_projectiles(
    ctx: FireContext, target: tuple[int, float, float]
) -> tuple[ProjectileSpec, ...]:
    """Build the projectile salvo aimed from the player at ``target``.

    The direction is the plain Euclidean unit vector from player to target (a
    projectile travels in real world space; aspect correction is screen-only),
    scaled to the weapon's projectile speed. ``projectile_count`` shots and the
    weapon's ``pierce`` are honored. Degenerate case: a target coinciding with
    the player launches along +X, avoiding divide-by-zero on normalization.
    """
    weapon = ctx.weapon_def
    px, py = ctx.player_pos
    _tid, tx, ty = target
    dx = tx - px
    dy = ty - py
    dist = hypot(dx, dy)
    if dist == 0.0:
        vx = weapon.projectile_speed
        vy = 0.0
    else:
        scale = weapon.projectile_speed / dist
        vx = dx * scale
        vy = dy * scale
    spec = ProjectileSpec(
        vx=vx,
        vy=vy,
        damage=weapon.damage,
        ttl=weapon.projectile_ttl,
        pierce=weapon.pierce,
    )
    count = max(1, weapon.projectile_count)
    return tuple(spec for _ in range(count))


def _make_forward_arc_hits(ctx: FireContext) -> tuple[InstantHitSpec, ...]:
    """Return instant hits on enemies inside the forward arc (melee swing).

    An enemy is hit when it is within ``weapon_def.arc_range`` (Euclidean world
    distance) AND lies inside the forward arc: the cosine of the angle between
    the player facing and the player->enemy direction is at least
    ``weapon_def.arc_half_width`` (1.0 = straight ahead only, 0.0 = the forward
    half-plane, so rear enemies are always excluded). Enemies exactly on the
    player are treated as in-arc (point-blank). Hits are ordered by enemy id for
    determinism.
    """
    weapon = ctx.weapon_def
    px, py = ctx.player_pos
    fx, fy = ctx.player_facing
    facing_len = hypot(fx, fy)
    if facing_len == 0.0:
        # No facing yet: default to +X so the arc is well-defined.
        fx, fy, facing_len = 1.0, 0.0, 1.0
    inv_facing = 1.0 / facing_len

    hits: list[InstantHitSpec] = []
    for eid, ex, ey in ctx.enemy_positions:
        dx = ex - px
        dy = ey - py
        dist = hypot(dx, dy)
        if dist > weapon.arc_range:
            continue
        if dist == 0.0:
            # Point-blank: always inside the arc.
            hits.append(InstantHitSpec(target_id=eid, damage=weapon.damage))
            continue
        # cos(angle) between facing and player->enemy direction.
        cos_angle = (dx * fx + dy * fy) * inv_facing / dist
        if cos_angle >= weapon.arc_half_width:
            hits.append(InstantHitSpec(target_id=eid, damage=weapon.damage))

    hits.sort(key=lambda h: h.target_id)
    return tuple(hits)


def tick_weapon(
    cooldown_remaining: float, ctx: FireContext, rng: Random
) -> WeaponFireResult:
    """Advance one weapon by ``ctx.dt`` and decide whether it fires (pure).

    Cooldown gate: ``remaining = cooldown_remaining - dt``; if still positive the
    weapon does not fire and ``new_cooldown`` is the decremented remaining time.
    Once ready, the targeting strategy decides the fire:

      * ``"forward_arc"`` resolves instant hits in front of the player. With no
        enemy in the arc the weapon does not fire and ``new_cooldown`` is 0.0 so
        it retries next tick (it is ready but idle).
      * otherwise (``"nearest"`` / ``"nearest_or_random"``) it aims a projectile
        salvo at the selected target; with no target it does not fire and
        ``new_cooldown`` is 0.0.

    On a successful fire the cooldown resets to
    ``weapon_def.cooldown * attack_speed_mult`` (the attack-speed passive is
    already folded into ``attack_speed_mult`` by effective_stats, so the reset is
    a single multiply). Pure: ``ctx`` and ``rng`` state aside, no input is
    mutated and no buffer is touched.
    """
    remaining = cooldown_remaining - ctx.dt
    if remaining > 0.0:
        return WeaponFireResult(fired=False, new_cooldown=remaining)

    reset = ctx.weapon_def.cooldown * ctx.attack_speed_mult

    if ctx.weapon_def.targeting == "forward_arc":
        hits = _make_forward_arc_hits(ctx)
        if not hits:
            return WeaponFireResult(fired=False, new_cooldown=_READY_IDLE_COOLDOWN)
        return WeaponFireResult(
            fired=True, new_cooldown=reset, instant_hits=hits
        )

    target = _select_target(ctx, rng)
    if target is None:
        return WeaponFireResult(fired=False, new_cooldown=_READY_IDLE_COOLDOWN)
    specs = _make_projectiles(ctx, target)
    return WeaponFireResult(fired=True, new_cooldown=reset, projectiles=specs)
