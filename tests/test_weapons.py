"""Tests for terminal_vs.rules.weapons: nearest targeting, tie-break, fire spec."""

from __future__ import annotations

from math import hypot

from terminal_vs.rules.weapons import (
    ProjectileSpec,
    select_target,
    should_fire,
    spawn_projectile_intent,
)

from .conftest import make_config


class _FakeEnemy:
    """Minimal enemy duck-type for targeting (id + x/y)."""

    def __init__(self, entity_id: int, x: float, y: float) -> None:
        self.id = entity_id
        self.x = x
        self.y = y


def test_select_nearest_of_three():
    cfg = make_config(aspect_x=2.0)
    # Player at origin. With aspect_x=2, X distance is weighted 2x, so the
    # nearest by on-screen distance is the one closest along Y here.
    enemies = [
        _FakeEnemy(0, 10.0, 0.0),   # aspect d2 = (10*2)^2 = 400
        _FakeEnemy(1, 0.0, 3.0),    # aspect d2 = 3^2 = 9   <- nearest
        _FakeEnemy(2, 5.0, 5.0),    # aspect d2 = (5*2)^2 + 25 = 125
    ]
    assert select_target(0.0, 0.0, enemies, cfg) == 1


def test_select_distance_tie_breaks_to_lowest_id():
    cfg = make_config(aspect_x=2.0)
    # Two enemies mirrored across the player are at identical aspect distance.
    # The tie MUST break to the lowest entity id (id 3 over id 7).
    enemies = [
        _FakeEnemy(7, 4.0, 0.0),
        _FakeEnemy(3, -4.0, 0.0),
    ]
    assert select_target(0.0, 0.0, enemies, cfg) == 3
    # Order-independence: same result if presented in the other order.
    assert select_target(0.0, 0.0, list(reversed(enemies)), cfg) == 3


def test_select_no_enemies_returns_none():
    cfg = make_config()
    assert select_target(0.0, 0.0, [], cfg) is None


def test_should_fire_is_threshold_on_remaining():
    # should_fire is a pure threshold on the sim-advanced timer: the sim advances
    # weapon_cooldown_remaining by dt each tick BEFORE calling this, so readiness
    # is `remaining <= 0`, NOT `remaining - dt <= 0` (which would double-count dt
    # and fire one tick early while the cooldown is still positive).
    cfg = make_config()

    class _W:
        weapon_cooldown_remaining = 0.0

    # Exactly elapsed -> ready to fire.
    assert should_fire(_W(), dt=0.05, cfg=cfg) is True

    class _Wmid:
        weapon_cooldown_remaining = 0.04  # still 0.04s left, less than one dt

    # NOT ready: the timer has not reached zero. The old double-count bug would
    # wrongly return True here because 0.04 - 0.05 <= 0.
    assert should_fire(_Wmid(), dt=0.05, cfg=cfg) is False

    class _W2:
        weapon_cooldown_remaining = 1.0

    # Plenty of cooldown left -> not ready.
    assert should_fire(_W2(), dt=0.05, cfg=cfg) is False


def test_spawn_projectile_intent_speed_and_direction():
    cfg = make_config(projectile_speed=10.0, weapon_damage=10.0, projectile_ttl=1.2)
    spec = spawn_projectile_intent(0.0, 0.0, 3.0, 4.0, cfg)
    assert isinstance(spec, ProjectileSpec)
    # Velocity magnitude equals projectile_speed (plain Euclidean aim).
    assert abs(hypot(spec.vx, spec.vy) - 10.0) < 1e-9
    # Aimed toward (3,4): direction matches the unit vector (0.6, 0.8).
    assert abs(spec.vx - 6.0) < 1e-9
    assert abs(spec.vy - 8.0) < 1e-9
    assert spec.damage == 10.0
    assert spec.ttl == 1.2


def test_spawn_projectile_intent_degenerate_target_on_player():
    cfg = make_config(projectile_speed=10.0)
    # Target coincides with player -> deterministic +X launch, no div-by-zero.
    spec = spawn_projectile_intent(5.0, 5.0, 5.0, 5.0, cfg)
    assert spec.vx == 10.0
    assert spec.vy == 0.0
