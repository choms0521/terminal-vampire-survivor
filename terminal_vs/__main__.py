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
"""

from __future__ import annotations

import os
import random

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


def main() -> int:
    """Set up the terminal and run the game loop. Returns 0 on clean exit."""
    import blessed

    term = blessed.Terminal()
    cfg = load_default_config()
    rng = _make_rng()
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        run(term, cfg, rng)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
