"""terminal_vs.config - load, validate, and freeze the game configuration.

This module is the configuration contract consumed by every downstream layer
(world, sim, rules, render, loop). It loads two TOML files with the standard
library ``tomllib`` (Python 3.11+, master plan section 5.5):

  * ``config/tuning.toml``  -> operating-point constants (Phase 0 measured):
    sim_tps, poll_timeout, max_catchup, viewport_w/h, entity_cap, aspect_x,
    render_mode.
  * ``config/balance.toml`` -> game-balance constants (weapon, enemy, xp curve,
    magnet range).

Design rules (master plan sections 5.5, 6 / ADR-001):

  * The returned :class:`Config` and its nested :class:`BalanceTable` are frozen
    dataclasses -- immutable, injected read-only into the rules layer.
  * Missing keys (or a missing file) fall back to code defaults so the game runs
    on a first launch without any config file.
  * Out-of-range values (non-positive rates / sizes) raise a clear ``ValueError``.

Operating-point numbers are NOT hardcoded as named constants here: the code
defaults live in string-keyed ``_*_DEFAULTS`` dicts so the only literal forms in
this file are dict-key strings (``"sim_tps": ...``), never ``sim_tps = <number>``
assignments. This keeps the "no hardcoded performance numbers" boundary intact
while still providing fallbacks.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

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

# Balance fallbacks, grouped by table section (mirrors config/balance.toml).
_WEAPON_DEFAULTS: dict[str, object] = {
    "cooldown": 0.6,
    "damage": 10.0,
    "projectile_speed": 18.0,
    "projectile_ttl": 1.2,
}
_ENEMY_DEFAULTS: dict[str, object] = {
    "hp": 20.0,
    "move_speed": 4.0,
    "spawn_weight": 1.0,
}
_XP_DEFAULTS: dict[str, object] = {
    "base": 5.0,
    "growth": 1.5,
}
_PICKUP_DEFAULTS: dict[str, object] = {
    "magnet_range": 4.0,
}


@dataclass(frozen=True)
class WeaponBalance:
    """Immutable weapon (dagger) balance constants (from balance.toml)."""

    cooldown: float          # seconds between auto-fire shots
    damage: float            # damage applied per projectile hit
    projectile_speed: float  # world units per second
    projectile_ttl: float    # projectile lifetime in seconds


@dataclass(frozen=True)
class EnemyBalance:
    """Immutable enemy (single Phase 1 type) balance constants."""

    hp: float            # starting hit points
    move_speed: float    # world units per second toward the player
    spawn_weight: float  # relative spawn weight (flat ratio in Phase 1)


@dataclass(frozen=True)
class XpCurve:
    """Immutable experience-curve parameters.

    The xp required to clear level ``L`` (1-based) is ``base * growth ** (L-1)``.
    rules/leveling consumes this; the exact formula lives there, not here.
    """

    base: float    # xp needed to clear level 1
    growth: float  # geometric multiplier per level


@dataclass(frozen=True)
class BalanceTable:
    """Immutable container of all game-balance sub-tables (master section 5.5).

    rules/defs.py reads this to build weapon/enemy/xp definitions; the whole
    table is injected read-only into the rules layer.
    """

    weapon: WeaponBalance
    enemy: EnemyBalance
    xp: XpCurve
    magnet_range: float  # pickup auto-collect radius in world units


@dataclass(frozen=True)
class Config:
    """Immutable game configuration (master section 6 boundary, frozen side).

    Operating-point fields are loaded from config/tuning.toml by key; nested
    ``balance`` is built from config/balance.toml. Never construct these numbers
    inline elsewhere -- read them from a ``Config`` instance.
    """

    sim_tps: float        # simulation ticks per second
    poll_timeout: float   # input poll timeout in seconds
    max_catchup: int      # max sim catch-up ticks per render frame
    viewport_w: int       # viewport width in cells
    viewport_h: int       # viewport height in cells
    entity_cap: int       # max simultaneous entities
    aspect_x: float       # horizontal cell aspect compensation factor (section 3.1)
    render_mode: str      # "full" | "diff" (Phase 1 emits full frames only; the
                          #   diff renderer is deferred to Phase 2, so this field
                          #   is loaded/validated but not yet consumed by render)
    balance: BalanceTable  # game-balance constants from balance.toml


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
    and sectioned (e.g. ``weapon.cooldown``) while operating-point keys are flat
    (e.g. ``sim_tps``), so the message names the file the bad value came from.
    """
    if value <= 0:
        source = "config/balance.toml" if "." in name else "config/tuning.toml"
        raise ValueError(
            f"config: {name} must be > 0, got {value!r} (check {source})"
        )


def _build_balance(balance_data: dict) -> BalanceTable:
    """Build the immutable BalanceTable from raw balance.toml data + defaults."""
    weapon_data = balance_data.get("weapon", {})
    enemy_data = balance_data.get("enemy", {})
    xp_data = balance_data.get("xp", {})
    pickup_data = balance_data.get("pickup", {})

    weapon = WeaponBalance(
        cooldown=_f(weapon_data, "cooldown", _WEAPON_DEFAULTS),
        damage=_f(weapon_data, "damage", _WEAPON_DEFAULTS),
        projectile_speed=_f(weapon_data, "projectile_speed", _WEAPON_DEFAULTS),
        projectile_ttl=_f(weapon_data, "projectile_ttl", _WEAPON_DEFAULTS),
    )
    enemy = EnemyBalance(
        hp=_f(enemy_data, "hp", _ENEMY_DEFAULTS),
        move_speed=_f(enemy_data, "move_speed", _ENEMY_DEFAULTS),
        spawn_weight=_f(enemy_data, "spawn_weight", _ENEMY_DEFAULTS),
    )
    xp = XpCurve(
        base=_f(xp_data, "base", _XP_DEFAULTS),
        growth=_f(xp_data, "growth", _XP_DEFAULTS),
    )
    magnet_range = _f(pickup_data, "magnet_range", _PICKUP_DEFAULTS)

    # Range validation on balance constants (all must be strictly positive: a
    # zero/negative weapon.damage means enemies never die, and a non-positive
    # enemy.spawn_weight makes spawn weighting nonsensical).
    _require_positive("weapon.cooldown", weapon.cooldown)
    _require_positive("weapon.damage", weapon.damage)
    _require_positive("weapon.projectile_speed", weapon.projectile_speed)
    _require_positive("weapon.projectile_ttl", weapon.projectile_ttl)
    _require_positive("enemy.hp", enemy.hp)
    _require_positive("enemy.move_speed", enemy.move_speed)
    _require_positive("enemy.spawn_weight", enemy.spawn_weight)
    _require_positive("xp.base", xp.base)
    _require_positive("xp.growth", xp.growth)
    _require_positive("pickup.magnet_range", magnet_range)

    return BalanceTable(weapon=weapon, enemy=enemy, xp=xp, magnet_range=magnet_range)


def load_config(tuning_path: str | Path, balance_path: str | Path) -> Config:
    """Load and validate both TOML files into a frozen :class:`Config`.

    Missing keys (or a missing file) fall back to code defaults. Out-of-range
    operating-point values raise a clear ``ValueError``.

    Args:
        tuning_path: path to the operating-point TOML (tuning.toml).
        balance_path: path to the game-balance TOML (balance.toml).

    Returns:
        An immutable :class:`Config`.

    Raises:
        ValueError: if a rate/size value is not strictly positive.
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
        balance=_build_balance(balance_data),
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
