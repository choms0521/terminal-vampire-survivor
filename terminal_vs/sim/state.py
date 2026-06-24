"""terminal_vs.sim.state - mutable simulation state buffers (Day 3).

This module owns the *mutable* side of the section 6 / ADR-001 immutability
boundary. SimState and its entity buffers (player, enemies, projectiles,
pickups) are mutated in place by ``sim/step.py`` each tick. They must NOT leak
outside the sim layer as mutable handles: render and rules read them read-only.

Mutability split (master section 6):

  * Entities (Player / Enemy / Projectile / Pickup) are mutated in place each
    tick, so they are plain (non-frozen) mutable classes.
  * Values that cross into the pure rules layer (Intent, LevelState) are FROZEN
    dataclasses -- rules return new instances and never mutate inputs.

Determinism: every id comes from a single monotonic counter (``next_id``) and
all randomness flows through an injected ``random.Random``. No wall-clock time
is read here or in step.

Pure, blessed-free.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..config import Config
from ..world import Camera

# Team tags. Projectiles inherit the firing team so friendly fire is excluded.
TEAM_PLAYER = "player"
TEAM_ENEMY = "enemy"

# Player starting hp. This is a balance value (not a Phase 0 performance
# operating-point number), so it is not gated by the no-hardcode perf check.
# It lives here rather than balance.toml because Chunk A's frozen BalanceTable
# has no player-hp field; wiring a new balance key is out of Chunk B scope and
# left for a later balancing phase.
_PLAYER_START_HP = 100.0


@dataclass(frozen=True)
class Intent:
    """Frozen 8-direction movement intent produced by the loop (Chunk C).

    ``dx``/``dy`` are each in ``{-1, 0, 1}``; the zero value ``Intent()`` is
    neutral (no movement). This is movement only -- level-up choice handling is
    the loop's job via rules.leveling, never via the step intent.
    """

    dx: int = 0
    dy: int = 0


# Convenient neutral intent (no allocation needed at call sites that want it).
NEUTRAL_INTENT = Intent()


@dataclass(frozen=True)
class LevelState:
    """Frozen leveling/xp state (the pure side of the boundary).

    ``rules.leveling`` operates on this immutably: ``accrue_xp`` returns a NEW
    ``LevelState`` (never mutates), and ``apply_choice`` returns the post-level
    state. ``xp`` is the xp accumulated toward the *current* level; ``level`` is
    1-based. The xp needed to clear level ``L`` is ``base * growth ** (L - 1)``.
    """

    level: int = 1
    xp: float = 0.0


class Player:
    """Mutable player entity (in-place updated inside sim/step.py).

    Duck-typed against world.Camera.follow (exposes float .x / .y). ``id`` comes
    from the deterministic id sequence.
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
        # Weapon cooldown timer (seconds until the next auto-fire shot is ready).
        self.weapon_cooldown_remaining: float = 0.0


class Enemy:
    """Mutable enemy entity (single Phase 1 type)."""

    def __init__(
        self,
        entity_id: int,
        x: float,
        y: float,
        hp: float,
        glyph: str = "z",
        color: str = "red",
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.hp: float = hp
        self.team: str = TEAM_ENEMY
        self.glyph: str = glyph
        self.color: str = color


class Projectile:
    """Mutable projectile entity (dagger shot). ``ttl`` counts down in seconds."""

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
        glyph: str = "*",
        color: str = "yellow",
    ) -> None:
        self.id: int = entity_id
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self.damage: float = damage
        self.ttl: float = ttl
        self.team: str = team
        self.glyph: str = glyph
        self.color: str = color


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


class SimState:
    """Mutable simulation state -- the section 6 boundary's mutable side.

    Holds every mutable entity buffer plus per-run bookkeeping. ``step`` mutates
    this in place; it must not be handed out as a mutable reference to the rules
    or render layers (they read it). Buffers are plain lists so iteration order
    is deterministic (insertion order), which matters for reproducible runs.

    Fields:
      * player: the single Player.
      * enemies / projectiles / pickups: entity lists, mutated in place.
      * camera: world.Camera, follows the player (stage 10).
      * level_state: frozen LevelState (xp/level); replaced wholesale by
        rules.leveling results (never mutated in place).
      * level_up_pending: bool flag set by step stage 8 when xp crosses the
        threshold; CLEARED by the loop via rules.apply_choice, never by step.
      * next_id: monotonic id counter; ``alloc_id`` hands out the next id.
      * elapsed: survival timer in seconds (advanced by step using the fixed dt).
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg: Config = cfg
        self.player: Player
        self.enemies: list[Enemy] = []
        self.projectiles: list[Projectile] = []
        self.pickups: list[Pickup] = []
        self.camera: Camera = Camera(0.0, 0.0)
        self.level_state: LevelState = LevelState()
        self.level_up_pending: bool = False
        self.next_id: int = 0
        self.elapsed: float = 0.0

    def alloc_id(self) -> int:
        """Return the next deterministic entity id (monotonic, never reused)."""
        entity_id = self.next_id
        self.next_id += 1
        return entity_id


def new_run(cfg: Config, rng: random.Random) -> SimState:
    """Create a fresh mutable SimState for a new run.

    ``rng`` is accepted for signature symmetry with step/maybe_spawn (and future
    randomized starts); the Phase 1 start is deterministic. The player spawns at
    the world origin with full hp from the ``_PLAYER_START_HP`` module constant
    (player hp/speed are not yet in the balance table; externalizing them is a
    Phase 3 balancing concern), and the camera centers on it.
    """
    state = SimState(cfg)
    player = Player(
        entity_id=state.alloc_id(),
        x=0.0,
        y=0.0,
        hp=_PLAYER_START_HP,
    )
    state.player = player
    state.camera.follow(player)
    return state
