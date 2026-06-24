"""terminal_vs.rules.leveling - xp accrual and level-up draft (Day 4).

Pure functions over the frozen :class:`terminal_vs.sim.state.LevelState`. No
side effects, no blessed, no global state. Every function returns a NEW value;
none mutates its input (the frozen dataclass makes this structural).

State-machine contract (consumed by Chunk C's loop):

  * ``accrue_xp`` ONLY accumulates xp into the current level. It never bumps the
    level or resets xp.
  * ``level_up_pending`` is True while accumulated xp meets/exceeds the current
    level's threshold (``base * growth ** (level - 1)``). It stays True until the
    level-up is consumed. A single large xp grant can bank several levels at
    once: each ``apply_choice`` consumes exactly ONE level, so the loop must
    re-check ``level_up_pending`` after applying a choice and surface another
    overlay while it remains True.
  * ``apply_choice`` is what consumes a level-up: it increments the level and
    carries the xp overflow into the next level. The sim's step sets the
    ``SimState.level_up_pending`` flag; the LOOP clears it by applying a choice.
    step never clears the flag.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from ..config import Config
from .defs import xp_curve

# Local import only for typing/return construction. Imported lazily inside
# functions would avoid a cycle, but sim.state imports config/world (not rules),
# so importing LevelState here is safe and keeps signatures concrete.
from ..sim.state import LevelState


@dataclass(frozen=True)
class Choice:
    """Frozen level-up choice (the pure result of a draft).

    Phase 1 offers a single generic choice. ``kind`` identifies the upgrade
    family and ``label`` is a human-readable name for the overlay; richer payload
    (weapon id, stat delta) is deferred to Phase 2's multi-choice draft. This
    value crosses the rules/sim boundary read-only.
    """

    kind: str
    label: str


def xp_to_clear(level: int, cfg: Config) -> float:
    """Xp required to clear ``level`` (1-based): ``base * growth ** (level-1)``."""
    curve = xp_curve(cfg)
    return curve.base * (curve.growth ** (level - 1))


def accrue_xp(level_state: LevelState, gained: float) -> LevelState:
    """Return a NEW LevelState with ``gained`` xp added to the current level.

    Pure: the input ``level_state`` is never mutated (it is frozen). Only the xp
    accumulator changes; level and threshold logic are handled by
    ``level_up_pending`` / ``apply_choice``.
    """
    return replace(level_state, xp=level_state.xp + gained)


def level_up_pending(level_state: LevelState, cfg: Config) -> bool:
    """True if accumulated xp meets/exceeds the current level's threshold."""
    return level_state.xp >= xp_to_clear(level_state.level, cfg)


def roll_choices(
    level_state: LevelState,
    cfg: Config,
    rng: random.Random,
    n: int = 1,
) -> tuple[Choice, ...]:
    """Return ``n`` level-up choices. Phase 1 always returns exactly one.

    The ``rng`` and ``n`` parameters are kept for the Phase 2 N-choice draft (an
    rng-shuffled subset of an upgrade pool). In Phase 1 the single returned
    choice is fixed, so the result is effectively deterministic; ``rng`` is
    accepted but not consumed yet.
    """
    # Phase 1: a single generic upgrade. The multi-choice pool is Phase 2, so n
    # is ignored here and exactly one choice is returned.
    choice = Choice(kind="level_up", label=f"Level {level_state.level + 1}")
    return (choice,)


def apply_choice(level_state: LevelState, choice: Choice, cfg: Config) -> LevelState:
    """Consume a level-up: return a NEW LevelState one level higher.

    The current level's xp threshold is subtracted (overflow carries into the
    next level), and the level is incremented. Pure: the input is not mutated.
    ``choice`` has no stat payload in Phase 1, so it does not alter the math yet;
    it is threaded through for the Phase 2 upgrade effects.
    """
    threshold = xp_to_clear(level_state.level, cfg)
    carried = level_state.xp - threshold
    if carried < 0.0:
        carried = 0.0
    return LevelState(level=level_state.level + 1, xp=carried)
