"""Tests for terminal_vs.rules.leveling: xp accrual, threshold, draft, immutability."""

from __future__ import annotations

import random

from terminal_vs.rules.leveling import (
    Choice,
    accrue_xp,
    apply_choice,
    level_up_pending,
    roll_choices,
    xp_to_clear,
)
from terminal_vs.sim.state import LevelState

from .conftest import make_config


def test_level_up_pending_below_threshold_false():
    cfg = make_config(xp_base=5.0, xp_growth=1.5)
    # Level 1 threshold = 5.0; xp 4.0 is below it.
    ls = LevelState(level=1, xp=4.0)
    assert level_up_pending(ls, cfg) is False


def test_level_up_pending_at_threshold_true():
    cfg = make_config(xp_base=5.0, xp_growth=1.5)
    # Exactly at the threshold counts as pending.
    ls = LevelState(level=1, xp=5.0)
    assert level_up_pending(ls, cfg) is True


def test_level_up_pending_over_threshold_true():
    cfg = make_config(xp_base=5.0, xp_growth=1.5)
    ls = LevelState(level=1, xp=12.0)
    assert level_up_pending(ls, cfg) is True


def test_xp_to_clear_curve():
    cfg = make_config(xp_base=5.0, xp_growth=1.5)
    assert xp_to_clear(1, cfg) == 5.0
    assert xp_to_clear(2, cfg) == 5.0 * 1.5
    assert xp_to_clear(3, cfg) == 5.0 * 1.5 * 1.5


def test_accrue_xp_returns_new_state_and_does_not_mutate_input():
    ls = LevelState(level=1, xp=2.0)
    out = accrue_xp(ls, 3.0)
    # Input object is unchanged (immutability assertion).
    assert ls.level == 1
    assert ls.xp == 2.0
    # A new state is returned with the accumulated xp.
    assert out is not ls
    assert out.xp == 5.0
    assert out.level == 1


def test_roll_choices_returns_exactly_one():
    cfg = make_config()
    rng = random.Random(123)
    ls = LevelState(level=1, xp=10.0)
    choices = roll_choices(ls, cfg, rng, n=1)
    assert len(choices) == 1
    assert isinstance(choices[0], Choice)


def test_apply_choice_increments_level_and_carries_overflow():
    cfg = make_config(xp_base=5.0, xp_growth=1.5)
    rng = random.Random(0)
    ls = LevelState(level=1, xp=7.0)  # 2.0 over the level-1 threshold of 5.0
    (choice,) = roll_choices(ls, cfg, rng)
    out = apply_choice(ls, choice, cfg)
    # Level incremented, overflow xp carried into the next level.
    assert out.level == 2
    assert abs(out.xp - 2.0) < 1e-9
    # Input unchanged (pure).
    assert ls.level == 1
    assert ls.xp == 7.0
