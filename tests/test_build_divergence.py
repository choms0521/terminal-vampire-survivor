"""Headless deterministic build-divergence tests (Phase 2 Day 7, AC7).

These translate the subjective "builds diverge" thesis into an objective,
reproducible proxy (master plan section 7 / plan Day 7): two fixed-seed level-up
paths driven through the real ``roll_choices`` draft converge on DIFFERENT weapon
and passive sets, and only the dagger-focused path reaches evolution eligibility.

The driver is a deterministic preference-driven selector over the real draft:
at every level it rolls the N-pick draft (``roll_choices``) and applies the
offered card that best matches the path's preference. When the preferred card is
not in the offered set it falls back to the first card that is NOT in the path's
hard-skip set; if every offered card is hard-skipped it skips that level entirely
(no apply). Hard-skipping dagger upgrades and evolution cards on path B pins its
dagger at level 1 at any level count, so path B is STRUCTURALLY never eligible to
evolve -- the divergence is a property of the driver, not of a lucky seed/length.

Every run uses a fresh ``random.Random(seed)``; the same seed + same path is
exactly reproducible (asserted), and the pinned final builds are the values the
real rules actually produce for these seeds.
"""

from __future__ import annotations

import random

from terminal_vs.rules.evolution import eligible_evolutions
from terminal_vs.rules.leveling import (
    KIND_EVOLUTION,
    KIND_NEW_WEAPON,
    KIND_PASSIVE,
    KIND_WEAPON_UPGRADE,
    BuildState,
    Choice,
    apply_choice,
    roll_choices,
)

from .conftest import make_defs

# This AC7 test pins exact fixed-seed builds over the PHASE 2 weapon set. Later
# stages add weapons to the default pool (lance / nova / orbit, ...); without
# pinning the pool here, every new draftable weapon would perturb these seeds and
# break the pinned builds for reasons unrelated to the divergence thesis. So the
# driver uses make_defs restricted to the Phase 2 weapons -- the content this AC
# was written against (master plan section 7 Day 7).
_PHASE2_WEAPONS = ("dagger", "magic_bolt", "swing", "dagger_evolved")


def _phase2_defs():
    """make_defs with its weapon pool restricted to the Phase 2 set (see above)."""
    full = make_defs()
    weapons = {name: full.weapons[name] for name in _PHASE2_WEAPONS}
    return make_defs(weapons=weapons)


# A path preference / hard-skip is an ordered list of (kind, target) matchers.
# ``target=None`` matches any target of that kind.
_Matcher = tuple[str, str | None]

# Path A favors maxing the dagger and stacking attack_speed (the evolution pair),
# and hard-skips evolution cards (so the e2e applies the evolution explicitly, and
# eligibility can be asserted with the base dagger still owned), the rival weapon
# (magic_bolt) and the rival passive (magnet).
_PATH_A_PREFER: tuple[_Matcher, ...] = (
    (KIND_WEAPON_UPGRADE, "dagger"),
    (KIND_PASSIVE, "attack_speed"),
)
_PATH_A_SKIP: tuple[_Matcher, ...] = (
    (KIND_EVOLUTION, None),
    (KIND_NEW_WEAPON, "magic_bolt"),
    (KIND_PASSIVE, "magnet"),
)

# Path B favors acquiring + maxing magic_bolt and stacking magnet, and HARD-SKIPS
# dagger upgrades, attack_speed, and evolution cards. Skipping dagger upgrades
# pins the dagger at level 1 forever, so path B can never satisfy the dagger_x
# evolution's "dagger at max + attack_speed owned" precondition at any length.
_PATH_B_PREFER: tuple[_Matcher, ...] = (
    (KIND_NEW_WEAPON, "magic_bolt"),
    (KIND_WEAPON_UPGRADE, "magic_bolt"),
    (KIND_PASSIVE, "magnet"),
)
_PATH_B_SKIP: tuple[_Matcher, ...] = (
    (KIND_WEAPON_UPGRADE, "dagger"),
    (KIND_PASSIVE, "attack_speed"),
    (KIND_EVOLUTION, None),
)

# Fixed seed + level count for the divergence comparison. Chosen so both paths
# reach a stable, distinct composition; the asserted final builds below are the
# exact values the real rules produce for this seed/count.
_SEED = 2024
_LEVELS = 18


def _matches(choice: Choice, kind: str, target: str | None) -> bool:
    """True if ``choice`` is of ``kind`` and (when given) targets ``target``."""
    return choice.kind == kind and (target is None or choice.target == target)


def _select(
    choices: tuple[Choice, ...],
    prefer: tuple[_Matcher, ...],
    hard_skip: tuple[_Matcher, ...],
) -> Choice | None:
    """Pick the path's card from an offered draft, or None to skip this level.

    Priority: the first offered card matching the preference order; else the
    first offered card matching NONE of the hard-skip matchers; else None (every
    offered card is hard-skipped, so the level is intentionally skipped to keep
    the path's composition structurally pure).
    """
    for kind, target in prefer:
        for choice in choices:
            if _matches(choice, kind, target):
                return choice
    for choice in choices:
        if not any(_matches(choice, k, t) for k, t in hard_skip):
            return choice
    return None


def _drive_path(
    seed: int,
    prefer: tuple[_Matcher, ...],
    hard_skip: tuple[_Matcher, ...],
    levels: int,
    *,
    stop_on_eligible: bool = False,
) -> BuildState:
    """Drive a build deterministically through ``levels`` real drafts.

    Uses a fresh ``random.Random(seed)`` and the default Phase 2 ``make_defs``
    content, rolling ``draft_choices`` (3) cards per level and applying the
    path-selected card via the real ``apply_choice``. ``apply_choice`` does not
    advance level/xp (the loop owns that); this driver only grows the weapon /
    passive composition, which is what AC7 measures. When ``stop_on_eligible`` is
    set, the drive halts as soon as the build can evolve (used to assert
    eligibility with the base weapon still owned).
    """
    defs = _phase2_defs()
    rng = random.Random(seed)
    build = BuildState()
    for _ in range(levels):
        choices = roll_choices(build, defs, rng, defs.leveling.draft_choices)
        selected = _select(choices, prefer, hard_skip)
        if selected is not None:
            build = apply_choice(build, selected)
        if stop_on_eligible and eligible_evolutions(build, defs):
            break
    return build


def _weapon_set(build: BuildState) -> frozenset[str]:
    """The frozenset of weapon names owned by ``build``."""
    return frozenset(name for name, _ in build.weapon_levels)


def _passive_set(build: BuildState) -> frozenset[str]:
    """The frozenset of passive names owned by ``build``."""
    return frozenset(name for name, _ in build.passive_levels)


def test_two_paths_diverge():
    """Two fixed-seed paths converge on different weapon AND passive sets.

    Structural divergence (path A favors dagger/attack_speed and skips
    magic_bolt/magnet; path B is the mirror) plus the exact pinned final builds
    as the determinism lock.
    """
    build_a = _drive_path(_SEED, _PATH_A_PREFER, _PATH_A_SKIP, _LEVELS)
    build_b = _drive_path(_SEED, _PATH_B_PREFER, _PATH_B_SKIP, _LEVELS)

    # The thesis: the two paths diverge in both weapon and passive composition.
    assert _weapon_set(build_a) != _weapon_set(build_b)
    assert _passive_set(build_a) != _passive_set(build_b)

    # The distinguishing content each path is built around.
    assert "magic_bolt" not in _weapon_set(build_a)
    assert "magic_bolt" in _weapon_set(build_b)
    assert "attack_speed" in _passive_set(build_a)
    assert "magnet" in _passive_set(build_b)
    assert "attack_speed" not in _passive_set(build_b)

    # Determinism lock: the exact final builds these seeds produce. If the draft
    # or selection logic drifts, these pinned tuples catch it.
    assert build_a.weapon_levels == (("dagger", 8), ("swing", 4))
    assert build_a.passive_levels == (("attack_speed", 5), ("move_speed", 1))
    assert build_b.weapon_levels == (
        ("dagger", 1),
        ("magic_bolt", 8),
        ("swing", 4),
    )
    assert build_b.passive_levels == (("magnet", 5), ("move_speed", 1))


def test_only_path_a_reaches_evolution():
    """Only the dagger/attack_speed path reaches evolution eligibility.

    Path A maxes the dagger and owns attack_speed, so ``eligible_evolutions``
    returns the dagger_x evolution (with the base dagger still owned, since the
    path hard-skips applying the evolution card). Path B hard-skips dagger
    upgrades, pinning its dagger at level 1 forever, so it is never eligible --
    confirmed both at the divergence level count and far beyond it.
    """
    defs = _phase2_defs()
    build_a = _drive_path(_SEED, _PATH_A_PREFER, _PATH_A_SKIP, _LEVELS)
    build_b = _drive_path(_SEED, _PATH_B_PREFER, _PATH_B_SKIP, _LEVELS)

    eligible_a = eligible_evolutions(build_a, defs)
    assert eligible_a != ()
    assert "dagger_x" in {evo.name for evo in eligible_a}
    # Eligibility holds with the base dagger still owned (evolution not consumed).
    assert dict(build_a.weapon_levels)["dagger"] == 8

    assert eligible_evolutions(build_b, defs) == ()
    # Structural, not seed-luck: even driven far longer, path B's dagger stays at
    # level 1, so it can never satisfy the evolution precondition.
    build_b_long = _drive_path(_SEED, _PATH_B_PREFER, _PATH_B_SKIP, 200)
    assert dict(build_b_long.weapon_levels).get("dagger") == 1
    assert eligible_evolutions(build_b_long, defs) == ()


def test_same_seed_same_path_reproducible():
    """Same seed + same path run twice yields the identical final BuildState."""
    first = _drive_path(_SEED, _PATH_A_PREFER, _PATH_A_SKIP, _LEVELS)
    second = _drive_path(_SEED, _PATH_A_PREFER, _PATH_A_SKIP, _LEVELS)
    assert first == second

    first_b = _drive_path(_SEED, _PATH_B_PREFER, _PATH_B_SKIP, _LEVELS)
    second_b = _drive_path(_SEED, _PATH_B_PREFER, _PATH_B_SKIP, _LEVELS)
    assert first_b == second_b
