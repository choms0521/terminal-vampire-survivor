"""terminal_vs.rules - pure, immutable game-rule functions.

The rules layer is the pure/immutable side of the ADR-001 (section 6) boundary:
no side effects, no global state, no blessed import. Configuration is injected
read-only. Modules here are stubs until Phase 1 Day 4 (except evolution, which
stays a stub through Phase 1).
"""

from __future__ import annotations
