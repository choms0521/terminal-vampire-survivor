"""bench/emoji_spike.py - feasibility probe for an optional emoji glyph mode.

This probe MOTIVATED the emoji glyph set now shipped behind ``glyph_set = "emoji"``
(see ``terminal_vs/render/frame.py`` ``_cell_to_columns`` / ``config.py`` load-time
normalization). Originally ``compose_cells`` wrote one glyph per grid cell and the
row was padded by ``len()`` -- a one-glyph-per-terminal-cell assumption. Color
emoji occupy TWO cells, so dropping them into that model misaligned every row to
the right of an emoji.

The viable path (now implemented) is a uniform "2-cell slot" grid: every logical
cell emits ``cell_width`` columns (an ASCII glyph becomes ``glyph + space``; an
emoji fills the slot exactly). That ONLY stays aligned if the terminal+font
actually draws each emoji as a clean 2 cells -- which varies by terminal
(iTerm2/kitty/WezTerm good; Terminal.app, tmux, some SSH setups inconsistent) and
by emoji (single-codepoint stable; VS16/ZWJ sequences unpredictable), which is why
ASCII stays the shipped default and emoji is opt-in.

This script does two things:
  1. Reports the Unicode-standard width of candidate emoji (machine-checkable).
  2. Renders an ASCII baseline grid next to an emoji grid so you can EYEBALL
     whether the columns line up in YOUR terminal.

It does NOT touch the game; it is a throwaway measurement tool.

Run:  python bench/emoji_spike.py
"""

from __future__ import annotations

import unicodedata as ud

try:
    from wcwidth import wcswidth  # type: ignore

    _HAVE_WCWIDTH = True
except Exception:  # pragma: no cover - optional dependency
    _HAVE_WCWIDTH = False

    def wcswidth(s: str) -> int:  # fallback: east-asian-width estimate
        total = 0
        for ch in s:
            total += 2 if ud.east_asian_width(ch) in ("W", "F") else 1
        return total


# Candidate emoji by role. Single-codepoint where possible (more width-stable);
# avoid ZWJ sequences (family, profession) which render at unpredictable widths.
CANDIDATES = {
    "player": ["\U0001F642", "\U0001F600", "\U0001F916", "\U0001F9D9", "\U0001F977"],
    "gem/xp": ["\U0001F48E", "\U0001F4A0", "\U0001F537", "⭐", "\U0001FA99"],
    "enemy": ["\U0001F47E", "\U0001F479", "\U0001F480", "\U0001F9DF", "\U0001F987"],
    "boss": ["\U0001F451", "\U0001F409", "\U0001F608", "\U0001F531"],
}


def _expected_width(ch: str) -> int:
    """Unicode-standard cell width: W/F -> 2, else 1. A 2 is what we WANT."""
    return 2 if ud.east_asian_width(ch) in ("W", "F") else 1


def report_widths() -> None:
    print("=" * 60)
    print("[1] WIDTH PROBE (machine-checked, Unicode standard)")
    print("=" * 60)
    src = "wcwidth lib" if _HAVE_WCWIDTH else "east_asian_width fallback"
    print(f"measurement source: {src}")
    print(f"{'role':8} {'emoji':6} {'EAW':4} {'wcwidth':8} name")
    all_two = True
    for role, glyphs in CANDIDATES.items():
        for ch in glyphs:
            eaw = ud.east_asian_width(ch)
            w = wcswidth(ch)
            if w != 2:
                all_two = False
            try:
                name = ud.name(ch)
            except ValueError:
                name = "?"
            print(f"{role:8} {ch:6} {eaw:4} {str(w):8} {name}")
    print()
    if all_two:
        print(">> All candidates are 2 cells by the Unicode standard. A 2-cell")
        print(">> grid model CAN stay aligned IF your terminal honors that width.")
    else:
        print(">> Some candidates are NOT a clean 2 cells -- those would misalign")
        print(">> even in a 2-cell grid. Prefer the ones that report wcwidth == 2.")
    print()


def _ascii_grid_rows() -> list[str]:
    """8x4 ASCII grid in 2-cell slots. Always aligns (every slot is 2 cols)."""
    layout = [
        list("........"),
        list(".@..z..."),
        list("....B..."),
        list("........"),
    ]
    # Each cell -> 2 columns: "<glyph> " so ASCII slots are exactly 2 wide.
    return ["".join(f"{c} " for c in row) for row in layout]


def _emoji_grid_rows() -> list[str]:
    """Same layout, but entities are emoji. A 2-cell emoji fills the slot; the
    floor '. ' stays 2 cols. Columns line up ONLY if the emoji is truly 2 cells.
    """
    player, gem, enemy, boss = (
        CANDIDATES["player"][0],
        CANDIDATES["gem/xp"][0],
        CANDIDATES["enemy"][0],
        CANDIDATES["boss"][0],
    )
    layout = [
        [". ", ". ", ". ", ". ", ". ", ". ", ". ", ". "],
        [". ", player, ". ", ". ", enemy, ". ", ". ", ". "],
        [". ", ". ", ". ", ". ", boss, ". ", ". ", ". "],
        [". ", ". ", ". ", gem, ". ", ". ", ". ", ". "],
    ]
    return ["".join(cells) for cells in layout]


def render_alignment_demo() -> None:
    print("=" * 60)
    print("[2] ALIGNMENT DEMO (eyeball this in YOUR terminal)")
    print("=" * 60)
    print("A 2-cell grid. The floor is '. ' (a dot then a space) = 2 columns per")
    print("cell. Watch the vertical columns of dots.\n")

    print("--- ASCII baseline (this MUST line up) ---")
    for r in _ascii_grid_rows():
        print(r)
    print()
    print("--- EMOJI grid (lines up ONLY if emoji draw as 2 cells here) ---")
    for r in _emoji_grid_rows():
        print(r)
    print()

    print("--- control: emoji in a 1-cell model (this is EXPECTED to break) ---")
    print("shows why the current renderer can't just swap glyphs:")
    p = CANDIDATES["player"][0]
    print("a" + p + "b" + p + "c   <- letters should be evenly spaced; they won't be")
    print()


def verdict_guide() -> None:
    print("=" * 60)
    print("[3] HOW TO READ THIS")
    print("=" * 60)
    print("- If the EMOJI grid's dot columns line up as cleanly as the ASCII")
    print("  baseline -> emoji render at 2 cells here -> EMOJI MODE IS VIABLE.")
    print("- If they stagger / drift right -> your terminal draws emoji at")
    print("  inconsistent widths -> emoji mode would misalign here. Keep ASCII")
    print("  as the default with emoji as an opt-in toggle + fallback.")
    print("- The [1] table tells us the Unicode-standard intent; [2] tells us")
    print("  what your terminal ACTUALLY does. Both must agree to ship emoji mode.")
    print()


def main() -> None:
    report_widths()
    render_alignment_demo()
    verdict_guide()


if __name__ == "__main__":
    main()
