"""terminal_vs.render.hud - HUD lines + modal overlays (Phase 3 Day 5).

Builds the HUD as plain text lines (no terminal I/O) and the modal overlay
panels the loop's mode machine shows over it. The HUD carries the five elements
(master section 9): an HP bar, a level + xp bar, a survival timer, the kill
count, and the owned-weapon/passive list. The frame composer overlays the HUD on
the top rows of the viewport.

Modal overlays, one per non-play loop mode:
  * ``draft_overlay_lines`` / ``overlay_lines("levelup", ...)`` -- the numbered
    level-up draft cards.
  * ``overlay_lines("pause", ...)`` -- the pause panel.
  * ``overlay_lines("gameover", ...)`` -- the run-summary + restart panel.

This module is pure and render-free: it returns strings only. ``render.frame``
pads/colorizes them; the HP/xp maximums are passed in (never hardcoded) so the
HUD has no knowledge of player-start constants.

The xp shown is progress toward clearing the CURRENT level, whose threshold comes
from ``rules.leveling.xp_for_level`` -- the single source of truth for the curve.
The level/xp/weapons/passives values are read from ``state.build`` (the
BuildState); the kill count from ``state.kills``.
"""

from __future__ import annotations

from ..config import Config
from ..meta.accrue import upgrade_cost
from ..rules.leveling import Choice, xp_for_level

# Width of each text bar in characters (a UI layout choice, not a Phase 0
# performance number, so it is not gated by the no-hardcode perf check).
_BAR_WIDTH = 20

# Overlay modes -- mirror the loop's state-machine mode names so the loop can
# pass its current mode straight through to the composer. "play" shows no modal
# panel; the other three each show a distinct, non-empty overlay.
MODE_PLAY = "play"
MODE_LEVELUP = "levelup"
MODE_PAUSE = "pause"
MODE_GAMEOVER = "gameover"


def _bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    """Render a ``[####----]`` style bar for ``fraction`` in [0, 1]."""
    clamped = 0.0 if fraction < 0.0 else (1.0 if fraction > 1.0 else fraction)
    filled = int(round(clamped * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _level_tokens(levels: tuple[tuple[str, int], ...]) -> str:
    """Join ``(name, level)`` pairs as ``"name Lv1 other Lv2"`` (empty -> "")."""
    return " ".join(f"{name} Lv{level}" for name, level in levels)


def hud_lines(state, cfg: Config, max_hp: float | None = None) -> list[str]:
    """Return the HUD as plain text lines (top-of-viewport overlay).

    The five HUD elements (master section 9), laid out on four lines:
      0. ``HP`` bar + current/max,
      1. ``LV`` + ``XP`` bar + xp/threshold,
      2. ``TIME`` survival timer + ``KILLS`` count,
      3. ``WPN`` owned weapons (name + level) + ``PSV`` owned passives.

    ``max_hp`` is the player's full hit points, supplied by the loop (captured
    from the fresh run) so the HP bar has a denominator without importing any
    private start constant. If it is ``None`` or non-positive, the current hp is
    used as the maximum, which renders a full bar rather than dividing by zero.
    """
    player_hp = state.player.hp
    denom = max_hp if (max_hp is not None and max_hp > 0.0) else player_hp
    hp_fraction = (player_hp / denom) if denom > 0.0 else 0.0
    shown_hp = player_hp if player_hp > 0.0 else 0.0
    hp_line = f"HP {_bar(hp_fraction)} {shown_hp:.0f}/{denom:.0f}"

    level = state.build.level
    xp = state.build.xp
    threshold = xp_for_level(level, cfg.defs)
    xp_fraction = (xp / threshold) if threshold > 0.0 else 0.0
    level_line = f"LV {level}  XP {_bar(xp_fraction)} {xp:.0f}/{threshold:.0f}"

    elapsed = state.elapsed
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60
    time_line = f"TIME {minutes:02d}:{seconds:02d}   KILLS {state.kills}"

    weapons = _level_tokens(state.build.weapon_levels)
    passives = _level_tokens(state.build.passive_levels)
    build_line = f"WPN {weapons}   PSV {passives}".rstrip()

    return [hp_line, level_line, time_line, build_line]


def draft_overlay_lines(pending_choices: tuple[Choice, ...]) -> list[str]:
    """Return the level-up draft as numbered choice lines (pure, blessed-free).

    Each card is listed as ``"1) <label>"``, ``"2) <label>"``, ... (1-based to
    match the number keys the loop maps to a selection). A leading header line
    introduces the overlay. With no pending choices the list is empty, so the
    overlay renders nothing. Strings only -- ``render.frame`` overlays them.
    """
    if not pending_choices:
        return []
    lines = ["LEVEL UP -- choose:"]
    for index, choice in enumerate(pending_choices, start=1):
        lines.append(f"{index}) {choice.label}")
    return lines


def pause_overlay_lines() -> list[str]:
    """Return the pause panel as plain text lines (pure, static help text)."""
    return ["== PAUSED ==", "p: resume", "q: quit"]


def gameover_overlay_lines(state) -> list[str]:
    """Return the game-over panel: run summary + upgrade shop + restart/quit help.

    Reads the survival time, final level, and kill count from the read-only sim
    state so the panel reflects how the run ended, then lists the banked gold and
    one numbered line per permanent upgrade (its next-level price, or MAX). The
    loop's game-over mode turns the matching digit into a purchase; ``r`` restarts
    and ``q`` quits. Pure -- returns strings only.
    """
    elapsed = state.elapsed
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60
    lines = [
        "== GAME OVER ==",
        f"survived {minutes:02d}:{seconds:02d}",
        f"level {state.build.level}   kills {state.kills}",
        f"gold {state.meta.gold}",
    ]
    # Permanent-upgrade shop: one numbered line per upgrade (sorted for a stable
    # digit->upgrade mapping the loop reuses). Press the digit to buy the next
    # level on the game-over screen.
    upgrades = state.cfg.defs.upgrades
    for i, uid in enumerate(sorted(upgrades), start=1):
        udef = upgrades[uid]
        owned = state.meta.upgrades.get(uid, 0)
        if owned >= udef.max_level:
            lines.append(f"[{i}] {uid} MAX")
        else:
            lines.append(f"[{i}] {uid} Lv{owned} -> {upgrade_cost(udef, owned)}g")
    lines.append("r: restart   q: quit")
    return lines


def overlay_lines(mode: str, state) -> list[str]:
    """Return the modal overlay lines for a loop ``mode`` (pure, render-free).

    Dispatch by the loop's mode name:
      * ``levelup``  -> the numbered draft cards (from ``state.pending_choices``),
      * ``pause``    -> the pause panel,
      * ``gameover`` -> the run-summary panel,
      * anything else (``play``) -> no overlay (empty list).

    The three non-play modes return distinct, non-empty line lists, so a composed
    frame unambiguously shows which mode it is in.
    """
    if mode == MODE_LEVELUP:
        return draft_overlay_lines(getattr(state, "pending_choices", ()))
    if mode == MODE_PAUSE:
        return pause_overlay_lines()
    if mode == MODE_GAMEOVER:
        return gameover_overlay_lines(state)
    return []
