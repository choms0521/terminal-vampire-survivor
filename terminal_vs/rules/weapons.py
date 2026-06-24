"""terminal_vs.rules.weapons - weapon firing logic (Day 4).

Pure functions: nearest-enemy target selection, cooldown expiry, and the
projectile launch spec. No side effects, no blessed, no global state. Aspect
distance comes from :func:`terminal_vs.world.sq_dist_aspect` -- the single
source of truth for on-screen distance -- so targeting is never redefined here.

Targeting tie-break (deterministic): when two enemies are at the same aspect
distance, the one with the LOWEST entity id wins. This makes target selection
reproducible and unit-testable (see tests/test_weapons.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from ..config import Config
from ..world import sq_dist_aspect


@dataclass(frozen=True)
class ProjectileSpec:
    """Frozen launch spec for one projectile (the pure result of a fire).

    Velocity is already aimed at the target and scaled to the weapon's
    projectile speed; ``damage`` and ``ttl`` come from the balance table. The sim
    layer reads this to construct a mutable Projectile entity -- this value
    itself is immutable and crosses the rules/sim boundary read-only.
    """

    vx: float
    vy: float
    damage: float
    ttl: float


def select_target(
    player_x: float,
    player_y: float,
    enemies,
    cfg: Config,
):
    """Return the id of the nearest enemy to the player, or ``None`` if none.

    Nearest is measured with aspect-corrected distance (``sq_dist_aspect``) so it
    matches what the player sees on screen. Pure: ``enemies`` is read-only.

    Tie-break: on equal distance the LOWEST entity id is chosen, which keeps the
    result deterministic regardless of iteration order.
    """
    best_id = None
    best_d2 = None
    for enemy in enemies:
        d2 = sq_dist_aspect(player_x, player_y, enemy.x, enemy.y, cfg)
        if (
            best_d2 is None
            or d2 < best_d2
            or (d2 == best_d2 and enemy.id < best_id)
        ):
            best_id = enemy.id
            best_d2 = d2
    return best_id


def should_fire(weapon_state, dt: float, cfg: Config) -> bool:
    """True once the weapon cooldown has elapsed.

    ``weapon_state`` exposes ``weapon_cooldown_remaining`` (seconds). The sim
    advances that timer by the fixed ``dt`` each tick BEFORE calling this, so
    readiness is a pure threshold on the already-advanced timer: ready when the
    remaining cooldown reaches zero. The ``dt`` is therefore NOT subtracted again
    here (doing so would double-count the tick and fire one tick early). Pure:
    does not mutate ``weapon_state``; the sim resets the timer (from
    ``cfg.balance.weapon.cooldown``) when it actually fires. ``dt`` is retained in
    the signature for the Phase 2 multi-weapon generalization.
    """
    return weapon_state.weapon_cooldown_remaining <= 0.0


def spawn_projectile_intent(
    player_x: float,
    player_y: float,
    target_x: float,
    target_y: float,
    cfg: Config,
) -> ProjectileSpec:
    """Return a :class:`ProjectileSpec` aimed from the player at the target.

    The direction is the plain Euclidean unit vector from player to target (a
    projectile travels in real world space; aspect correction is a screen-only
    concern), scaled to ``cfg.balance.weapon.projectile_speed``. Damage and ttl
    come from the same balance table. Pure.

    Degenerate case: if the target coincides with the player, the projectile is
    launched along +X with full speed -- a deterministic default that avoids a
    divide-by-zero on normalization.
    """
    weapon = cfg.balance.weapon
    dx = target_x - player_x
    dy = target_y - player_y
    dist = hypot(dx, dy)
    if dist == 0.0:
        vx = weapon.projectile_speed
        vy = 0.0
    else:
        scale = weapon.projectile_speed / dist
        vx = dx * scale
        vy = dy * scale
    return ProjectileSpec(
        vx=vx,
        vy=vy,
        damage=weapon.damage,
        ttl=weapon.projectile_ttl,
    )
