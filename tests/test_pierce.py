"""Tests for pierce-aware projectile collision semantics (Phase 2).

A pierce=N projectile must:
  (a) damage up to N+1 DISTINCT enemies (one initial hit + N pierce-throughs),
  (b) never apply more than one hit to the same enemy, even across consecutive
      overlapping ticks where the projectile lingers.

These tests drive the scenario at the sim layer (no blessed, no render) using
manually placed enemies so the geometry is deterministic without relying on the
director spawn.
"""

from __future__ import annotations

import random

from terminal_vs.sim.state import Enemy, Intent, Projectile, SimState, new_run
from terminal_vs.sim.step import step, _resolve_collisions

from .conftest import make_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_with_player() -> tuple[SimState, object]:
    """Return a fresh (state, cfg) pair with the player at the origin."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    return state, cfg


def _add_enemy(state: SimState, x: float, y: float, hp: float = 100.0) -> Enemy:
    """Add a walker-kind enemy at (x, y) directly into the state buffer."""
    enemy = Enemy(
        entity_id=state.alloc_id(),
        x=x,
        y=y,
        hp=hp,
        kind="walker",
        glyph="z",
        color="red",
    )
    state.enemies.append(enemy)
    return enemy


def _add_projectile(
    state: SimState,
    x: float,
    y: float,
    pierce: int,
    damage: float = 10.0,
    ttl: float = 5.0,
) -> Projectile:
    """Add a stationary projectile at (x, y) with the given pierce value."""
    proj = Projectile(
        entity_id=state.alloc_id(),
        x=x,
        y=y,
        vx=0.0,
        vy=0.0,
        damage=damage,
        ttl=ttl,
        pierce=pierce,
    )
    state.projectiles.append(proj)
    return proj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pierce_hits_distinct_enemies():
    """A pierce=2 projectile damages at most 3 DISTINCT enemies, not the same one.

    Three enemies placed at the projectile's location (radius 0 -- guaranteed
    in-range). With pierce=2 each collision call selects the nearest un-hit enemy
    (sorted ids break ties); after 3 calls all three enemies should have taken
    damage and the projectile should be consumed (pierce exhausted + final hit
    sets ttl=0).
    """
    state, cfg = _state_with_player()
    e1 = _add_enemy(state, 0.0, 0.0)  # all three at origin
    e2 = _add_enemy(state, 0.0, 0.0)
    e3 = _add_enemy(state, 0.0, 0.0)
    proj = _add_projectile(state, 0.0, 0.0, pierce=2, damage=10.0)
    initial_hp = 100.0

    # Three collision passes: each should hit a fresh enemy.
    _resolve_collisions(state, cfg)
    _resolve_collisions(state, cfg)
    _resolve_collisions(state, cfg)

    damaged = [e for e in [e1, e2, e3] if e.hp < initial_hp]
    assert len(damaged) == 3, (
        f"Expected 3 distinct enemies hit, got {len(damaged)}: "
        f"hp=({e1.hp}, {e2.hp}, {e3.hp})"
    )
    # Each enemy should have taken exactly one hit (10 damage).
    for e in [e1, e2, e3]:
        assert e.hp == initial_hp - 10.0, f"Enemy {e.id} hp={e.hp} (expected {initial_hp - 10.0})"
    # After 3 hits on pierce=2, the projectile is consumed.
    assert proj.ttl <= 0.0, f"Projectile should be consumed after pierce exhausted, ttl={proj.ttl}"


def test_pierce_no_rehit_same_enemy():
    """A pierce=4 projectile never re-hits the same enemy across multiple ticks.

    One enemy placed at the projectile position. Even after many collision passes
    the enemy takes damage exactly once; the projectile keeps its pierce but never
    applies a second hit to the same enemy (because its id is in hit_ids).
    """
    state, cfg = _state_with_player()
    enemy = _add_enemy(state, 0.0, 0.0, hp=100.0)
    proj = _add_projectile(state, 0.0, 0.0, pierce=4, damage=10.0)

    # Run 10 collision passes simulating 10 overlapping ticks.
    for _ in range(10):
        _resolve_collisions(state, cfg)

    assert enemy.hp == 90.0, (
        f"Enemy should have taken damage exactly once (hp=90), got hp={enemy.hp}"
    )
    # Projectile still alive (no fresh enemy to exhaust pierce on).
    assert proj.ttl > 0.0, "Projectile should still be alive (only one enemy to hit)"
    # Pierce was decremented once (for the first hit), then no further changes.
    assert proj.pierce == 3, f"Expected pierce=3 after one hit, got pierce={proj.pierce}"


def test_pierce_zero_consumed_on_first_hit():
    """A pierce=0 projectile is consumed on the very first hit (classic behavior)."""
    state, cfg = _state_with_player()
    _add_enemy(state, 0.0, 0.0, hp=100.0)
    proj = _add_projectile(state, 0.0, 0.0, pierce=0, damage=10.0)

    _resolve_collisions(state, cfg)

    assert proj.ttl <= 0.0, "pierce=0 projectile must be consumed on first hit"


def test_pierce_hit_ids_independent_per_projectile():
    """Two projectiles at the same position each track their own hit_ids.

    Both start with pierce=0 and one enemy. Each projectile must be consumed
    independently and the enemy takes two hits total (one from each projectile).
    """
    state, cfg = _state_with_player()
    enemy = _add_enemy(state, 0.0, 0.0, hp=100.0)
    proj_a = _add_projectile(state, 0.0, 0.0, pierce=0, damage=10.0)
    proj_b = _add_projectile(state, 0.0, 0.0, pierce=0, damage=10.0)

    # Single collision pass: both projectiles resolve independently.
    _resolve_collisions(state, cfg)

    assert proj_a.ttl <= 0.0, "proj_a should be consumed"
    assert proj_b.ttl <= 0.0, "proj_b should be consumed"
    # Each projectile dealt 10 damage for a total of 20.
    assert enemy.hp == 80.0, f"Expected enemy hp=80.0, got {enemy.hp}"
    # Confirm hit_ids are separate sets (not shared).
    assert proj_a.hit_ids is not proj_b.hit_ids, "hit_ids must be distinct sets per projectile"


def test_pierce_determinism_across_two_runs():
    """Two same-seed runs with pierce projectiles produce identical results.

    Uses the full step pipeline (not just _resolve_collisions) with a fixed rng
    seed to confirm the hit_ids set does not break the determinism guarantee.
    hit_ids membership tests consume no rng, so the rng stream is unaffected.
    """
    cfg = make_config()

    def _run(seed: int) -> tuple:
        rng = random.Random(seed)
        state = new_run(cfg, rng)
        for _ in range(200):
            step(state, Intent(0, 0), cfg, rng)
        return (
            tuple((e.id, round(e.hp, 9)) for e in state.enemies),
            round(state.build.xp, 9),
            state.build.level,
        )

    assert _run(42) == _run(42), "Same-seed runs must produce identical results with pierce"
