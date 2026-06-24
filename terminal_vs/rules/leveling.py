"""terminal_vs.rules.leveling - build state, xp curve, N-pick draft, passive stats.

Pure functions over the frozen :class:`BuildState` (the single source of truth
for a run's weapons, passives, level, and xp). Every function returns a NEW value
and never mutates its input; the frozen dataclasses make this structural. No
side effects, no blessed, no global state, no Chinese characters.

This module OWNS :class:`BuildState`, :class:`Stats`, and :class:`Choice` (the
rules-side build types). It does NOT import :mod:`terminal_vs.sim.state` -- the
rules layer must not depend on the sim layer. It imports
:mod:`terminal_vs.rules.evolution` to apply evolution choices; evolution avoids
the reverse import by constructing new states with ``dataclasses.replace``.

State-machine contract (consumed by Chunk 2's loop):

  * ``accrue_xp`` ONLY accumulates xp; it never bumps the level.
  * ``level_up_pending`` is True while accumulated xp meets/exceeds the current
    level's threshold. One ``apply_choice`` consumes exactly one pending level
    (it bumps level and carries the xp overflow), so the loop re-checks
    ``level_up_pending`` after each choice to drain banked levels.
  * ``roll_choices`` produces the N-pick draft deterministically from the build +
    injected rng; ``apply_choice`` applies the selected card to a new BuildState.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from .defs import BalanceDefs, EvolutionDef
from .evolution import apply_evolution, eligible_evolutions

# Choice kinds (the upgrade families a draft card can represent).
KIND_WEAPON_UPGRADE = "weapon_upgrade"
KIND_NEW_WEAPON = "new_weapon"
KIND_PASSIVE = "passive"
KIND_EVOLUTION = "evolution"
KIND_FALLBACK = "fallback"

# Passive id -> which Stats field it multiplies. Single mapping so effective_stats
# and any future stat readers agree.
_ATTACK_SPEED = "attack_speed"
_MOVE_SPEED = "move_speed"
_MAGNET = "magnet"

# Deterministic fallback weight so an empty draft pool still yields a card.
_FALLBACK_WEIGHT = 1


@dataclass(frozen=True)
class BuildState:
    """Frozen run build: weapons, passives, level, and accumulated xp.

    ``weapon_levels`` / ``passive_levels`` are ordered tuples of ``(name, level)``
    pairs (1-based levels); insertion order is preserved for determinism.
    ``level`` is the 1-based player level and ``xp`` is the xp accumulated toward
    clearing the current level. This subsumes the Phase 1 LevelState. The
    starting build is ``BuildState(weapon_levels=(("dagger", 1),))``.
    """

    weapon_levels: tuple[tuple[str, int], ...] = (("dagger", 1),)
    passive_levels: tuple[tuple[str, int], ...] = ()
    level: int = 1
    xp: float = 0.0


@dataclass(frozen=True)
class Stats:
    """Frozen multiplicative stat bundle derived from owned passives.

    Each field is the product of the relevant passive's per-level multiplier over
    its owned levels: ``attack_speed_mult`` scales weapon cooldown (smaller =
    faster), ``move_speed_mult`` scales movement, ``magnet_mult`` scales the
    pickup radius. With no passives owned every field is 1.0 (identity).
    """

    attack_speed_mult: float = 1.0
    move_speed_mult: float = 1.0
    magnet_mult: float = 1.0


@dataclass(frozen=True)
class Choice:
    """Frozen level-up draft card with enough payload to apply without re-rolling.

    ``kind`` is one of the ``KIND_*`` families; ``label`` is the overlay text;
    ``target`` is the weapon/passive id the card upgrades or grants (empty for an
    evolution/fallback that carries its own ref); ``evolution`` is the
    :class:`EvolutionDef` for an evolution card (None otherwise). This value
    crosses the rules/sim boundary read-only.
    """

    kind: str
    label: str
    target: str = ""
    evolution: EvolutionDef | None = None


def xp_for_level(level: int, defs: BalanceDefs) -> float:
    """Xp required to clear ``level`` (1-based): ``base * growth ** (level-1)``.

    Monotonically increasing in ``level`` because ``growth > 1`` (validated on
    config load). Returns a float -- the geometric curve is fractional.
    """
    curve = defs.leveling
    return curve.xp_curve_base * (curve.xp_curve_growth ** (level - 1))


def accrue_xp(build: BuildState, gained: float) -> BuildState:
    """Return a NEW BuildState with ``gained`` xp added to the current level.

    Pure: ``build`` is never mutated (it is frozen). Only the xp accumulator
    changes; level and threshold logic are handled by ``level_up_pending`` /
    ``apply_choice``.
    """
    return replace(build, xp=build.xp + gained)


def level_up_pending(build: BuildState, defs: BalanceDefs) -> bool:
    """True if accumulated xp meets/exceeds the current level's threshold."""
    return build.xp >= xp_for_level(build.level, defs)


def effective_stats(build: BuildState, defs: BalanceDefs) -> Stats:
    """Compute the multiplicative passive stats for ``build`` (single source).

    Each owned passive multiplies its mapped stat once per level (product over
    levels). Unknown passive ids (not in ``defs.passives``) are skipped. Pure.
    """
    attack_speed_mult = 1.0
    move_speed_mult = 1.0
    magnet_mult = 1.0
    for name, level in build.passive_levels:
        pdef = defs.passives.get(name)
        if pdef is None or level <= 0:
            continue
        factor = pdef.multiplier_per_level ** level
        if name == _ATTACK_SPEED:
            attack_speed_mult *= factor
        elif name == _MOVE_SPEED:
            move_speed_mult *= factor
        elif name == _MAGNET:
            magnet_mult *= factor
    return Stats(
        attack_speed_mult=attack_speed_mult,
        move_speed_mult=move_speed_mult,
        magnet_mult=magnet_mult,
    )


def _weapon_upgrade_candidates(
    build: BuildState, defs: BalanceDefs
) -> list[tuple[Choice, int]]:
    """Owned, non-maxed weapons as "+1 level" cards (with spawn weights)."""
    out: list[tuple[Choice, int]] = []
    for name, level in build.weapon_levels:
        wdef = defs.weapons.get(name)
        if wdef is None or level >= wdef.max_level:
            continue
        choice = Choice(
            kind=KIND_WEAPON_UPGRADE,
            label=f"{name} Lv{level + 1}",
            target=name,
        )
        out.append((choice, 1))
    return out


def _new_weapon_candidates(
    build: BuildState, defs: BalanceDefs
) -> list[tuple[Choice, int]]:
    """Unowned weapons as "acquire at Lv1" cards.

    Evolution result weapons are excluded from the new-weapon pool: they are only
    obtained by applying the evolution, never drafted directly.
    """
    owned = {name for name, _ in build.weapon_levels}
    evolved_results = {evo.result_weapon for evo in defs.evolutions}
    out: list[tuple[Choice, int]] = []
    for name in defs.weapons:
        if name in owned or name in evolved_results:
            continue
        choice = Choice(
            kind=KIND_NEW_WEAPON,
            label=f"New: {name}",
            target=name,
        )
        out.append((choice, 1))
    return out


def _passive_candidates(
    build: BuildState, defs: BalanceDefs
) -> list[tuple[Choice, int]]:
    """Passives not yet at max (owned-and-upgradable or unowned) as cards."""
    owned = dict(build.passive_levels)
    out: list[tuple[Choice, int]] = []
    for name, pdef in defs.passives.items():
        level = owned.get(name, 0)
        if level >= pdef.max_level:
            continue
        choice = Choice(
            kind=KIND_PASSIVE,
            label=f"{name} Lv{level + 1}",
            target=name,
        )
        out.append((choice, 1))
    return out


def _eligible_evolution_choices(
    build: BuildState, defs: BalanceDefs
) -> list[tuple[Choice, int]]:
    """Evolution cards for every currently-eligible evolution (Day 4 policy).

    Per the contract, eligible evolutions are injected into the draft pool rather
    than shown as a separate UI, so the same overlay presents them.
    """
    out: list[tuple[Choice, int]] = []
    for evo in eligible_evolutions(build, defs):
        choice = Choice(
            kind=KIND_EVOLUTION,
            label=f"Evolve: {evo.result_weapon}",
            target=evo.base,
            evolution=evo,
        )
        out.append((choice, 1))
    return out


def _fallback_candidates(defs: BalanceDefs) -> list[tuple[Choice, int]]:
    """Deterministic fallback when the draft pool is otherwise empty.

    Everything maxed should never starve the draft, so a single neutral "bonus"
    card is offered. It carries no upgrade payload; ``apply_choice`` treats it as
    a no-op on weapons/passives (the level-up itself is still consumed by the
    loop). ``defs`` is accepted for signature symmetry / future tuning.
    """
    return [(Choice(kind=KIND_FALLBACK, label="Bonus"), _FALLBACK_WEIGHT)]


def _weighted_sample(
    pool: list[tuple[Choice, int]], rng: Random, n: int
) -> tuple[Choice, ...]:
    """Deterministically pick up to ``n`` distinct cards from a weighted pool.

    Selection without replacement: at each step a card is drawn proportional to
    its weight (injected rng), then removed so it cannot repeat. With a fixed seed
    and identical pool the result is identical, including order. If the pool has
    fewer than ``n`` cards, all of them are returned.
    """
    remaining = list(pool)
    picked: list[Choice] = []
    count = min(n, len(remaining))
    for _ in range(count):
        total = sum(weight for _, weight in remaining)
        roll = rng.uniform(0.0, total)
        cumulative = 0.0
        index = len(remaining) - 1
        for i, (_, weight) in enumerate(remaining):
            cumulative += weight
            if roll <= cumulative:
                index = i
                break
        picked.append(remaining.pop(index)[0])
    return tuple(picked)


def roll_choices(
    build: BuildState, defs: BalanceDefs, rng: Random, n: int
) -> tuple[Choice, ...]:
    """Return up to ``n`` level-up draft cards for ``build`` (pure, deterministic).

    The pool is weapon upgrades (excluding maxed weapons) + new weapons
    (excluding owned and evolution results) + passives (excluding maxed) +
    eligible evolution cards. An empty pool falls back to a deterministic bonus
    card so the draft is never empty. Sampling uses the injected ``rng`` so the
    same seed + build yields the same tuple.
    """
    pool: list[tuple[Choice, int]] = []
    pool += _weapon_upgrade_candidates(build, defs)
    pool += _new_weapon_candidates(build, defs)
    pool += _passive_candidates(build, defs)
    pool += _eligible_evolution_choices(build, defs)
    if not pool:
        pool = _fallback_candidates(defs)
    return _weighted_sample(pool, rng, n)


def _bump(levels: tuple[tuple[str, int], ...], name: str) -> tuple[tuple[str, int], ...]:
    """Return a new (name, level) tuple with ``name`` added or its level +1'd."""
    found = False
    out: list[tuple[str, int]] = []
    for entry_name, level in levels:
        if entry_name == name:
            out.append((entry_name, level + 1))
            found = True
        else:
            out.append((entry_name, level))
    if not found:
        out.append((name, 1))
    return tuple(out)


def apply_choice(build: BuildState, choice: Choice) -> BuildState:
    """Apply ``choice`` to ``build``, returning a NEW BuildState (pure).

    The selected card bumps the targeted weapon/passive level (adding it at level
    1 if unowned), applies an evolution (delegating to rules.evolution), or is a
    no-op for the fallback bonus. This function does NOT advance ``level``/``xp``:
    its signature has no ``defs`` and therefore cannot compute a level threshold,
    so consuming a pending level (and carrying the xp overflow) is the caller's
    job (Chunk 2's loop). The input ``build`` is never mutated.
    """
    if choice.kind == KIND_WEAPON_UPGRADE or choice.kind == KIND_NEW_WEAPON:
        new_weapons = _bump(build.weapon_levels, choice.target)
        upgraded = replace(build, weapon_levels=new_weapons)
    elif choice.kind == KIND_PASSIVE:
        new_passives = _bump(build.passive_levels, choice.target)
        upgraded = replace(build, passive_levels=new_passives)
    elif choice.kind == KIND_EVOLUTION and choice.evolution is not None:
        upgraded = apply_evolution(build, choice.evolution)
    else:
        # Fallback / unknown: no weapon/passive change, level-up still consumed.
        upgraded = build
    return upgraded
