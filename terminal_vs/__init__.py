"""terminal_vs - a terminal (TUI) Vampire-Survivors-style bullet-heaven game.

Package layout (master plan section 5.1):

  * config.py  - load/validate/freeze configuration (real).
  * world.py   - world<->cell mapping, aspect correction, camera (real).
  * loop.py    - fixed-timestep game loop (stub until Phase 1 Day 5).
  * sim/       - mutable simulation state and tick pipeline (stubs until Day 3).
  * rules/     - pure, immutable game-rule functions (stubs until Day 4).
  * render/    - blessed-backed rendering and HUD (stubs until Day 5).
  * content/   - content definitions (stub).
"""

from __future__ import annotations

__all__ = ["config", "world"]
