"""Immutable meta-progression state and its error type.

``MetaState`` is the frozen value that persists across runs: accumulated gold,
the owned permanent-upgrade levels, the set of unlocked ids, and a run counter.
It crosses into the rules layer read-only (injected at run start), so it is a
frozen dataclass with value equality -- the round-trip tests rely on ``==``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class MetaState:
    """Frozen cross-run progression.

    ``gold`` is spendable currency; ``upgrades`` maps an upgrade id to its owned
    level (0 = not owned); ``unlocked`` is the set of unlocked weapon/character
    ids; ``total_runs`` counts completed runs. Defaults describe a first launch
    with no save file. Equality is structural (dataclass ``__eq__``), which the
    save/load round-trip asserts against.
    """

    gold: int = 0
    upgrades: Mapping[str, int] = field(default_factory=dict)
    unlocked: frozenset[str] = field(default_factory=frozenset)
    total_runs: int = 0


class MetaSaveError(ValueError):
    """A save file is missing required keys, has a wrong type, or is out of range.

    Subclasses ``ValueError`` so callers that already guard config loads with a
    broad ``except ValueError`` keep working; the distinct type lets meta-aware
    callers tell a corrupt save apart from other value errors.
    """
