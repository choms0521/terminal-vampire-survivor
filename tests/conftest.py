"""Shared test fixtures/helpers for the headless deterministic tests.

Tests build a Config directly (no TOML) so they are self-contained and fast.
Literal numbers are fine here -- the no-hardcode perf gate scans only the
``terminal_vs/`` package, not tests.
"""

from __future__ import annotations

from terminal_vs.config import (
    BalanceTable,
    Config,
    EnemyBalance,
    WeaponBalance,
    XpCurve,
)


def make_config(
    *,
    aspect_x: float = 2.0,
    viewport_w: int = 100,
    viewport_h: int = 30,
    entity_cap: int = 200,
    sim_tps: float = 20.0,
    weapon_cooldown: float = 0.6,
    weapon_damage: float = 10.0,
    projectile_speed: float = 18.0,
    projectile_ttl: float = 1.2,
    enemy_hp: float = 20.0,
    enemy_move_speed: float = 4.0,
    xp_base: float = 5.0,
    xp_growth: float = 1.5,
    magnet_range: float = 4.0,
) -> Config:
    """Construct a Config for tests with sensible, overridable defaults."""
    balance = BalanceTable(
        weapon=WeaponBalance(
            cooldown=weapon_cooldown,
            damage=weapon_damage,
            projectile_speed=projectile_speed,
            projectile_ttl=projectile_ttl,
        ),
        enemy=EnemyBalance(
            hp=enemy_hp,
            move_speed=enemy_move_speed,
            spawn_weight=1.0,
        ),
        xp=XpCurve(base=xp_base, growth=xp_growth),
        magnet_range=magnet_range,
    )
    return Config(
        sim_tps=sim_tps,
        poll_timeout=0.005,
        max_catchup=5,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        entity_cap=entity_cap,
        aspect_x=aspect_x,
        render_mode="full",
        balance=balance,
    )
