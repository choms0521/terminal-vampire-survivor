"""terminal_vs.rules.damage - damage and knockback math (Day 4).

Pure functions, no side effects, no blessed, no global state. ``apply_hit`` and
``is_dead`` operate on plain hp floats; ``knockback`` operates on (x, y) world
tuples and returns a NEW tuple displaced away from the source. The sim layer
applies these results in place; nothing here mutates its inputs.
"""

from __future__ import annotations

from math import hypot


def apply_hit(hp: float, dmg: float) -> float:
    """Return the hp remaining after taking ``dmg`` damage (clamped at 0).

    Pure: returns a new value. Damage is clamped so hp never goes negative,
    which keeps downstream hp comparisons and HUD bars well-behaved.
    """
    return max(0.0, hp - dmg)


def is_dead(hp: float) -> bool:
    """True if hp has reached zero (or below)."""
    return hp <= 0.0


def knockback(
    pos: tuple[float, float],
    source_pos: tuple[float, float],
    force: float,
) -> tuple[float, float]:
    """Return ``pos`` displaced AWAY from ``source_pos`` by ``force`` units.

    Pure: returns a new (x, y) tuple, never mutates the inputs. The displacement
    direction is the unit vector from ``source_pos`` to ``pos`` (i.e. pushing the
    target further from the source), and its magnitude equals ``force`` exactly.

    Degenerate case: if ``pos == source_pos`` the direction is undefined, so the
    position is returned unchanged (zero displacement) -- a deterministic default
    that avoids a divide-by-zero on normalization.

    This is plain Euclidean (world) geometry: knockback is a physical push, not
    an on-screen-distance effect, so it does NOT use the aspect correction.
    """
    px, py = pos
    sx, sy = source_pos
    dx = px - sx
    dy = py - sy
    dist = hypot(dx, dy)
    if dist == 0.0:
        return (px, py)
    scale = force / dist
    return (px + dx * scale, py + dy * scale)
