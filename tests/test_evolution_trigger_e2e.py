"""Headless deterministic evolution-trigger e2e (Phase 2 Day 7, AC8).

Drives the dagger + attack_speed path through the real ``roll_choices`` draft end
to end until the dagger_x evolution becomes eligible, then applies the evolution
card the draft offers. This is a genuine reach (the evolution card only enters the
pool once the build qualifies), not a hand-set build: the final build owns the
evolution result ``dagger_evolved`` and no longer owns the base ``dagger``.

Determinism: a fresh ``random.Random(seed)`` drives selection; the same seed
reaches the same eligible build and the same applied result.
"""

from __future__ import annotations

import random

from terminal_vs.rules.evolution import eligible_evolutions
from terminal_vs.rules.leveling import (
    KIND_EVOLUTION,
    KIND_PASSIVE,
    KIND_WEAPON_UPGRADE,
    BuildState,
    Choice,
    apply_choice,
    roll_choices,
)

from .conftest import make_defs

# Drive seed and a guard cap on draft iterations. The dagger path reaches
# eligibility well within this cap (empirically ~15 iterations for this seed);
# the cap only prevents an infinite loop if the rules ever regress.
_SEED = 2024
_MAX_DRAFTS = 60
# Large enough to draw the WHOLE draft pool (sampling is without replacement), so
# the offered evolution card is guaranteed present once eligible.
_FULL_POOL = 50


def _favor_dagger_then_attack_speed(choices: tuple[Choice, ...]) -> Choice:
    """Pick a dagger upgrade, else an attack_speed passive, else the first card.

    Drives toward the dagger_x precondition (dagger at max + attack_speed owned)
    without ever selecting an evolution card, so eligibility is reached with the
    base dagger still owned and the evolution is applied explicitly afterward.
    """
    for kind, target in ((KIND_WEAPON_UPGRADE, "dagger"), (KIND_PASSIVE, "attack_speed")):
        for choice in choices:
            if choice.kind == kind and choice.target == target:
                return choice
    for choice in choices:
        if choice.kind != KIND_EVOLUTION:
            return choice
    return choices[0]


def _drive_to_eligible(seed: int) -> BuildState:
    """Drive the dagger/attack_speed build until it can evolve (or hit the cap).

    Rolls the real N-pick draft each level and applies the dagger-favoring card.
    Returns the build at the first moment ``eligible_evolutions`` is non-empty,
    with the base dagger still owned (the evolution card itself is never picked
    here).
    """
    defs = make_defs()
    rng = random.Random(seed)
    build = BuildState()
    for _ in range(_MAX_DRAFTS):
        choices = roll_choices(build, defs, rng, defs.leveling.draft_choices)
        build = apply_choice(build, _favor_dagger_then_attack_speed(choices))
        if eligible_evolutions(build, defs):
            return build
    return build


def test_dagger_path_evolves():
    """The dagger+attack_speed path reaches evolution and ends owning dagger_evolved.

    End to end: drive to eligibility through the real draft, then roll the full
    pool, select the offered evolution card, and apply it. The final build owns
    the evolution result and has shed the base dagger.
    """
    defs = make_defs()
    build = _drive_to_eligible(_SEED)

    # The build genuinely reached the evolution precondition through the draft.
    eligible = eligible_evolutions(build, defs)
    assert "dagger_x" in {evo.name for evo in eligible}
    assert dict(build.weapon_levels)["dagger"] == defs.weapons["dagger"].max_level
    assert dict(build.passive_levels).get("attack_speed", 0) > 0

    # Roll the whole pool so the eligible evolution card is offered, then apply it
    # through the real apply_choice path (the same path the loop takes).
    rng = random.Random(_SEED)
    pool = roll_choices(build, defs, rng, _FULL_POOL)
    evolution_cards = [c for c in pool if c.kind == KIND_EVOLUTION]
    assert evolution_cards, "the eligible build's full draft pool must offer the evolution card"

    evolved = apply_choice(build, evolution_cards[0])

    owned = dict(evolved.weapon_levels)
    assert "dagger_evolved" in owned
    assert "dagger" not in owned


def test_evolution_reach_is_reproducible():
    """Same seed reaches the same eligible build and the same evolved result."""
    first = _drive_to_eligible(_SEED)
    second = _drive_to_eligible(_SEED)
    assert first == second

    defs = make_defs()
    evo = eligible_evolutions(first, defs)[0]
    assert apply_choice(first, _evolution_choice(evo)) == apply_choice(
        second, _evolution_choice(evo)
    )


def _evolution_choice(evo) -> Choice:
    """Build an evolution Choice for ``evo`` (mirrors the draft's evolution card)."""
    return Choice(
        kind=KIND_EVOLUTION,
        label=f"Evolve: {evo.result_weapon}",
        target=evo.base,
        evolution=evo,
    )
