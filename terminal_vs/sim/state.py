"""terminal_vs.sim.state - mutable simulation state buffers (Phase 2).

This module owns the *mutable* side of the section 6 / ADR-001 immutability
boundary. SimState and its entity buffers (player, enemies, projectiles,
pickups) are mutated in place by ``sim/step.py`` each tick. They must NOT leak
outside the sim layer as mutable handles: render and rules read them read-only.

Mutability split (master section 6):

  * Entities (Player / Enemy / Projectile / Pickup) are mutated in place each
    tick, so they are plain (non-frozen) mutable classes.
  * Values that cross into the pure rules layer (Intent, BuildState, Choice) are
    FROZEN -- rules return new instances and never mutate inputs. ``build`` (a
    frozen BuildState from rules.leveling) is the run's leveling/weapon state; it
    is replaced wholesale by rules results, never mutated in place.

Phase 2 multi-weapon model: cooldowns no longer live on the player. ``SimState``
holds ``weapon_cooldowns`` (one entry per owned weapon) so every owned weapon
ticks its own cooldown; ``reconcile_weapon_cooldowns`` keeps the dict's keys in
step with ``build.weapon_levels`` (adding new weapons at 0.0, dropping weapons
removed by an evolution swap).

Determinism: every id comes from a single monotonic counter (``next_id``) and
all randomness flows through an injected ``random.Random``. No wall-clock time
is read here or in step.

Pure, blessed-free.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..config import Config
from ..meta.schema import MetaState
from ..rules.defs import EnemyDef
from ..rules.leveling import BuildState, Choice
from ..world import Camera

# Team tags. Projectiles inherit the firing team so friendly fire is excluded.
TEAM_PLAYER = "player"
TEAM_ENEMY = "enemy"

# Player starting hp. This is a balance value (not a Phase 0 performance
# operating-point number), so it is not gated by the no-hardcode perf check.
# Externalizing player hp into balance.toml and tuning the exact value is a
# Phase 3 balancing concern; the Phase 2 BalanceDefs has no player-hp field.
_PLAYER_START_HP = 100.0


@dataclass(frozen=True)
class Intent:
    """Frozen 8-direction movement intent produced by the loop.

    ``dx``/``dy`` are each in ``{-1, 0, 1}``; the zero value ``Intent()`` is
    neutral (no movement). This is movement only -- level-up choice handling is
    the loop's job via rules.leveling, never via the step intent.
    """

    dx: int = 0
    dy: int = 0


# Convenient neutral intent (no allocation needed at call sites that want it).
NEUTRAL_INTENT = Intent()


class Player:
    """Mutable player entity (in-place updated inside sim/step.py).

    Duck-typed against world.Camera.follow (exposes float .x / .y). ``id`` comes
    from the deterministic id sequence. ``facing_x`` / ``facing_y`` track the
    last non-zero movement direction (a unit-ish vector); the forward_arc weapon
    aims along it, so it persists between idle ticks rather than resetting to
    zero when the player stops.
    """

    def __init__(
        self,
        entity_id: int,
        x: float,
        y: float,
        hp: float,
        glyph: str = "@",
        color: str = "white",
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.hp: float = hp
        self.team: str = TEAM_PLAYER
        self.glyph: str = glyph
        self.color: str = color
        # Last non-zero movement direction (forward_arc targeting). Defaults to
        # +X so the arc is well-defined before the player first moves.
        self.facing_x: float = 1.0
        self.facing_y: float = 0.0


class Enemy:
    """Mutable enemy entity. ``kind`` names its EnemyDef (e.g. "walker"/"swarm").

    ``kind`` selects the per-kind move speed in step stage 3 (enemies of
    different kinds chase at different speeds) and is the render/glyph source.
    Build instances via :func:`make_enemy` so the def's hp/glyph/color/kind stay
    consistent.
    """

    def __init__(
        self,
        entity_id: int,
        x: float,
        y: float,
        hp: float,
        kind: str = "walker",
        glyph: str = "z",
        color: str = "red",
        xp_value: float = 1.0,
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.hp: float = hp
        self.kind: str = kind
        self.team: str = TEAM_ENEMY
        self.glyph: str = glyph
        self.color: str = color
        # Xp dropped when this enemy dies (stamped from EnemyDef.xp_value): a boss
        # carries a much larger value than a regular mob.
        self.xp_value: float = xp_value


def make_enemy(entity_id: int, x: float, y: float, enemy_def: EnemyDef) -> Enemy:
    """Build an :class:`Enemy` from an :class:`EnemyDef` (kind/hp/glyph/color).

    The single place enemy entities are constructed from balance data, so a new
    enemy type is a balance.toml change with no sim edits. ``kind`` is the def's
    name (used by step to look the def's move speed back up).
    """
    return Enemy(
        entity_id=entity_id,
        x=x,
        y=y,
        hp=enemy_def.hp,
        kind=enemy_def.name,
        glyph=enemy_def.glyph,
        color=enemy_def.color,
        xp_value=enemy_def.xp_value,
    )


class Projectile:
    """Mutable projectile entity (a weapon shot). ``ttl`` counts down in seconds.

    ``pierce`` is how many further enemies the projectile can pass through after
    a hit: each hit on a DISTINCT enemy decrements pierce and the projectile
    survives while pierce remains; once pierce is exhausted the next hit consumes
    it (ttl set to 0). A pierce of 0 (the Phase 2 default for the dagger) is the
    Phase 1 "consume on first hit" behavior.

    ``hit_ids`` is a per-projectile set of enemy ids already struck. Collision
    resolution skips any id already in this set so a lingering pierce projectile
    can never re-hit the same enemy on a subsequent overlapping tick. The set is
    created fresh in __init__ (never a shared mutable default), so each
    projectile tracks its own victims independently.
    """

    def __init__(
        self,
        entity_id: int,
        x: float,
        y: float,
        vx: float,
        vy: float,
        damage: float,
        ttl: float,
        team: str = TEAM_PLAYER,
        pierce: int = 0,
        glyph: str = "*",
        color: str = "yellow",
        orbit_radius: float = 0.0,
        orbit_angle: float = 0.0,
        orbit_angular_speed: float = 0.0,
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self.damage: float = damage
        self.ttl: float = ttl
        self.team: str = team
        self.pierce: int = pierce
        self.glyph: str = glyph
        self.color: str = color
        # Orbit motion (radius 0 = a normal straight projectile). When
        # orbit_radius > 0 the sim ignores vx/vy and revolves this projectile
        # around the player at orbit_angular_speed from the current orbit_angle.
        self.orbit_radius: float = orbit_radius
        self.orbit_angle: float = orbit_angle
        self.orbit_angular_speed: float = orbit_angular_speed
        # Fresh set per projectile -- NEVER use a mutable default argument here.
        self.hit_ids: set[int] = set()


class Pickup:
    """Mutable xp-gem pickup dropped on enemy death. ``xp`` is its xp value."""

    def __init__(
        self,
        entity_id: int,
        x: float,
        y: float,
        xp: float,
        glyph: str = ".",
        color: str = "green",
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.xp: float = xp
        self.team: str = "pickup"
        self.glyph: str = glyph
        self.color: str = color


class Effect:
    """Mutable visual-only effect marker (e.g. a melee swing arc glyph).

    Purely cosmetic: it carries a render glyph/color and a ``ttl`` that counts
    down each tick, with NO damage, NO collision, and NO id (it has no identity
    and never interacts, so it does not consume ``next_id``). The render layer
    draws it like any entity (duck-typed ``x`` / ``y`` / ``glyph`` / ``color``);
    step decrements ``ttl`` and cleanup drops it once it expires.
    """

    def __init__(
        self,
        x: float,
        y: float,
        glyph: str = "*",
        color: str = "white",
        ttl: float = 0.0,
    ) -> None:
        self.x: float = x
        self.y: float = y
        self.glyph: str = glyph
        self.color: str = color
        self.ttl: float = ttl


class SimState:
    """Mutable simulation state -- the section 6 boundary's mutable side.

    Holds every mutable entity buffer plus per-run bookkeeping. ``step`` mutates
    this in place; it must not be handed out as a mutable reference to the rules
    or render layers (they read it). Buffers are plain lists so iteration order
    is deterministic (insertion order), which matters for reproducible runs.

    Fields:
      * player: the single Player.
      * enemies / projectiles / pickups: entity lists, mutated in place.
      * camera: world.Camera, follows the player.
      * build: frozen BuildState (weapons / passives / level / xp); replaced
        wholesale by rules.leveling results (never mutated in place).
      * weapon_cooldowns: per-owned-weapon seconds-until-ready dict, mutated in
        place by step stage 4 and kept in step with ``build.weapon_levels`` via
        ``reconcile_weapon_cooldowns``.
      * spawn_accumulator: director spawn timer (seconds), advanced by dt and
        drained by the director-driven spawn.
      * pending_choices: the rolled draft cards shown in the level-up overlay
        (set by the loop on entering levelup; the overlay renders them).
      * level_up_pending: bool flag set by step stage 8 when xp crosses the
        threshold; CLEARED by the loop's draft selection, never by step.
      * kills: cumulative enemy-death count, incremented by step's death stage
        (one per enemy that dies, counted the single tick it dies before
        cleanup removes it). The HUD shows it and the headless driver / balance
        tests read it as a run-outcome metric.
      * next_id: monotonic id counter; ``alloc_id`` hands out the next id.
      * elapsed: survival timer in seconds (advanced by step using the fixed dt).
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg: Config = cfg
        self.player: Player
        self.enemies: list[Enemy] = []
        self.projectiles: list[Projectile] = []
        self.effects: list[Effect] = []
        self.pickups: list[Pickup] = []
        self.camera: Camera = Camera(0.0, 0.0)
        self.build: BuildState = BuildState()
        # Cross-run meta progression, injected read-only at run start (new_run).
        # effective_stats folds its permanent upgrades on top of the passives;
        # the sim never mutates it mid-tick (ADR-001).
        self.meta: MetaState = MetaState()
        self.weapon_cooldowns: dict[str, float] = {}
        self.spawn_accumulator: float = 0.0
        self.pending_choices: tuple[Choice, ...] = ()
        self.level_up_pending: bool = False
        self.kills: int = 0
        self.next_id: int = 0
        self.elapsed: float = 0.0

    def alloc_id(self) -> int:
        """Return the next deterministic entity id (monotonic, never reused)."""
        entity_id = self.next_id
        self.next_id += 1
        return entity_id


def reconcile_weapon_cooldowns(state: SimState) -> None:
    """Sync ``state.weapon_cooldowns`` keys to ``state.build.weapon_levels``.

    Weapons newly added to the build (a new-weapon draft or an evolution result)
    get a fresh ``0.0`` cooldown so they can fire immediately; weapons removed
    from the build (the base weapon an evolution replaces) are dropped from the
    dict. Called in place inside the sim layer after the build changes (each step
    before firing, and after a draft selection swaps weapons). Mutates the dict
    rather than rebinding so any held reference stays valid.
    """
    owned = {name for name, _ in state.build.weapon_levels}
    for name in owned:
        if name not in state.weapon_cooldowns:
            state.weapon_cooldowns[name] = 0.0
    for name in list(state.weapon_cooldowns):
        if name not in owned:
            del state.weapon_cooldowns[name]


def new_run(
    cfg: Config, rng: random.Random, meta: MetaState | None = None
) -> SimState:
    """Create a fresh mutable SimState for a new run.

    ``rng`` is accepted for signature symmetry with step/maybe_spawn (and future
    randomized starts); the Phase 2 start is deterministic. The player spawns at
    the world origin with full hp from the ``_PLAYER_START_HP`` module constant
    (player hp/speed are not yet in the balance table; externalizing them is a
    Phase 3 balancing concern), and the camera centers on it.

    The build starts as the default :class:`BuildState` (dagger at level 1) and
    ``weapon_cooldowns`` is reconciled to it (one ``0.0`` entry per owned
    weapon), so the dagger is ready to fire on the first tick.
    """
    state = SimState(cfg)
    # Inject the cross-run meta read-only (a default empty MetaState if none is
    # given, e.g. tests / first launch). effective_stats reads it from state.meta.
    if meta is not None:
        state.meta = meta
    player = Player(
        entity_id=state.alloc_id(),
        x=0.0,
        y=0.0,
        hp=_PLAYER_START_HP,
    )
    state.player = player
    state.camera.follow(player)
    reconcile_weapon_cooldowns(state)
    return state
