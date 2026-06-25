"""Tests for the level-up draft flow end to end (Phase 2, loop-independent).

These verify the three contract points (master plan Day 6 / section 8) without a
terminal: step stage 8 SETS the pending flag when xp crosses a threshold, a draft
selection applies the chosen card to the build (weapon or passive reflected), and
the drain clears the pending flag + pending choices. The selection/drain go
through the loop's headless helpers (``apply_draft_selection`` / ``_drain_levelups``)
so the test drives the exact code path the interactive loop uses.
"""

from __future__ import annotations

import random

from dataclasses import replace

from terminal_vs.loop import _drain_levelups, _roll_pending, apply_draft_selection
from terminal_vs.rules.leveling import (
    KIND_NEW_WEAPON,
    KIND_PASSIVE,
    Choice,
    xp_for_level,
)
from terminal_vs.sim.state import Intent, new_run
from terminal_vs.sim.step import step

from .conftest import make_config


def test_levelup_pending_set_on_threshold():
    """Step stage 8 sets level_up_pending once accrued xp clears the threshold.

    Drive a stationary run until the magnet collects enough xp to cross level 1's
    threshold; the flag must flip to True (step sets it, never clears it).
    """
    cfg = make_config()
    rng = random.Random(42)
    state = new_run(cfg, rng)
    saw_pending = False
    for _ in range(1100):
        step(state, Intent(0, 0), cfg, rng)
        if state.level_up_pending:
            saw_pending = True
            break
    assert saw_pending is True
    assert state.build.xp >= xp_for_level(1, cfg.defs)


def test_choice_index_applies_weapon_to_build():
    """Selecting a new-weapon card reflects that weapon in the build."""
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    state.build = replace(state.build, level=1, xp=xp_for_level(1, cfg.defs))
    state.level_up_pending = True
    state.pending_choices = (
        Choice(kind=KIND_NEW_WEAPON, label="New: swing", target="swing"),
    )

    apply_draft_selection(state, 0, cfg, rng)

    weapons = {name for name, _ in state.build.weapon_levels}
    assert "swing" in weapons
    assert state.build.level == 2  # the selection consumed exactly one level


def test_choice_index_applies_passive_to_build():
    """Selecting a passive card reflects that passive in the build."""
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    state.build = replace(state.build, level=1, xp=xp_for_level(1, cfg.defs))
    state.level_up_pending = True
    state.pending_choices = (
        Choice(kind=KIND_PASSIVE, label="attack_speed Lv1", target="attack_speed"),
    )

    apply_draft_selection(state, 0, cfg, rng)

    passives = dict(state.build.passive_levels)
    assert passives.get("attack_speed") == 1


def test_pending_cleared_after_drain():
    """After the drain consumes all banked levels, pending is False + empty."""
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    state.build = replace(state.build, level=1, xp=xp_for_level(1, cfg.defs))
    state.level_up_pending = True
    _roll_pending(state, cfg, rng)

    _drain_levelups(state, cfg, rng)

    assert state.level_up_pending is False
    assert state.pending_choices == ()
    assert state.build.level == 2


def test_pending_choices_rolled_to_draft_size():
    """The rolled draft has up to draft_choices cards (the balance N-pick size)."""
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    _roll_pending(state, cfg, rng)
    assert 0 < len(state.pending_choices) <= cfg.defs.leveling.draft_choices
