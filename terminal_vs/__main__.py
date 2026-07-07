"""terminal_vs.__main__ - package entry point (``python -m terminal_vs``).

Thin wiring (Day 5): build the blessed terminal, enter fullscreen / cbreak /
hidden-cursor mode, and hand control to ``loop.run`` with the default config and a
seeded ``random.Random``. All gameplay lives in ``loop`` / ``sim`` / ``rules``;
this module only sets up and tears down the terminal.

Importing this module must stay side-effect free: ``blessed.Terminal()`` is
constructed inside ``main()`` (under the ``__main__`` guard), never at import
time, so ``import terminal_vs.__main__`` does not open a terminal session.

Seeding: ``TVS_SEED`` may pin the run for reproducible play/debugging; otherwise
a system-entropy seed is used.

Glyph set: ``TVS_GLYPH_SET`` ("ascii" | "emoji") forces a render glyph set at
launch without editing tracked config and always wins. When it is unset/empty a
narrow auto-detect downgrades to "ascii" ONLY on a positive non-UTF-8 signal (a
non-UTF-8 stdout encoding, or a C/POSIX locale), so a clearly emoji-incapable
terminal does not render the broken emoji default; anything ambiguous keeps the
shipped "emoji" default. It cannot detect a UTF-8 locale paired with an
emoji-incapable font -- use ``TVS_GLYPH_SET=ascii`` (or ``./run.sh --ascii``)
there. An invalid value fails on the same load-time validation path as an invalid
TOML value.
"""

from __future__ import annotations

import os
import random
import sys

from .config import load_default_config
from .loop import run


def _make_rng() -> random.Random:
    """Build the run rng. ``TVS_SEED`` (int) pins it; otherwise system entropy."""
    seed_env = os.environ.get("TVS_SEED")
    if seed_env is not None:
        try:
            return random.Random(int(seed_env))
        except ValueError:
            pass
    return random.Random()


def _glyph_set_override() -> str | None:
    """Return the ``TVS_GLYPH_SET`` launch override (``None`` when unset).

    Read here (not in config.py) so ``os.environ`` stays out of the config
    module, mirroring how ``TVS_SEED`` is read for the rng. The value is validated
    downstream by ``load_default_config`` -> ``load_config``, so an invalid string
    fails on the same path as an invalid TOML ``glyph_set``.
    """
    return os.environ.get("TVS_GLYPH_SET")


def _detect_glyph_fallback(
    stdout_encoding: str | None,
    lang: str | None,
    lc_all: str | None,
    lc_ctype: str | None,
) -> str | None:
    """Return ``"ascii"`` only on a positive non-UTF-8 signal, else ``None``.

    Pure (env values are passed in, not read here) so it is unit-testable without
    touching ``os.environ`` / ``sys``. Deliberately false-positive averse: it
    downgrades the shipped emoji default ONLY when the environment clearly cannot
    encode emoji, and keeps emoji on anything ambiguous.

    Order of evidence:
      * The stdout encoding is the most direct signal of what will actually be
        written -- UTF-8 keeps emoji; a present non-UTF-8 encoding
        (ascii/latin-1/cp1252) forces ascii.
      * With no stdout encoding, fall back to the effective locale (POSIX
        precedence LC_ALL -> LC_CTYPE -> LANG): a UTF-8 locale keeps emoji, a
        C/POSIX locale forces ascii.
      * Anything else is ambiguous -> keep the emoji default (``None``).

    A UTF-8 locale paired with an emoji-incapable font is NOT detectable here; that
    case is covered by the explicit ``TVS_GLYPH_SET=ascii`` / ``run.sh --ascii``
    escape hatch, not this heuristic.
    """
    enc = (stdout_encoding or "").lower()
    if "utf" in enc:
        return None
    if enc:  # present but not UTF-8 -> the terminal will mangle 2-column emoji
        return "ascii"
    locale = (lc_all or lc_ctype or lang or "").lower()
    if "utf" in locale:
        return None
    if locale in ("c", "posix"):
        return "ascii"
    return None


def _resolve_glyph_override(
    explicit: str | None,
    stdout_encoding: str | None,
    lang: str | None,
    lc_all: str | None,
    lc_ctype: str | None,
) -> str | None:
    """Resolve the glyph_set override for ``load_default_config``.

    A non-empty explicit ``TVS_GLYPH_SET`` always wins (an empty value is treated
    as unset, matching ``load_config``'s ``glyph_set_override or ...`` semantics);
    otherwise the narrow non-UTF-8 auto-detect decides. ``None`` means "no
    override" -> the shipped TOML default (emoji) is used.
    """
    if explicit:
        return explicit
    return _detect_glyph_fallback(stdout_encoding, lang, lc_all, lc_ctype)


def main() -> int:
    """Set up the terminal and run the game loop. Returns 0 on clean exit."""
    import blessed

    term = blessed.Terminal()
    override = _resolve_glyph_override(
        _glyph_set_override(),
        getattr(sys.stdout, "encoding", None),
        os.environ.get("LANG"),
        os.environ.get("LC_ALL"),
        os.environ.get("LC_CTYPE"),
    )
    cfg = load_default_config(glyph_set_override=override)
    rng = _make_rng()
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        run(term, cfg, rng)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
