"""terminal_vs.sim - mutable simulation state and tick pipeline.

The sim layer is the mutable side of the ADR-001 (section 6) immutability
boundary: entity buffers are mutated in place inside the tick step for
throughput. Mutable state must not leak outside this package. Modules here are
stubs until Phase 1 Day 3.
"""

from __future__ import annotations
