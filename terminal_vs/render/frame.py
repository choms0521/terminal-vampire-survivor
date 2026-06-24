"""terminal_vs.render.frame - layered viewport rendering (Day 5).

This module composites the visible simulation into a flicker-free terminal frame
(master plan sections 3.4, 3.6). It is split into two layers:

  * A PURE composer (``compose_cells`` / ``compose_frame``) that builds the cell
    grid and a plain frame string. It takes NO ``term`` and never touches
    blessed, so it is unit-tested headlessly (tests/test_render_frame.py).
  * A thin blessed emitter (``render_frame``) that colorizes the pure cell grid,
    pads each row to the fixed viewport width, and emits the whole frame after a
    single ``term.home`` (NO full-screen clear -> no flicker, master 3.6). It
    returns the emitted string so a no-TTY smoke test can assert it is non-empty.

Draw priority (later overwrites earlier, master 3.4):
``floor < pickups < enemies < projectiles < player < HUD``. The player is ALWAYS
drawn on top of the entity layers; the HUD overlays everything last.

Culling: only entities that ``world.is_visible`` are placed, and each glyph's
cell is bounds-checked, so off-screen entities cost nothing and never overflow
the grid.

Phase 1 always emits a full frame; ``cfg.render_mode`` ("full" | "diff") is not
consumed here yet -- the diff renderer is deferred to Phase 2.
"""

from __future__ import annotations

from ..config import Config
from ..world import Camera, is_visible, world_to_cell
from .hud import hud_lines

# Empty floor cell. A single space both reads as "no entity here" and, once rows
# are padded to the fixed width, erases any ghost glyph left from a prior frame.
_FLOOR_GLYPH = " "

# Known entity color names (the entity ``.color`` strings from sim.state). The
# blessed emitter maps these to terminal escapes; an unknown name falls back to
# the plain glyph so the emitter can never raise on unexpected data.
_KNOWN_COLORS = ("white", "red", "yellow", "green")


def compose_cells(state, cam: Camera, cfg: Config) -> list[list[tuple[str, str]]]:
    """Build the pure ``viewport_h`` x ``viewport_w`` grid of ``(glyph, color)``.

    No blessed, no ``term``: this is the testable heart of rendering. The grid is
    initialized to floor cells, then each visible entity layer is written in draw
    order so later layers overwrite earlier ones at a shared cell. The player is
    written after the entity layers (always-on-top, master 3.4).

    Off-screen entities are culled via ``is_visible``; every computed cell is
    bounds-checked before it is written, so a glyph can never index out of grid.
    """
    width = cfg.viewport_w
    height = cfg.viewport_h
    grid: list[list[tuple[str, str]]] = [
        [(_FLOOR_GLYPH, "white") for _ in range(width)] for _ in range(height)
    ]

    def _place(entity) -> None:
        if not is_visible(entity.x, entity.y, cam, cfg):
            return
        col, row = world_to_cell(entity.x, entity.y, cam, cfg)
        if 0 <= col < width and 0 <= row < height:
            grid[row][col] = (entity.glyph, entity.color)

    # Draw priority (each layer overwrites the previous at a shared cell):
    # pickups < enemies < projectiles, then the player on top of all entities.
    for pickup in state.pickups:
        _place(pickup)
    for enemy in state.enemies:
        _place(enemy)
    for projectile in state.projectiles:
        _place(projectile)
    _place(state.player)  # always-on-top (master 3.4)

    return grid


def compose_frame(
    state,
    cam: Camera,
    cfg: Config,
    colorize,
    max_hp: float | None = None,
) -> str:
    """Compose the full frame string from the pure cell grid + HUD overlay.

    ``colorize(glyph, color_name) -> str`` is injected so this stays blessed-free
    and unit-testable: the headless test passes an identity colorizer, the
    emitter passes a blessed-backed one. Each row is padded to exactly
    ``cfg.viewport_w`` cells (fixed width erases ghosts, master 3.6); the HUD
    lines overlay the top rows last (HUD draws over everything, master 3.4).

    ``max_hp`` is threaded into the HUD as the HP-bar denominator (captured by the
    loop from the fresh run) so no player-start constant is hardcoded here.
    """
    grid = compose_cells(state, cam, cfg)

    # HUD overlay: replace the leading rows' text with HUD lines. The HUD is the
    # topmost layer, so it overwrites whatever the cell grid had on those rows.
    overlay = hud_lines(state, cfg, max_hp)
    rendered_rows: list[str] = []
    for row_index, cells in enumerate(grid):
        if row_index < len(overlay):
            # HUD text is plain (no per-glyph color); clip then pad to fixed width.
            text = overlay[row_index][: cfg.viewport_w]
            rendered_rows.append(text.ljust(cfg.viewport_w))
        else:
            rendered_rows.append(
                "".join(colorize(glyph, color) for glyph, color in cells)
            )
    return "\n".join(rendered_rows)


def _identity_colorize(glyph: str, name: str) -> str:
    """A blessed-free colorizer that returns the glyph unchanged.

    Used by headless tests (and as a safe default) so the pure compose path can
    run without a terminal.
    """
    return glyph


def _term_colorize(term):
    """Return a ``colorize(glyph, name) -> str`` backed by a blessed ``term``.

    Maps each known color name to the matching ``term`` color attribute; an
    unknown name falls back to the plain glyph so the emitter never raises.
    """
    color_attrs = {name: getattr(term, name, None) for name in _KNOWN_COLORS}

    def colorize(glyph: str, name: str) -> str:
        attr = color_attrs.get(name)
        if not attr:
            return glyph
        return f"{attr}{glyph}{term.normal}"

    return colorize


def render_frame(term, state, cam: Camera, cfg: Config, max_hp: float | None = None) -> str:
    """Compose and emit one flicker-free frame; return the emitted frame string.

    Flicker-free (master 3.6): build the entire frame as one string, then emit it
    after a single ``term.home`` with NO clear. Returning the frame string lets a
    no-TTY smoke test assert the compose path produced a non-empty result without
    needing a real terminal for the write.
    """
    frame = compose_frame(state, cam, cfg, _term_colorize(term), max_hp)
    # Single home + one write, no clear (master 3.6): printing the cursor-home
    # escape then the frame overwrites the previous frame in place.
    print(term.home + frame, end="", flush=True)
    return frame
