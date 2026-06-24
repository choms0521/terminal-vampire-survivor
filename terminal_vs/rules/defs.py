"""terminal_vs.rules.defs - balance-table accessors (Day 4).

Thin pure accessors that read the injected immutable :class:`Config`'s balance
table. They exist so the rest of the rules layer (and sim) depend on these
accessors rather than reaching into ``cfg.balance.*`` directly, keeping the
balance-read surface in one place. No side effects, no blessed.
"""

from __future__ import annotations

from ..config import Config, EnemyBalance, WeaponBalance, XpCurve


def weapon_def(cfg: Config) -> WeaponBalance:
    """Return the immutable weapon (dagger) balance from cfg."""
    return cfg.balance.weapon


def enemy_def(cfg: Config) -> EnemyBalance:
    """Return the immutable enemy balance from cfg."""
    return cfg.balance.enemy


def xp_curve(cfg: Config) -> XpCurve:
    """Return the immutable xp-curve parameters from cfg."""
    return cfg.balance.xp


def magnet_range(cfg: Config) -> float:
    """Return the pickup auto-collect radius (world units) from cfg."""
    return cfg.balance.magnet_range
