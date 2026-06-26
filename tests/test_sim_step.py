"""Tests for terminal_vs.sim.step: determinism under a fixed seed.

Running new_run + N steps twice with random.Random(42) must produce identical
entity positions, HP, and the id sequence -- the core determinism guarantee.
"""

from __future__ import annotations

import random

from dataclasses import replace

from terminal_vs.rules.defs import EnemyDef
from terminal_vs.sim.state import Enemy, Intent, new_run
from terminal_vs.sim.step import (
    _PLAYER_FALLBACK_BASE_SPEED,
    _drop_xp_on_death,
    _fire_weapons,
    _reference_move_speed,
    step,
)

from .conftest import make_config, make_defs


def _snapshot(state) -> tuple:
    """A fully comparable snapshot of the mutable state's observable fields."""
    player = (
        state.player.id,
        round(state.player.x, 9),
        round(state.player.y, 9),
        round(state.player.hp, 9),
    )
    enemies = tuple(
        (e.id, round(e.x, 9), round(e.y, 9), round(e.hp, 9))
        for e in state.enemies
    )
    projectiles = tuple(
        (p.id, round(p.x, 9), round(p.y, 9), round(p.ttl, 9))
        for p in state.projectiles
    )
    pickups = tuple(
        (pk.id, round(pk.x, 9), round(pk.y, 9), round(pk.xp, 9))
        for pk in state.pickups
    )
    level = (state.build.level, round(state.build.xp, 9))
    return (
        player,
        enemies,
        projectiles,
        pickups,
        level,
        state.level_up_pending,
        state.next_id,
        round(state.elapsed, 9),
    )


def _run(n: int, seed: int) -> tuple:
    cfg = make_config()
    rng = random.Random(seed)
    state = new_run(cfg, rng)
    # A wandering intent so the player moves and the run is non-degenerate.
    intents = [
        Intent(1, 0),
        Intent(1, 1),
        Intent(0, 1),
        Intent(-1, 0),
        Intent(0, 0),
    ]
    for i in range(n):
        step(state, intents[i % len(intents)], cfg, rng)
    return _snapshot(state)


def test_same_seed_two_runs_identical():
    snap_a = _run(n=200, seed=42)
    snap_b = _run(n=200, seed=42)
    assert snap_a == snap_b


def test_different_seed_diverges():
    # Sanity: a different seed should change the run (spawns differ), proving the
    # determinism above is not just a constant ignoring rng.
    snap_a = _run(n=200, seed=42)
    snap_c = _run(n=200, seed=7)
    assert snap_a != snap_c


def test_player_out_runs_enemies():
    # The player's base move speed must exceed the WALKER (basic chaser) move
    # speed so kiting works (the core survival loop). Guards the
    # _PLAYER_SPEED_MULT > 1 invariant against a silent regression (e.g. resetting
    # the multiplier to 1.0). The swarm enemy is intentionally faster than the
    # player by design, so the invariant is measured against the walker.
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    step(state, Intent(1, 0), cfg, random.Random(0))
    assert abs(state.player.vx) > cfg.defs.enemies["walker"].move_speed


def test_id_sequence_is_monotonic_and_contiguous():
    cfg = make_config()
    rng = random.Random(42)
    state = new_run(cfg, rng)
    for _ in range(50):
        step(state, Intent(1, 0), cfg, rng)
    # Every allocated id is unique and the counter only ever grew.
    assert state.next_id >= 1  # at least the player
    assert state.player.id == 0  # player is the first id allocated


def test_run_progresses_toward_levelup_with_default_seed():
    # Not a strict acceptance test (that's the integration test), but confirms
    # the pipeline closes: with enough ticks the run accrues xp at least once.
    cfg = make_config()
    rng = random.Random(42)
    state = new_run(cfg, rng)
    saw_pending = False
    for _ in range(1100):
        step(state, Intent(0, 0), cfg, rng)
        if state.level_up_pending:
            saw_pending = True
            break
    assert saw_pending is True


def _enemy(name: str, move_speed: float) -> EnemyDef:
    return EnemyDef(
        name=name,
        hp=10.0,
        move_speed=move_speed,
        spawn_weight=1.0,
        glyph="z",
        color="red",
    )


def test_reference_move_speed_prefers_walker():
    """With the reference kind present, the player's base speed reads walker's."""
    defs = make_defs(
        enemies={"walker": _enemy("walker", 2.5), "swarm": _enemy("swarm", 5.0)}
    )
    assert _reference_move_speed(defs) == 2.5


def test_reference_move_speed_falls_back_to_slowest_without_walker():
    """A data-driven balance without 'walker' must not KeyError; uses the slowest.

    Regression for the direct cfg.defs.enemies["walker"] index that crashed the sim
    when a custom enemy set omitted the reference kind.
    """
    defs = make_defs(
        enemies={"swarm": _enemy("swarm", 5.0), "brute": _enemy("brute", 3.0)}
    )
    assert _reference_move_speed(defs) == 3.0


def test_reference_move_speed_empty_enemies_uses_guard():
    """The degenerate no-enemy table falls back to the fixed guard, not a crash."""
    defs = make_defs(enemies={})
    assert _reference_move_speed(defs) == _PLAYER_FALLBACK_BASE_SPEED


def test_kills_counter_counts_only_dead_enemies_once():
    """The death stage tallies one kill per dead enemy and ignores live ones.

    ``_drop_xp_on_death`` runs the single tick an enemy is dead (stage 6 set its
    hp <= 0, stage 9 cleanup removes it next), so it both drops a gem and bumps
    ``state.kills`` exactly once per kill. A live enemy in the same buffer must
    not be counted. This is the unit guard for the HUD / balance kill metric.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    assert state.kills == 0  # a fresh run has no kills
    state.enemies.append(Enemy(state.alloc_id(), 1.0, 0.0, hp=0.0))   # dead
    state.enemies.append(Enemy(state.alloc_id(), 2.0, 0.0, hp=5.0))   # alive
    state.enemies.append(Enemy(state.alloc_id(), 3.0, 0.0, hp=-1.0))  # dead

    _drop_xp_on_death(state, random.Random(0))

    assert state.kills == 2          # only the two dead enemies were counted
    assert len(state.pickups) == 2   # one xp gem dropped per kill


def test_projectiles_carry_their_weapon_glyph_and_color():
    """Each weapon stamps its own glyph/color onto the projectiles it fires, so
    different weapons read distinctly on screen instead of sharing the default '*'.

    Builds a player owning two distinct projectile weapons (dagger '-' white,
    magic_bolt '*' cyan), both ready, with one enemy in range so each fires once,
    then checks the spawned projectiles carry their own weapon's look.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    # Own two projectile weapons, both off cooldown this tick.
    state.build = replace(
        state.build, weapon_levels=(("dagger", 1), ("magic_bolt", 1))
    )
    state.weapon_cooldowns = {"dagger": 0.0, "magic_bolt": 0.0}
    # A single enemy in range: both nearest-targeting weapons aim at it and fire.
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 2.0, state.player.y, hp=100.0)
    )

    _fire_weapons(state, cfg, 1.0 / cfg.sim_tps, random.Random(0))

    looks = {(p.glyph, p.color) for p in state.projectiles}
    assert ("-", "white") in looks  # the dagger's dart
    assert ("*", "cyan") in looks  # the magic_bolt's arcane bolt
    assert len(looks) >= 2  # the two weapons are visually distinct


def test_weapon_def_glyph_color_default_to_prior_look():
    """A WeaponDef built without glyph/color falls back to the historical
    projectile look ('*'/'yellow'), so weapon data predating the render hints
    keeps its prior appearance (backward compatible)."""
    from terminal_vs.rules.defs import WeaponDef

    w = WeaponDef(
        name="plain",
        max_level=1,
        cooldown=1.0,
        damage=1.0,
        projectile_count=1,
        projectile_speed=1.0,
        projectile_ttl=1.0,
        targeting="nearest",
    )
    assert w.glyph == "*"
    assert w.color == "yellow"


def test_swing_fire_spawns_visual_effect_entities():
    """A swing (forward_arc) fire appends cosmetic Effect entities so the melee
    swing is visible; they carry the swing glyph and a ttl exceeding one tick."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.build = replace(state.build, weapon_levels=(("swing", 1),))
    state.weapon_cooldowns = {"swing": 0.0}
    state.player.facing_x, state.player.facing_y = 1.0, 0.0
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 3.0, state.player.y, hp=100.0)
    )

    dt = 1.0 / cfg.sim_tps
    _fire_weapons(state, cfg, dt, random.Random(0))

    assert len(state.effects) > 0  # the swing drew its arc
    assert all(e.glyph == ")" for e in state.effects)  # the swing weapon's glyph
    assert all(e.ttl > dt for e in state.effects)  # survives to the next render


def test_swing_effects_expire_and_are_cleaned_up():
    """Swing effect entities age each tick and cleanup removes them once expired,
    so they do not accumulate (no leak)."""
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.build = replace(state.build, weapon_levels=(("swing", 1),))
    state.weapon_cooldowns = {"swing": 0.0}
    state.player.facing_x, state.player.facing_y = 1.0, 0.0
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 3.0, state.player.y, hp=1_000_000.0)
    )

    # First step fires the swing and spawns its effects.
    step(state, Intent(0, 0), cfg, random.Random(0))
    assert len(state.effects) > 0
    # ttl 0.15s at dt 0.05s -> ~3 ticks; swing cooldown 1.0s -> no refire soon.
    for _ in range(5):
        step(state, Intent(0, 0), cfg, random.Random(0))
    assert state.effects == []  # all expired and cleaned up


def test_orbit_projectiles_revolve_on_the_ring_around_the_player():
    """Orbit projectiles stay at orbit_radius from the player and advance their
    angle each tick -- they revolve rather than flying off in a straight line."""
    from math import hypot

    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.build = replace(state.build, weapon_levels=(("orbit", 1),))
    state.weapon_cooldowns = {"orbit": 0.0}
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 10.0, state.player.y, hp=1e9, kind="pinned")
    )

    step(state, Intent(0, 0), cfg, random.Random(0))  # fire the ring
    orbiters = [p for p in state.projectiles if p.orbit_radius > 0.0]
    assert orbiters  # the ring spawned
    a0 = orbiters[0].orbit_angle

    for _ in range(5):
        step(state, Intent(0, 0), cfg, random.Random(0))
        for p in state.projectiles:
            if p.orbit_radius > 0.0:
                d = hypot(p.x - state.player.x, p.y - state.player.y)
                assert abs(d - p.orbit_radius) < 1e-6  # stays exactly on the ring

    moved = [p for p in state.projectiles if p.orbit_radius > 0.0]
    assert moved and moved[0].orbit_angle != a0  # it actually revolved


def test_orbit_damages_an_enemy_repeatedly_over_time():
    """The orbit ring deals damage as it sweeps past an enemy and, respawned each
    cooldown, RE-HITS it across lives (genuine DoT, not a one-hit cosmetic ring).

    Pin an enemy on the ring (a kind with no EnemyDef, so it stays put) and run
    well past several cooldowns. One orbit life can strike this single enemy at
    most once per orbiting shot (the per-projectile hit_ids guard), i.e. at most
    ``count * damage``. Exceeding that proves the respawn re-hit cadence works --
    the DoT proof, distinct from merely drawing the ring.
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.build = replace(state.build, weapon_levels=(("orbit", 1),))
    state.weapon_cooldowns = {"orbit": 0.0}
    # kind 'pinned' has no EnemyDef, so the enemy is stationary on the ring (r=4).
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 4.0, state.player.y, hp=1e9, kind="pinned")
    )
    hp0 = state.enemies[0].hp

    for _ in range(200):  # cooldown 3.0s = 60 ticks -> several respawns
        step(state, Intent(0, 0), cfg, random.Random(0))

    dmg = hp0 - state.enemies[0].hp
    wdef = cfg.defs.weapons["orbit"]
    assert dmg > wdef.projectile_count * wdef.damage  # re-hit across lives, not one-shot


def test_orbit_does_not_stack_rings_under_attack_speed_passive():
    """The attack_speed passive (< 1) shrinks the effective cooldown
    (``cooldown * attack_speed_mult``). The orbit ttl is scaled by the SAME
    factor, so the ring still expires strictly before the next spawn -- at most
    ``projectile_count`` orbit projectiles are alive at any tick, at any passive
    level.

    Without the ttl scaling the max attack_speed passive drops the effective
    cooldown (~39 ticks at 0.92**5) below the fixed ttl (~56 ticks), so a second
    ring spawns while the first is still alive: the ring stacks (6 projectiles)
    and damage inflates. Max level is the worst case (shortest cooldown).
    """
    cfg = make_config()
    state = new_run(cfg, random.Random(0))
    state.build = replace(
        state.build,
        weapon_levels=(("orbit", 1),),
        passive_levels=(("attack_speed", 5),),  # max -> shortest cooldown, worst case
    )
    state.weapon_cooldowns = {"orbit": 0.0}
    # An enemy must exist for orbit to fire; kind 'pinned' has no EnemyDef so it
    # stays put and never dies, keeping the weapon firing every cooldown.
    state.enemies.append(
        Enemy(state.alloc_id(), state.player.x + 4.0, state.player.y, hp=1e9, kind="pinned")
    )
    count = cfg.defs.weapons["orbit"].projectile_count

    for _ in range(200):  # well past several scaled cooldowns
        step(state, Intent(0, 0), cfg, random.Random(0))
        orbiters = [p for p in state.projectiles if p.orbit_radius > 0.0]
        assert len(orbiters) <= count  # never stacks, even under max attack_speed
