"""terminal_vs.config - load, validate, and freeze the game configuration.

This module is the configuration contract consumed by every downstream layer
(world, sim, rules, render, loop). It loads two TOML files with the standard
library ``tomllib`` (Python 3.11+, master plan section 5.5):

  * ``config/tuning.toml``  -> operating-point constants (Phase 0 measured):
    sim_tps, poll_timeout, max_catchup, viewport_w/h, entity_cap, aspect_x,
    render_mode.
  * ``config/balance.toml`` -> game-balance constants (weapons, passives,
    enemies, evolution, director curve, leveling, magnet range).

Design rules (master plan sections 5.5, 6 / ADR-001):

  * The returned :class:`Config` is a frozen dataclass; its ``defs`` field is the
    immutable :class:`~terminal_vs.rules.defs.BalanceDefs` table built by
    :func:`terminal_vs.rules.defs.build_defs`. Both are injected read-only into
    the rules layer.
  * Missing keys (or a missing file) fall back to code defaults so the game runs
    on a first launch without any config file.
  * Out-of-range values (non-positive rates / sizes) raise a clear ``ValueError``
    whose message names the offending key and the file it came from.

Operating-point numbers are NOT hardcoded as named constants here: the code
defaults live in string-keyed ``_*_DEFAULTS`` dicts so the only literal forms in
this file are dict-key strings (``"sim_tps": ...``), never ``sim_tps = <number>``
assignments. This keeps the "no hardcoded performance numbers" boundary intact
while still providing fallbacks.

The balance-side definition dataclasses live in :mod:`terminal_vs.rules.defs`,
which this module imports (defs.py imports nothing from config, breaking the
cycle). config.py owns only loading, default-fill, and range validation of the
balance dict; ``build_defs`` turns the validated dict into the typed tables.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .rules.defs import STARTING_WEAPON, BalanceDefs, build_defs

# --- Code-default fallbacks (string-keyed; never named perf constants) ---------
# Each value is reached via a key string, so this file contains no
# ``sim_tps = <number>`` / ``timeout=<number>`` style assignments. These are
# fallbacks only; the authoritative values live in config/tuning.toml.
_TUNING_DEFAULTS: dict[str, object] = {
    "sim_tps": 20.0,
    "poll_timeout": 0.005,
    "max_catchup": 5,
    "viewport_w": 100,
    "viewport_h": 30,
    "entity_cap": 200,
    "aspect_x": 2.0,
    "render_mode": "diff",
}

# Balance fallbacks, grouped by table section (mirrors config/balance.toml). A
# missing section or key falls back to these so the game runs with no file. The
# values are dict-reached (no ``cooldown = <number>`` named-constant forms) and
# are balance dials, not performance operating-point numbers.
_LEVELING_DEFAULTS: dict[str, object] = {
    "draft_choices": 3,
    "xp_curve_base": 5.0,
    "xp_curve_growth": 1.5,
}
_WEAPON_DEFAULTS: dict[str, object] = {
    "max_level": 8,
    "cooldown": 1.2,
    "damage": 6.0,
    "projectile_count": 1,
    "projectile_speed": 14.0,
    "projectile_ttl": 1.2,
    "targeting": "nearest",
    "pierce": 0,
    "arc_range": 0.0,
    "arc_half_width": 0.0,
}
_PASSIVE_DEFAULTS: dict[str, object] = {
    "max_level": 5,
    "multiplier_per_level": 1.0,
}
_ENEMY_DEFAULTS: dict[str, object] = {
    "hp": 10.0,
    "move_speed": 2.5,
    "spawn_weight": 1.0,
    "glyph": "z",
    "color": "red",
    "boss": False,
    "xp_value": 1.0,
    "fire_cadence": 0.0,
    "fire_damage": 0.0,
    "fire_speed": 0.0,
    "fire_ttl": 0.0,
}
_EVOLUTION_DEFAULTS: dict[str, object] = {
    "base": "dagger",
    "requires_passive": "attack_speed",
    "base_max_level": 8,
    "result_weapon": "dagger_evolved",
}
_DIRECTOR_DEFAULTS: dict[str, object] = {
    "base_spawn_interval": 2.0,
    "min_spawn_interval": 0.4,
    "reinforce_steps": [[0, 1.0, 1]],
}
_PICKUP_DEFAULTS: dict[str, object] = {
    "magnet_range": 4.0,
}
_UPGRADE_DEFAULTS: dict[str, object] = {
    "max_level": 3,
    "stat": "move_speed",
    "multiplier_per_level": 1.1,
    "cost_base": 50,
    "cost_growth": 1.5,
}

# Stats a permanent upgrade may target -- the same stat ids effective_stats maps
# the passives to (rules/leveling), so an upgrade multiplies a known stat.
_VALID_UPGRADE_STATS: frozenset[str] = frozenset(
    {"attack_speed", "move_speed", "magnet"}
)
_META_DEFAULTS: dict[str, object] = {
    "gold_per_kill": 1,
}

# Default content set, used when balance.toml omits a whole section (so the game
# still has weapons/passives/enemies/evolutions on a first launch). Each entry is
# a code default keyed by name; the loader merges any present overrides on top.
_DEFAULT_WEAPON_NAMES: tuple[str, ...] = ("dagger", "dagger_evolved")
_DEFAULT_PASSIVE_NAMES: tuple[str, ...] = ("attack_speed",)
_DEFAULT_ENEMY_NAMES: tuple[str, ...] = ("walker",)
_DEFAULT_EVOLUTION_NAMES: tuple[str, ...] = ("dagger_x",)

# Targeting strategies a weapon may declare (validated on load).
_VALID_TARGETING: frozenset[str] = frozenset(
    {"nearest", "nearest_or_random", "forward_arc", "radial", "orbit"}
)


@dataclass(frozen=True)
class Config:
    """Immutable game configuration (master section 6 boundary, frozen side).

    Operating-point fields are loaded from config/tuning.toml by key; ``defs`` is
    the immutable balance table built from config/balance.toml. Never construct
    these numbers inline elsewhere -- read them from a ``Config`` instance.
    """

    sim_tps: float        # simulation ticks per second
    poll_timeout: float   # input poll timeout in seconds
    max_catchup: int      # max sim catch-up ticks per render frame
    viewport_w: int       # viewport width in cells
    viewport_h: int       # viewport height in cells
    entity_cap: int       # max simultaneous entities
    aspect_x: float       # horizontal cell aspect compensation factor (section 3.1)
    render_mode: str      # "full" | "diff"
    defs: BalanceDefs     # immutable balance tables built from balance.toml


def _load_toml(path: str | Path) -> dict:
    """Load a TOML file, returning an empty dict if the file is absent.

    A missing file is not an error: callers fall back to code defaults so the
    game runs on a first launch without any config present.
    """
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def _f(data: dict, key: str, defaults: dict) -> float:
    """Read ``key`` as float, coercing TOML ints (e.g. ``aspect_x = 2``)."""
    return float(data.get(key, defaults[key]))


def _i(data: dict, key: str, defaults: dict) -> int:
    """Read ``key`` as int."""
    return int(data.get(key, defaults[key]))


def _require_positive(name: str, value: float) -> None:
    """Raise a clear ValueError if a rate/size value is not strictly positive.

    The hint points at the right file by the key's shape: balance keys are dotted
    and sectioned (e.g. ``weapons.dagger.cooldown``) while operating-point keys
    are flat (e.g. ``sim_tps``), so the message names the file the bad value came
    from.

    A bool is rejected explicitly: ``bool`` is a subclass of ``int``, so ``True``
    would otherwise satisfy ``value <= 0`` as 1 and parse silently as 1.0. This
    matches the explicit bool guard in :func:`_validate_boss_spawn_times`.
    """
    if isinstance(value, bool) or value <= 0:
        source = "config/balance.toml" if "." in name else "config/tuning.toml"
        raise ValueError(
            f"config: {name} must be > 0, got {value!r} (check {source})"
        )


def _merged_section(raw: dict, name: str, defaults: dict) -> dict:
    """Return one named entry with code defaults filled in for missing keys.

    ``raw`` is the section dict (e.g. all ``[weapons.*]`` tables); ``name`` is
    the entry id. Present keys win; absent keys fall back to ``defaults``. The
    result is a fresh dict (the input is never mutated).
    """
    entry = dict(raw.get(name, {}))
    merged = dict(defaults)
    merged.update(entry)
    return merged


def _validate_weapon(name: str, w: dict) -> None:
    """Range/enum validation for one weapon entry (keys hinted as balance).

    Projectile fields (speed) are only required positive for weapons that
    actually fire projectiles. A ``forward_arc`` melee weapon carries zero
    projectile count/speed/ttl by design, so requiring those positive would
    wrongly reject it; its reach is validated via ``arc_range`` instead.
    """
    _require_positive(f"weapons.{name}.max_level", w["max_level"])
    _require_positive(f"weapons.{name}.cooldown", w["cooldown"])
    _require_positive(f"weapons.{name}.damage", w["damage"])
    if w["targeting"] not in _VALID_TARGETING:
        raise ValueError(
            f"config: weapons.{name}.targeting must be one of "
            f"{sorted(_VALID_TARGETING)}, got {w['targeting']!r} "
            f"(check config/balance.toml)"
        )
    if int(w["projectile_count"]) < 0:
        raise ValueError(
            f"config: weapons.{name}.projectile_count must be >= 0, got "
            f"{w['projectile_count']!r} (check config/balance.toml)"
        )
    if int(w["pierce"]) < 0:
        raise ValueError(
            f"config: weapons.{name}.pierce must be >= 0, got "
            f"{w['pierce']!r} (check config/balance.toml)"
        )
    if w["targeting"] == "forward_arc":
        # Melee: the arc reach must be positive (it replaces projectile range).
        _require_positive(f"weapons.{name}.arc_range", w["arc_range"])
        # arc_half_width is a cosine value so it must be in [-1.0, 1.0].
        ahw = float(w["arc_half_width"])
        if not (-1.0 <= ahw <= 1.0):
            raise ValueError(
                f"config: weapons.{name}.arc_half_width must be in [-1.0, 1.0], "
                f"got {ahw!r} (check config/balance.toml)"
            )
    elif w["targeting"] == "orbit":
        # Orbit: shots revolve at orbit_angular_speed at orbit_radius around the
        # player. Linear projectile_speed is unused (it may be 0), so instead the
        # radius and angular speed must be positive, plus a count and a ttl.
        _require_positive(
            f"weapons.{name}.orbit_radius", float(w.get("orbit_radius", 0.0))
        )
        _require_positive(
            f"weapons.{name}.orbit_angular_speed",
            float(w.get("orbit_angular_speed", 0.0)),
        )
        _require_positive(
            f"weapons.{name}.projectile_count", w["projectile_count"]
        )
        _require_positive(f"weapons.{name}.projectile_ttl", w["projectile_ttl"])
        # Load-bearing coupling: an orbit ring is ttl-bounded and respawned each
        # cooldown, and that respawn is what restores the per-life hit_ids re-hit
        # cadence (see rules/weapons._make_orbit). A ttl >= cooldown lets rings
        # stack and silently inflates damage, so require ttl < cooldown -- the same
        # load-time enforcement this config applies to other balance couplings.
        if float(w["projectile_ttl"]) >= float(w["cooldown"]):
            raise ValueError(
                f"config: weapons.{name}.projectile_ttl ({w['projectile_ttl']}) must "
                f"be < cooldown ({w['cooldown']}) for an orbit weapon, so the ring "
                f"respawns each cooldown (check config/balance.toml)"
            )
    else:
        # Projectile weapons must travel, fire at least one projectile, and give
        # that projectile a positive lifetime. A count or ttl of 0 on a projectile
        # weapon would silently produce no effective shots. forward_arc melee is
        # handled in the branch above and legitimately carries zero projectile
        # fields, so these strict-positive checks apply only here.
        _require_positive(
            f"weapons.{name}.projectile_speed", w["projectile_speed"]
        )
        _require_positive(
            f"weapons.{name}.projectile_count", w["projectile_count"]
        )
        _require_positive(
            f"weapons.{name}.projectile_ttl", w["projectile_ttl"]
        )


def _validate_passive(name: str, p: dict) -> None:
    """Range validation for one passive entry."""
    _require_positive(f"passives.{name}.max_level", p["max_level"])
    _require_positive(f"passives.{name}.multiplier_per_level", p["multiplier_per_level"])


def _validate_upgrade(name: str, u: dict) -> None:
    """Range/enum validation for one permanent-upgrade entry (Phase 4A)."""
    _require_positive(f"upgrades.{name}.max_level", u["max_level"])
    if u["stat"] not in _VALID_UPGRADE_STATS:
        raise ValueError(
            f"config: upgrades.{name}.stat must be one of "
            f"{sorted(_VALID_UPGRADE_STATS)}, got {u['stat']!r} "
            f"(check config/balance.toml)"
        )
    _require_positive(
        f"upgrades.{name}.multiplier_per_level", u["multiplier_per_level"]
    )
    _require_positive(f"upgrades.{name}.cost_base", u["cost_base"])
    # Cost must not shrink with level -- a growth < 1 would make higher levels
    # cheaper. Mirrors the xp curve's "growth >= 1" progression intent.
    if float(u["cost_growth"]) < 1.0:
        raise ValueError(
            f"config: upgrades.{name}.cost_growth must be >= 1.0, got "
            f"{u['cost_growth']!r} (check config/balance.toml)"
        )


def _validate_enemy(name: str, e: dict) -> None:
    """Range validation for one enemy entry."""
    _require_positive(f"enemies.{name}.hp", e["hp"])
    _require_positive(f"enemies.{name}.move_speed", e["move_speed"])
    # spawn_weight stays > 0 even for a boss (which is excluded from the weighted
    # pool): the value is unused for a boss, but one positive-weight rule for every
    # enemy is simpler than a boss-only exemption. xp_value is the death reward.
    _require_positive(f"enemies.{name}.spawn_weight", e["spawn_weight"])
    _require_positive(f"enemies.{name}.xp_value", e["xp_value"])
    # A firing enemy (fire_cadence > 0, a caster boss) must carry a positive shot
    # damage, speed, and ttl, else it would emit no-op projectiles. fire_cadence 0
    # is a non-firing enemy, which legitimately leaves the other fire fields at 0.
    # A negative cadence would never tick down to a shot, so it is rejected.
    # Reject a bool before float(): bool is an int subclass, so fire_cadence=true
    # would parse as 1.0 and silently turn a non-firing enemy into a caster. Mirrors
    # the explicit bool guard for director.boss_spawn_times.
    if isinstance(e["fire_cadence"], bool):
        raise ValueError(
            f"config: enemies.{name}.fire_cadence must be a number >= 0, got "
            f"{e['fire_cadence']!r} (check config/balance.toml)"
        )
    fire_cadence = float(e["fire_cadence"])
    if fire_cadence < 0.0:
        raise ValueError(
            f"config: enemies.{name}.fire_cadence must be >= 0, got "
            f"{e['fire_cadence']!r} (check config/balance.toml)"
        )
    if fire_cadence > 0.0:
        _require_positive(f"enemies.{name}.fire_damage", e["fire_damage"])
        _require_positive(f"enemies.{name}.fire_speed", e["fire_speed"])
        _require_positive(f"enemies.{name}.fire_ttl", e["fire_ttl"])


def _validate_reinforce_steps(steps) -> None:
    """Validate the director's per-minute reinforce table row by row.

    Each row must be ``[minute, interval_mult, concurrent]`` with ``minute >= 0``,
    ``interval_mult > 0``, ``concurrent >= 1``, and the minute thresholds must be
    non-decreasing (sim/spawn's active-step lookup assumes ascending order). A
    malformed or out-of-range row would make the director never spawn, spawn zero
    enemies, or select steps unpredictably, so it is rejected at load time with a
    message naming the offending row index and config/balance.toml.
    """
    prev_minute: float | None = None
    for idx, row in enumerate(steps):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError(
                f"config: director.reinforce_steps[{idx}] must be "
                f"[minute, interval_mult, concurrent], got {row!r} "
                f"(check config/balance.toml)"
            )
        minute, interval_mult, concurrent = row
        if minute < 0:
            raise ValueError(
                f"config: director.reinforce_steps[{idx}].minute must be >= 0, "
                f"got {minute!r} (check config/balance.toml)"
            )
        _require_positive(
            f"director.reinforce_steps[{idx}].interval_mult", interval_mult
        )
        if int(concurrent) < 1:
            raise ValueError(
                f"config: director.reinforce_steps[{idx}].concurrent must be "
                f">= 1, got {concurrent!r} (check config/balance.toml)"
            )
        if prev_minute is not None and minute < prev_minute:
            raise ValueError(
                f"config: director.reinforce_steps minutes must be "
                f"non-decreasing, got {minute!r} after {prev_minute!r} at index "
                f"{idx} (check config/balance.toml)"
            )
        prev_minute = minute


def _validate_boss_spawn_times(times) -> None:
    """Validate the director's boss spawn schedule.

    Each mark is an elapsed-seconds value >= 0 at which a boss spawns. An empty
    schedule is valid (no boss). A negative mark would never be crossed by the
    monotonic elapsed timer (so the boss would never appear), and a bool sneaks
    through ``isinstance(x, int)``, so both are rejected at load time naming the
    offending index and config/balance.toml.
    """
    for idx, t in enumerate(times):
        if isinstance(t, bool) or not isinstance(t, (int, float)) or t < 0:
            raise ValueError(
                f"config: director.boss_spawn_times[{idx}] must be a number >= 0, "
                f"got {t!r} (check config/balance.toml)"
            )


def _normalized_balance(balance_data: dict) -> dict:
    """Fill defaults + validate ranges, returning a dict ready for build_defs.

    Each section's entries are merged over code defaults (so a partial entry or a
    whole missing section still yields a usable table on first launch), then
    range-validated. The returned dict mirrors the balance.toml schema and is a
    fresh structure -- ``balance_data`` is never mutated.

    Raises:
        ValueError: if any balance value is out of range; the message names the
            offending dotted key and points at config/balance.toml.
    """
    leveling_raw = balance_data.get("leveling", {})
    leveling = {
        "draft_choices": _i(leveling_raw, "draft_choices", _LEVELING_DEFAULTS),
        "xp_curve_base": _f(leveling_raw, "xp_curve_base", _LEVELING_DEFAULTS),
        "xp_curve_growth": _f(leveling_raw, "xp_curve_growth", _LEVELING_DEFAULTS),
    }
    _require_positive("leveling.draft_choices", leveling["draft_choices"])
    _require_positive("leveling.xp_curve_base", leveling["xp_curve_base"])
    # The xp curve is base * growth ** (level - 1); rules.leveling.xp_for_level
    # documents it as monotonically increasing, which holds only for growth > 1.0.
    # A growth of <= 1.0 would make later levels require equal or *less* xp, which
    # breaks progression and the determinism assumptions in tests/docs.
    if leveling["xp_curve_growth"] <= 1.0:
        raise ValueError(
            f"config: leveling.xp_curve_growth must be > 1.0 (a monotonically "
            f"increasing xp curve), got {leveling['xp_curve_growth']!r} "
            f"(check config/balance.toml)"
        )

    # Sections fall back to a default name set when absent, so the rules layer
    # always has at least the starting content.
    weapons_raw = balance_data.get("weapons", {})
    weapon_names = list(weapons_raw) or list(_DEFAULT_WEAPON_NAMES)
    weapons = {}
    for name in weapon_names:
        w = _merged_section(weapons_raw, name, _WEAPON_DEFAULTS)
        _validate_weapon(name, w)
        weapons[name] = w

    # A run begins owning the starting weapon (rules.leveling.BuildState's
    # default). If the user provided a [weapons.*] section it must define that
    # weapon -- otherwise the run starts holding a weapon with no WeaponDef, which
    # never fires and skews the level-up draft pool. When no weapons section is
    # given the default content set (which includes it) is used, so this only
    # guards user-authored balance files.
    if weapons_raw and STARTING_WEAPON not in weapons:
        raise ValueError(
            f"config: the starting weapon {STARTING_WEAPON!r} must be defined in "
            f"[weapons.*] (a run begins owning it); add it or the run starts with "
            f"a weapon that has no stats (check config/balance.toml)"
        )

    passives_raw = balance_data.get("passives", {})
    passive_names = list(passives_raw) or list(_DEFAULT_PASSIVE_NAMES)
    passives = {}
    for name in passive_names:
        p = _merged_section(passives_raw, name, _PASSIVE_DEFAULTS)
        _validate_passive(name, p)
        passives[name] = p

    # Permanent upgrades are optional content: no default-name injection (an
    # absent [upgrades.*] section yields an empty table, unlike weapons/passives
    # which fall back to a starter set so a run always has content).
    upgrades_raw = balance_data.get("upgrades", {})
    upgrades = {}
    for name in upgrades_raw:
        u = _merged_section(upgrades_raw, name, _UPGRADE_DEFAULTS)
        _validate_upgrade(name, u)
        upgrades[name] = u

    enemies_raw = balance_data.get("enemies", {})
    enemy_names = list(enemies_raw) or list(_DEFAULT_ENEMY_NAMES)
    enemies = {}
    for name in enemy_names:
        e = _merged_section(enemies_raw, name, _ENEMY_DEFAULTS)
        _validate_enemy(name, e)
        enemies[name] = e

    evolution_raw = balance_data.get("evolution", {})
    # Only inject default evolutions when the ENTIRE balance file is absent (both
    # weapons and evolution sections missing). If the user specified weapons but
    # omitted evolutions, we produce an empty evolution table rather than injecting
    # defaults that may reference weapons the user did not define.
    _no_user_balance = not weapons_raw and not evolution_raw
    evolution_names = list(evolution_raw) or (
        list(_DEFAULT_EVOLUTION_NAMES) if _no_user_balance else []
    )
    evolution = {}
    for name in evolution_names:
        ev = _merged_section(evolution_raw, name, _EVOLUTION_DEFAULTS)
        _require_positive(f"evolution.{name}.base_max_level", ev["base_max_level"])
        evolution[name] = ev

    director_raw = balance_data.get("director", {})
    director = {
        "base_spawn_interval": _f(
            director_raw, "base_spawn_interval", _DIRECTOR_DEFAULTS
        ),
        "min_spawn_interval": _f(
            director_raw, "min_spawn_interval", _DIRECTOR_DEFAULTS
        ),
        "reinforce_steps": director_raw.get(
            "reinforce_steps", _DIRECTOR_DEFAULTS["reinforce_steps"]
        ),
        "boss_spawn_times": director_raw.get("boss_spawn_times", []),
    }
    _require_positive("director.base_spawn_interval", director["base_spawn_interval"])
    _require_positive("director.min_spawn_interval", director["min_spawn_interval"])
    if not director["reinforce_steps"]:
        raise ValueError(
            "config: director.reinforce_steps must be non-empty "
            "(check config/balance.toml)"
        )
    _validate_reinforce_steps(director["reinforce_steps"])
    _validate_boss_spawn_times(director["boss_spawn_times"])

    pickup_raw = balance_data.get("pickup", {})
    magnet_range = _f(pickup_raw, "magnet_range", _PICKUP_DEFAULTS)
    _require_positive("pickup.magnet_range", magnet_range)

    meta_raw = balance_data.get("meta", {})
    gold_per_kill = _i(meta_raw, "gold_per_kill", _META_DEFAULTS)
    _require_positive("meta.gold_per_kill", gold_per_kill)

    # Cross-reference: every evolution's base, result_weapon, and requires_passive
    # must resolve to real entries in their respective tables.
    for evo_name, ev in evolution.items():
        base = ev["base"]
        if base not in weapons:
            raise ValueError(
                f"config: evolution.{evo_name}.base '{base}' does not name a "
                f"weapon defined in [weapons.*] (check config/balance.toml)"
            )
        result = ev["result_weapon"]
        if result not in weapons:
            raise ValueError(
                f"config: evolution.{evo_name}.result_weapon '{result}' does not "
                f"name a weapon defined in [weapons.*] (check config/balance.toml)"
            )
        req_passive = ev["requires_passive"]
        if req_passive not in passives:
            raise ValueError(
                f"config: evolution.{evo_name}.requires_passive '{req_passive}' "
                f"does not name a passive defined in [passives.*] "
                f"(check config/balance.toml)"
            )

    return {
        "leveling": leveling,
        "weapons": weapons,
        "passives": passives,
        "upgrades": upgrades,
        "enemies": enemies,
        "evolution": evolution,
        "director": director,
        "pickup": {"magnet_range": magnet_range},
        "meta": {"gold_per_kill": gold_per_kill},
    }


def _build_defs(balance_data: dict) -> BalanceDefs:
    """Normalize + validate the raw balance dict, then build the typed tables."""
    return build_defs(_normalized_balance(balance_data))


def load_config(tuning_path: str | Path, balance_path: str | Path) -> Config:
    """Load and validate both TOML files into a frozen :class:`Config`.

    Missing keys (or a missing file) fall back to code defaults. Out-of-range
    operating-point or balance values raise a clear ``ValueError``.

    Args:
        tuning_path: path to the operating-point TOML (tuning.toml).
        balance_path: path to the game-balance TOML (balance.toml).

    Returns:
        An immutable :class:`Config`.

    Raises:
        ValueError: if a rate/size value is not strictly positive, or a weapon
            declares an unknown targeting strategy.
    """
    tuning = _load_toml(tuning_path)
    balance_data = _load_toml(balance_path)

    sim_tps = _f(tuning, "sim_tps", _TUNING_DEFAULTS)
    poll_timeout = _f(tuning, "poll_timeout", _TUNING_DEFAULTS)
    max_catchup = _i(tuning, "max_catchup", _TUNING_DEFAULTS)
    viewport_w = _i(tuning, "viewport_w", _TUNING_DEFAULTS)
    viewport_h = _i(tuning, "viewport_h", _TUNING_DEFAULTS)
    entity_cap = _i(tuning, "entity_cap", _TUNING_DEFAULTS)
    aspect_x = _f(tuning, "aspect_x", _TUNING_DEFAULTS)
    render_mode = str(tuning.get("render_mode", _TUNING_DEFAULTS["render_mode"]))
    if render_mode not in ("full", "diff"):
        raise ValueError(
            f"config: render_mode must be 'full' or 'diff', got {render_mode!r} "
            f"(check config/tuning.toml)"
        )

    # Range validation: rates and sizes must be strictly positive.
    _require_positive("sim_tps", sim_tps)
    _require_positive("poll_timeout", poll_timeout)
    _require_positive("max_catchup", max_catchup)
    _require_positive("viewport_w", viewport_w)
    _require_positive("viewport_h", viewport_h)
    _require_positive("entity_cap", entity_cap)
    _require_positive("aspect_x", aspect_x)

    return Config(
        sim_tps=sim_tps,
        poll_timeout=poll_timeout,
        max_catchup=max_catchup,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        entity_cap=entity_cap,
        aspect_x=aspect_x,
        render_mode=render_mode,
        defs=_build_defs(balance_data),
    )


def _repo_config_dir() -> Path:
    """Path to the repo's ``config/`` directory, derived from this file.

    cwd-independent: walks up from ``terminal_vs/config.py`` to the repo root.
    """
    return Path(__file__).resolve().parent.parent / "config"


def load_default_config() -> Config:
    """Load the repo's ``config/tuning.toml`` and ``config/balance.toml``."""
    config_dir = _repo_config_dir()
    return load_config(config_dir / "tuning.toml", config_dir / "balance.toml")
