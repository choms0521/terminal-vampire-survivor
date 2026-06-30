"""terminal_vs.rules.defs - immutable balance definition tables (Phase 2).

This module OWNS the frozen balance dataclasses (WeaponDef, PassiveDef,
EnemyDef, EvolutionDef, ReinforceStep, DirectorDef, LevelingDef, BalanceDefs)
and the pure :func:`build_defs` constructor that turns a raw ``balance.toml``
dict into the immutable :class:`BalanceDefs` table injected into the rules layer.

Design rules (master plan sections 5.5, 6 / ADR-001):

  * Every def is a frozen dataclass -- immutable, injected read-only into rules.
  * ``build_defs`` is PURE: it reads its input dict and returns new values,
    never mutating the input and never touching global state.
  * This module MUST NOT import :mod:`terminal_vs.config`. config.py imports
    *this* module (loads + validates balance.toml, then calls ``build_defs``),
    so importing config here would create an import cycle. Keeping defs.py free
    of config also keeps the def schema testable in isolation.
  * No blessed, no side effects, no Chinese characters.

The name-keyed fields on :class:`BalanceDefs` (weapons / passives / enemies) are
read-only mappings: ``build_defs`` wraps them in :class:`types.MappingProxyType`
so callers index them but cannot mutate the shared balance table at runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# The weapon a run begins owning (rules.leveling.BuildState's default). Defined
# here in the cycle-free base module (config and leveling both import defs but not
# each other through it) so the starting weapon has a single source of truth:
# BuildState reads it for the default build, and config-load validates that a
# user-provided [weapons.*] section defines it.
STARTING_WEAPON = "dagger"


@dataclass(frozen=True)
class WeaponDef:
    """Immutable definition of one weapon (master plan section 7).

    ``targeting`` selects the firing strategy in rules/weapons.py:
    ``"nearest"`` / ``"nearest_or_random"`` build projectiles, while
    ``"forward_arc"`` resolves instant hits. ``pierce`` is how many enemies a
    projectile passes through (0 = stop on first hit); evolved weapons set it.
    The arc fields are only meaningful for ``"forward_arc"`` weapons.

    ``glyph`` / ``color`` are render hints stamped onto the projectiles (or the
    melee swing effect) this weapon fires, so each weapon reads distinctly on
    screen. They default to the historical projectile look (``*`` / ``yellow``)
    so a weapon that omits them keeps the prior appearance.
    """

    name: str
    max_level: int
    cooldown: float          # seconds between auto-fire shots (passive-scaled)
    damage: float            # damage applied per projectile / instant hit
    projectile_count: int    # projectiles launched per fire (0 for melee)
    projectile_speed: float  # world units per second
    projectile_ttl: float    # projectile lifetime in seconds
    targeting: str           # "nearest" | "nearest_or_random" | "forward_arc"
    pierce: int = 0          # enemies a projectile passes through (0 = none)
    arc_range: float = 0.0       # forward_arc reach in world units
    arc_half_width: float = 0.0  # forward_arc cosine half-width (1 = forward only)
    glyph: str = "*"         # render glyph for this weapon's projectile / effect
    color: str = "yellow"    # render color for this weapon's projectile / effect
    spread_angle: float = 0.0  # total fan angle (deg) across multi-shot; 0 = stacked
    effect_ttl: float = 0.0    # forward_arc swing visual lifetime (sec); must
    # exceed one tick (1 / sim_tps) to ever render -- it is created and aged the
    # same tick, so a ttl <= dt is culled before any frame draws it (0 = no effect).
    orbit_radius: float = 0.0         # orbit ring radius (world units); 0 = not an orbit
    orbit_angular_speed: float = 0.0  # orbit revolution speed (radians / second)


@dataclass(frozen=True)
class PassiveDef:
    """Immutable definition of one passive upgrade.

    ``multiplier_per_level`` is applied multiplicatively once per owned level
    (product over levels) to a single stat. rules/leveling's ``effective_stats``
    maps the passive id to which stat it multiplies (attack speed / move speed /
    magnet range).
    """

    name: str
    max_level: int
    multiplier_per_level: float


@dataclass(frozen=True)
class MetaUpgradeDef:
    """Immutable definition of one permanent (cross-run) upgrade (Phase 4A).

    A permanent upgrade is bought with gold between runs and applied read-only at
    run start. ``stat`` names which ``effective_stats`` field it multiplies -- the
    same stat ids the passives map to ("attack_speed" / "move_speed" / "magnet")
    -- and ``multiplier_per_level`` is applied once per owned level (product over
    levels), mirroring :class:`PassiveDef`. The gold price of the NEXT level is
    ``cost_base * cost_growth ** current_level`` (geometric, like the xp curve).
    """

    name: str
    max_level: int
    stat: str
    multiplier_per_level: float
    cost_base: int
    cost_growth: float


@dataclass(frozen=True)
class EnemyDef:
    """Immutable definition of one enemy type.

    ``spawn_weight`` is the relative weight the director uses for weighted enemy
    selection; ``glyph`` and ``color`` are render hints consumed by sim/render.
    ``boss`` flags a boss: it is excluded from the regular weighted spawn pool and
    spawned only when a director ``boss_spawn_times`` mark is crossed. ``xp_value``
    is the xp dropped on death (a boss's is far larger than a mob's); it defaults
    to 1.0 so existing enemies keep the historical single-gem reward.
    """

    name: str
    hp: float
    move_speed: float    # world units per second toward the player
    spawn_weight: float  # relative weight for weighted spawn selection
    glyph: str
    color: str
    boss: bool = False
    xp_value: float = 1.0
    # Enemy projectile fire (a caster boss). ``fire_cadence`` is the seconds between
    # shots (0 = never fires -- the default for regular enemies and a melee boss);
    # a shot is aimed straight at the player at ``fire_speed``, deals ``fire_damage``,
    # and lives ``fire_ttl`` seconds.
    fire_cadence: float = 0.0
    fire_damage: float = 0.0
    fire_speed: float = 0.0
    fire_ttl: float = 0.0


@dataclass(frozen=True)
class EvolutionDef:
    """Immutable definition of one weapon evolution rule (master plan section 8).

    The evolution applies when the ``base`` weapon is at ``base_max_level`` and
    the ``requires_passive`` passive is owned (level > 0); the base weapon is
    then replaced by ``result_weapon``. Adding evolutions is data-only.
    """

    name: str
    base: str
    requires_passive: str
    base_max_level: int
    result_weapon: str


@dataclass(frozen=True)
class ReinforceStep:
    """One row of the director's per-minute reinforcement table.

    ``minute`` is the elapsed-minute threshold at/after which this step applies;
    ``interval_mult`` scales the base spawn interval (smaller = faster spawns)
    and ``concurrent`` is how many enemies spawn together at each spawn tick.
    """

    minute: int
    interval_mult: float
    concurrent: int


@dataclass(frozen=True)
class DirectorDef:
    """Immutable director difficulty-curve definition (master plan section 7).

    ``base_spawn_interval`` is the initial seconds between spawns; the active
    reinforce step scales it down (bounded below by ``min_spawn_interval``).
    ``reinforce_steps`` is ordered by ascending ``minute``.
    """

    base_spawn_interval: float
    min_spawn_interval: float
    reinforce_steps: tuple[ReinforceStep, ...]
    # Elapsed-seconds marks at which a boss spawns (each crossed once). Empty = no
    # boss schedule, so the director never sets boss_due and a boss-free balance
    # behaves exactly as before.
    boss_spawn_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class LevelingDef:
    """Immutable leveling parameters: draft size + xp curve.

    The xp required to clear level ``L`` (1-based) is
    ``xp_curve_base * xp_curve_growth ** (L - 1)``; the exact formula lives in
    rules/leveling, not here. ``draft_choices`` is the N of the N-pick draft.
    """

    draft_choices: int
    xp_curve_base: float
    xp_curve_growth: float


@dataclass(frozen=True)
class BalanceDefs:
    """Immutable container of every balance table injected into the rules layer.

    Built by :func:`build_defs` from a validated balance.toml dict and stored on
    ``Config.defs``. The ``weapons`` / ``passives`` / ``enemies`` mappings are
    read-only: ``build_defs`` wraps them in :class:`types.MappingProxyType`, so a
    runtime ``cfg.defs.weapons[...] = ...`` raises rather than silently mutating
    the shared balance table (the ADR-001 immutability boundary, now enforced not
    just documented). ``evolutions`` is a tuple so iteration order is
    deterministic. ``magnet_range`` is the base pickup radius that the magnet
    passive multiplies.
    """

    weapons: Mapping[str, WeaponDef] = field(
        default_factory=lambda: MappingProxyType({})
    )
    passives: Mapping[str, PassiveDef] = field(
        default_factory=lambda: MappingProxyType({})
    )
    upgrades: Mapping[str, MetaUpgradeDef] = field(
        default_factory=lambda: MappingProxyType({})
    )
    enemies: Mapping[str, EnemyDef] = field(
        default_factory=lambda: MappingProxyType({})
    )
    evolutions: tuple[EvolutionDef, ...] = ()
    director: DirectorDef = field(
        default_factory=lambda: DirectorDef(2.0, 0.4, (ReinforceStep(0, 1.0, 1),))
    )
    leveling: LevelingDef = field(
        default_factory=lambda: LevelingDef(3, 5.0, 1.5)
    )
    magnet_range: float = 4.0
    gold_per_kill: int = 1  # gold awarded per enemy kill (Phase 4A meta progression)


def build_defs(raw_balance: dict) -> BalanceDefs:
    """Build the immutable :class:`BalanceDefs` from a raw balance.toml dict.

    Pure: reads ``raw_balance`` and returns a new :class:`BalanceDefs`, never
    mutating the input. This constructor assumes the caller (config.py) has
    already filled missing keys with defaults and validated ranges, so it does
    no validation itself -- it is the boundary between "a dict of numbers" and
    "the typed immutable tables the rules layer consumes".

    Args:
        raw_balance: nested dict mirroring the balance.toml schema, e.g.
            ``{"weapons": {"dagger": {...}}, "leveling": {...}, ...}``.

    Returns:
        An immutable :class:`BalanceDefs`.
    """
    weapons_raw: dict = raw_balance.get("weapons", {})
    passives_raw: dict = raw_balance.get("passives", {})
    upgrades_raw: dict = raw_balance.get("upgrades", {})
    enemies_raw: dict = raw_balance.get("enemies", {})
    evolutions_raw: dict = raw_balance.get("evolution", {})
    director_raw: dict = raw_balance.get("director", {})
    leveling_raw: dict = raw_balance.get("leveling", {})
    pickup_raw: dict = raw_balance.get("pickup", {})
    meta_raw: dict = raw_balance.get("meta", {})

    weapons = {
        name: WeaponDef(
            name=name,
            max_level=int(w["max_level"]),
            cooldown=float(w["cooldown"]),
            damage=float(w["damage"]),
            projectile_count=int(w["projectile_count"]),
            projectile_speed=float(w["projectile_speed"]),
            projectile_ttl=float(w["projectile_ttl"]),
            targeting=str(w["targeting"]),
            pierce=int(w.get("pierce", 0)),
            arc_range=float(w.get("arc_range", 0.0)),
            arc_half_width=float(w.get("arc_half_width", 0.0)),
            glyph=str(w.get("glyph", "*")),
            color=str(w.get("color", "yellow")),
            spread_angle=float(w.get("spread_angle", 0.0)),
            effect_ttl=float(w.get("effect_ttl", 0.0)),
            orbit_radius=float(w.get("orbit_radius", 0.0)),
            orbit_angular_speed=float(w.get("orbit_angular_speed", 0.0)),
        )
        for name, w in weapons_raw.items()
    }

    passives = {
        name: PassiveDef(
            name=name,
            max_level=int(p["max_level"]),
            multiplier_per_level=float(p["multiplier_per_level"]),
        )
        for name, p in passives_raw.items()
    }

    upgrades = {
        name: MetaUpgradeDef(
            name=name,
            max_level=int(u["max_level"]),
            stat=str(u["stat"]),
            multiplier_per_level=float(u["multiplier_per_level"]),
            cost_base=int(u["cost_base"]),
            cost_growth=float(u["cost_growth"]),
        )
        for name, u in upgrades_raw.items()
    }

    enemies = {
        name: EnemyDef(
            name=name,
            hp=float(e["hp"]),
            move_speed=float(e["move_speed"]),
            spawn_weight=float(e["spawn_weight"]),
            glyph=str(e["glyph"]),
            color=str(e["color"]),
            boss=bool(e.get("boss", False)),
            xp_value=float(e.get("xp_value", 1.0)),
            fire_cadence=float(e.get("fire_cadence", 0.0)),
            fire_damage=float(e.get("fire_damage", 0.0)),
            fire_speed=float(e.get("fire_speed", 0.0)),
            fire_ttl=float(e.get("fire_ttl", 0.0)),
        )
        for name, e in enemies_raw.items()
    }

    evolutions = tuple(
        EvolutionDef(
            name=name,
            base=str(ev["base"]),
            requires_passive=str(ev["requires_passive"]),
            base_max_level=int(ev["base_max_level"]),
            result_weapon=str(ev["result_weapon"]),
        )
        for name, ev in evolutions_raw.items()
    )

    steps = tuple(
        ReinforceStep(
            minute=int(row[0]),
            interval_mult=float(row[1]),
            concurrent=int(row[2]),
        )
        for row in director_raw["reinforce_steps"]
    )
    director = DirectorDef(
        base_spawn_interval=float(director_raw["base_spawn_interval"]),
        min_spawn_interval=float(director_raw["min_spawn_interval"]),
        reinforce_steps=steps,
        boss_spawn_times=tuple(
            float(t) for t in director_raw.get("boss_spawn_times", ())
        ),
    )

    leveling = LevelingDef(
        draft_choices=int(leveling_raw["draft_choices"]),
        xp_curve_base=float(leveling_raw["xp_curve_base"]),
        xp_curve_growth=float(leveling_raw["xp_curve_growth"]),
    )

    magnet_range = float(pickup_raw["magnet_range"])
    gold_per_kill = int(meta_raw.get("gold_per_kill", 1))

    return BalanceDefs(
        # Wrap the name-keyed tables in read-only proxies so the immutability
        # boundary holds at runtime: the rules/sim layers index these but can
        # never mutate the shared balance table through cfg.defs.
        weapons=MappingProxyType(weapons),
        passives=MappingProxyType(passives),
        upgrades=MappingProxyType(upgrades),
        enemies=MappingProxyType(enemies),
        evolutions=evolutions,
        director=director,
        leveling=leveling,
        magnet_range=magnet_range,
        gold_per_kill=gold_per_kill,
    )
