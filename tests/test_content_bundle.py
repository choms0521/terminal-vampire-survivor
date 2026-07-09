"""Tests for the data-only content bundle: the scatter weapon + charger enemy.

Both are pure balance.toml + emoji-map additions (no sim/targeting code), so these
pin that (a) they parse from the SHIPPED config with the intended fields, (b) the
scatter data actually drives the shared nearest+spread fire path to 5 fanned
pellets, and (c) their glyphs map to emoji (width enforced dict-wide elsewhere).
"""

from __future__ import annotations

import random
from math import atan2

from terminal_vs.config import load_default_config
from terminal_vs.render.frame import _EMOJI_GLYPHS
from terminal_vs.rules.weapons import FireContext, ProjectileSpec, tick_weapon


def test_scatter_and_charger_load_from_shipped_config():
    """The new weapon/enemy parse from the shipped balance.toml with their fields;
    charger is a regular (non-boss) enemy so it auto-joins the weighted spawn pool
    and scatter is a normal (non-evolution) weapon so it is draftable."""
    defs = load_default_config().defs

    scatter = defs.weapons["scatter"]
    assert scatter.targeting == "nearest"
    assert scatter.projectile_count == 5
    assert scatter.spread_angle == 55.0
    assert scatter.glyph == "•"
    # Not an evolution result -> eligible as a draftable new weapon.
    assert scatter.name not in {evo.result_weapon for evo in defs.evolutions}

    charger = defs.enemies["charger"]
    assert charger.boss is False  # -> included in the regular weighted spawn pool
    assert charger.spawn_weight > 0.0
    assert charger.hp == 22.0
    assert charger.move_speed == 4.0
    assert charger.glyph == "C"


def test_scatter_fans_five_pellets_from_shipped_data():
    """The shipped scatter fires projectile_count pellets fanned across its spread
    (data reaches behavior via the same nearest+spread path as dagger_evolved)."""
    defs = load_default_config().defs
    ctx = FireContext(
        player_pos=(0.0, 0.0),
        player_facing=(1.0, 0.0),
        enemy_positions=((0, 3.0, 0.0),),  # nearest, straight along +X
        weapon_def=defs.weapons["scatter"],
        attack_speed_mult=1.0,
        dt=1.0,
        aspect_x=2.0,
    )
    result = tick_weapon(cooldown_remaining=0.0, ctx=ctx, rng=random.Random(0))

    assert result.fired is True
    assert len(result.projectiles) == 5  # projectile_count pellets
    assert all(isinstance(p, ProjectileSpec) for p in result.projectiles)
    # Fanned across the cone, not stacked on one line: 5 distinct heading angles.
    angles = {round(atan2(p.vy, p.vx), 6) for p in result.projectiles}
    assert len(angles) == 5


def test_content_bundle_glyphs_map_to_emoji():
    """The scatter pellet and charger glyphs map to their emoji (width is enforced
    dict-wide by test_all_emoji_glyphs_are_width_two)."""
    assert _EMOJI_GLYPHS["•"] == "🟠"
    assert _EMOJI_GLYPHS["C"] == "🐺"
