"""terminal_vs.sim.step - tick pipeline (Day 3).

``step`` runs the master section 5.4 ten-stage pipeline for one simulation tick,
mutating ``SimState`` in place. This is the ONLY place the entity buffers are
mutated; the rules layer it calls is pure (returns values, never mutates).

Immutability boundary (section 6 / ADR-001):

    +---------------------------------------------------------------+
    | This function mutates state's entity buffers in-place. The    |
    | rules/* functions it calls take read-only inputs and return   |
    | new values. The mutable state never leaks outside the sim     |
    | layer as a writable handle.                                   |
    +---------------------------------------------------------------+

Determinism: the per-tick dt is the FIXED ``1.0 / cfg.sim_tps`` -- no wall-clock
time is read here. All randomness flows through the injected ``random.Random``
with a fixed call order, and collision candidate ids from the spatial hash are
processed in sorted order. Two runs with the same seed produce identical state.

Blessed-free.
"""

from __future__ import annotations

import random
from math import hypot

from ..config import Config
from ..rules import damage as rules_damage
from ..rules import leveling as rules_leveling
from ..rules import weapons as rules_weapons
from .spatial import SpatialHash
from .spawn import maybe_spawn
from .state import (
    Enemy,
    Intent,
    Pickup,
    Projectile,
    SimState,
)

# Collision radii (world units). These are gameplay hitbox sizes, not Phase 0
# performance numbers, so they are not gated by the no-hardcode perf check.
_PROJECTILE_HIT_RADIUS = 0.75
_ENEMY_TOUCH_RADIUS = 0.75
# Knockback applied to the player when an enemy touches it.
_PLAYER_KNOCKBACK_FORCE = 1.5
# Contact damage an enemy deals to the player on touch, per tick.
_ENEMY_CONTACT_DAMAGE = 5.0
# Xp value of a gem dropped on enemy death.
_XP_GEM_VALUE = 1.0
# Player base move speed as a multiple of the enemy move speed. Strictly > 1 so
# the player can out-run enemies and kite -- the core survival mechanic that
# keeps the vertical slice playable (with equal speed, enemies always catch the
# player and the contact damage is unavoidable). A Phase 1 playability constant;
# externalizing player speed/hp into balance.toml and tuning the exact value is
# deferred to the Phase 3 balancing pass.
_PLAYER_SPEED_MULT = 1.5
# Spatial-hash bucket size (world units) used for collision queries.
_COLLISION_CELL_SIZE = 2.0
# Despawn distance: enemies/pickups farther than this many viewport-half-widths
# from the camera are culled. Expressed as a multiple so it scales with the
# configured viewport rather than hardcoding a world distance.
_DESPAWN_VIEWPORT_MULTIPLE = 3.0


def step(state: SimState, intent: Intent, cfg: Config, rng: random.Random) -> None:
    """Advance the simulation one fixed tick, mutating ``state`` in place.

    See the module docstring for the immutability boundary. ``intent`` is
    movement-only (8-direction); level-up choice handling is the loop's job.
    """
    dt = 1.0 / cfg.sim_tps  # FIXED timestep; never read wall-clock time here.

    # Each stage carries an impl/defer marker. "impl" stages are fully built for
    # Phase 1; the trailing note names the extension deferred to Phase 2.
    _apply_input(state, intent, cfg, dt)            # 1) input: impl 8-dir; analog/dash deferred Phase 2
    maybe_spawn(state, cfg, rng)                    # 2) spawn: minimal flat rate; director curve placeholder, deferred Phase 2
    _move_enemies_toward_player(state, cfg, dt)     # 3) enemy AI: impl chase; 2nd enemy type / flocking deferred Phase 2
    _fire_weapons(state, cfg, dt)                   # 4) weapon: impl dagger cooldown+fire; multi-weapon/evolution deferred Phase 2
    _advance_projectiles(state, dt)                 # 5) projectiles: impl move+ttl; pierce/homing deferred Phase 2
    _resolve_collisions(state, cfg)                 # 6) collisions: impl proj<->enemy, enemy<->player+knockback; hazard/aura deferred Phase 2
    _drop_xp_on_death(state, rng)                   # 7) death->xp drop: impl fixed gem; drop-table variety deferred Phase 2
    _collect_pickups(state, cfg)                    # 8) pickup->xp->level flag: impl magnet collect; magnet upgrades deferred Phase 2
    _cleanup_dead_and_far(state, cfg)               # 9) cleanup: impl dead removal + far despawn; entity-cap pressure tuning deferred Phase 2
    state.camera.follow(state.player)               # 10) camera: impl follow; screen-shake/lerp deferred Phase 2

    state.elapsed += dt
    # NOTE: evolution / multi-weapon / hazard whole-stages are absent in Phase 1
    # (deferred to Phase 2); there is no TODO(phase2) work hidden inside step.


# --- Stage 1: input ----------------------------------------------------------
def _apply_input(state: SimState, intent: Intent, cfg: Config, dt: float) -> None:
    """Set the player's velocity from the 8-direction intent and integrate it.

    The intent vector is normalized so diagonal movement is not faster than
    orthogonal movement, then scaled by the player's base move speed. Phase 1
    derives that from the enemy move speed times ``_PLAYER_SPEED_MULT`` (> 1) so
    the player out-runs enemies and can kite -- the core survival loop. Tuning
    and externalizing this value is deferred to the Phase 3 balancing pass.
    """
    dx = float(intent.dx)
    dy = float(intent.dy)
    speed = cfg.balance.enemy.move_speed * _PLAYER_SPEED_MULT
    mag = hypot(dx, dy)
    if mag == 0.0:
        state.player.vx = 0.0
        state.player.vy = 0.0
    else:
        state.player.vx = dx / mag * speed
        state.player.vy = dy / mag * speed
    state.player.x += state.player.vx * dt
    state.player.y += state.player.vy * dt


# --- Stage 3: enemy AI -------------------------------------------------------
def _move_enemies_toward_player(state: SimState, cfg: Config, dt: float) -> None:
    """Move every enemy straight toward the player at the balance move speed.

    Plain Euclidean steering (physical movement, not screen distance). Enemies
    are iterated in list order for deterministic updates.
    """
    speed = cfg.balance.enemy.move_speed
    px, py = state.player.x, state.player.y
    for enemy in state.enemies:
        dx = px - enemy.x
        dy = py - enemy.y
        dist = hypot(dx, dy)
        if dist == 0.0:
            enemy.vx = 0.0
            enemy.vy = 0.0
            continue
        enemy.vx = dx / dist * speed
        enemy.vy = dy / dist * speed
        enemy.x += enemy.vx * dt
        enemy.y += enemy.vy * dt


# --- Stage 4: weapon cooldown + fire -----------------------------------------
def _fire_weapons(state: SimState, cfg: Config, dt: float) -> None:
    """Tick the weapon cooldown and, when ready, fire at the nearest enemy.

    Multi-weapon / evolution firing is deferred to Phase 2; Phase 1 fires the
    single dagger. The target and projectile spec come from pure rules.weapons.
    """
    player = state.player
    # Advance the cooldown timer toward readiness.
    player.weapon_cooldown_remaining = max(
        0.0, player.weapon_cooldown_remaining - dt
    )
    if not rules_weapons.should_fire(player, dt, cfg):
        return
    if not state.enemies:
        return
    target_id = rules_weapons.select_target(player.x, player.y, state.enemies, cfg)
    if target_id is None:
        return
    target = _enemy_by_id(state, target_id)
    if target is None:
        return
    spec = rules_weapons.spawn_projectile_intent(
        player.x, player.y, target.x, target.y, cfg
    )
    state.projectiles.append(
        Projectile(
            entity_id=state.alloc_id(),
            x=player.x,
            y=player.y,
            vx=spec.vx,
            vy=spec.vy,
            damage=spec.damage,
            ttl=spec.ttl,
            team=player.team,
        )
    )
    # Reset cooldown from the balance table (single-weapon Phase 1 behavior).
    player.weapon_cooldown_remaining = cfg.balance.weapon.cooldown


# --- Stage 5: projectile move + ttl ------------------------------------------
def _advance_projectiles(state: SimState, dt: float) -> None:
    """Integrate projectile positions and decrement their ttl in place."""
    for proj in state.projectiles:
        proj.x += proj.vx * dt
        proj.y += proj.vy * dt
        proj.ttl -= dt


# --- Stage 6: collision resolve ----------------------------------------------
def _resolve_collisions(state: SimState, cfg: Config) -> None:
    """Resolve projectile->enemy damage and enemy->player contact + knockback.

    A spatial hash over enemies turns each projectile/player query into a
    local-bucket scan (master section 5.3). Candidate ids come back sorted, so
    resolution order is deterministic. Damage and knockback use pure rules.damage;
    hazard/aura damage is deferred to Phase 2.
    """
    if not state.enemies:
        return
    grid = SpatialHash.build(state.enemies, _COLLISION_CELL_SIZE)

    # Projectile -> enemy: each projectile damages the NEAREST live in-radius
    # enemy (parity with rules.weapons targeting). One hit per projectile per
    # tick keeps it simple. candidate_ids is sorted ascending and we only replace
    # on a strictly smaller distance, so an exact distance tie breaks to the
    # lowest id -- selection stays deterministic.
    for proj in state.projectiles:
        if proj.ttl <= 0.0:
            continue
        candidate_ids = grid.query_near(proj.x, proj.y, _PROJECTILE_HIT_RADIUS)
        best_enemy = None
        best_d2 = None
        for enemy_id in candidate_ids:
            enemy = _enemy_by_id(state, enemy_id)
            if enemy is None or rules_damage.is_dead(enemy.hp):
                continue
            dx = enemy.x - proj.x
            dy = enemy.y - proj.y
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best_enemy = enemy
                best_d2 = d2
        if best_enemy is not None:
            best_enemy.hp = rules_damage.apply_hit(best_enemy.hp, proj.damage)
            proj.ttl = 0.0  # consume the projectile on hit

    # Enemy -> player: contact damage + knockback pushing the player away.
    player = state.player
    touch_ids = grid.query_near(player.x, player.y, _ENEMY_TOUCH_RADIUS)
    for enemy_id in touch_ids:  # sorted ascending
        enemy = _enemy_by_id(state, enemy_id)
        if enemy is None:
            continue
        player.hp = rules_damage.apply_hit(player.hp, _ENEMY_CONTACT_DAMAGE)
        new_x, new_y = rules_damage.knockback(
            (player.x, player.y), (enemy.x, enemy.y), _PLAYER_KNOCKBACK_FORCE
        )
        player.x, player.y = new_x, new_y


# --- Stage 7: death -> xp gem drop -------------------------------------------
def _drop_xp_on_death(state: SimState, rng: random.Random) -> None:
    """Drop an xp gem at each dead enemy's position.

    ``rng`` is accepted for future drop-table variety (deferred to Phase 2);
    Phase 1 drops a single fixed-value gem per kill, so it is unused here.
    """
    for enemy in state.enemies:
        if rules_damage.is_dead(enemy.hp):
            state.pickups.append(
                Pickup(
                    entity_id=state.alloc_id(),
                    x=enemy.x,
                    y=enemy.y,
                    xp=_XP_GEM_VALUE,
                )
            )


# --- Stage 8: pickup collect -> xp -> level-up flag ---------------------------
def _collect_pickups(state: SimState, cfg: Config) -> None:
    """Collect pickups within magnet range, accrue xp, set the level-up flag.

    Xp accrual and the pending check are pure rules.leveling. The flag is SET
    here when xp crosses the threshold; it is CLEARED by the loop applying a
    choice (step never clears it). Multi-pickup magnet upgrades are Phase 2.
    """
    magnet_r = cfg.balance.magnet_range
    magnet_r2 = magnet_r * magnet_r
    px, py = state.player.x, state.player.y
    collected_xp = 0.0
    remaining: list[Pickup] = []
    for pickup in state.pickups:
        dx = pickup.x - px
        dy = pickup.y - py
        if dx * dx + dy * dy <= magnet_r2:
            collected_xp += pickup.xp
        else:
            remaining.append(pickup)
    if collected_xp > 0.0:
        state.pickups = remaining
        state.level_state = rules_leveling.accrue_xp(state.level_state, collected_xp)
    if rules_leveling.level_up_pending(state.level_state, cfg):
        state.level_up_pending = True


# --- Stage 9: cleanup dead + far despawn -------------------------------------
def _cleanup_dead_and_far(state: SimState, cfg: Config) -> None:
    """Remove dead enemies, expired projectiles, and far-off entities.

    Far despawn keeps the entity count bounded under ``cfg.entity_cap``: enemies
    and pickups beyond a viewport-scaled distance from the camera are dropped.
    """
    cam_x, cam_y = state.camera.x, state.camera.y
    # Despawn distance scales with the configured viewport (no hardcoded world
    # distance): a multiple of the larger world half-extent.
    half_w_world = (cfg.viewport_w / 2.0) / cfg.aspect_x
    half_h_world = cfg.viewport_h / 2.0
    despawn_r = max(half_w_world, half_h_world) * _DESPAWN_VIEWPORT_MULTIPLE
    despawn_r2 = despawn_r * despawn_r

    def _far(entity) -> bool:
        dx = entity.x - cam_x
        dy = entity.y - cam_y
        return dx * dx + dy * dy > despawn_r2

    state.enemies = [
        e for e in state.enemies
        if not rules_damage.is_dead(e.hp) and not _far(e)
    ]
    state.projectiles = [p for p in state.projectiles if p.ttl > 0.0]
    state.pickups = [p for p in state.pickups if not _far(p)]


# --- helpers -----------------------------------------------------------------
def _enemy_by_id(state: SimState, enemy_id: int) -> Enemy | None:
    """Return the enemy with ``enemy_id`` or None (linear scan over the buffer)."""
    for enemy in state.enemies:
        if enemy.id == enemy_id:
            return enemy
    return None
