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

from .schema import MetaState


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
