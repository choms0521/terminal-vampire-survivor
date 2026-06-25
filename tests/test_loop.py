"""Tests for terminal_vs.loop: the level-up draft selection and drain (Phase 2).

These exercise the loop's level-up handling headlessly with a fake terminal,
without depending on the player surviving long enough to level up organically
(survival is balance-gated and is a Phase 3 concern). The loop's ``sim`` test
seam lets us inject a SimState that already has a pending level-up.

The Phase 2 draft is a SELECTION (number keys 1..N), not a single confirm. The
loop rolls ``state.pending_choices`` on entering levelup and ``apply_draft_selection``
applies the chosen card, advances one level (carrying the xp overflow), and
reconciles the per-weapon cooldowns; the headless ``_drain_levelups`` auto-picks
index 0 per banked level via that same helper.
"""

from __future__ import annotations

import random

from dataclasses import replace

from terminal_vs.loop import _drain_levelups, apply_draft_selection, run
from terminal_vs.rules.leveling import xp_for_level
from terminal_vs.sim.state import new_run

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


def _prime_pending(state, cfg, level: int, xp: float) -> None:
    """Set the build's level/xp and flag a pending level-up (as step would)."""
    state.build = replace(state.build, level=level, xp=xp)
    state.level_up_pending = True


def test_drain_levelups_consumes_one_level():
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    # Exactly enough xp to clear level 1, flagged pending (as step would).
    _prime_pending(state, cfg, level=1, xp=xp_for_level(1, cfg.defs))

    _drain_levelups(state, cfg, rng)

    assert state.build.level == 2
    assert state.level_up_pending is False
    assert state.pending_choices == ()


def test_drain_levelups_consumes_multiple_banked_levels():
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    # Bank enough xp to clear BOTH level 1 and level 2 in one drain.
    banked = xp_for_level(1, cfg.defs) + xp_for_level(2, cfg.defs)
    _prime_pending(state, cfg, level=1, xp=banked)

    _drain_levelups(state, cfg, rng)

    # Two thresholds cleared -> level 3, and the flag is cleared.
    assert state.build.level == 3
    assert state.level_up_pending is False
    assert state.pending_choices == ()


def test_apply_draft_selection_reconciles_cooldowns():
    """Selecting a new-weapon card adds the weapon and a fresh 0.0 cooldown."""
    cfg = make_config()
    rng = random.Random(0)
    state = new_run(cfg, rng)
    _prime_pending(state, cfg, level=1, xp=xp_for_level(1, cfg.defs))
    # Force a deterministic, known choice: a new magic_bolt weapon card.
    from terminal_vs.rules.leveling import KIND_NEW_WEAPON, Choice

    state.pending_choices = (
        Choice(kind=KIND_NEW_WEAPON, label="New: magic_bolt", target="magic_bolt"),
    )

    apply_draft_selection(state, 0, cfg, rng)

    weapon_names = {name for name, _ in state.build.weapon_levels}
    assert "magic_bolt" in weapon_names
    # The cooldown dict was reconciled to the new weapon set.
    assert "magic_bolt" in state.weapon_cooldowns
    assert state.weapon_cooldowns["magic_bolt"] == 0.0
    assert state.build.level == 2
    assert state.level_up_pending is False


def test_levelup_overlay_select_returns_to_play():
    """play -> (pending) -> levelup overlay -> select -> back to play.

    Drive run() with an injected primed sim: a neutral poll trips the level-up
    mode (rolling the draft), a number key selects card 1, and a quit key exits.
    The observable result is that the injected sim advanced a level and the
    pending flag was cleared by the loop (step never clears it).
    """
    cfg = make_config()
    rng = random.Random(0)
    sim = new_run(cfg, rng)
    _prime_pending(sim, cfg, level=1, xp=xp_for_level(1, cfg.defs))

    term = _FakeTerm([_FakeKey(""), _FakeKey("1"), _FakeKey("q")])
    run(term, cfg, rng, sim=sim)

    assert sim.build.level >= 2
    assert sim.level_up_pending is False
    assert sim.pending_choices == ()


def test_gameover_restart_repaints_a_fresh_play_frame(capsys):
    """play -> (hp<=0) game-over overlay -> 'r' restart -> fresh full-hp play frame.

    The restart key on the game-over screen must start a NEW run and repaint a
    play frame, not sit frozen. Drive run() with an injected sim that is already
    dead (player.hp == 0): the first play poll trips game-over without needing to
    step, 'r' restarts, and 'q' quits. The captured frames must show the game-over
    panel and then end on a fresh full-hp play frame -- the wire test that the
    restart actually repaints (guards against a "restart key does nothing"
    regression), per the render-overlay wire-test lesson.
    """
    cfg = make_config()
    rng = random.Random(0)
    sim = new_run(cfg, rng)
    sim.player.hp = 0.0  # already dead: the first play poll trips game-over

    term = _FakeTerm([_FakeKey(""), _FakeKey("r"), _FakeKey("q")])
    term.home = "<F>"  # frame separator so the captured frames can be split
    run(term, cfg, rng, sim=sim)

    # Derive the expected full-HP token from a reference fresh run instead of
    # hardcoding "100/100", so the assertion follows the start HP / HUD format.
    full_hp = new_run(cfg, random.Random(0)).player.hp
    full_hp_token = f"{full_hp:.0f}/{full_hp:.0f}"

    frames = [f for f in capsys.readouterr().out.split("<F>") if f.strip()]
    assert any("GAME OVER" in f for f in frames)  # the game-over overlay was shown
    assert "GAME OVER" not in frames[-1]          # ended on a play frame (restarted)
    assert full_hp_token in frames[-1]            # fresh full hp after the restart


def test_pause_resume_repaints_a_play_frame(capsys):
    """play -> 'p' pause overlay -> 'p' resume -> immediate play repaint.

    Resuming from pause must repaint at once so the "PAUSED" panel clears
    instantly; otherwise the just-reset accumulator yields zero steps on the next
    play iteration and the play branch's render guard skips the repaint, leaving
    the stale overlay on screen (a user-visible glitch). The captured frames must
    show the PAUSED panel and then END on a play frame with no PAUSED text.
    """
    cfg = make_config()
    rng = random.Random(0)
    sim = new_run(cfg, rng)

    term = _FakeTerm([_FakeKey("p"), _FakeKey("p"), _FakeKey("q")])
    term.home = "<F>"  # frame separator so the captured frames can be split
    run(term, cfg, rng, sim=sim)

    frames = [f for f in capsys.readouterr().out.split("<F>") if f.strip()]
    assert any("PAUSED" in f for f in frames)  # the pause overlay was shown
    assert "PAUSED" not in frames[-1]          # resume repainted a clean play frame
