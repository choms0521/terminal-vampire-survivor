"""Unit tests for the launch-time glyph-set auto-detect (backlog 3.2).

The heuristic lives in ``terminal_vs.__main__`` as two pure functions that take the
relevant env/stdout values as arguments, so they are exercised by passing strings
directly -- no ``os.environ`` monkeypatching, no terminal, fully deterministic.

Design intent under test: emoji is the shipped default; the fallback downgrades to
ascii ONLY on a positive non-UTF-8 signal, keeps emoji on anything ambiguous, and a
non-empty explicit ``TVS_GLYPH_SET`` always wins over detection.
"""

from __future__ import annotations

from terminal_vs.__main__ import _detect_glyph_fallback, _resolve_glyph_override


def test_utf8_stdout_keeps_emoji():
    """A UTF-8 stdout encoding is the strongest keep-emoji signal."""
    assert _detect_glyph_fallback("utf-8", None, None, None) is None


def test_ascii_stdout_falls_back():
    """A present non-UTF-8 stdout encoding forces ascii even if the locale is UTF-8
    (stdout is what actually gets written)."""
    assert _detect_glyph_fallback("ascii", "en_US.UTF-8", None, None) == "ascii"


def test_c_locale_falls_back_when_no_stdout_enc():
    """With no stdout encoding, a C/POSIX locale forces ascii."""
    assert _detect_glyph_fallback("", None, None, "C") == "ascii"
    assert _detect_glyph_fallback(None, None, None, "POSIX") == "ascii"


def test_utf8_locale_keeps_emoji_without_stdout_enc():
    """With no stdout encoding, a UTF-8 locale keeps emoji."""
    assert _detect_glyph_fallback("", "en_US.UTF-8", None, None) is None


def test_ambiguous_keeps_emoji():
    """No stdout encoding and no locale signal is ambiguous -> keep emoji (no false
    positive that would downgrade a capable terminal)."""
    assert _detect_glyph_fallback("", None, None, None) is None
    # A non-UTF-8, non-C locale (e.g. a bare language tag) is still ambiguous.
    assert _detect_glyph_fallback("", "en_US", None, None) is None


def test_lc_precedence():
    """LC_ALL overrides LANG (POSIX precedence): C wins over a UTF-8 LANG."""
    assert _detect_glyph_fallback("", "en_US.UTF-8", "C", None) == "ascii"
    # LC_CTYPE overrides LANG too.
    assert _detect_glyph_fallback("", "en_US.UTF-8", None, "C") == "ascii"


def test_explicit_env_beats_detection():
    """A non-empty explicit TVS_GLYPH_SET always wins over auto-detect."""
    assert _resolve_glyph_override("emoji", "ascii", None, None, "C") == "emoji"
    assert _resolve_glyph_override("ascii", "utf-8", None, None, None) == "ascii"


def test_empty_explicit_runs_detection():
    """An empty/None explicit value falls through to detection (matches
    load_config's ``glyph_set_override or ...`` empty-is-unset semantics)."""
    assert _resolve_glyph_override("", "utf-8", None, None, None) is None
    assert _resolve_glyph_override(None, "ascii", None, None, None) == "ascii"
