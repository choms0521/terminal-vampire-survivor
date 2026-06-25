"""terminal_vs.rules.evolution - weapon evolution eligibility and application.

Pure functions implementing the master plan section 8 evolution rule: a weapon
evolves when its base weapon is at the required max level AND the paired passive
is owned. Eligibility is checked by iterating the data-driven evolution table
(``defs.evolutions``), so adding evolutions is a balance.toml change with no code
edits. No side effects, no blessed, no global state, no Chinese characters.

Import boundary (avoids the leveling<->evolution cycle): this module imports only
:class:`~terminal_vs.rules.defs.EvolutionDef` at runtime. It constructs the new
build with ``dataclasses.replace`` (no runtime ``BuildState`` import); the
``BuildState`` reference is a ``TYPE_CHECKING``-only hint. rules.leveling imports
this module, never the reverse at runtime.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .defs import BalanceDefs, EvolutionDef

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import (no cycle)
    from .leveling import BuildState


def eligible_evolutions(
    build: "BuildState", defs: BalanceDefs
) -> tuple[EvolutionDef, ...]:
    """Return every evolution ``build`` currently qualifies for (pure).

    For each evolution in ``defs.evolutions``, the build qualifies when its base
    weapon is owned at >= ``base_max_level`` AND its ``requires_passive`` passive
    is owned (level > 0). The result preserves ``defs.evolutions`` order for
    determinism. Pure: ``build`` and ``defs`` are read-only.
    """
    weapon_lv = dict(build.weapon_levels)
    passive_lv = dict(build.passive_levels)
    out: list[EvolutionDef] = []
    for evo in defs.evolutions:
        base_lv = weapon_lv.get(evo.base, 0)
        has_passive = passive_lv.get(evo.requires_passive, 0) > 0
        if base_lv >= evo.base_max_level and has_passive:
            out.append(evo)
    return tuple(out)


def apply_evolution(build: "BuildState", evo: EvolutionDef) -> "BuildState":
    """Return a NEW build with ``evo.base`` replaced by ``evo.result_weapon``.

    The base weapon is removed and the result weapon is added at level 1; all
    other weapons and every passive carry over unchanged, as do ``level`` and
    ``xp``. Pure: the input ``build`` is never mutated. If the base weapon is not
    owned the build is returned with only the result weapon appended (a defensive
    no-op on removal), but callers should only apply evolutions returned by
    :func:`eligible_evolutions`, where the base is always owned.
    """
    new_weapons = tuple(
        (name, level)
        for name, level in build.weapon_levels
        if name != evo.base
    )
    new_weapons = new_weapons + ((evo.result_weapon, 1),)
    return replace(build, weapon_levels=new_weapons)
