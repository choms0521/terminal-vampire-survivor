"""Tests for terminal_vs.config: operating-point load, fallback, range validation.

Uses tmp_path-written TOML files so the repo's real config is never mutated.
Balance-side coverage (cfg.defs / the balance.toml schema) lives in
tests/test_config_balance.py; this file covers the tuning.toml operating point.
"""

from __future__ import annotations

import textwrap

import pytest

from terminal_vs.config import Config, load_config, load_default_config

# A minimal valid balance.toml shared by the tuning-focused tests below. The
# balance schema itself is exercised in test_config_balance.py; here it just
# needs to be valid so load_config succeeds and we can assert the tuning side.
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
    reinforce_steps = [[0, 1.0, 1]]

    [pickup]
    magnet_range = 5.0
"""

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


def _write(path, text: str) -> str:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


def test_valid_load_returns_config_with_expected_fields(tmp_path):
    """A valid pair of TOMLs loads into a Config with operating-point values."""
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)

    cfg = load_config(tuning, balance)

    assert isinstance(cfg, Config)
    # Operating-point fields loaded from tuning.toml (with int->float coercion).
    assert cfg.sim_tps == 25.0
    assert isinstance(cfg.sim_tps, float)
    assert cfg.viewport_w == 80
    assert cfg.viewport_h == 24
    assert cfg.entity_cap == 150
    assert cfg.poll_timeout == 0.01
    assert cfg.max_catchup == 4
    assert cfg.aspect_x == 2.0
    assert cfg.render_mode == "full"
    # The balance side is present as the immutable defs table.
    assert cfg.defs.weapons["dagger"].cooldown == 1.2


def test_config_is_frozen_immutable(tmp_path):
    """Config is frozen (section 6 boundary)."""
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)
    cfg = load_config(tuning, balance)

    with pytest.raises(Exception):
        cfg.sim_tps = 99.0  # type: ignore[misc]
    with pytest.raises(Exception):
        cfg.defs = None  # type: ignore[misc]


def test_missing_key_falls_back_to_default(tmp_path):
    """A tuning file missing a key falls back to the code default for that key."""
    # Omit entity_cap and aspect_x entirely; keep the rest.
    partial = """\
        sim_tps      = 30
        viewport_w   = 64
        viewport_h   = 20
        poll_timeout = 0.02
        max_catchup  = 3
    """
    tuning = _write(tmp_path / "tuning.toml", partial)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)

    cfg = load_config(tuning, balance)

    # Present keys honored.
    assert cfg.sim_tps == 30.0
    assert cfg.viewport_w == 64
    # Missing keys fall back to code defaults (positive, valid Config built).
    assert cfg.entity_cap > 0
    assert cfg.aspect_x > 0
    assert cfg.render_mode  # default render_mode string present


def test_missing_files_use_all_defaults(tmp_path):
    """Absent config files do not error -- all defaults are used (first launch)."""
    cfg = load_config(tmp_path / "absent_tuning.toml", tmp_path / "absent_balance.toml")
    assert isinstance(cfg, Config)
    assert cfg.sim_tps > 0
    assert cfg.defs.weapons  # default weapon content present


@pytest.mark.parametrize(
    "bad_line",
    [
        "sim_tps = 0",
        "sim_tps = -5",
        "viewport_w = 0",
        "viewport_h = -1",
        "entity_cap = 0",
        "aspect_x = 0",
        "poll_timeout = 0",
        "max_catchup = 0",
    ],
)
def test_out_of_range_value_raises_valueerror(tmp_path, bad_line):
    """A non-positive operating-point value raises a clear ValueError."""
    key = bad_line.split("=", 1)[0].strip()
    # Build a tuning file that is valid except for the one bad line.
    lines = []
    for ln in textwrap.dedent(VALID_TUNING).splitlines():
        name = ln.split("=", 1)[0].strip()
        lines.append(bad_line if name == key else ln)
    tuning = _write(tmp_path / "tuning.toml", "\n".join(lines) + "\n")
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)

    with pytest.raises(ValueError) as exc:
        load_config(tuning, balance)
    # The hint points at the operating-point file for a tuning value.
    assert "config/tuning.toml" in str(exc.value)


def test_invalid_render_mode_raises_valueerror(tmp_path):
    """A render_mode outside {'full','diff'} raises a clear ValueError."""
    bad_tuning = VALID_TUNING.replace('render_mode  = "full"', 'render_mode  = "fancy"')
    tuning = _write(tmp_path / "tuning.toml", bad_tuning)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)

    with pytest.raises(ValueError) as exc:
        load_config(tuning, balance)
    assert "render_mode" in str(exc.value)


def test_shipped_config_loads_and_validates():
    """The repo's shipped config/tuning.toml + balance.toml load and validate.

    Every other test builds Config / BalanceDefs synthetically (conftest helpers
    or tmp_path TOMLs), so this is the single guard that the ACTUAL shipped
    runtime artifacts parse and pass schema validation -- catching a typo or an
    out-of-range edit (e.g. in the Phase 3 director-curve tune) before launch
    rather than at game start.
    """
    cfg = load_default_config()

    assert isinstance(cfg, Config)
    assert cfg.sim_tps > 0
    assert cfg.defs.weapons          # weapon content present
    assert cfg.defs.enemies          # enemy content present
    # The director reinforce curve parsed to its rows with non-decreasing minutes
    # (the order sim/spawn's active-step lookup relies on).
    minutes = [step.minute for step in cfg.defs.director.reinforce_steps]
    assert minutes  # non-empty
    assert minutes == sorted(minutes)

    # The new weapon render / fan / melee-effect fields parse from the SHIPPED
    # balance.toml (conftest mirrors these by hand, so this pins the real data
    # against drift between the mirror and the production config).
    weapons = cfg.defs.weapons
    assert weapons["dagger"].glyph == "-"
    assert weapons["dagger"].color == "white"
    assert weapons["magic_bolt"].color == "cyan"
    assert weapons["dagger_evolved"].spread_angle == 30.0  # the 3-dart fan cone
    assert weapons["swing"].effect_ttl == 0.15  # the swing-visual lifetime
    assert weapons["lance"].pierce == 99  # lance pierces a whole line
    assert weapons["nova"].targeting == "radial"  # nova is the 360-deg burst
    assert weapons["orbit"].targeting == "orbit"  # orbit revolves around the player
    assert weapons["orbit"].orbit_radius == 4.0  # the ring radius

    # Phase 4A permanent (cross-run) upgrades parse from the shipped balance.toml.
    upgrades = cfg.defs.upgrades
    assert upgrades["swift"].stat == "move_speed"
    assert upgrades["fury"].stat == "attack_speed"
    assert upgrades["fury"].cost_base == 60
    assert cfg.defs.gold_per_kill == 1  # Phase 4A: gold banked per enemy kill
