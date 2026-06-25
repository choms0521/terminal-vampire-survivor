"""terminal_vs.render.hud - minimal HUD lines + level-up draft overlay (Phase 2).

Builds the HUD as plain text lines (no blessed): an HP bar, a level + xp bar, and
a survival timer. The frame composer overlays these on the top rows of the
viewport. ``draft_overlay_lines`` renders the level-up draft cards as numbered
choice lines. Weapon/passive icons and kill count are deferred to Phase 3.

This module is pure and blessed-free: it returns strings only. ``render.frame``
pads/colorizes them; the HP/xp maximums are passed in (never hardcoded) so the
HUD has no knowledge of player-start constants.

The xp shown is progress toward clearing the CURRENT level, whose threshold comes
from ``rules.leveling.xp_for_level`` -- the single source of truth for the curve.
The level/xp values are read from ``state.build`` (the Phase 2 BuildState).
"""

from __future__ import annotations

from ..config import Config
from ..rules.leveling import Choice, xp_for_level

# Width of each text bar in characters (a UI layout choice, not a Phase 0
# performance number, so it is not gated by the no-hardcode perf check).
_BAR_WIDTH = 20


def _bar(fraction: float, width: int = _BAR_WIDTH) -> str:
    """Render a ``[####----]`` style bar for ``fraction`` in [0, 1]."""
    clamped = 0.0 if fraction < 0.0 else (1.0 if fraction > 1.0 else fraction)
    filled = int(round(clamped * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def hud_lines(state, cfg: Config, max_hp: float | None = None) -> list[str]:
    """Return the HUD as a list of plain text lines (top-of-viewport overlay).

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
    time_line = f"TIME {minutes:02d}:{seconds:02d}"

    return [hp_line, level_line, time_line]


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
