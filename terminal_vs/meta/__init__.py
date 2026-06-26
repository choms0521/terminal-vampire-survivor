"""terminal_vs.meta - cross-run meta progression (gold, permanent upgrades, unlocks).

Phase 4A. This package is blessed-free and sim-free: it defines the immutable
``MetaState`` (the saved progression), pure save/load/validation, and the pure
post-run ``accrue_meta``. A run is fully determined by (seed + the injected,
read-only MetaState); meta is never mutated during a sim tick (ADR-001).
"""

from .schema import MetaSaveError, MetaState

__all__ = ["MetaState", "MetaSaveError"]
