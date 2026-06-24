"""terminal_vs - a terminal (TUI) Vampire-Survivors-style bullet-heaven game.

Package layout (master plan section 5.1):

  * config.py  - load/validate/freeze configuration (real).
  * world.py   - world<->cell mapping, aspect correction, camera (real).
  * loop.py    - fixed-timestep game loop (real).
  * sim/       - mutable simulation state and tick pipeline (real).
  * rules/     - pure, immutable game-rule functions (real; evolution is a
                 Phase 2 stub).
  * render/    - blessed-backed rendering and HUD (real).
  * content/   - content definitions (stub; populated in later phases).
"""

from __future__ import annotations

__all__ = ["config", "world"]
