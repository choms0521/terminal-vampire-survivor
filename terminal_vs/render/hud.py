"""terminal_vs.render.hud - minimal HUD lines (Day 5).

Builds the Phase 1 HUD as plain text lines (no blessed): an HP bar, a level + xp
bar, and a survival timer. The frame composer overlays these lines on the top
rows of the viewport. Weapon/passive icons and kill count are deferred to Phase 3
(master plan section, HUD minimal in Phase 1).

This module is pure and blessed-free: it returns strings only. ``render.frame``
pads/colorizes them; the HP/xp maximums are passed in (never hardcoded) so the
HUD has no knowledge of player-start constants.

The xp shown is progress toward clearing the CURRENT level, whose threshold comes
from ``rules.leveling.xp_to_clear`` -- the single source of truth for the curve.
"""

from __future__ import annotations

from ..config import Config
from ..rules.leveling import xp_to_clear

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

    level = state.level_state.level
    xp = state.level_state.xp
    threshold = xp_to_clear(level, cfg)
    xp_fraction = (xp / threshold) if threshold > 0.0 else 0.0
    level_line = f"LV {level}  XP {_bar(xp_fraction)} {xp:.0f}/{threshold:.0f}"

    elapsed = state.elapsed
    minutes = int(elapsed) // 60
    seconds = int(elapsed) % 60
    time_line = f"TIME {minutes:02d}:{seconds:02d}"

    return [hp_line, level_line, time_line]
