"""Post-run meta accrual: the pure function that turns a finished run into the
next :class:`MetaState`.

This runs AFTER the sim is done (game over), never inside a tick. ``RunResult``
is the small immutable summary the sim hands off; ``accrue_meta`` folds it into a
NEW ``MetaState`` (ADR-001: the old state is never mutated). v1 only accrues gold
and the run count -- unlock gating is deferred, so ``unlocked`` carries over
unchanged, and permanent upgrades change through a separate spend path, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .schema import MetaState

if TYPE_CHECKING:
    # Type-only import: spend_gold reads upgrade defs at runtime via duck typing,
    # so this stays behind TYPE_CHECKING -- meta never imports rules at runtime.
    from ..rules.defs import BalanceDefs, MetaUpgradeDef


@dataclass(frozen=True)
class RunResult:
    """Immutable summary of one finished run, consumed once by ``accrue_meta``.

    ``gold_earned`` is the gold the run accumulated (the in-run mutable counter,
    read off at game over). Negative gold is corruption, not a valid run, so the
    constructor rejects it.
    """

    gold_earned: int = 0

    def __post_init__(self) -> None:
        if self.gold_earned < 0:
            raise ValueError(f"gold_earned must be >= 0: {self.gold_earned}")


def accrue_meta(old_meta: MetaState, result: RunResult) -> MetaState:
    """Return a NEW ``MetaState`` after one run: gold accrues, run count +1.

    Pure: ``old_meta`` is frozen and never mutated. ``upgrades`` and ``unlocked``
    carry over unchanged (v1 does not gate unlocks here, and upgrade purchases are
    a separate, explicit spend).
    """
    return replace(
        old_meta,
        gold=old_meta.gold + result.gold_earned,
        total_runs=old_meta.total_runs + 1,
    )


def upgrade_cost(udef: MetaUpgradeDef, current_level: int) -> int:
    """Gold price of the NEXT level above ``current_level`` (geometric curve).

    ``cost_base * cost_growth ** current_level`` -- so level 0->1 costs
    ``cost_base``, 1->2 costs ``cost_base * cost_growth``, and so on. Truncated to
    an int (gold is whole).
    """
    return int(udef.cost_base * udef.cost_growth**current_level)


def spend_gold(meta: MetaState, upgrade_id: str, defs: BalanceDefs) -> MetaState:
    """Buy one level of ``upgrade_id`` if affordable and not maxed.

    Pure: returns a NEW ``MetaState`` on a successful purchase, or ``meta``
    unchanged when the upgrade is already at max level or the player cannot afford
    the next level (a no-op the caller can detect by an unchanged gold total).
    Raises ``KeyError`` if ``upgrade_id`` names no upgrade def (a programming
    error, not a runtime affordability case).
    """
    udef = defs.upgrades[upgrade_id]  # KeyError on unknown id -> programming error
    current = meta.upgrades.get(upgrade_id, 0)
    if current >= udef.max_level:
        return meta  # already maxed
    cost = upgrade_cost(udef, current)
    if meta.gold < cost:
        return meta  # cannot afford the next level
    new_upgrades = dict(meta.upgrades)
    new_upgrades[upgrade_id] = current + 1
    return replace(meta, gold=meta.gold - cost, upgrades=new_upgrades)
