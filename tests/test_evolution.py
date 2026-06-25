"""Tests for terminal_vs.rules.evolution: eligibility + apply (pure)."""

from __future__ import annotations

import copy

from terminal_vs.rules.evolution import apply_evolution, eligible_evolutions
from terminal_vs.rules.leveling import BuildState

from .conftest import make_defs


def test_eligible_when_max_and_passive():
    """Dagger at max + attack_speed passive owned -> dagger_x is eligible."""
    defs = make_defs()  # dagger_x: base=dagger, base_max_level=8, req attack_speed
    build = BuildState(
        weapon_levels=(("dagger", 8),),
        passive_levels=(("attack_speed", 1),),
    )
    evos = eligible_evolutions(build, defs)
    assert len(evos) == 1
    assert evos[0].name == "dagger_x"
    assert evos[0].result_weapon == "dagger_evolved"


def test_not_eligible_without_passive():
    """Dagger at max but no attack_speed passive -> not eligible (empty tuple)."""
    defs = make_defs()
    build = BuildState(weapon_levels=(("dagger", 8),), passive_levels=())
    assert eligible_evolutions(build, defs) == ()


def test_not_eligible_when_not_maxed():
    """attack_speed owned but dagger below max -> not eligible (empty tuple)."""
    defs = make_defs()
    build = BuildState(
        weapon_levels=(("dagger", 7),),
        passive_levels=(("attack_speed", 1),),
    )
    assert eligible_evolutions(build, defs) == ()


def test_apply_evolution_replaces_base():
    """apply_evolution removes the base weapon, adds the result, input immutable."""
    defs = make_defs()
    build = BuildState(
        weapon_levels=(("dagger", 8),),
        passive_levels=(("attack_speed", 1),),
        level=9,
        xp=3.0,
    )
    build_before = copy.deepcopy(build)
    (evo,) = eligible_evolutions(build, defs)
    out = apply_evolution(build, evo)

    weapons = dict(out.weapon_levels)
    assert "dagger" not in weapons
    assert weapons["dagger_evolved"] == 1
    # Passives and level/xp carry over unchanged.
    assert dict(out.passive_levels)["attack_speed"] == 1
    assert out.level == 9
    assert out.xp == 3.0
    # Input build is not mutated (deepcopy compare).
    assert out is not build
    assert build == build_before


def test_apply_evolution_keeps_other_weapons():
    """Non-base weapons survive the evolution unchanged."""
    defs = make_defs()
    build = BuildState(
        weapon_levels=(("dagger", 8), ("magic_bolt", 3)),
        passive_levels=(("attack_speed", 2),),
    )
    (evo,) = eligible_evolutions(build, defs)
    out = apply_evolution(build, evo)
    weapons = dict(out.weapon_levels)
    assert "dagger" not in weapons
    assert weapons["magic_bolt"] == 3
    assert weapons["dagger_evolved"] == 1
