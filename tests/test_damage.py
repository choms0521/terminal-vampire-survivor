"""Tests for terminal_vs.rules.damage: apply_hit, is_dead, knockback."""

from __future__ import annotations

from math import hypot

from terminal_vs.rules.damage import apply_hit, is_dead, knockback


def test_apply_hit_subtracts_damage():
    assert apply_hit(20.0, 5.0) == 15.0
    assert apply_hit(10.0, 10.0) == 0.0


def test_apply_hit_clamps_at_zero():
    # Overkill never produces negative hp.
    assert apply_hit(3.0, 10.0) == 0.0


def test_is_dead_at_or_below_zero():
    assert is_dead(0.0) is True
    assert is_dead(-1.0) is True
    assert is_dead(0.5) is False


def test_knockback_direction_away_from_source():
    # Source at origin, target to the +X side -> pushed further along +X.
    new_pos = knockback((3.0, 0.0), (0.0, 0.0), 2.0)
    assert new_pos[0] > 3.0      # moved further from source on X
    assert new_pos[1] == 0.0     # no Y component for a pure-X separation
    # Direction is exactly +X.
    assert new_pos == (5.0, 0.0)


def test_knockback_magnitude_equals_force():
    pos = (2.0, 1.0)
    source = (0.0, 0.0)
    force = 3.0
    new_pos = knockback(pos, source, force)
    # The displacement vector length equals force exactly.
    disp = hypot(new_pos[0] - pos[0], new_pos[1] - pos[1])
    assert abs(disp - force) < 1e-9
    # And it points away from the source (same direction as pos - source).
    # Dot product of displacement and (pos - source) is positive.
    dx, dy = pos[0] - source[0], pos[1] - source[1]
    ddx, ddy = new_pos[0] - pos[0], new_pos[1] - pos[1]
    assert dx * ddx + dy * ddy > 0.0


def test_knockback_degenerate_same_position_no_displacement():
    # Undefined direction -> deterministic zero displacement, no div-by-zero.
    assert knockback((1.0, 1.0), (1.0, 1.0), 5.0) == (1.0, 1.0)


def test_knockback_does_not_mutate_inputs():
    pos = (2.0, 3.0)
    source = (0.0, 0.0)
    knockback(pos, source, 1.0)
    assert pos == (2.0, 3.0)
    assert source == (0.0, 0.0)
