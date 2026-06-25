#!/usr/bin/env python3
"""selftest.py - headless self-test entry (exit-0 contract).

Runs the full pytest suite with the rules + config coverage gate and propagates
pytest's return code as the process exit code: a passing run (with coverage at
or above the threshold) exits 0, any test failure or coverage shortfall exits
non-zero. Side-effect free -- it opens no terminal and emits no escape
sequences, only pytest's own report -- so it is a clean CI / pre-commit gate.

Coverage scope (Phase 3 plan section 3.2): the 80% gate applies to
``terminal_vs.rules`` and ``terminal_vs.config``, the pure and deterministic
layers where line coverage is meaningful. The blessed render I/O and the
interactive loop are deliberately excluded from headless coverage measurement
(they are verified by behavior tests and the qa-tester tmux session instead).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def main() -> int:
    """Run the full suite with the coverage gate; return pytest's exit code."""
    # Resolve the tests directory relative to THIS file, not the current working
    # directory, so the self-test works when invoked from anywhere (CI wrappers,
    # tooling, a different cwd) -- not only from the repo root. The --cov targets
    # are import names, already cwd-independent.
    tests_dir = str(Path(__file__).resolve().parent / "tests")
    return int(
        pytest.main(
            [
                tests_dir,
                "--cov=terminal_vs.rules",
                "--cov=terminal_vs.config",
                "--cov-fail-under=80",
                "-q",
            ]
        )
    )


if __name__ == "__main__":
    sys.exit(main())
