"""Tests for the balance side of config: load -> BalanceDefs, fallback, ranges.

These cover the Phase 2 balance schema (weapons / passives / enemies / evolution
/ director / leveling / pickup) loaded into the immutable ``cfg.defs``. Uses
tmp_path-written TOML so the repo's real config is never mutated.
"""

from __future__ import annotations

import textwrap

import pytest

from terminal_vs.config import Config, load_config
from terminal_vs.rules.defs import BalanceDefs, WeaponDef

VALID_TUNING = """\
    sim_tps      = 25
    viewport_w   = 80
    viewport_h   = 24
    entity_cap   = 150
    render_mode  = "full"
    poll_timeout = 0.01
    max_catchup  = 4
    aspect_x     = 2
"""

VALID_BALANCE = """\
    [leveling]
    draft_choices   = 3
    xp_curve_base   = 6.0
    xp_curve_growth = 1.4

    [weapons.dagger]
    max_level        = 8
    cooldown         = 1.2
    damage           = 6.0
    projectile_count = 1
    projectile_speed = 14.0
    projectile_ttl   = 1.2
    targeting        = "nearest"

    [weapons.swing]
    max_level        = 8
    cooldown         = 1.0
    damage           = 8.0
    projectile_count = 0
    projectile_speed = 0.0
    projectile_ttl   = 0.0
    targeting        = "forward_arc"
    arc_range        = 5.0
    arc_half_width   = 0.0

    [passives.attack_speed]
    max_level            = 5
    multiplier_per_level = 0.92

    [enemies.walker]
    hp           = 10.0
    move_speed   = 2.5
    spawn_weight = 70.0
    glyph        = "z"
    color        = "red"

    [weapons.dagger_evolved]
    max_level        = 1
    cooldown         = 0.6
    damage           = 10.0
    projectile_count = 3
    projectile_speed = 18.0
    projectile_ttl   = 1.2
    targeting        = "nearest"
    pierce           = 4

    [evolution.dagger_x]
    base             = "dagger"
    requires_passive = "attack_speed"
    base_max_level   = 8
    result_weapon    = "dagger_evolved"

    [director]
    base_spawn_interval = 2.0
    min_spawn_interval  = 0.4
    reinforce_steps = [[0, 1.0, 1], [1, 0.8, 2]]

    [pickup]
    magnet_range = 5.0
"""


def _write(path, text: str) -> str:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


def _load(tmp_path, balance_text: str = VALID_BALANCE) -> Config:
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    balance = _write(tmp_path / "balance.toml", balance_text)
    return load_config(tuning, balance)


def test_valid_load_builds_balance_defs(tmp_path):
    """A valid balance.toml loads into the typed immutable BalanceDefs tables."""
    cfg = _load(tmp_path)
    assert isinstance(cfg.defs, BalanceDefs)
    # Weapons read by name with the declared dials.
    assert isinstance(cfg.defs.weapons["dagger"], WeaponDef)
    assert cfg.defs.weapons["dagger"].cooldown == 1.2
    assert cfg.defs.weapons["dagger"].damage == 6.0
    assert cfg.defs.weapons["dagger"].targeting == "nearest"
    assert cfg.defs.weapons["swing"].targeting == "forward_arc"
    assert cfg.defs.weapons["swing"].arc_range == 5.0
    # Passive / enemy / evolution / director / leveling / pickup.
    assert cfg.defs.passives["attack_speed"].multiplier_per_level == 0.92
    assert cfg.defs.enemies["walker"].hp == 10.0
    assert cfg.defs.enemies["walker"].glyph == "z"
    assert cfg.defs.evolutions[0].base == "dagger"
    assert cfg.defs.evolutions[0].result_weapon == "dagger_evolved"
    assert cfg.defs.director.base_spawn_interval == 2.0
    assert cfg.defs.director.reinforce_steps[1].concurrent == 2
    assert cfg.defs.leveling.draft_choices == 3
    assert cfg.defs.magnet_range == 5.0


def test_load_balance_returns_immutable(tmp_path):
    """The loaded defs and their nested defs are frozen (section 6 boundary)."""
    cfg = _load(tmp_path)
    with pytest.raises(Exception):
        cfg.defs.magnet_range = 1.0  # type: ignore[misc]
    with pytest.raises(Exception):
        cfg.defs.weapons["dagger"].cooldown = 9.9  # type: ignore[misc]
    with pytest.raises(Exception):
        cfg.defs.leveling.draft_choices = 7  # type: ignore[misc]


def test_missing_key_falls_back_to_default(tmp_path):
    """A weapon entry missing keys falls back to code defaults for those keys."""
    # dagger present but only declares cooldown; the rest fall back.
    partial = """\
        [weapons.dagger]
        cooldown = 0.7
        targeting = "nearest"
    """
    cfg = _load(tmp_path, partial)
    # Present key honored.
    assert cfg.defs.weapons["dagger"].cooldown == 0.7
    # Missing keys fall back to positive code defaults (valid defs built).
    assert cfg.defs.weapons["dagger"].damage > 0
    assert cfg.defs.weapons["dagger"].projectile_speed > 0
    assert cfg.defs.weapons["dagger"].max_level > 0
    # Whole missing sections fall back to the default content set.
    assert cfg.defs.passives  # at least one default passive
    assert cfg.defs.enemies   # at least one default enemy
    assert cfg.defs.leveling.draft_choices > 0
    assert cfg.defs.magnet_range > 0


def test_missing_files_use_all_defaults(tmp_path):
    """Absent config files do not error -- all balance defaults are used."""
    cfg = load_config(tmp_path / "absent_tuning.toml", tmp_path / "absent_balance.toml")
    assert isinstance(cfg, Config)
    assert cfg.defs.weapons  # default weapon content present
    assert cfg.defs.magnet_range > 0


def test_out_of_range_raises(tmp_path):
    """A non-positive balance value raises a ValueError naming the key + file."""
    bad = VALID_BALANCE.replace("cooldown         = 1.2", "cooldown         = -1.0")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "weapons.dagger.cooldown" in msg
    assert "config/balance.toml" in msg


def test_out_of_range_enemy_hp_raises(tmp_path):
    """A non-positive enemy hp raises a ValueError naming the enemy key."""
    bad = VALID_BALANCE.replace("hp           = 10.0", "hp           = 0")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    assert "enemies.walker.hp" in str(exc.value)


def test_invalid_targeting_raises(tmp_path):
    """A weapon with an unknown targeting strategy raises a clear ValueError."""
    bad = VALID_BALANCE.replace('targeting        = "nearest"', 'targeting        = "spiral"')
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    assert "targeting" in str(exc.value)


def test_dangling_result_weapon_raises(tmp_path):
    """An evolution whose result_weapon is not in [weapons.*] raises ValueError naming the key."""
    bad = VALID_BALANCE.replace('result_weapon    = "dagger_evolved"', 'result_weapon    = "nonexistent_weapon"')
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "result_weapon" in msg
    assert "nonexistent_weapon" in msg
    assert "config/balance.toml" in msg


def test_dangling_base_weapon_raises(tmp_path):
    """An evolution whose base is not in [weapons.*] raises ValueError naming the key."""
    bad = VALID_BALANCE.replace('base             = "dagger"', 'base             = "missing_base"')
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "missing_base" in msg
    assert "config/balance.toml" in msg


def test_dangling_requires_passive_raises(tmp_path):
    """An evolution whose requires_passive is not in [passives.*] raises ValueError."""
    bad = VALID_BALANCE.replace('requires_passive = "attack_speed"', 'requires_passive = "no_such_passive"')
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "no_such_passive" in msg
    assert "config/balance.toml" in msg


def test_arc_half_width_out_of_range_raises(tmp_path):
    """A forward_arc weapon with arc_half_width outside [-1, 1] raises ValueError naming the key."""
    bad = VALID_BALANCE.replace("arc_half_width   = 0.0", "arc_half_width   = 1.5")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "arc_half_width" in msg
    assert "config/balance.toml" in msg
