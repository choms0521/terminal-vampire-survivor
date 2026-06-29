"""Phase 4B: data-driven content additions LOAD and become REACHABLE in-game.

These prove the Phase 4 plan's data-driven-design exit criterion: new content
added by editing ONLY ``config/balance.toml`` (no ``terminal_vs/*.py`` change,
AC-3) is not merely parsed into ``BalanceDefs`` but actually reaches the player.
"Loadable" is a weaker claim than "reachable" -- a test that only asserts
``cfg.defs.enemies["brute"]`` exists would pass while the enemy never spawns. So
each test drives the real enumeration point:

  * a new enemy enters the director's weighted spawn table (``director_params``),
  * a new evolution becomes eligible and its result weapon is obtained by
    evolving (``eligible_evolutions`` / ``apply_evolution``),
  * the evolved weapon stays OUT of the normal new-weapon draft pool
    (``_new_weapon_candidates``), so it is terminal -- reachable only by evolving.

All three read the SHIPPED config via ``load_default_config`` so they verify the
production ``config/balance.toml`` content, not a synthetic test fixture.
"""

from __future__ import annotations

from terminal_vs.config import load_default_config
from terminal_vs.rules.evolution import apply_evolution, eligible_evolutions
from terminal_vs.rules.leveling import (
    KIND_NEW_WEAPON,
    BuildState,
    _new_weapon_candidates,
)
from terminal_vs.sim.spawn import director_params


def test_content_load_new_enemy_brute_is_defined_and_spawnable():
    """The new ``brute`` enemy parses AND enters the director's weighted spawn
    table, so it is actually reachable by the spawner (not just loadable)."""
    cfg = load_default_config()
    assert "brute" in cfg.defs.enemies
    brute = cfg.defs.enemies["brute"]
    assert brute.hp > 0
    assert brute.move_speed > 0
    assert brute.spawn_weight > 0
    # The director enumerates defs.enemies by spawn_weight, so brute appears in the
    # weighted table the weighted pick draws from -- proof it can spawn in a run.
    weights = director_params(0.0, cfg.defs).enemy_weights
    spawnable = {name for name, _ in weights}
    assert "brute" in spawnable


def test_content_load_new_evolution_lance_x_is_eligible_and_evolves():
    """The new ``lance_x`` evolution is eligible for a maxed-lance + move_speed
    build and applying it grants ``lance_evolved`` (removing the base lance)."""
    cfg = load_default_config()
    assert "lance_evolved" in cfg.defs.weapons
    lance_max = cfg.defs.weapons["lance"].max_level
    build = BuildState(
        weapon_levels=(("lance", lance_max),),
        passive_levels=(("move_speed", 1),),
    )

    evos = eligible_evolutions(build, cfg.defs)
    matching = [e for e in evos if e.result_weapon == "lance_evolved"]
    assert matching, "lance_x should be eligible for a maxed-lance + move_speed build"

    evolved = apply_evolution(build, matching[0])
    owned = {name for name, _ in evolved.weapon_levels}
    assert "lance_evolved" in owned
    assert "lance" not in owned  # the base weapon is replaced, not kept


def test_content_load_evolution_weapon_stays_out_of_new_weapon_draft():
    """The evolved weapon is reachable ONLY by evolving: it must never appear as a
    plain 'new weapon' draft card. The data-driven exclusion (any evolution's
    result_weapon) keeps it terminal without a hardcoded name list."""
    cfg = load_default_config()
    fresh = BuildState()  # owns only the starting weapon; no evolution applied yet
    new_cards = _new_weapon_candidates(fresh, cfg.defs)
    draftable = {choice.target for choice, _ in new_cards}

    assert "lance_evolved" not in draftable
    # The base lance, by contrast, IS a normal draftable weapon.
    assert "lance" in draftable
    # Sanity: every card in this pool is a new-weapon card.
    assert all(choice.kind == KIND_NEW_WEAPON for choice, _ in new_cards)
