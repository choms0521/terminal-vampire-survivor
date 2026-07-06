# Emoji Mode — Implementation Plan (xmultiplan consensus)

> Status: **implemented** (2026-07-06) on branch `feat/emoji-mode`. Steps 1–11 are
> complete and the machine gate is green (full pytest pass, selftest coverage
> 97.68% ≥ 80%, `ruff check` clean). Step 12 (human-in-the-loop terminal
> verification with `TVS_GLYPH_SET=emoji python -m terminal_vs`) is the remaining
> acceptance gate and can only be confirmed by a person running the game.
>
> _Original consensus header retained below for the audit trail._

## Consensus Summary

| Field | Value |
|-------|-------|
| Workflow | `/xmultiplan` (cross-runtime Planner ↔ Critic loop) |
| Planner | Codex (`codex-cli 0.142.2`, external, `model_reasoning_effort=high`) |
| Critic | Claude (inline, this session) |
| Rounds | 2 (Round 1 ITERATE → 3 findings → Round 2 APPROVE) |
| Final verdict | **APPROVE** |
| Date | 2026-06-30 |
| Target branch | `feat/emoji-mode` |

### Round 1 → Round 2 deltas (critic findings resolved)
1. Ghost-prevention test was mis-designed (player is pinned to viewport center by
   `Camera.follow`). Fixed: test a moving enemy/projectile vacating a cell, plus a
   single whole-frame `wcswidth(row) == render_cols` invariant as the primary guard.
2. `effective_aspect_x = raw_aspect_x / 2` silently assumed `cell_width == 2`. Fixed:
   derive via `cell_width` (`raw_aspect_x / cell_width`, `raw_viewport_w // cell_width`,
   reject when `raw_viewport_w % cell_width != 0`).
3. End-user activation conflated with manual-test activation. Fixed: added a
   `TVS_GLYPH_SET` env override (mirrors `TVS_SEED`); shipped default stays `ascii`.

## ADR — Optional 2-column emoji render mode

- **Decision**: Add an opt-in `glyph_set = "ascii" | "emoji"` render mode. Emoji mode
  changes ONLY the render output stage: each logical cell emits exactly `cell_width`
  terminal columns; effective `viewport_w` / `aspect_x` are derived at config load
  (divided by `cell_width`); a render-layer by-glyph dict maps ASCII glyphs to emoji.
  ASCII stays the shipped default and the fallback.
- **Decision drivers**: (1) the no-clear `term.home` redraw makes a stale 2nd-column
  emoji ghost the primary failure mode; (2) `compose_cells` / `world_to_cell` are
  already parameterized by `viewport_w` / `aspect_x`, so the coordinate layer needs no
  change; (3) HUD/overlay padding currently equates char-count with column-count,
  which emoji breaks.
- **Alternatives considered**: raw+effective config fields (rejected: larger API,
  wrong-field misuse); branch on `glyph_set` in world/render call sites (rejected:
  spreads emoji awareness, risks a 200-column stretch); per-entity emoji data fields
  (rejected: schema migration + fixture churn — on-screen glyphs are collision-free so
  a render-layer dict suffices); tuning-file-only toggle for activation (rejected:
  forces a hand-edit per play — chose a `TVS_GLYPH_SET` env override instead).
- **Why chosen**: keeps coordinate/grid/sim layers untouched, isolates all change to
  the render output stage plus config normalization, and keeps ASCII safe as the
  default and fallback.
- **Consequences**: `Config.viewport_w` / `aspect_x` become effective
  (post-normalization) values, not raw TOML values; emoji mode requires
  `raw_viewport_w % cell_width == 0`; the real acceptance gate is a human running the
  game (no-clear ghosting + alignment cannot be proven by pytest).
- **Follow-ups (out of scope for v1)**: terminal capability auto-detection;
  TOML-driven emoji set; diff renderer (deferred — though emoji sharpens the no-clear
  ghosting risk, which is why the moving-entity test matters).

---

_Below is the APPROVED planner draft (Codex, round 2) verbatim._

# Plan: Optional 2-Column Emoji Render Mode

## RALPLAN-DR Summary

- Principles (3-5):
  - Keep simulation, world mapping, and entity data unchanged; emoji mode is a render-output and config-normalization feature.
  - Preserve ASCII as the shipped default and fallback path.
  - Treat terminal columns, not Python string length, as the invariant in emoji mode.
  - Derive effective grid geometry at config load so users do not need to coordinate `glyph_set`, `viewport_w`, and `aspect_x` manually.
  - Keep the no-clear renderer safe by ensuring every logical cell emits exactly `cfg.cell_width` terminal columns.

- Decision Drivers (top 3):
  - The renderer emits `term.home + frame` with no clear, so stale second columns from moving emoji are the primary failure mode.
  - `compose_cells()` and `world_to_cell()` already operate on logical cells and are fully parameterized by `cfg.viewport_w` and `cfg.aspect_x`.
  - HUD and modal overlays currently use `cfg.viewport_w`, `len(line)`, slicing, and `ljust`; those must switch to terminal-column width in emoji mode.

- Viable Options (>=2):

  1. Config shape for `cell_width`, `viewport_w`, and `aspect_x`

     Option A, chosen: store effective `viewport_w` and effective `aspect_x` on `Config`, plus `glyph_set`, `cell_width`, and a derived `render_cols` property.
     - Pros: all existing world/sim/render grid code continues to read `cfg.viewport_w` and `cfg.aspect_x` without branching; `compose_cells()` stays untouched; render code can use `cfg.render_cols` for terminal-column padding.
     - Cons: `Config.viewport_w` no longer always equals the raw TOML value when `glyph_set = "emoji"`.
     - Rationale: this directly honors the architecture decision that coordinate/grid code does not change. The raw TOML value is only needed during load-time normalization, so storing it long-term would invite accidental misuse.

     Option B: store both raw and effective fields, for example `raw_viewport_w`, `viewport_w`, `raw_aspect_x`, `aspect_x`.
     - Pros: preserves observability of user-authored values.
     - Cons: larger config API; downstream code can accidentally choose the wrong field; more test churn.

     Option C: keep raw `viewport_w` and `aspect_x` on `Config`, and make render/world code branch on `glyph_set`.
     - Pros: TOML-to-config mapping is literal.
     - Cons: violates the chosen design; spreads emoji awareness into world/render call sites; makes it easy to produce a stretched 200-column render.

     Width divisibility decision: reject `raw_viewport_w` when `raw_viewport_w % cell_width != 0`. For emoji v1, `cell_width == 2`, but the derivation should still use `cell_width` as the single source of truth:
     - `effective_viewport_w = raw_viewport_w // cell_width`
     - `effective_aspect_x = raw_aspect_x / cell_width`

  2. Where the cell-to-terminal-columns helper lives

     Option A, chosen: add private render helpers in `terminal_vs/render/frame.py`, for example `_render_cols(cfg)`, `_display_glyph(glyph, cfg)`, and `_cell_to_columns(glyph, color, cfg, colorize)`.
     - Pros: keeps width measurement next to the row join that needs it; avoids introducing render concepts into `world.py`, `hud.py`, or entity state.
     - Cons: private helpers will be imported by focused tests, matching existing test style for `_term_colorize`, `_FLOOR_GLYPH`, etc.

     Option B: put column-width helpers on `Config`.
     - Pros: easy call site syntax.
     - Cons: config would start owning rendering mechanics and glyph measurement.

     Option C: put helper logic in `hud.py`.
     - Pros: HUD already builds text overlays.
     - Cons: gameplay cells are the core consumer; HUD text is ASCII and only needs a target width.

  3. Glyph supply model

     Option A, chosen: render-layer dict keyed by existing ASCII/entity glyph.
     - Pros: no changes to `balance.toml`, `rules.defs`, `sim.state`, `make_enemy()`, or `conftest.make_defs`; the existing glyph uniqueness check makes this sufficient.
     - Cons: two entities sharing a glyph would also share an emoji if future content collides.

     Option B: add per-entity or per-def emoji fields.
     - Pros: more explicit and content-driven.
     - Cons: larger schema migration; test fixtures hardcode synthetic content and would need broad updates; out of scope for v1.

  4. End-user activation model

     Option A: document editing `config/tuning.toml` as the sole v1 toggle.
     - Pros: smallest code change.
     - Cons: users must hand-edit shipped config to play emoji mode, and manual test instructions can blur with final PR state.

     Option B, chosen: keep shipped `glyph_set = "ascii"` but add a lightweight `TVS_GLYPH_SET` environment override, mirroring the existing `TVS_SEED` launch precedent.
     - Pros: users can opt in without mutating tracked config; manual verification can run emoji mode without a temporary config edit; shipped default remains ASCII.
     - Cons: adds one small startup-path branch and one config override test.
     - Rationale: this cleanly separates default product behavior from opt-in/manual-test activation.

## Plan Steps

1. Branch and baseline check

   Goal: Ensure implementation lands on the intended feature branch and starts from a known green-ish baseline.

   Deliverable: Work performed on `feat/emoji-mode`; baseline test/lint results recorded before edits.

   Files touched: none.

   **Measurable exit condition**:
   - `git branch --show-current` prints `feat/emoji-mode`.
   - Run:
     ```bash
     python -m pytest tests/test_config.py tests/test_render_frame.py
     ruff check
     ```
     Any pre-existing failures are documented before implementation.

2. Extend `Config` with glyph mode fields

   Goal: Add the public config contract for `glyph_set = "ascii" | "emoji"` and the render cell width.

   Deliverable:
   - Add `_TUNING_DEFAULTS["glyph_set"] = "ascii"`.
   - Add `glyph_set: str = "ascii"` and `cell_width: int = 1` to the frozen `Config` dataclass after existing required fields so current direct test construction remains valid.
   - Add `Config.render_cols` property returning `self.viewport_w * self.cell_width`.
   - Update docstrings/comments to clarify:
     - TOML `viewport_w` is the target terminal-column budget before glyph-set normalization.
     - `Config.viewport_w` is the effective logical grid width after normalization.
     - `Config.aspect_x` is the effective aspect factor after normalization.

   Files touched:
   - `terminal_vs/config.py`

   **Measurable exit condition**:
   - `python -m pytest tests/test_config.py::test_missing_files_use_all_defaults` passes.
   - In a Python REPL check, `load_config(absent_tuning, absent_balance).glyph_set == "ascii"` and `.cell_width == 1`.

3. Normalize glyph mode in `load_config()`

   Goal: Derive effective geometry once at config load.

   Deliverable:
   - Read `glyph_set = str(tuning.get("glyph_set", _TUNING_DEFAULTS["glyph_set"]))`, with an optional override hook for the startup env var.
   - Validate `glyph_set in ("ascii", "emoji")`; otherwise raise `ValueError` naming `glyph_set` and `config/tuning.toml`.
   - Compute `cell_width = 1` for ASCII, `2` for emoji.
   - Validate raw `viewport_w`, `viewport_h`, `aspect_x`, and other tuning values as today.
   - Require `raw_viewport_w % cell_width == 0`; if not, raise `ValueError` naming `viewport_w`, `glyph_set`, `cell_width`, and `config/tuning.toml`.
   - Derive:
     - `effective_viewport_w = raw_viewport_w // cell_width`
     - `effective_aspect_x = raw_aspect_x / cell_width`
   - For ASCII, this preserves current values because `cell_width == 1`.
   - Return `Config(... viewport_w=effective_viewport_w, aspect_x=effective_aspect_x, glyph_set=glyph_set, cell_width=cell_width, ...)`.

   Files touched:
   - `terminal_vs/config.py`

   **Measurable exit condition**:
   - New config tests pass:
     ```bash
     python -m pytest tests/test_config.py -q
     ```
   - Specific assertions added:
     - Valid ASCII tuning with no `glyph_set` keeps `viewport_w == 80`, `aspect_x == 2.0`, `cell_width == 1`, `render_cols == 80`.
     - Valid emoji tuning with raw `viewport_w = 80`, raw `aspect_x = 2`, `glyph_set = "emoji"` yields `viewport_w == 40`, `aspect_x == 1.0`, `cell_width == 2`, `render_cols == 80`.
     - `glyph_set = "bad"` raises `ValueError`.
     - `glyph_set = "emoji"` with raw `viewport_w = 81` raises `ValueError`.

4. Update shipped tuning default and add opt-in env activation

   Goal: Expose emoji mode while preserving current default behavior.

   Deliverable:
   - Add `glyph_set = "ascii"` to `config/tuning.toml`.
   - Update the nearby comment for `viewport_w` to clarify it is the terminal-column budget; effective logical cells are derived for emoji mode.
   - Add `TVS_GLYPH_SET` handling in `terminal_vs/__main__.py`, mirroring the existing `TVS_SEED` pattern.
   - Pass the env override into config loading so the same load-time normalization path derives `cell_width`, `viewport_w`, and `aspect_x`.
   - Do not mutate `config/tuning.toml` during normal launch or manual testing.

   Files touched:
   - `config/tuning.toml`
   - `terminal_vs/__main__.py`
   - `terminal_vs/config.py` only if needed for an override parameter

   **Measurable exit condition**:
   - `python -m pytest tests/test_config.py::test_shipped_config_loads_and_validates -q` passes.
   - `load_default_config()` shows `glyph_set == "ascii"`, `cell_width == 1`, and `render_cols == viewport_w`.
   - `TVS_GLYPH_SET=emoji python -m terminal_vs` launches using emoji mode without editing tracked config.
   - Invalid `TVS_GLYPH_SET` values fail with the same `ValueError` path as invalid TOML.

5. Add render-layer emoji mapping and cell-width helper

   Goal: Convert each logical render cell into exactly `cfg.cell_width` terminal columns before row assembly.

   Deliverable:
   - Import `wcswidth` from `wcwidth` in `terminal_vs/render/frame.py`.
   - Add a private mapping in `frame.py`:
     ```python
     _EMOJI_GLYPHS = {
         "☻": "🙂",
         "✦": "💎",
         "z": "🧟",
         "x": "🦇",
         "B": "👹",
         "◉": "🐗",
         "✸": "🧙",
     }
     ```
   - Add `_display_glyph(glyph, cfg)`:
     - ASCII mode returns `glyph`.
     - Emoji mode returns `_EMOJI_GLYPHS.get(glyph, glyph)`.
   - Add `_cell_to_columns(glyph, color, cfg, colorize)`:
     - Map to display glyph first.
     - Measure raw display glyph with `wcswidth(display_glyph)` before colorizing.
     - If measured width is `1`, emit `colorize(display_glyph, color) + " " * (cfg.cell_width - 1)`.
     - If measured width is `2` and `cfg.cell_width == 2`, emit only the colorized glyph.
     - In ASCII mode, current behavior remains equivalent.
     - Padding spaces are uncolored.
   - Include defensive behavior for unexpected widths:
     - If `wcswidth()` returns `< 1` or `> cfg.cell_width`, fall back to the original ASCII glyph if it fits; otherwise use `"?"`.
     - This prevents a bad glyph from breaking row width.

   Files touched:
   - `terminal_vs/render/frame.py`

   **Measurable exit condition**:
   - New focused tests for `_cell_to_columns()` pass:
     ```bash
     python -m pytest tests/test_render_frame.py -q
     ```
   - Test cases assert:
     - Floor `" "` in emoji mode emits two terminal columns.
     - ASCII fallback glyph `"·"` in emoji mode emits `"· "` with terminal width 2.
     - Mapped player glyph emits `🙂` with terminal width 2.
     - With a fake colorizer, padding spaces appear after the reset/normal marker, proving padding is uncolored.

6. Switch gameplay row assembly to the helper

   Goal: Make non-HUD gameplay rows column-stable in both modes.

   Deliverable:
   - In `compose_frame()`, replace:
     ```python
     "".join(colorize(glyph, color) for glyph, color in cells)
     ```
     with:
     ```python
     "".join(_cell_to_columns(glyph, color, cfg, colorize) for glyph, color in cells)
     ```
   - Leave `compose_cells()` untouched. It still builds a `cfg.viewport_h x cfg.viewport_w` logical grid of `(glyph, color)` tuples.
   - Leave `world.py` untouched. It continues to consume effective `cfg.viewport_w` and `cfg.aspect_x`.

   Files touched:
   - `terminal_vs/render/frame.py`

   **Measurable exit condition**:
   - Existing ASCII render tests still pass unchanged:
     ```bash
     python -m pytest tests/test_render_frame.py::test_compose_frame_rows_padded_to_fixed_width -q
     ```

7. Switch HUD and modal overlay padding to terminal columns

   Goal: Ensure HUD and panels overwrite the same terminal-column width as gameplay rows.

   Deliverable:
   - In `compose_frame()`, change HUD row logic from:
     ```python
     text = overlay[row_index][: cfg.viewport_w]
     rendered_rows.append(text.ljust(cfg.viewport_w))
     ```
     to use `cfg.render_cols`.
   - In `_overlay_panel_centered()`, change:
     ```python
     width = cfg.viewport_w
     indent = max(0, (width - len(line)) // 2)
     rendered_rows[row] = (" " * indent + line)[:width].ljust(width)
     ```
     to use `width = cfg.render_cols`.
   - Because HUD and panels are pure ASCII, `len(line)` remains valid for their clipping and centering strings.
   - Preserve vertical logic with `cfg.viewport_h` and `hud_height`.

   Files touched:
   - `terminal_vs/render/frame.py`

   **Measurable exit condition**:
   - New emoji tests pass:
     - HUD first row has `wcswidth(row) == cfg.render_cols` and starts with `"HP "`.
     - Level-up overlay rows have `wcswidth(row) == cfg.render_cols`.
     - Long draft labels are clipped to `cfg.render_cols`, not `cfg.viewport_w`.
     - Degenerate short viewport still preserves HUD rows.
   - Command:
     ```bash
     python -m pytest tests/test_render_frame.py -q
     ```

8. Update render tests for terminal-column invariants

   Goal: Cover the actual emoji-mode failure modes that pytest can catch.

   Deliverable:
   - Keep existing ASCII tests mostly unchanged; they should continue using `len(row) == cfg.viewport_w` where appropriate.
   - Add emoji-specific tests using a synthetic effective config, for example:
     ```python
     cfg = make_config(
         glyph_set="emoji",
         cell_width=2,
         viewport_w=50,
         viewport_h=30,
         aspect_x=1.0,
     )
     ```
   - Add the primary regression guard: a single emoji-mode invariant test using `_identity_colorize` that composes a frame containing gameplay rows, HUD rows, and modal-overlay rows, then asserts `wcwidth.wcswidth(row) == cfg.render_cols` for every rendered row.
   - Add tests that use `wcwidth.wcswidth(row)` for emoji rows because Python `len()` does not equal terminal columns for emoji.
   - Add a test that places player, pickup, and mapped enemies in visible cells and asserts the frame contains the expected emoji.
   - Add a test that unmapped projectiles such as `"-"`, `">"`, `"="`, `"#"`, `"O"`, `"✱"`, and `"✺"` remain ASCII and still occupy two columns through padding.
   - Add a supporting no-clear ghost-prevention test:
     - Keep the player/camera fixed, because `Camera.follow` pins the player to the viewport center.
     - Compose frame A with a moving enemy or projectile in a visible non-center logical cell.
     - Move that enemy or projectile to an adjacent logical cell and compose frame B.
     - Assert the vacated logical cell in frame B emits exactly `cfg.cell_width` floor columns, for example `"  "` in emoji mode, proving both columns are overwritten when a wide glyph leaves.
     - Use `_identity_colorize` and a test-local display-column slicer, or place the moving object where prior cells are floor-only, so ANSI escapes and emoji string length do not confound the assertion.

   Files touched:
   - `tests/test_render_frame.py`
   - `tests/conftest.py`

   **Measurable exit condition**:
   - `python -m pytest tests/test_render_frame.py -q` passes.
   - At least one test fails if any rendered row is narrower than `cfg.render_cols` in emoji mode.
   - At least one test fails if `_cell_to_columns()` emits only one space for floor cells in emoji mode.

9. Update config tests and fixture constructor

   Goal: Keep synthetic tests compatible with the new `Config` fields and lock down load-time derivation.

   Deliverable:
   - Extend `tests/conftest.py::make_config()` with optional `glyph_set: str = "ascii"` and `cell_width: int | None = None`.
   - If `cell_width is None`, derive `1` for ASCII and `2` for emoji.
   - Do not auto-halve `viewport_w` or `aspect_x` in `make_config()`; tests using direct construction should pass effective values explicitly. Load-time derivation belongs to `load_config()` tests.
   - Extend `tests/test_config.py`:
     - Default/missing key tests assert ASCII defaults.
     - Valid emoji tuning asserts effective geometry.
     - Invalid `glyph_set` test.
     - Non-divisible emoji `viewport_w` test.
     - Shipped config test asserts `glyph_set == "ascii"`.
     - Env override test asserts `TVS_GLYPH_SET=emoji` uses the same effective geometry derivation without changing shipped config.

   Files touched:
   - `tests/conftest.py`
   - `tests/test_config.py`

   **Measurable exit condition**:
   - `python -m pytest tests/test_config.py tests/test_render_frame.py -q` passes.

10. Documentation comments and spike alignment

   Goal: Make the implementation understandable without expanding scope.

   Deliverable:
   - Update `frame.py` module comments that currently say one glyph equals one terminal column. They should distinguish logical cells from terminal columns.
   - Update comments around `_FLOOR_GLYPH` to say floor emits `cfg.cell_width` terminal columns at output time.
   - Optionally update `bench/emoji_spike.py` comments only if they contradict the implementation; do not turn it into runtime detection.
   - Do not add terminal auto-detection, TOML-driven emoji sets, or diff rendering.

   Files touched:
   - `terminal_vs/render/frame.py`
   - `bench/emoji_spike.py` only if needed

   **Measurable exit condition**:
   - `rg "1 glyph == 1|viewport width in cells|ljust\\(cfg.viewport_w\\)|\\[: cfg.viewport_w\\]" terminal_vs bench tests` shows no stale implementation comments or render padding code that contradicts emoji mode.

11. Full machine gate

   Goal: Verify the implementation against the repo’s stated automated gate.

   Deliverable: Passing test/lint/selftest run.

   Files touched: none beyond previous steps.

   **Measurable exit condition**:
   ```bash
   python -m pytest
   python selftest.py
   ruff check
   ```
   - `pytest` passes.
   - `selftest.py` passes with coverage >= 80%.
   - `ruff check` exits 0.

12. Human-in-the-loop terminal verification

   Goal: Validate the real acceptance gate that automated tests cannot prove.

   Deliverable:
   - Run emoji mode through the opt-in env toggle, without editing tracked config:
     ```bash
     TVS_GLYPH_SET=emoji python -m terminal_vs
     ```
   - In the actual target terminal, move continuously, collect XP, trigger a level-up panel, pause/unpause, and watch for:
     - No stale second-column emoji ghosts after movement.
     - HUD rows and gameplay rows ending at the same visual column.
     - Level-up modal rows centered and erasing gameplay beneath them.
     - ASCII projectiles remaining readable and aligned in 2-column slots.
   - Confirm `config/tuning.toml` remains `glyph_set = "ascii"` before PR.

   Files touched:
   - none

   **Measurable exit condition**:
   - Human tester confirms: moving emoji mode has no ghosting and no HUD/modal misalignment.
   - Shipped `config/tuning.toml` default remains `glyph_set = "ascii"`.

## Acceptance Criteria

Machine-checkable criteria:

- ASCII remains the default:
  ```bash
  python - <<'PY'
  from terminal_vs.config import load_default_config
  cfg = load_default_config()
  assert cfg.glyph_set == "ascii"
  assert cfg.cell_width == 1
  assert cfg.render_cols == cfg.viewport_w
  PY
  ```

- Emoji config derives effective geometry:
  - `glyph_set = "emoji"`, raw `viewport_w = 100`, raw `aspect_x = 2` loads as effective `viewport_w = 50`, `aspect_x = 1.0`, `cell_width = 2`, `render_cols = 100`.
  - The derivation uses `cell_width`: `effective_viewport_w = raw_viewport_w // cell_width` and `effective_aspect_x = raw_aspect_x / cell_width`.

- End-user opt-in does not require config edits:
  - `TVS_GLYPH_SET=emoji python -m terminal_vs` launches emoji mode.
  - Shipped `config/tuning.toml` remains `glyph_set = "ascii"`.

- Invalid config is rejected:
  - Unknown `glyph_set` raises `ValueError`.
  - Raw `viewport_w` not divisible by `cell_width` with `glyph_set = "emoji"` raises `ValueError`.

- Render rows are width-stable:
  - ASCII compose tests keep `len(row) == cfg.viewport_w`.
  - Emoji compose tests use `wcwidth.wcswidth(row) == cfg.render_cols`.
  - A single emoji invariant test covers every rendered row in a frame containing gameplay, HUD, and modal-overlay rows using `_identity_colorize`.
  - A supporting no-clear regression test moves an enemy or projectile between adjacent cells and asserts the vacated cell emits exactly `cfg.cell_width` floor columns.

- Required commands pass:
  ```bash
  python -m pytest
  python selftest.py
  ruff check
  ```

Human-in-the-loop gate:

- Green pytest is necessary but not sufficient.
- The user must run the actual game in emoji mode in their terminal:
  ```bash
  TVS_GLYPH_SET=emoji python -m terminal_vs
  ```
- While moving and triggering a level-up panel, the user must confirm:
  - no stale second-column emoji ghosting from the no-clear redraw,
  - no HUD/gamefield column drift,
  - modal overlay rows align with and erase the field beneath them.

## Risks & Mitigations

- Ghosting on no-clear redraw:
  - Risk: a moving 2-column emoji leaves its second column behind when replaced by a 1-column floor space.
  - Mitigation: `_cell_to_columns()` emits exactly `cfg.cell_width` columns for every logical cell; floor `" "` emits `"  "` in emoji mode. Add a whole-frame `wcswidth(row) == cfg.render_cols` invariant test as the primary guard, plus a supporting moving-enemy/projectile test that verifies the vacated cell emits exactly `cfg.cell_width` floor columns.

- HUD/overlay column drift:
  - Risk: gameplay rows become 100 terminal columns while HUD/panels remain padded to 50 logical cells.
  - Mitigation: replace HUD clipping/padding and `_overlay_panel_centered()` width math with `cfg.render_cols`. Since HUD/panels are ASCII, `len()` remains valid for their internal clipping and centering, while tests still assert `wcswidth(row) == cfg.render_cols`.

- Non-divisible `viewport_w`:
  - Risk: raw `viewport_w = 101` cannot be evenly represented as 2-column cells.
  - Mitigation: reject raw `viewport_w` when `raw_viewport_w % cell_width != 0` with a clear `ValueError` instead of silently flooring or expanding.

- Aspect distortion:
  - Risk: hardcoding `raw_aspect_x / 2` couples geometry to today’s emoji width and can drift from the actual render cell width.
  - Mitigation: derive `effective_aspect_x = raw_aspect_x / cell_width`, matching `effective_viewport_w = raw_viewport_w // cell_width`.

- Emoji not actually 2-cell on some fonts:
  - Risk: `wcwidth` says width 2 but a terminal/font renders differently.
  - Mitigation: keep ASCII default; make emoji opt-in through `TVS_GLYPH_SET`; rely on the already-run spike for the user’s terminal; require final human verification in the real game.

- Measuring colorized strings:
  - Risk: terminal escape sequences corrupt width measurement.
  - Mitigation: measure the raw mapped glyph with `wcswidth()` before calling `colorize()`. Keep padding spaces outside color escapes. Use `_identity_colorize` for row-width invariant tests.

- ASCII default regressions:
  - Risk: render helper changes alter current ASCII behavior.
  - Mitigation: preserve existing ASCII tests, add explicit default config assertions, and ensure `cfg.cell_width == 1` makes `_cell_to_columns()` equivalent to the current join path.