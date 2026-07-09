"""terminal_vs.render.frame - layered viewport rendering (Day 5).

This module composites the visible simulation into a flicker-free terminal frame
(master plan sections 3.4, 3.6). It is split into two layers:

  * A PURE composer (``compose_cells`` / ``compose_frame``) that builds the cell
    grid and a plain frame string. It takes NO ``term`` and never touches
    blessed, so it is unit-tested headlessly (tests/test_render_frame.py).
  * A thin blessed emitter (``render_frame``) that colorizes the pure cell grid,
    pads each row to the fixed terminal-column width, and emits the whole frame
    after a single ``term.home`` (NO full-screen clear -> no flicker, master 3.6).
    It returns the emitted string so a no-TTY smoke test can assert it is non-empty.

Logical cells vs terminal columns: the cell grid is ``viewport_h`` x
``viewport_w`` LOGICAL cells, but each cell emits ``cfg.cell_width`` TERMINAL
columns at output time (1 in the fallback "ascii" glyph set, 2 in the shipped
"emoji" set where a 2-column emoji replaces an entity glyph). ``_cell_to_columns``
performs that
conversion, always emitting exactly ``cfg.cell_width`` columns per cell so a full
row is ``cfg.render_cols`` columns wide -- the invariant the no-clear redraw needs
so a moving wide glyph never leaves a stale second column behind.

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

import math

from wcwidth import wcswidth

from ..config import Config
from ..world import Camera, cell_to_world, is_visible, world_to_cell
from .hud import draft_overlay_lines, hud_lines, overlay_lines

# Empty floor cell. A single space both reads as "no entity here" and, once rows
# are padded to the fixed width, erases any ghost glyph left from a prior frame.
# At output time a floor cell emits ``cfg.cell_width`` terminal columns (one space
# in ascii, two in emoji), so it fully overwrites a wide glyph that just vacated
# the cell -- see ``_cell_to_columns``.
_FLOOR_GLYPH = " "
# Floor cells are UNCOLORED: the empty color name is not in _KNOWN_COLORS, so the
# blessed emitter returns the bare space with no SGR escape. Coloring the
# thousands of empty floor cells would emit a color escape per cell and inflate
# the per-frame byte count (master plan section 3.3, the throughput bottleneck)
# for no visual gain (a space has no foreground glyph to color).
_FLOOR_COLOR = ""

# Known entity color names (the entity ``.color`` strings from sim.state, plus
# the enemy colors from balance.toml). The blessed emitter maps these to terminal
# escapes; an unknown name falls back to the plain glyph so the emitter can never
# raise on unexpected data. "magenta" is the swarm enemy color, added so the
# swarm renders colored (Chunk 1 review follow-up); "cyan" is reserved for future
# enemy/effect colors. "bright_black" (dim gray) colors the background dot lattice
# so it never competes visually with the white player or colored enemies.
# "bright_yellow" is the xp-gem color: a bright gold that pops against the dim
# floor dots, so a dropped pickup reads at a glance (a plain green gem on the old
# "." glyph used to blend into the lattice).
_KNOWN_COLORS = (
    "white",
    "red",
    "yellow",
    "green",
    "magenta",
    "cyan",
    "bright_black",
    "bright_yellow",
)

# Background dot lattice -- the "moving through a world" cue. A sparse grid of
# points fixed in WORLD space; because the camera keeps the player centered, the
# points scroll past as the player moves, so an otherwise empty void reads as a
# large traversable field. Spacing is in world units; x is scaled by aspect_x on
# screen, so the values are chosen to read as a roughly even on-screen grid
# (~8 cells wide x 3 cells tall at aspect_x = 2).
_DOT_GLYPH = "·"  # middle dot
# Dimmed so dots never compete with the white player / colored enemies. Only a
# couple hundred dots are placed per frame (~130 in the default 100x30 viewport),
# so coloring them does NOT hit the empty-floor byte budget (master 3.3) that keeps
# the thousands of BLANK cells uncolored.
_DOT_COLOR = "bright_black"
_DOT_SPACING_X = 4.0  # world units; scaled by aspect_x -> ~8 cells between columns
_DOT_SPACING_Y = 3.0  # world units; maps 1:1 to rows -> 3 rows between dot rows

# Render-layer glyph -> emoji map (emoji glyph set only). Keyed by the ascii/unicode
# glyph the sim/balance layers already carry, so nothing upstream (balance.toml,
# rules.defs, sim.state, make_enemy, conftest) changes -- on-screen glyphs are
# unique, so a by-glyph dict is a sufficient supply model. Covers every on-screen
# entity and weapon glyph; the only glyph left unmapped is the background dot "·",
# which stays ascii and is padded to cell_width columns. Each emoji here is a
# 2-column (wcswidth == 2) cell (asserted by test_all_emoji_glyphs_are_width_two).
_EMOJI_GLYPHS = {
    # Entities: player, pickup, enemies, bosses.
    "☻": "🙂",  # player
    "✦": "💎",  # xp-gem pickup
    "z": "🧟",  # walker enemy
    "x": "🦇",  # swarm enemy
    "B": "👹",  # brute enemy
    "◉": "🐗",  # tank boss
    "✸": "🧙",  # caster boss (its projectiles reuse this glyph)
    "C": "🐺",  # charger enemy (fast, durable rusher)
    # Weapons: projectile / melee-effect glyphs. Each maps to a single-code-point
    # width-2 emoji in the same 0x1F3xx-0x1F5xx range as the entities above. No
    # variation-selector (VS16) emoji -- those render width-1 in some terminals and
    # would break the row-width invariant the no-clear redraw depends on.
    "-": "🔪",  # dagger dart
    "✱": "🔮",  # magic_bolt
    ")": "🌀",  # swing (melee arc effect)
    ">": "🏹",  # dagger_evolved (piercing fan)
    "=": "🔱",  # lance
    "#": "🌟",  # lance_evolved
    "✺": "💥",  # nova (radial burst)
    "O": "🔵",  # orbit
    "•": "🟠",  # scatter (shotgun pellet)
}


def _display_glyph(glyph: str, cfg: Config) -> str:
    """Map a logical cell glyph to its display glyph for the active glyph set.

    Ascii mode returns the glyph unchanged; emoji mode substitutes a mapped emoji
    (unmapped glyphs pass through). No colorizing here -- only glyph selection, so
    width can be measured on the raw display glyph before ansi escapes are added.
    """
    if cfg.glyph_set == "emoji":
        return _EMOJI_GLYPHS.get(glyph, glyph)
    return glyph


def _cell_to_columns(glyph: str, color: str, cfg: Config, colorize) -> str:
    """Render one logical cell as exactly ``cfg.cell_width`` terminal columns.

    The width invariant the no-clear redraw depends on: every cell contributes a
    fixed column count so a full row is ``cfg.render_cols`` wide and a moving wide
    glyph never leaves a stale second column behind (master 3.6).

    Width is measured with ``wcswidth`` on the RAW display glyph BEFORE colorizing,
    because ansi escapes make ``wcswidth`` return -1 on a colorized string. A
    width-1 glyph is colorized then right-padded with uncolored spaces to fill the
    cell; a full-width (== cell_width) glyph fills the cell alone. In ascii mode
    cell_width == 1, so this reduces to the previous ``colorize(glyph, color)``.

    Defensive: a glyph whose measured width is < 1 or > cell_width (a control char,
    or a wide glyph landing in a narrow cell) would corrupt row alignment, so it
    degrades to the original glyph if that fits one column, else a ``"?"``
    placeholder, padded to cell_width. This keeps the row-width invariant intact
    even on unexpected data.
    """
    display = _display_glyph(glyph, cfg)
    width = wcswidth(display)
    cell_width = cfg.cell_width
    if width < 1 or width > cell_width:
        fallback = glyph if wcswidth(glyph) == 1 else "?"
        return colorize(fallback, color) + " " * (cell_width - 1)
    # width in [1, cell_width]: colorize the glyph, then pad the leftover columns
    # with UNCOLORED spaces (padding stays outside the color escapes).
    return colorize(display, color) + " " * (cell_width - width)


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
        [(_FLOOR_GLYPH, _FLOOR_COLOR) for _ in range(width)] for _ in range(height)
    ]
    # Lay the scrolling background dots first, under every entity layer.
    _place_background_dots(grid, cam, cfg)

    def _place(entity) -> None:
        if not is_visible(entity.x, entity.y, cam, cfg):
            return
        col, row = world_to_cell(entity.x, entity.y, cam, cfg)
        if 0 <= col < width and 0 <= row < height:
            grid[row][col] = (entity.glyph, entity.color)

    # Draw priority (each layer overwrites the previous at a shared cell):
    # pickups < enemies < projectiles < effects, then the player on top of all.
    for pickup in state.pickups:
        _place(pickup)
    for enemy in state.enemies:
        _place(enemy)
    for projectile in state.projectiles:
        _place(projectile)
    for effect in state.effects:
        _place(effect)
    _place(state.player)  # always-on-top (master 3.4)

    return grid


def _place_background_dots(
    grid: list[list[tuple[str, str]]], cam: Camera, cfg: Config
) -> None:
    """Seed the floor with a sparse, world-fixed dot lattice that scrolls.

    The dots live on a fixed world-space grid; the player-following camera maps
    them to shifting screen cells, so they scroll past as the player moves and the
    void reads as a traversable field. Only the lattice points within the visible
    band are iterated (far cheaper than testing every cell), each placed on its
    floor cell; entity layers drawn afterwards overwrite any dot they share a cell
    with, so the lattice stays strictly in the background.
    """
    width = cfg.viewport_w
    height = cfg.viewport_h
    # World bounds of the viewport corners. With the camera centered these bracket
    # the visible region; cell_to_world is the exact inverse of world_to_cell on
    # integer cells, so points derived here map back into the viewport.
    wx0, wy0 = cell_to_world(0, 0, cam, cfg)
    wx1, wy1 = cell_to_world(width - 1, height - 1, cam, cfg)
    x_lo, x_hi = (wx0, wx1) if wx0 <= wx1 else (wx1, wx0)
    y_lo, y_hi = (wy0, wy1) if wy0 <= wy1 else (wy1, wy0)
    # Integer lattice indices spanning the band, padded by 1 each side so an edge
    # point that rounds back into an edge cell is not dropped (which would make a
    # row/column pop in a cell late while scrolling). Out-of-range cells are culled
    # by the bounds check below.
    i_lo = math.ceil(x_lo / _DOT_SPACING_X) - 1
    i_hi = math.floor(x_hi / _DOT_SPACING_X) + 1
    j_lo = math.ceil(y_lo / _DOT_SPACING_Y) - 1
    j_hi = math.floor(y_hi / _DOT_SPACING_Y) + 1
    for i in range(i_lo, i_hi + 1):
        wx = i * _DOT_SPACING_X
        for j in range(j_lo, j_hi + 1):
            wy = j * _DOT_SPACING_Y
            col, row = world_to_cell(wx, wy, cam, cfg)
            if 0 <= col < width and 0 <= row < height:
                grid[row][col] = (_DOT_GLYPH, _DOT_COLOR)


def compose_frame(
    state,
    cam: Camera,
    cfg: Config,
    colorize,
    max_hp: float | None = None,
    mode: str = "play",
) -> str:
    """Compose the full frame string from the pure cell grid + HUD + modal overlay.

    ``colorize(glyph, color_name) -> str`` is injected so this stays render-free
    and unit-testable: the headless test passes an identity colorizer, the
    emitter passes a blessed-backed one. Each row is built to exactly
    ``cfg.render_cols`` terminal columns -- gameplay rows via ``_cell_to_columns``
    (cell_width columns per logical cell), HUD/panel rows via ``ljust`` -- so the
    fixed width erases ghosts (master 3.6); the HUD lines overlay the top rows last
    (HUD draws over everything, master 3.4).

    ``max_hp`` is threaded into the HUD as the HP-bar denominator (captured by the
    loop from the fresh run) so no player-start constant is hardcoded here.

    Modal overlay (master 3.4, 8/9): ``mode`` selects the panel drawn centered
    over the frame above the HUD rows -- the level-up draft (``levelup``), the
    pause panel (``pause``), or the game-over summary (``gameover``); ``play``
    draws none. For backward compatibility the draft also appears whenever
    ``state.pending_choices`` is non-empty even if ``mode`` is left at ``play``
    (callers that drive the draft purely via ``pending_choices``).
    """
    grid = compose_cells(state, cam, cfg)

    # HUD overlay: replace the leading rows' text with HUD lines. The HUD is the
    # topmost layer, so it overwrites whatever the cell grid had on those rows.
    overlay = hud_lines(state, cfg, max_hp)
    rendered_rows: list[str] = []
    for row_index, cells in enumerate(grid):
        if row_index < len(overlay):
            # HUD text is plain ascii (no per-glyph color, len == columns); clip
            # then pad to the terminal-column width so it overwrites the full row.
            text = overlay[row_index][: cfg.render_cols]
            rendered_rows.append(text.ljust(cfg.render_cols))
        else:
            # Each logical cell emits exactly cfg.cell_width terminal columns, so
            # the row is cfg.render_cols wide in both ascii and emoji modes.
            rendered_rows.append(
                "".join(
                    _cell_to_columns(glyph, color, cfg, colorize)
                    for glyph, color in cells
                )
            )

    # Modal overlay: the mode's panel (pause/gameover) or the level-up draft,
    # drawn centered over the frame above the HUD rows. The draft also shows
    # whenever pending_choices is set even at mode="play" (backward compatible
    # with callers that drive the draft via pending_choices). getattr keeps the
    # composer tolerant of test doubles without a pending_choices field.
    panel = overlay_lines(mode, state)
    if not panel and getattr(state, "pending_choices", ()):
        panel = draft_overlay_lines(state.pending_choices)
    if panel:
        _overlay_panel_centered(rendered_rows, panel, cfg, hud_height=len(overlay))

    return "\n".join(rendered_rows)


def _overlay_panel_centered(
    rendered_rows: list[str],
    panel: list[str],
    cfg: Config,
    hud_height: int,
) -> None:
    """Overlay a modal panel's lines centered on the frame, in place.

    Serves every modal overlay (draft / pause / game-over). Vertically centered
    but never on top of the ``hud_height`` HUD rows, and horizontally centered.
    Each line is plain ascii text (no per-glyph color, like the HUD, so ``len`` ==
    columns) clipped and padded to the terminal-column width so it centers across
    and cleanly overwrites the full gameplay row beneath it. Lines that would fall
    outside the viewport are skipped, so a tall panel never overflows the grid.
    """
    width = cfg.render_cols
    height = cfg.viewport_h
    start = max(hud_height, (height - len(panel)) // 2)
    for offset, line in enumerate(panel):
        row = start + offset
        if not (0 <= row < height):
            continue
        indent = max(0, (width - len(line)) // 2)
        rendered_rows[row] = (" " * indent + line)[:width].ljust(width)


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


def render_frame(
    term,
    state,
    cam: Camera,
    cfg: Config,
    max_hp: float | None = None,
    mode: str = "play",
) -> str:
    """Compose and emit one flicker-free frame; return the emitted frame string.

    Flicker-free (master 3.6): build the entire frame as one string, then emit it
    after a single ``term.home`` with NO clear. Returning the frame string lets a
    no-TTY smoke test assert the compose path produced a non-empty result without
    needing a real terminal for the write. ``mode`` is threaded to the composer so
    the pause / game-over / level-up overlay matches the loop's current mode.
    """
    frame = compose_frame(state, cam, cfg, _term_colorize(term), max_hp, mode)
    # Single home + one write, no clear (master 3.6): printing the cursor-home
    # escape then the frame overwrites the previous frame in place.
    print(term.home + frame, end="", flush=True)
    return frame
