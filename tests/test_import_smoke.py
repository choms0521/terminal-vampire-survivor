"""Import smoke test: every module imports without side effects (Phase 3 Day 1).

Importing any module -- including the blessed-dependent render modules and the
package entry point -- must NOT open a terminal or enter the game loop. Terminal
setup and loop entry live behind ``__main__.main()`` and the ``__name__`` guard,
so a bare import is inert. This test locks that invariant: it imports the whole
package surface (the import itself is the assertion -- a side effect that opened
a terminal or blocked on the loop would hang or raise here) and confirms the
entry point is a function that is NOT executed on import.

This is the headless counterpart to the acceptance command
``python -c "import terminal_vs.__main__, ..."`` which additionally asserts zero
escape sequences are emitted to stdout.
"""

from __future__ import annotations

import importlib

import pytest

# Every importable module in the package. A newly added module belongs here so
# the smoke test keeps covering the whole import surface.
MODULES = [
    "terminal_vs",
    "terminal_vs.__main__",
    "terminal_vs.config",
    "terminal_vs.content",
    "terminal_vs.loop",
    "terminal_vs.world",
    "terminal_vs.render",
    "terminal_vs.render.frame",
    "terminal_vs.render.hud",
    "terminal_vs.sim",
    "terminal_vs.sim.state",
    "terminal_vs.sim.step",
    "terminal_vs.sim.spawn",
    "terminal_vs.sim.spatial",
    "terminal_vs.rules",
    "terminal_vs.rules.defs",
    "terminal_vs.rules.weapons",
    "terminal_vs.rules.damage",
    "terminal_vs.rules.evolution",
    "terminal_vs.rules.leveling",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_module_imports_without_side_effects(module_name):
    """Importing the module neither raises nor opens a terminal / enters a loop."""
    importlib.import_module(module_name)


def test_entry_point_is_guarded():
    """``__main__`` exposes ``main()`` but does not run it on import.

    The blessed terminal is constructed inside ``main()`` (behind the
    ``if __name__ == "__main__"`` guard), so importing the module leaves the loop
    un-entered and no terminal open. Importing here and finding ``main`` callable
    -- without the process blocking -- is the proof.
    """
    import terminal_vs.__main__ as entry

    assert callable(entry.main)
