"""Tests for terminal_vs.rules.weapons.tick_weapon: cooldown, targeting, purity."""

from __future__ import annotations

import copy
import random
from math import hypot

from terminal_vs.rules.weapons import (
    FireContext,
    InstantHitSpec,
    ProjectileSpec,
    WeaponFireResult,
    tick_weapon,
)

from .conftest import make_defs


def _ctx(
    *,
    weapon: str,
    enemies: tuple[tuple[int, float, float], ...],
    player_pos: tuple[float, float] = (0.0, 0.0),
    facing: tuple[float, float] = (1.0, 0.0),
    attack_speed_mult: float = 1.0,
    dt: float = 0.05,
    aspect_x: float = 2.0,
) -> FireContext:
    """Build a FireContext for ``weapon`` from make_defs."""
    defs = make_defs()
    return FireContext(
        player_pos=player_pos,
        player_facing=facing,
        enemy_positions=enemies,
        weapon_def=defs.weapons[weapon],
        attack_speed_mult=attack_speed_mult,
        dt=dt,
        aspect_x=aspect_x,
    )


def test_cooldown_blocks_fire():
    """A positive remaining cooldown blocks the fire and decrements by dt."""
    ctx = _ctx(weapon="dagger", enemies=((0, 3.0, 0.0),), dt=0.05)
    result = tick_weapon(cooldown_remaining=1.0, ctx=ctx, rng=random.Random(0))
    assert isinstance(result, WeaponFireResult)
    assert result.fired is False
    # Remaining cooldown reduced by exactly dt.
    assert abs(result.new_cooldown - 0.95) < 1e-9
    assert result.projectiles == ()
    assert result.instant_hits == ()


def test_dagger_targets_nearest():
    """The dagger aims its projectile at the nearest enemy (aspect-corrected)."""
    # Player at origin, aspect_x=2 weights X distance 2x. Enemy 1 at (0,3) is
    # nearest on screen; the projectile velocity must point straight up (+Y).
    enemies = (
        (0, 10.0, 0.0),   # aspect d2 = (10*2)^2 = 400
        (1, 0.0, 3.0),    # aspect d2 = 9   <- nearest
        (2, 5.0, 5.0),    # aspect d2 = 125
    )
    ctx = _ctx(weapon="dagger", enemies=enemies, dt=1.0)
    result = tick_weapon(cooldown_remaining=0.5, ctx=ctx, rng=random.Random(0))
    assert result.fired is True
    assert len(result.projectiles) == 1
    spec = result.projectiles[0]
    assert isinstance(spec, ProjectileSpec)
    # Aimed at (0,3): unit direction (0, 1) scaled to projectile_speed (14.0).
    assert abs(spec.vx - 0.0) < 1e-9
    assert abs(spec.vy - 14.0) < 1e-9
    assert abs(hypot(spec.vx, spec.vy) - 14.0) < 1e-9


def test_dagger_nearest_tie_breaks_to_lowest_id():
    """On an aspect-distance tie the dagger targets the lowest enemy id."""
    # Two enemies mirrored across the player are at identical aspect distance.
    enemies = ((7, 4.0, 0.0), (3, -4.0, 0.0))
    ctx = _ctx(weapon="dagger", enemies=enemies, dt=1.0)
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    assert result.fired is True
    # id 3 is at -4 on X, so the projectile flies in the -X direction.
    assert result.projectiles[0].vx < 0.0


def test_swing_forward_arc_hits_only_arc():
    """The swing instant-hits only enemies in the forward arc; rear excluded."""
    # Facing +X. Enemy 0 ahead (in range), enemy 1 directly behind (excluded),
    # enemy 2 far ahead beyond arc_range (excluded).
    enemies = (
        (0, 3.0, 0.0),     # ahead, within arc_range=5 -> HIT
        (1, -3.0, 0.0),    # behind -> excluded (cos < 0)
        (2, 9.0, 0.0),     # ahead but beyond arc_range -> excluded
    )
    ctx = _ctx(weapon="swing", enemies=enemies, facing=(1.0, 0.0), dt=1.0)
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    assert result.fired is True
    assert result.projectiles == ()
    hit_ids = [h.target_id for h in result.instant_hits]
    assert hit_ids == [0]
    assert all(isinstance(h, InstantHitSpec) for h in result.instant_hits)


def test_swing_no_target_in_arc_does_not_fire():
    """With no enemy in the arc the swing does not fire and resets cooldown to 0."""
    # Only a rear enemy: nothing in the forward arc.
    ctx = _ctx(weapon="swing", enemies=((0, -3.0, 0.0),), facing=(1.0, 0.0), dt=1.0)
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    assert result.fired is False
    assert result.new_cooldown == 0.0


def test_magic_bolt_random_target_deterministic():
    """nearest_or_random resolves equidistant ties deterministically per seed."""
    # Four enemies equidistant from the player (all at aspect d2 = 4) so the
    # tie-break path (rng.choice among tied) is exercised.
    enemies = (
        (0, 1.0, 0.0),
        (1, -1.0, 0.0),
        (2, 0.0, 2.0),
        (3, 0.0, -2.0),
    )

    def run(seed: int) -> ProjectileSpec:
        ctx = _ctx(weapon="magic_bolt", enemies=enemies, dt=1.0)
        result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(seed))
        assert result.fired is True
        return result.projectiles[0]

    # Same seed -> same target (same velocity vector).
    a = run(42)
    b = run(42)
    assert (a.vx, a.vy) == (b.vx, b.vy)


def test_tick_weapon_is_pure():
    """tick_weapon mutates neither its context nor its enemy snapshot."""
    enemies = ((0, 3.0, 0.0), (1, 0.0, 4.0))
    ctx = _ctx(weapon="dagger", enemies=enemies, dt=1.0)
    ctx_before = copy.deepcopy(ctx)
    tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(1))
    # The frozen context (and its enemy tuple) is unchanged after the call.
    assert ctx == ctx_before
    assert ctx.enemy_positions == enemies


def test_swing_hits_off_axis_in_cone_not_rear():
    """Swing (arc_half_width=0.3) hits an off-axis-but-inside-cone enemy; rear excluded.

    The shipped swing has arc_half_width=0.3 (~cos(72 deg) cone half-angle).
    Facing +X:
      - enemy 0 at (3, 1): cos_angle = 3/sqrt(10) ~= 0.949 > 0.3 -> IN cone -> HIT
      - enemy 1 at (-2, 0): directly behind, cos_angle = -1 < 0.3 -> EXCLUDED
    """
    from terminal_vs.rules.defs import WeaponDef

    swing_def = WeaponDef(
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
    )
    enemies = (
        (0, 3.0, 1.0),   # off-axis but inside cone: cos ~= 0.949 > 0.3 -> HIT
        (1, -2.0, 0.0),  # directly behind: cos = -1 < 0.3 -> EXCLUDED
    )
    ctx = FireContext(
        player_pos=(0.0, 0.0),
        player_facing=(1.0, 0.0),
        enemy_positions=enemies,
        weapon_def=swing_def,
        attack_speed_mult=1.0,
        dt=1.0,
        aspect_x=2.0,
    )
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    assert result.fired is True
    hit_ids = [h.target_id for h in result.instant_hits]
    assert 0 in hit_ids, "off-axis but in-cone enemy must be hit"
    assert 1 not in hit_ids, "rear enemy must be excluded"


def test_nearest_or_random_tie_order_independent():
    """nearest_or_random picks the same target regardless of enemy buffer order.

    Chunk 2 may swap-remove enemies, changing iteration order. The tie-break sort
    by id before rng.choice ensures the same seed always yields the same target.
    """
    enemies_fwd = (
        (0, 1.0, 0.0),
        (1, -1.0, 0.0),
        (2, 0.0, 2.0),
        (3, 0.0, -2.0),
    )
    # Reversed order — simulates a swap-remove producing a different iteration order.
    enemies_rev = tuple(reversed(enemies_fwd))

    seed = 77

    ctx_fwd = _ctx(weapon="magic_bolt", enemies=enemies_fwd, dt=1.0)
    ctx_rev = _ctx(weapon="magic_bolt", enemies=enemies_rev, dt=1.0)

    result_fwd = tick_weapon(cooldown_remaining=0.0, ctx=ctx_fwd, rng=random.Random(seed))
    result_rev = tick_weapon(cooldown_remaining=0.0, ctx=ctx_rev, rng=random.Random(seed))

    assert result_fwd.fired is True
    assert result_rev.fired is True
    # Velocity vector (= aimed-at target) must be identical regardless of order.
    assert (result_fwd.projectiles[0].vx, result_fwd.projectiles[0].vy) == (
        result_rev.projectiles[0].vx,
        result_rev.projectiles[0].vy,
    ), "same seed must hit same target regardless of enemy buffer order"


def test_multishot_fans_projectiles_across_the_spread():
    """A multi-shot weapon fans its shots across spread_angle instead of stacking
    them on one line: dagger_evolved (count 3, spread 30 deg) fires three darts at
    distinct angles, the middle one dead-on the target, all at the same speed."""
    # Target straight along +X so the fan spreads symmetrically in Y.
    ctx = _ctx(weapon="dagger_evolved", enemies=((0, 5.0, 0.0),), dt=1.0)
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    assert result.fired is True
    specs = result.projectiles
    assert len(specs) == 3  # projectile_count darts

    speed = 18.0  # dagger_evolved projectile_speed; only DIRECTION differs per shot
    for s in specs:
        assert abs(hypot(s.vx, s.vy) - speed) < 1e-9
    # The shots fan out: their Y velocities are strictly distinct (not stacked).
    vys = sorted(s.vy for s in specs)
    assert vys[0] < vys[1] < vys[2]
    # Symmetric about the +X aim: middle dart straight, outer two mirror in Y.
    assert abs(vys[1]) < 1e-9            # middle dart dead-on the target
    assert abs(vys[0] + vys[2]) < 1e-9   # outer darts mirror in Y
    assert all(s.vx > 0.0 for s in specs)  # all still travel toward the target


def test_zero_spread_stacks_multishot_backward_compatible():
    """A multi-shot weapon with spread_angle == 0 stacks every shot on the aim line
    (the pre-fan behavior), so weapon data without a spread is unchanged."""
    from dataclasses import replace

    defs = make_defs()
    stacked = replace(defs.weapons["dagger_evolved"], spread_angle=0.0)
    ctx = FireContext(
        player_pos=(0.0, 0.0),
        player_facing=(1.0, 0.0),
        enemy_positions=((0, 5.0, 0.0),),
        weapon_def=stacked,
        attack_speed_mult=1.0,
        dt=1.0,
        aspect_x=2.0,
    )
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))
    specs = result.projectiles
    assert len(specs) == 3
    # Zero spread -> every dart identical (stacked on the aim line).
    assert all((s.vx, s.vy) == (specs[0].vx, specs[0].vy) for s in specs)
