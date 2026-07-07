"""Headless tests for the PURE render compose path (Day 5/6).

These exercise ``render.frame.compose_cells`` / ``compose_frame`` without blessed
or a TTY: the pure composer takes no ``term``, so the cell-grid build, culling,
draw-priority overdraw, and fixed-width padding are all unit-testable headlessly.
The blessed emitter (``render_frame``) is a thin wrapper over this path; its
compose result is what these tests cover.
"""

from __future__ import annotations

import random

from wcwidth import wcswidth

from terminal_vs.render.frame import (
    _DOT_COLOR,
    _DOT_GLYPH,
    _DOT_SPACING_X,
    _DOT_SPACING_Y,
    _EMOJI_GLYPHS,
    _FLOOR_GLYPH,
    _KNOWN_COLORS,
    _cell_to_columns,
    _identity_colorize,
    _term_colorize,
    compose_cells,
    compose_frame,
)
from terminal_vs.rules.leveling import Choice
from terminal_vs.sim.state import Enemy, Pickup, make_enemy, new_run
from terminal_vs.world import world_to_cell

from .conftest import make_config


def test_player_lands_at_viewport_center():
    """The camera follows the player, so the player maps to the center cell."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    center_col = cfg.viewport_w // 2
    center_row = cfg.viewport_h // 2
    glyph, color = grid[center_row][center_col]
    assert glyph == state.player.glyph
    assert color == state.player.color


def test_player_overdraws_enemy_sharing_a_cell():
    """An enemy on the player's cell is overwritten by the always-on-top player."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # Place an enemy exactly on the player's world position (shared cell).
    state.enemies.append(
        Enemy(entity_id=state.alloc_id(), x=state.player.x, y=state.player.y, hp=1.0)
    )
    grid = compose_cells(state, state.camera, cfg)
    center_col = cfg.viewport_w // 2
    center_row = cfg.viewport_h // 2
    glyph, _ = grid[center_row][center_col]
    assert glyph == state.player.glyph  # player wins the shared cell


def test_offscreen_entity_is_culled():
    """An entity far outside the viewport never appears in the grid."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    far = state.player.x + cfg.viewport_w * 1000.0
    state.enemies.append(
        Enemy(entity_id=state.alloc_id(), x=far, y=state.player.y, hp=1.0)
    )
    grid = compose_cells(state, state.camera, cfg)
    glyphs = {glyph for row in grid for glyph, _ in row}
    assert "z" not in glyphs  # the off-screen enemy glyph is absent


def test_blank_floor_cells_are_uncolored():
    """Blank floor cells carry no color so the emitter emits no SGR per empty cell
    (master 3.3 byte budget). The thousands of blank cells are the budget concern;
    the sparse background dots are colored separately (~130 per default viewport).
    Guards against re-coloring the empty floor."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    # Every blank cell (glyph == space, i.e. not a dot or entity) must be uncolored.
    for row in grid:
        for glyph, color in row:
            if glyph == _FLOOR_GLYPH:
                assert color == ""  # uncolored -> emitter returns a bare glyph


def test_background_dot_lattice_is_present():
    """The floor is seeded with background dots (not an empty void), so the world
    reads as a large traversable space rather than the player standing still."""
    cfg = make_config()  # default 100x30 viewport: ample room for the 8x3 lattice
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    dot_count = sum(1 for row in grid for glyph, _ in row if glyph == _DOT_GLYPH)
    assert dot_count > 0


def test_background_dots_are_dimmed_not_default_fg():
    """Background dots are colored dim so they never compete with the player /
    enemies. Guards against the dots rendering in the bright default foreground."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    dot_colors = {color for row in grid for glyph, color in row if glyph == _DOT_GLYPH}
    assert dot_colors == {_DOT_COLOR}  # every dot carries the dim color
    assert _DOT_COLOR in _KNOWN_COLORS  # and the emitter knows how to dim it


def test_background_dots_scroll_with_camera():
    """Moving the camera shifts the world-fixed dot lattice on screen, so the
    player reads as moving THROUGH a world rather than standing in place. Guards
    the core "movement feel": the dots are anchored in world space, not screen
    space."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid_a = compose_cells(state, state.camera, cfg)
    # Shift by a non-lattice-multiple world delta so the on-screen dots must move
    # (1.0 world -> 2 cells in X at aspect_x=2 / 1 row in Y, both below the period).
    state.camera.x += 1.0
    state.camera.y += 1.0
    grid_b = compose_cells(state, state.camera, cfg)

    def _dot_cells(grid):
        return {
            (col, row)
            for row, cells in enumerate(grid)
            for col, (glyph, _) in enumerate(cells)
            if glyph == _DOT_GLYPH
        }

    assert _dot_cells(grid_a) != _dot_cells(grid_b)  # the lattice scrolled


def test_entity_draws_over_a_background_dot():
    """An entity sharing a cell with a lattice dot is drawn on top: the player sits
    on the world origin (a lattice point) yet renders as its glyph, proving dots
    are background-only and never occlude gameplay."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # Precondition: the player must sit on a lattice point for a dot to actually
    # land on its cell -- otherwise this test would pass trivially (no dot to
    # overdraw) and silently rot if a future change started the player off-origin.
    # The fresh player starts at the world origin, a multiple of every spacing.
    assert state.player.x % _DOT_SPACING_X == 0.0
    assert state.player.y % _DOT_SPACING_Y == 0.0

    grid = compose_cells(state, state.camera, cfg)
    center_col = cfg.viewport_w // 2
    center_row = cfg.viewport_h // 2
    glyph, _ = grid[center_row][center_col]
    assert glyph == state.player.glyph  # entity wins over the background dot
    assert glyph != _DOT_GLYPH


def test_swarm_enemy_renders_with_known_color():
    """A swarm enemy's "magenta" color is emitted (now a known color).

    The grid carries the swarm's glyph + color, and the blessed emitter wraps a
    known color in an SGR escape rather than dropping it (Chunk 1 review
    follow-up: magenta was added to _KNOWN_COLORS). Guards against the swarm
    rendering uncolored.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    swarm_def = cfg.defs.enemies["swarm"]
    # Place a swarm on the player's cell-neighborhood so it is visible.
    state.enemies.append(
        make_enemy(state.alloc_id(), state.player.x + 1.0, state.player.y, swarm_def)
    )
    grid = compose_cells(state, state.camera, cfg)
    colors = {color for row in grid for _, color in row}
    assert swarm_def.color in colors  # the swarm's color is present in the grid
    assert swarm_def.color in _KNOWN_COLORS  # and the emitter knows it

    # The emitter wraps a known color (non-empty marker) instead of the bare glyph.
    class _FakeTerm:
        normal = "<<>>"

        def __getattr__(self, name: str) -> str:
            return f"<{name}>"

    colorize = _term_colorize(_FakeTerm())
    emitted = colorize(swarm_def.glyph, swarm_def.color)
    assert emitted != swarm_def.glyph  # colorized, not the bare glyph
    assert swarm_def.color in emitted


def test_grid_dimensions_are_fixed():
    """The grid is exactly viewport_h rows of viewport_w cells."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    grid = compose_cells(state, state.camera, cfg)
    assert len(grid) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in grid)


def test_compose_frame_rows_padded_to_fixed_width():
    """Every emitted row is exactly viewport_w wide (fixed-width erases ghosts)."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)


def test_compose_frame_includes_hud_overlay():
    """The HUD lines overlay the top rows of the frame."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    first_row = frame.split("\n")[0]
    assert first_row.startswith("HP ")  # HP bar is the first HUD line


def test_compose_frame_is_nonempty():
    """The pure compose path yields a non-empty multi-row string."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    assert len(frame) > 0
    assert "\n" in frame


def test_compose_frame_draws_draft_overlay_when_pending():
    """A pending level-up draft is drawn into the frame (regression: the overlay
    was rolled into ``pending_choices`` but never rendered -- an invisible menu).

    Guards the wiring that overlays ``draft_overlay_lines`` onto the composed
    frame whenever a draft is pending, so the player can see the numbered cards.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
        Choice(kind="passive", label="attack_speed Lv1", target="attack_speed"),
    )
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)

    assert "LEVEL UP -- choose:" in frame
    assert "1) dagger Lv2" in frame
    assert "2) attack_speed Lv1" in frame
    # The fixed-width invariant must survive the overlay (no row grows/shrinks).
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)


def test_compose_frame_no_draft_overlay_when_not_pending():
    """With no pending draft, the frame carries no draft overlay text."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))  # fresh run: pending_choices == ()
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    assert "LEVEL UP" not in frame


def test_compose_frame_draft_long_label_is_clipped():
    """A draft card label wider than the viewport is clipped, never overflows.

    Locks in the fixed-width invariant for the overlay path: a too-long label is
    clipped to viewport_w (not wrapped onto a new row), so every row stays exactly
    viewport_w wide.
    """
    cfg = make_config(viewport_w=20, viewport_h=12)
    state = new_run(cfg, random.Random(0))
    state.pending_choices = (
        Choice(kind="passive", label="x" * 60, target="x"),  # far wider than 20
    )
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)  # clipped, no overflow


def test_compose_frame_draft_hidden_on_degenerate_viewport():
    """When the viewport is too short to fit any draft row below the HUD, the
    overlay is skipped without error and the HUD rows are preserved."""
    cfg = make_config(viewport_w=40, viewport_h=3)  # exactly the HUD height
    state = new_run(cfg, random.Random(0))
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
        Choice(kind="passive", label="attack_speed Lv1", target="attack_speed"),
    )
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    assert all(len(row) == cfg.viewport_w for row in rows)
    assert rows[0].startswith("HP ")  # HUD intact, not clobbered by the draft
    assert "LEVEL UP" not in frame  # no room below the HUD -> overlay hidden


# --- Emoji glyph set: 2-column render mode -----------------------------------
#
# In emoji mode every logical cell emits cfg.cell_width (== 2) terminal columns.
# Terminal columns, not Python str length, are the invariant: an emoji is one code
# point but two columns, so these tests measure with wcwidth.wcswidth (identity
# colorize only -- ansi escapes make wcswidth return -1).


def _emoji_cfg(**overrides):
    """A directly-constructed emoji-mode Config (EFFECTIVE geometry passed in).

    50 logical cells x 2 columns == 100 render columns; aspect_x is the already
    halved effective value (load-time derivation is covered by the config tests).
    """
    params = dict(
        glyph_set="emoji", cell_width=2, viewport_w=50, viewport_h=30, aspect_x=1.0
    )
    params.update(overrides)
    return make_config(**params)


def _display_columns(row: str) -> list[str]:
    """Expand a rendered row into one entry per TERMINAL column.

    A wide glyph (wcswidth 2) becomes its code point plus a "" continuation entry,
    so ``cols[c*cell_width:(c+1)*cell_width]`` isolates logical cell c's columns.
    Assumes an ansi-free row (identity colorize), so wcswidth is well-defined.
    """
    cols: list[str] = []
    for ch in row:
        width = wcswidth(ch)
        if width <= 0:
            continue
        cols.append(ch)
        cols.extend([""] * (width - 1))
    return cols


def test_cell_to_columns_floor_emits_cell_width_columns():
    """A floor cell emits cell_width space columns in emoji mode (ghost erase)."""
    cfg = _emoji_cfg()
    out = _cell_to_columns(_FLOOR_GLYPH, "", cfg, _identity_colorize)
    assert out == "  "
    assert wcswidth(out) == cfg.cell_width


def test_cell_to_columns_ascii_glyph_padded_to_cell_width():
    """An unmapped 1-wide glyph becomes ``glyph + space`` (two columns)."""
    cfg = _emoji_cfg()
    out = _cell_to_columns(_DOT_GLYPH, _DOT_COLOR, cfg, _identity_colorize)
    assert out == _DOT_GLYPH + " "
    assert wcswidth(out) == cfg.cell_width


def test_cell_to_columns_maps_player_glyph_to_emoji():
    """The player glyph maps to its emoji, which fills the 2-column slot alone."""
    cfg = _emoji_cfg()
    out = _cell_to_columns("☻", "white", cfg, _identity_colorize)
    assert out == _EMOJI_GLYPHS["☻"]
    assert wcswidth(out) == cfg.cell_width


def test_cell_to_columns_padding_is_uncolored():
    """Padding spaces sit OUTSIDE the color escapes (width measured pre-colorize)."""
    cfg = _emoji_cfg()

    def fake(glyph: str, name: str) -> str:
        return f"<{name}>{glyph}</>"

    # A 1-wide unmapped glyph: the colorized glyph, then a bare (uncolored) pad.
    # The background dot stays unmapped in emoji mode, so it exercises this branch
    # (weapon glyphs like "-" now map to a full-width emoji instead).
    out = _cell_to_columns(_DOT_GLYPH, "white", cfg, fake)
    assert out == f"<white>{_DOT_GLYPH}</> "
    assert out.endswith("> ")  # trailing pad is a plain space, not inside <...>


def test_cell_to_columns_defensive_fallback_for_wide_glyph_in_narrow_cell():
    """A wide glyph in a 1-column ascii cell degrades to '?' rather than overflow.

    Pathological input (an emoji reached in ascii mode): width 2 > cell_width 1, so
    the defensive branch preserves the row-width invariant with a 1-column
    placeholder instead of emitting two columns.
    """
    cfg = make_config()  # ascii, cell_width == 1
    out = _cell_to_columns("🙂", "white", cfg, _identity_colorize)
    assert out == "?"
    assert wcswidth(out) == cfg.cell_width


def test_emoji_frame_every_row_is_render_cols_wide():
    """PRIMARY invariant: every rendered row is exactly render_cols columns wide in
    emoji mode -- gameplay, HUD, and modal-overlay rows alike. A short row would
    leave a stale ghost column under the no-clear redraw."""
    cfg = _emoji_cfg()
    state = new_run(cfg, random.Random(0))
    # Cover all three row kinds: gameplay entities + the HUD (always) + a modal.
    state.enemies.append(
        make_enemy(
            state.alloc_id(),
            state.player.x + 3.0,
            state.player.y,
            cfg.defs.enemies["walker"],
        )
    )
    state.pickups.append(
        Pickup(state.alloc_id(), state.player.x - 3.0, state.player.y + 1.0, xp=1.0)
    )
    state.pending_choices = (
        Choice(kind="weapon_upgrade", label="dagger Lv2", target="dagger"),
        Choice(kind="passive", label="attack_speed Lv1", target="attack_speed"),
    )
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    rows = frame.split("\n")
    assert len(rows) == cfg.viewport_h
    for row in rows:
        assert wcswidth(row) == cfg.render_cols


def test_emoji_frame_contains_mapped_glyphs():
    """Player, pickup, and a mapped enemy render as their emoji in emoji mode."""
    cfg = _emoji_cfg()
    state = new_run(cfg, random.Random(0))
    state.enemies.append(
        make_enemy(
            state.alloc_id(),
            state.player.x + 3.0,
            state.player.y,
            cfg.defs.enemies["walker"],
        )
    )
    state.pickups.append(
        Pickup(state.alloc_id(), state.player.x - 3.0, state.player.y + 1.0, xp=1.0)
    )
    frame = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    assert _EMOJI_GLYPHS["☻"] in frame  # player
    assert _EMOJI_GLYPHS["z"] in frame  # walker enemy
    assert _EMOJI_GLYPHS["✦"] in frame  # xp-gem pickup


def test_emoji_weapon_glyphs_map_to_emoji():
    """Every weapon projectile / melee-effect glyph maps to a width-2 emoji that
    fills the 2-column slot alone (no padding), so combat reads as emoji-native."""
    cfg = _emoji_cfg()
    for glyph in ("-", "✱", ")", ">", "=", "#", "✺", "O"):
        emoji = _EMOJI_GLYPHS[glyph]  # KeyError here == a weapon glyph went unmapped
        out = _cell_to_columns(glyph, "white", cfg, _identity_colorize)
        assert out == emoji  # substituted, fills the cell alone (no trailing pad)
        assert wcswidth(out) == cfg.cell_width


def test_all_emoji_glyphs_are_width_two():
    """Regression backstop: EVERY mapped emoji (entities + weapons) must measure
    exactly 2 columns. A VS16 / narrow emoji added later would silently break the
    row-width invariant the no-clear redraw depends on -- this catches it at test
    time (wcswidth agreement; the terminal-font check stays a human gate)."""
    for src, emoji in _EMOJI_GLYPHS.items():
        assert wcswidth(emoji) == 2, (src, emoji)


def test_emoji_moving_enemy_leaves_no_ghost_column():
    """When a wide enemy vacates a cell, that cell emits cell_width floor columns
    (both overwritten), so the no-clear redraw leaves no stale second column.

    The player is pinned to viewport center by Camera.follow, so an ENEMY is moved
    between adjacent cells; the vacated cell must render back to floor."""
    cfg = _emoji_cfg()
    state = new_run(cfg, random.Random(0))
    walker = cfg.defs.enemies["walker"]
    enemy = make_enemy(
        state.alloc_id(), state.player.x + 3.0, state.player.y + 2.0, walker
    )
    state.enemies.append(enemy)

    grid_a = compose_cells(state, state.camera, cfg)
    old_col, old_row = world_to_cell(enemy.x, enemy.y, state.camera, cfg)
    assert grid_a[old_row][old_col][0] == "z"  # enemy occupies its cell in A

    # Slide the enemy right ~2 cells (aspect_x == 1 -> ~1 cell per world unit).
    enemy.x += 2.0
    grid_b = compose_cells(state, state.camera, cfg)
    new_col, new_row = world_to_cell(enemy.x, enemy.y, state.camera, cfg)
    assert (new_col, new_row) != (old_col, old_row)  # it really changed cells
    assert grid_b[old_row][old_col][0] == _FLOOR_GLYPH  # vacated cell is floor again

    frame_b = compose_frame(state, state.camera, cfg, _identity_colorize, max_hp=100.0)
    cols = _display_columns(frame_b.split("\n")[old_row])
    vacated = cols[old_col * cfg.cell_width : (old_col + 1) * cfg.cell_width]
    assert vacated == [" ", " "]  # exactly cell_width floor columns, no emoji ghost
