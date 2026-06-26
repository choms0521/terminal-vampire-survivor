"""Pure HUD + modal-overlay tests (Phase 3 Day 5).

``hud_lines`` renders the five HUD elements (HP / level+xp / timer / kills /
weapons+passives) and ``overlay_lines`` renders the three non-play modal panels
(levelup / pause / gameover). All render-free: strings only, asserted directly,
no terminal or TTY.
"""

from __future__ import annotations

import random

from terminal_vs.meta.schema import MetaState
from terminal_vs.render.hud import hud_lines, overlay_lines
from terminal_vs.rules.defs import MetaUpgradeDef
from terminal_vs.rules.leveling import Choice
from terminal_vs.sim.state import new_run

from .conftest import make_config, make_defs


def _fresh(kills: int = 0):
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.kills = kills
    return cfg, state


def test_hud_has_all_five_elements():
    """All five HUD elements appear in the composed HUD text (AC7)."""
    cfg, state = _fresh(kills=9)
    text = "\n".join(hud_lines(state, cfg, max_hp=100.0))
    assert "HP " in text          # 1. hp bar
    assert "LV " in text          # 2a. level
    assert "XP " in text          # 2b. xp bar
    assert "TIME " in text        # 3. survival timer
    assert "KILLS 9" in text      # 4. kill count
    assert "WPN " in text         # 5a. owned weapons
    assert "PSV" in text          # 5b. owned passives


def test_hud_lists_owned_weapon_with_level():
    """The weapon/passive line shows owned entries as name + level."""
    cfg, state = _fresh()
    text = "\n".join(hud_lines(state, cfg, 100.0))
    assert "dagger Lv1" in text  # the starting weapon, at level 1


def test_hud_reflects_live_kill_count():
    """The HUD shows the current kill count, not a fixed value."""
    cfg, state = _fresh(kills=42)
    text = "\n".join(hud_lines(state, cfg, 100.0))
    assert "KILLS 42" in text


def test_overlay_three_modes_are_distinct_and_nonempty():
    """levelup, pause, and gameover overlays each render distinct, non-empty text."""
    cfg, state = _fresh(kills=5)
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
        Choice(kind="passive", label="attack_speed Lv1", target="attack_speed"),
    )
    levelup = overlay_lines("levelup", state)
    pause = overlay_lines("pause", state)
    gameover = overlay_lines("gameover", state)

    assert levelup and pause and gameover    # all three non-empty
    assert levelup != pause                  # pairwise distinct
    assert pause != gameover
    assert levelup != gameover
    # Each carries its mode's signature text.
    assert any("LEVEL UP" in line for line in levelup)
    assert any("PAUSED" in line for line in pause)
    assert any("GAME OVER" in line for line in gameover)


def test_overlay_play_mode_is_empty():
    """Play mode shows no modal overlay panel."""
    cfg, state = _fresh()
    assert overlay_lines("play", state) == []


def test_levelup_overlay_lists_the_draft_cards():
    """The levelup overlay numbers each pending draft card."""
    cfg, state = _fresh()
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
        Choice(kind="passive", label="attack_speed Lv1", target="attack_speed"),
    )
    lines = overlay_lines("levelup", state)
    assert "1) dagger Lv2" in lines
    assert "2) attack_speed Lv1" in lines


def test_gameover_overlay_summarizes_the_run():
    """The gameover panel reports survival time, level, kills, and restart help."""
    cfg, state = _fresh(kills=17)
    state.elapsed = 75.0  # 01:15
    panel = "\n".join(overlay_lines("gameover", state))
    assert "01:15" in panel
    assert "kills 17" in panel
    assert "level 1" in panel
    assert "restart" in panel  # the restart key is advertised


def test_gameover_overlay_shows_gold_and_upgrade_shop():
    """The gameover panel lists banked gold and a numbered shop line per upgrade."""
    cfg = make_config(
        defs=make_defs(
            upgrades={"swift": MetaUpgradeDef("swift", 5, "move_speed", 1.1, 50, 1.5)}
        )
    )
    state = new_run(cfg, random.Random(0), meta=MetaState(gold=120))
    panel = "\n".join(overlay_lines("gameover", state))
    assert "gold 120" in panel
    assert "[1] swift" in panel  # numbered shop line for the upgrade
    assert "50g" in panel  # next-level cost at level 0 (cost_base)
