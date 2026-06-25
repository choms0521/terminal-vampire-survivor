"""terminal_vs.sim.step - tick pipeline (Phase 2).

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

Phase 2 systems wired in: a time-based director spawn (stage 2), per-kind enemy
speed (stage 3), multi-weapon firing with passive-scaled cooldowns and
projectile/instant-hit specs (stage 4), pierce-aware collisions (stage 6), and
magnet-passive-scaled pickup with a BuildState xp accrual (stage 8).

Determinism: the per-tick dt is the FIXED ``1.0 / cfg.sim_tps`` -- no wall-clock
time is read here. All randomness flows through the injected ``random.Random``
with a fixed call order (spawn before fire; weapons iterate ``build.weapon_levels``
in order), and collision candidate ids from the spatial hash are processed in
sorted order. Two runs with the same seed produce identical state.

Blessed-free.
"""

from __future__ import annotations

import random
from math import hypot

from ..config import Config
from ..rules import damage as rules_damage
from ..rules import leveling as rules_leveling
from ..rules import weapons as rules_weapons
from ..rules.defs import BalanceDefs
from .spatial import SpatialHash
from .spawn import maybe_spawn
from .state import (
    Enemy,
    Intent,
    Pickup,
    Projectile,
    SimState,
    reconcile_weapon_cooldowns,
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
# Player base move speed as a multiple of the WALKER (basic chaser) move speed.
# Strictly > 1 so the player can out-run walkers and kite -- the core survival
# mechanic that keeps the vertical slice playable. The swarm enemy is
# intentionally faster than the player (it may catch up), so the invariant is
# measured against the walker. A playability constant; externalizing player
# speed/hp into balance.toml and tuning the value is deferred to Phase 3.
_PLAYER_SPEED_MULT = 1.5
# Reference enemy kind whose move speed defines the player's base speed.
_PLAYER_SPEED_REFERENCE_KIND = "walker"
# Degenerate fallback base speed, used ONLY when a balance defines no enemies at
# all -- unreachable via load_config (which always injects a default enemy set),
# so it is reachable only through a direct BalanceDefs construction in tests. It
# is a guard so _apply_input never fails on an empty enemy table, NOT a tunable
# balance dial; the normal path reads the reference (or slowest) enemy's speed.
_PLAYER_FALLBACK_BASE_SPEED = 2.5
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

    _apply_input(state, intent, cfg, dt)            # 1) input: 8-dir move + facing
    state.camera.follow(state.player)               #    re-center on the player after the input move so
                                                    #    spawn/despawn below use THIS tick's viewport, not a
                                                    #    1-tick-stale one (followed again at stage 10 post-knockback)
    maybe_spawn(state, cfg, rng)                    # 2) spawn: director-driven (time-based rate + reinforce steps)
    _move_enemies_toward_player(state, cfg, dt)     # 3) enemy AI: chase at each kind's move speed
    _fire_weapons(state, cfg, dt, rng)              # 4) weapon: tick every owned weapon (projectiles + instant hits)
    _advance_projectiles(state, dt)                 # 5) projectiles: move + ttl
    _resolve_collisions(state, cfg)                 # 6) collisions: pierce-aware proj<->enemy, enemy<->player+knockback
    _drop_xp_on_death(state, rng)                   # 7) death->xp drop: fixed gem
    _collect_pickups(state, cfg)                    # 8) pickup->xp->level flag: magnet-passive-scaled
    _cleanup_dead_and_far(state, cfg)               # 9) cleanup: dead removal + far despawn
    state.camera.follow(state.player)               # 10) camera: final follow after knockback so the rendered frame is centered

    state.elapsed += dt


# --- Stage 1: input ----------------------------------------------------------
def _reference_move_speed(defs: BalanceDefs) -> float:
    """Base enemy move speed the player's speed is measured against.

    Prefers the configured reference kind (``_PLAYER_SPEED_REFERENCE_KIND``,
    "walker"). If a data-driven balance omits that kind, fall back deterministically
    to the SLOWEST defined enemy (min move_speed, name tie-break) so this never
    KeyErrors on a custom enemy set -- mirroring the defensive ``.get()`` the enemy
    AI already uses. The no-enemy case is degenerate (unreachable via load_config)
    and uses a fixed guard value.
    """
    ref = defs.enemies.get(_PLAYER_SPEED_REFERENCE_KIND)
    if ref is not None:
        return ref.move_speed
    if defs.enemies:
        slowest = min(defs.enemies.values(), key=lambda e: (e.move_speed, e.name))
        return slowest.move_speed
    return _PLAYER_FALLBACK_BASE_SPEED


def _apply_input(state: SimState, intent: Intent, cfg: Config, dt: float) -> None:
    """Set the player's velocity from the 8-direction intent and integrate it.

    The intent vector is normalized so diagonal movement is not faster than
    orthogonal movement, then scaled by the player's base move speed. The base
    speed is the WALKER move speed times ``_PLAYER_SPEED_MULT`` (> 1) and the
    move-speed passive multiplier, so the player out-runs walkers and can kite.
    On a non-zero intent the player's facing is updated to the (normalized) move
    direction so the forward_arc weapon aims where the player is heading; an idle
    tick keeps the previous facing.
    """
    stats = rules_leveling.effective_stats(state.build, cfg.defs)
    base_speed = _reference_move_speed(cfg.defs)
    speed = base_speed * _PLAYER_SPEED_MULT * stats.move_speed_mult

    dx = float(intent.dx)
    dy = float(intent.dy)
    mag = hypot(dx, dy)
    if mag == 0.0:
        state.player.vx = 0.0
        state.player.vy = 0.0
    else:
        ux = dx / mag
        uy = dy / mag
        state.player.vx = ux * speed
        state.player.vy = uy * speed
        # Track the last non-zero direction for forward_arc targeting.
        state.player.facing_x = ux
        state.player.facing_y = uy
    state.player.x += state.player.vx * dt
    state.player.y += state.player.vy * dt


# --- Stage 3: enemy AI -------------------------------------------------------
def _move_enemies_toward_player(state: SimState, cfg: Config, dt: float) -> None:
    """Move every enemy straight toward the player at ITS kind's move speed.

    Each enemy's speed comes from ``cfg.defs.enemies[enemy.kind].move_speed`` so
    the two kinds (slow walker, fast swarm) chase at different rates. Plain
    Euclidean steering (physical movement, not screen distance). Enemies are
    iterated in list order for deterministic updates.
    """
    px, py = state.player.x, state.player.y
    for enemy in state.enemies:
        edef = cfg.defs.enemies.get(enemy.kind)
        speed = edef.move_speed if edef is not None else 0.0
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


# --- Stage 4: weapon cooldown + fire (multi-weapon) --------------------------
def _fire_weapons(
    state: SimState, cfg: Config, dt: float, rng: random.Random
) -> None:
    """Tick every owned weapon, spawning projectiles / applying instant hits.

    For each weapon in ``state.build.weapon_levels`` (fixed iteration order for
    determinism), build a read-only :class:`FireContext` from the current player
    pose + an enemy-position snapshot and call the pure ``tick_weapon``. The
    attack-speed passive is folded once via ``effective_stats``. A fired result
    yields projectile specs (appended as Projectile entities, carrying pierce) or
    instant-hit specs (damage applied directly to the named enemy). The weapon's
    new cooldown is written back to ``state.weapon_cooldowns``.

    Phase 2 note: the weapon LEVEL is tracked (and gates evolution at max level)
    but does NOT scale per-shot numbers here -- per-level stat scaling is a
    documented Phase 3 concern, so no level-driven curve is applied to damage /
    count / cooldown. Each shot uses the weapon def's base numbers.
    """
    reconcile_weapon_cooldowns(state)
    stats = rules_leveling.effective_stats(state.build, cfg.defs)
    player = state.player
    enemy_positions = tuple((e.id, e.x, e.y) for e in state.enemies)
    player_pos = (player.x, player.y)
    player_facing = (player.facing_x, player.facing_y)

    for name, _level in state.build.weapon_levels:
        wdef = cfg.defs.weapons.get(name)
        if wdef is None:
            continue
        ctx = rules_weapons.FireContext(
            player_pos=player_pos,
            player_facing=player_facing,
            enemy_positions=enemy_positions,
            weapon_def=wdef,
            attack_speed_mult=stats.attack_speed_mult,
            dt=dt,
            aspect_x=cfg.aspect_x,
        )
        result = rules_weapons.tick_weapon(
            state.weapon_cooldowns.get(name, 0.0), ctx, rng
        )
        state.weapon_cooldowns[name] = result.new_cooldown
        if not result.fired:
            continue
        for spec in result.projectiles:
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
                    pierce=spec.pierce,
                )
            )
        for hit in result.instant_hits:
            target = _enemy_by_id(state, hit.target_id)
            if target is not None:
                target.hp = rules_damage.apply_hit(target.hp, hit.damage)


# --- Stage 5: projectile move + ttl ------------------------------------------
def _advance_projectiles(state: SimState, dt: float) -> None:
    """Integrate projectile positions and decrement their ttl in place."""
    for proj in state.projectiles:
        proj.x += proj.vx * dt
        proj.y += proj.vy * dt
        proj.ttl -= dt


# --- Stage 6: collision resolve ----------------------------------------------
def _resolve_collisions(state: SimState, cfg: Config) -> None:
    """Resolve projectile->enemy damage (pierce-aware) and enemy->player contact.

    A spatial hash over enemies turns each projectile/player query into a
    local-bucket scan (master section 5.3). Candidate ids come back sorted, so
    resolution order is deterministic. A projectile damages the nearest live
    in-radius enemy; if it still has pierce left it decrements pierce and
    survives, otherwise it is consumed (ttl set to 0). Damage and knockback use
    pure rules.damage.
    """
    if not state.enemies:
        return
    grid = SpatialHash.build(state.enemies, _COLLISION_CELL_SIZE)

    # Projectile -> enemy: each projectile damages the NEAREST live in-radius
    # enemy (parity with weapon targeting). candidate_ids is sorted ascending and
    # we only replace on a strictly smaller distance, so an exact distance tie
    # breaks to the lowest id -- selection stays deterministic. A pierce>0
    # projectile keeps going (decrement pierce); pierce==0 is consumed on hit.
    # ``proj.hit_ids`` guards against re-hitting the same enemy across ticks: any
    # enemy id already in the set is skipped during candidate selection, so a
    # lingering pierce projectile can only damage each distinct enemy once.
    for proj in state.projectiles:
        if proj.ttl <= 0.0:
            continue
        candidate_ids = grid.query_near(proj.x, proj.y, _PROJECTILE_HIT_RADIUS)
        best_enemy = None
        best_d2 = None
        for enemy_id in candidate_ids:
            # Skip enemies already struck by this projectile (pierce re-hit guard).
            if enemy_id in proj.hit_ids:
                continue
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
            proj.hit_ids.add(best_enemy.id)  # record before pierce/consume branch
            best_enemy.hp = rules_damage.apply_hit(best_enemy.hp, proj.damage)
            if proj.pierce > 0:
                proj.pierce -= 1  # pass through this enemy, keep flying
            else:
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


# --- Stage 7: death -> xp gem drop + kill count ------------------------------
def _drop_xp_on_death(state: SimState, rng: random.Random) -> None:
    """Drop an xp gem at each dead enemy's position and tally the kill.

    A dead enemy is present for exactly the tick it dies: stage 6 sets its hp to
    <= 0, this stage (7) sees it, and stage 9 cleanup removes it before the next
    tick. So iterating dead enemies here counts each kill exactly once -- the
    single home for the ``state.kills`` tally (HUD + run-outcome metric).

    ``rng`` is accepted for future drop-table variety (deferred); a single
    fixed-value gem is dropped per kill, so it is unused here.
    """
    for enemy in state.enemies:
        if rules_damage.is_dead(enemy.hp):
            state.kills += 1
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
    """Collect pickups within the magnet radius, accrue xp, set the level-up flag.

    The magnet radius is the base ``cfg.defs.magnet_range`` scaled by the magnet
    passive (``effective_stats().magnet_mult``), so the magnet passive widens
    collection. Xp accrual and the pending check are pure rules.leveling: xp goes
    into ``state.build`` and the flag is SET here when xp crosses the threshold;
    it is CLEARED by the loop applying a draft choice (step never clears it).
    """
    stats = rules_leveling.effective_stats(state.build, cfg.defs)
    magnet_r = cfg.defs.magnet_range * stats.magnet_mult
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
        state.build = rules_leveling.accrue_xp(state.build, collected_xp)
    if rules_leveling.level_up_pending(state.build, cfg.defs):
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
