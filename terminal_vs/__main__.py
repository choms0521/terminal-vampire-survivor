"""terminal_vs.__main__ - package entry point (``python -m terminal_vs``).

Phase 1 Day 1 stub. The real entry (terminal setup + loop.run) lands in Day 5.
Importing this module must be side-effect free, so the only runtime action is
guarded under ``if __name__ == "__main__"`` -- the import smoke test imports this
module and must not start a terminal session.
"""

from __future__ import annotations


def main() -> int:
    """Stub entry. Returns 0; the real loop wiring lands in Phase 1 Day 5."""
    print("terminal_vs: entry stub (Phase 1 Day 1). Game loop lands in Day 5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
