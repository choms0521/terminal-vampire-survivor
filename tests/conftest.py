"""Shared test fixtures/helpers for the headless deterministic tests.

Tests build a Config / BalanceDefs directly (no TOML) so they are self-contained
and fast. Literal numbers are fine here -- the no-hardcode perf gate scans only
the ``terminal_vs/`` package, not tests.

Two helpers:

  * :func:`make_config` builds an immutable :class:`Config` with the
    operating-point fields plus a default :class:`BalanceDefs` on ``.defs``.
    Operating-point kwargs (aspect_x, viewport_w/h, entity_cap, sim_tps) are
    overridable so world/spatial/damage tests can tune the viewport.
  * :func:`make_defs` builds a small :class:`BalanceDefs` for the rules tests to
    inject (weapons / passives / enemies / evolution / director / leveling /
    magnet range), with sensible overridable defaults.
"""

from __future__ import annotations

from terminal_vs.config import Config
from terminal_vs.rules.defs import (
    BalanceDefs,
    DirectorDef,
    EnemyDef,
    EvolutionDef,
    LevelingDef,
    PassiveDef,
    ReinforceStep,
    WeaponDef,
)


def make_defs(
    *,
    weapons: dict[str, WeaponDef] | None = None,
    passives: dict[str, PassiveDef] | None = None,
    enemies: dict[str, EnemyDef] | None = None,
    evolutions: tuple[EvolutionDef, ...] | None = None,
    director: DirectorDef | None = None,
    leveling: LevelingDef | None = None,
    magnet_range: float = 4.0,
) -> BalanceDefs:
    """Build a small immutable BalanceDefs for rules tests, with defaults.

    The default content mirrors the Phase 2 starter set: dagger / magic_bolt /
    swing / dagger_evolved weapons, attack_speed / move_speed / magnet passives,
    walker / swarm enemies, the dagger_x evolution, a 4-step director curve, and
    the standard leveling curve. Any group can be overridden wholesale.
    """
    if weapons is None:
        weapons = {
            "dagger": WeaponDef(
                name="dagger",
                max_level=8,
                cooldown=1.2,
                damage=6.0,
                projectile_count=1,
                projectile_speed=14.0,
                projectile_ttl=1.2,
                targeting="nearest",
                glyph="-",
                color="white",
            ),
            "magic_bolt": WeaponDef(
                name="magic_bolt",
                max_level=8,
                cooldown=1.8,
                damage=9.0,
                projectile_count=1,
                projectile_speed=10.0,
                projectile_ttl=1.6,
                targeting="nearest_or_random",
                glyph="*",
                color="cyan",
            ),
            "swing": WeaponDef(
                name="swing",
                max_level=8,
                cooldown=1.0,
                damage=8.0,
                projectile_count=0,
                projectile_speed=0.0,
                projectile_ttl=0.0,
                targeting="forward_arc",
                arc_range=5.0,
                arc_half_width=0.3,
                glyph=")",
                color="red",
            ),
            "dagger_evolved": WeaponDef(
                name="dagger_evolved",
                max_level=1,
                cooldown=0.6,
                damage=10.0,
                projectile_count=3,
                projectile_speed=18.0,
                projectile_ttl=1.2,
                targeting="nearest",
                pierce=4,
                glyph=">",
                color="yellow",
                spread_angle=30.0,
            ),
        }
    if passives is None:
        passives = {
            "attack_speed": PassiveDef(
                name="attack_speed", max_level=5, multiplier_per_level=0.92
            ),
            "move_speed": PassiveDef(
                name="move_speed", max_level=5, multiplier_per_level=1.08
            ),
            "magnet": PassiveDef(
                name="magnet", max_level=5, multiplier_per_level=1.25
            ),
        }
    if enemies is None:
        enemies = {
            "walker": EnemyDef(
                name="walker",
                hp=10.0,
                move_speed=2.5,
                spawn_weight=70.0,
                glyph="z",
                color="red",
            ),
            "swarm": EnemyDef(
                name="swarm",
                hp=4.0,
                move_speed=5.0,
                spawn_weight=30.0,
                glyph="x",
                color="magenta",
            ),
        }
    if evolutions is None:
        evolutions = (
            EvolutionDef(
                name="dagger_x",
                base="dagger",
                requires_passive="attack_speed",
                base_max_level=8,
                result_weapon="dagger_evolved",
            ),
        )
    if director is None:
        director = DirectorDef(
            base_spawn_interval=2.0,
            min_spawn_interval=0.4,
            reinforce_steps=(
                ReinforceStep(0, 1.0, 1),
                ReinforceStep(1, 0.8, 2),
                ReinforceStep(2, 0.6, 3),
                ReinforceStep(3, 0.5, 4),
            ),
        )
    if leveling is None:
        leveling = LevelingDef(
            draft_choices=3, xp_curve_base=5.0, xp_curve_growth=1.5
        )
    return BalanceDefs(
        weapons=weapons,
        passives=passives,
        enemies=enemies,
        evolutions=evolutions,
        director=director,
        leveling=leveling,
        magnet_range=magnet_range,
    )


def make_config(
    *,
    aspect_x: float = 2.0,
    viewport_w: int = 100,
    viewport_h: int = 30,
    entity_cap: int = 200,
    sim_tps: float = 20.0,
    render_mode: str = "full",
    defs: BalanceDefs | None = None,
) -> Config:
    """Construct a Config for tests with overridable operating-point defaults.

    The balance side is a default :func:`make_defs` unless ``defs`` is provided,
    so world/spatial/damage tests that only touch operating-point fields need not
    care about balance content.
    """
    return Config(
        sim_tps=sim_tps,
        poll_timeout=0.005,
        max_catchup=5,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        entity_cap=entity_cap,
        aspect_x=aspect_x,
        render_mode=render_mode,
        defs=defs if defs is not None else make_defs(),
    )
