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


def test_balance_defs_mappings_are_read_only(tmp_path):
    """The weapons/passives/enemies tables are read-only mappings, not bare dicts.

    A frozen dataclass does not deep-freeze mutable fields, so build_defs wraps the
    name-keyed tables in MappingProxyType. Mutating one through cfg.defs must raise
    (the ADR-001 immutability boundary enforced at runtime), while reads still work.
    """
    cfg = _load(tmp_path)
    # Reads still work.
    assert cfg.defs.weapons["dagger"].cooldown == 1.2
    # Writes / deletes / inserts raise.
    with pytest.raises(TypeError):
        cfg.defs.weapons["dagger"] = None  # type: ignore[index,assignment]
    with pytest.raises(TypeError):
        cfg.defs.passives["new"] = None  # type: ignore[index,assignment]
    with pytest.raises(TypeError):
        del cfg.defs.enemies["walker"]  # type: ignore[attr-defined]


def test_missing_starting_weapon_raises(tmp_path):
    """A user-provided [weapons.*] section that omits the starting weapon raises.

    A run begins owning the BuildState default weapon; if the balance file defines
    weapons but not that one, the run would start holding a weapon with no stats.
    Config rejects it at load time, naming the weapon and the file.
    """
    # Rename the dagger section so a weapons section exists but 'dagger' is absent.
    bad = VALID_BALANCE.replace("[weapons.dagger]", "[weapons.knife]")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "dagger" in msg
    assert "config/balance.toml" in msg


def test_orbit_ttl_not_less_than_cooldown_raises(tmp_path):
    """An orbit weapon needs projectile_ttl < cooldown so its ring respawns each
    cooldown (which restores the per-life hit_ids re-hit cadence). A ttl >= cooldown
    is rejected at load, matching how this config enforces other load-bearing
    balance couplings."""
    orbit_block = (
        "\n[weapons.orbit]\n"
        "max_level = 8\n"
        "cooldown = 2.0\n"
        "damage = 6.0\n"
        "projectile_count = 3\n"
        "projectile_speed = 0.0\n"
        "projectile_ttl = 2.5\n"  # >= cooldown -> must be rejected
        'targeting = "orbit"\n'
        "orbit_radius = 4.0\n"
        "orbit_angular_speed = 3.0\n"
    )
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, VALID_BALANCE + orbit_block)
    msg = str(exc.value)
    assert "projectile_ttl" in msg
    assert "cooldown" in msg


_UPGRADE_BLOCK = (
    "\n[upgrades.swift]\n"
    "max_level = 5\n"
    'stat = "move_speed"\n'
    "multiplier_per_level = 1.08\n"
    "cost_base = 50\n"
    "cost_growth = 1.6\n"
)


def test_upgrades_parse_into_meta_upgrade_defs(tmp_path):
    """A valid [upgrades.*] section loads into MetaUpgradeDef entries on defs."""
    cfg = _load(tmp_path, VALID_BALANCE + _UPGRADE_BLOCK)
    up = cfg.defs.upgrades["swift"]
    assert up.stat == "move_speed"
    assert up.max_level == 5
    assert up.multiplier_per_level == 1.08
    assert up.cost_base == 50
    assert up.cost_growth == 1.6


def test_no_upgrades_section_yields_empty_table(tmp_path):
    """Permanent upgrades are optional content -- absent section -> empty table
    (no default-name injection, unlike weapons/passives)."""
    cfg = _load(tmp_path)  # VALID_BALANCE has no [upgrades.*]
    assert dict(cfg.defs.upgrades) == {}


def test_upgrade_invalid_stat_raises(tmp_path):
    """An upgrade targeting a stat effective_stats does not know is rejected at load."""
    bad = _UPGRADE_BLOCK.replace('stat = "move_speed"', 'stat = "luck"')
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, VALID_BALANCE + bad)
    msg = str(exc.value)
    assert "stat" in msg
    assert "config/balance.toml" in msg


def test_upgrade_cost_growth_below_one_raises(tmp_path):
    """cost_growth < 1 would make higher upgrade levels cheaper; rejected at load."""
    bad = _UPGRADE_BLOCK.replace("cost_growth = 1.6", "cost_growth = 0.5")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, VALID_BALANCE + bad)
    assert "cost_growth" in str(exc.value)


def test_meta_gold_per_kill_non_positive_raises(tmp_path):
    """meta.gold_per_kill must be > 0 -- a 0 / negative reward is a balance error."""
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, VALID_BALANCE + "\n[meta]\ngold_per_kill = 0\n")
    assert "gold_per_kill" in str(exc.value)


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


@pytest.mark.parametrize("growth", ["0.9", "1.0"])
def test_xp_curve_growth_not_increasing_raises(tmp_path, growth):
    """xp_curve_growth <= 1.0 (non-increasing curve) raises ValueError naming the key.

    xp_for_level is documented as monotonically increasing (growth > 1); a growth
    of 1.0 (flat) or below (decreasing) breaks that contract, so it must be rejected
    at load time -- including the 1.0 boundary, not just values below it.
    """
    bad = VALID_BALANCE.replace("xp_curve_growth = 1.4", f"xp_curve_growth = {growth}")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "xp_curve_growth" in msg
    assert "config/balance.toml" in msg


def test_projectile_count_zero_on_projectile_weapon_raises(tmp_path):
    """A projectile (non-forward_arc) weapon with projectile_count = 0 raises ValueError."""
    bad = VALID_BALANCE.replace("projectile_count = 1", "projectile_count = 0")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "projectile_count" in msg
    assert "config/balance.toml" in msg


def test_projectile_ttl_zero_on_projectile_weapon_raises(tmp_path):
    """A projectile (non-forward_arc) weapon with projectile_ttl = 0 raises ValueError."""
    bad = VALID_BALANCE.replace("projectile_ttl   = 1.2", "projectile_ttl   = 0.0")
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "projectile_ttl" in msg
    assert "config/balance.toml" in msg


def test_forward_arc_zero_projectile_fields_ok(tmp_path):
    """A forward_arc melee weapon legitimately carries zero projectile fields.

    Regression guard: the projectile_count/ttl strict-positive checks must apply
    ONLY to projectile weapons, never to forward_arc melee, whose zero
    count/speed/ttl are by design (its reach is arc_range).
    """
    cfg = _load(tmp_path)  # VALID_BALANCE's swing is forward_arc with zeros
    swing = cfg.defs.weapons["swing"]
    assert swing.targeting == "forward_arc"
    assert swing.projectile_count == 0
    assert swing.projectile_ttl == 0.0


def test_reinforce_step_non_positive_interval_raises(tmp_path):
    """A reinforce step with interval_mult <= 0 raises ValueError naming the key."""
    bad = VALID_BALANCE.replace(
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8, 2]]",
        "reinforce_steps = [[0, 1.0, 1], [1, -0.8, 2]]",
    )
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "interval_mult" in msg
    assert "config/balance.toml" in msg


def test_reinforce_step_zero_concurrent_raises(tmp_path):
    """A reinforce step with concurrent < 1 raises ValueError naming the key."""
    bad = VALID_BALANCE.replace(
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8, 2]]",
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8, 0]]",
    )
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "concurrent" in msg
    assert "config/balance.toml" in msg


def test_reinforce_steps_minutes_out_of_order_raises(tmp_path):
    """Reinforce steps whose minute thresholds decrease raise ValueError."""
    bad = VALID_BALANCE.replace(
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8, 2]]",
        "reinforce_steps = [[5, 1.0, 1], [1, 0.8, 2]]",
    )
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "non-decreasing" in msg
    assert "config/balance.toml" in msg


def test_reinforce_step_malformed_row_raises(tmp_path):
    """A reinforce step row that is not [minute, interval_mult, concurrent] raises ValueError."""
    bad = VALID_BALANCE.replace(
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8, 2]]",
        "reinforce_steps = [[0, 1.0, 1], [1, 0.8]]",
    )
    with pytest.raises(ValueError) as exc:
        _load(tmp_path, bad)
    msg = str(exc.value)
    assert "reinforce_steps" in msg
    assert "config/balance.toml" in msg
