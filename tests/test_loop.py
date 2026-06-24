"""Tests for terminal_vs.loop: the level-up mode transition and drain.

These exercise the loop's level-up handling headlessly with a fake terminal,
without depending on the player surviving long enough to level up organically
(survival is balance-gated and is a Phase 3 concern). The loop's ``sim`` test
seam lets us inject a SimState that already has a pending level-up.
"""

from __future__ import annotations

import random

from terminal_vs.loop import _drain_levelups, run
from terminal_vs.rules.leveling import xp_to_clear
from terminal_vs.sim.state import LevelState, new_run

from .conftest import make_config


class _FakeKey:
    """A polled key stand-in: ``str(key)`` and ``.name`` are what the loop reads."""

    def __init__(self, text: str = "", name: str | None = None) -> None:
        self._text = text
        self.name = name

    def __str__(self) -> str:
        return self._text


class _FakeTerm:
    """Minimal blessed stand-in: scripted ``inkey`` + render-safe attributes.

    ``render_frame`` reads ``term.home`` and ``getattr(term, <color>, None)``
    (unknown colors fall back to a plain glyph), so a bare object with ``home``
    is enough to drive the loop without a real terminal.
    """

    home = ""
    normal = ""

    def __init__(self, keys: list[_FakeKey]) -> None:
        self._keys = list(keys)

    def inkey(self, timeout: float = 0.0) -> _FakeKey:
        # Once the script is exhausted the loop should already be quitting; return
        # a quit key as a safety net so a test can never spin forever.
        if self._keys:
            return self._keys.pop(0)
        return _FakeKey("q")


def test_drain_levelups_consumes_one_level():
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    # Exactly enough xp to clear level 1, flagged pending (as step would).
    state.level_state = LevelState(level=1, xp=xp_to_clear(1, cfg))
    state.level_up_pending = True

    _drain_levelups(state, cfg, rng)

    assert state.level_state.level == 2
    assert state.level_up_pending is False


def test_drain_levelups_consumes_multiple_banked_levels():
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    # Bank enough xp to clear BOTH level 1 and level 2 in one drain.
    banked = xp_to_clear(1, cfg) + xp_to_clear(2, cfg)
    state.level_state = LevelState(level=1, xp=banked)
    state.level_up_pending = True

    _drain_levelups(state, cfg, rng)

    # Two thresholds cleared -> level 3, and the flag is cleared.
    assert state.level_state.level == 3
    assert state.level_up_pending is False


def test_levelup_overlay_confirm_returns_to_play():
    """play -> (pending) -> levelup overlay -> confirm drains -> back to play.

    Drive run() with an injected primed sim: a neutral poll trips the level-up
    mode, a confirm key drains it, and a quit key exits. The observable result is
    that the injected sim advanced a level and the pending flag was cleared by the
    loop (step never clears it).
    """
    cfg = make_config()
    rng = random.Random(0)
    sim = new_run(cfg, rng)
    sim.level_state = LevelState(level=1, xp=xp_to_clear(1, cfg))
    sim.level_up_pending = True

    term = _FakeTerm([_FakeKey(""), _FakeKey(" "), _FakeKey("q")])
    run(term, cfg, rng, sim=sim)

    assert sim.level_state.level >= 2
    assert sim.level_up_pending is False
