"""Tests for terminal_vs.rules.leveling: xp curve, draft, apply, passive stats."""

from __future__ import annotations

import copy
import random

from terminal_vs.rules.leveling import (
    BuildState,
    Choice,
    accrue_xp,
    apply_choice,
    effective_stats,
    level_up_pending,
    roll_choices,
    xp_for_level,
)

from .conftest import make_defs


def test_xp_curve_monotonic():
    """xp_for_level is strictly increasing in level (growth > 1)."""
    defs = make_defs()
    for n in range(1, 20):
        assert xp_for_level(n + 1, defs) > xp_for_level(n, defs)
    # Anchored values: base * growth ** (L - 1).
    assert xp_for_level(1, defs) == 5.0
    assert abs(xp_for_level(2, defs) - 5.0 * 1.5) < 1e-9


def test_level_up_pending_threshold():
    """level_up_pending is True at/above the current level threshold."""
    defs = make_defs()
    assert level_up_pending(BuildState(xp=4.0), defs) is False
    assert level_up_pending(BuildState(xp=5.0), defs) is True
    assert level_up_pending(BuildState(xp=12.0), defs) is True


def test_accrue_xp_returns_new_state_immutably():
    """accrue_xp returns a new state and never mutates its input."""
    build = BuildState(xp=2.0)
    out = accrue_xp(build, 3.0)
    assert out is not build
    assert out.xp == 5.0
    assert build.xp == 2.0  # input unchanged


def test_roll_choices_deterministic():
    """Same seed + same build yields the same draft tuple (kind, target, label)."""
    defs = make_defs()
    build = BuildState(weapon_levels=(("dagger", 1),), passive_levels=(), level=1)

    def run() -> tuple[tuple[str, str, str], ...]:
        choices = roll_choices(build, defs, random.Random(777), n=3)
        return tuple((c.kind, c.target, c.label) for c in choices)

    assert run() == run()
    # The draft honors n.
    assert len(roll_choices(build, defs, random.Random(1), n=3)) == 3


def test_maxed_weapon_excluded():
    """A maxed weapon never appears as a weapon-upgrade card in the draft."""
    defs = make_defs()
    # dagger at its max level (8); no other weapons owned, no passives.
    build = BuildState(weapon_levels=(("dagger", 8),), passive_levels=())
    # Roll the entire pool (large n) and confirm no dagger upgrade card.
    choices = roll_choices(build, defs, random.Random(5), n=50)
    dagger_upgrades = [
        c for c in choices if c.kind == "weapon_upgrade" and c.target == "dagger"
    ]
    assert dagger_upgrades == []


def test_apply_choice_weapon_upgrade_returns_new_state():
    """apply_choice returns a NEW build with the weapon bumped; input immutable."""
    build = BuildState(weapon_levels=(("dagger", 1),), passive_levels=())
    build_before = copy.deepcopy(build)
    choice = Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger")
    out = apply_choice(build, choice)
    assert out is not build
    assert dict(out.weapon_levels)["dagger"] == 2
    # Input unchanged (deepcopy compare).
    assert build == build_before


def test_apply_choice_new_weapon_adds_it():
    """A new-weapon card adds the weapon at level 1 without touching others."""
    build = BuildState(weapon_levels=(("dagger", 3),), passive_levels=())
    choice = Choice(kind="new_weapon", label="New: magic_bolt", target="magic_bolt")
    out = apply_choice(build, choice)
    weapons = dict(out.weapon_levels)
    assert weapons["dagger"] == 3
    assert weapons["magic_bolt"] == 1


def test_apply_choice_passive_adds_level():
    """A passive card adds/bumps the passive level."""
    build = BuildState(weapon_levels=(("dagger", 1),), passive_levels=())
    choice = Choice(kind="passive", label="attack_speed Lv1", target="attack_speed")
    out = apply_choice(build, choice)
    assert dict(out.passive_levels)["attack_speed"] == 1


def test_passive_multiplies_stats():
    """effective_stats multiplies the mapped stat by the passive's per-level factor."""
    defs = make_defs()
    # No passives -> identity stats.
    base = effective_stats(BuildState(), defs)
    assert base.attack_speed_mult == 1.0
    assert base.move_speed_mult == 1.0
    assert base.magnet_mult == 1.0

    # One level of attack_speed (multiplier_per_level=0.92) scales attack speed.
    one = effective_stats(
        BuildState(passive_levels=(("attack_speed", 1),)), defs
    )
    assert abs(one.attack_speed_mult - 0.92) < 1e-9
    assert one.move_speed_mult == 1.0

    # Two levels compound multiplicatively (0.92 ** 2).
    two = effective_stats(
        BuildState(passive_levels=(("attack_speed", 2),)), defs
    )
    assert abs(two.attack_speed_mult - 0.92 ** 2) < 1e-9

    # move_speed (1.08) and magnet (1.25) map to their own fields.
    mv = effective_stats(BuildState(passive_levels=(("move_speed", 1),)), defs)
    assert abs(mv.move_speed_mult - 1.08) < 1e-9
    mg = effective_stats(BuildState(passive_levels=(("magnet", 1),)), defs)
    assert abs(mg.magnet_mult - 1.25) < 1e-9
