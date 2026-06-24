"""Tests for terminal_vs.config: valid load, default fallback, range validation.

Uses tmp_path-written TOML files so the repo's real config is never mutated.
"""

from __future__ import annotations

import textwrap

import pytest

from terminal_vs.config import BalanceTable, Config, load_config


def _write(path, text: str) -> str:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


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
    [weapon]
    cooldown         = 0.5
    damage           = 12.0
    projectile_speed = 20.0
    projectile_ttl   = 1.5

    [enemy]
    hp           = 25.0
    move_speed   = 3.5
    spawn_weight = 2.0

    [xp]
    base   = 6.0
    growth = 1.4

    [pickup]
    magnet_range = 5.0
"""


def test_valid_load_returns_config_with_expected_fields(tmp_path):
    """A valid pair of TOMLs loads into a Config with values read by key."""
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
    # Nested balance table loaded from balance.toml.
    assert isinstance(cfg.balance, BalanceTable)
    assert cfg.balance.weapon.cooldown == 0.5
    assert cfg.balance.weapon.damage == 12.0
    assert cfg.balance.enemy.hp == 25.0
    assert cfg.balance.xp.base == 6.0
    assert cfg.balance.magnet_range == 5.0


def test_config_is_frozen_immutable(tmp_path):
    """Config and its nested balance are frozen (section 6 boundary)."""
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)
    cfg = load_config(tuning, balance)

    with pytest.raises(Exception):
        cfg.sim_tps = 99.0  # type: ignore[misc]
    with pytest.raises(Exception):
        cfg.balance.weapon.damage = 1.0  # type: ignore[misc]


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


def test_missing_balance_section_falls_back_to_default(tmp_path):
    """A balance file missing a whole section uses code defaults for it."""
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    # Only the weapon section; enemy/xp/pickup omitted.
    partial_balance = """\
        [weapon]
        cooldown = 0.4
    """
    balance = _write(tmp_path / "balance.toml", partial_balance)

    cfg = load_config(tuning, balance)

    assert cfg.balance.weapon.cooldown == 0.4
    # Omitted weapon keys + whole sections fall back to positive defaults.
    assert cfg.balance.weapon.damage > 0
    assert cfg.balance.enemy.hp > 0
    assert cfg.balance.xp.base > 0
    assert cfg.balance.magnet_range > 0


def test_missing_files_use_all_defaults(tmp_path):
    """Absent config files do not error -- all defaults are used (first launch)."""
    cfg = load_config(tmp_path / "absent_tuning.toml", tmp_path / "absent_balance.toml")
    assert isinstance(cfg, Config)
    assert cfg.sim_tps > 0
    assert cfg.balance.weapon.cooldown > 0


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


def test_out_of_range_balance_raises_valueerror(tmp_path):
    """A non-positive balance value raises a clear ValueError naming balance.toml."""
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    bad_balance = VALID_BALANCE.replace("hp           = 25.0", "hp           = 0")
    balance = _write(tmp_path / "balance.toml", bad_balance)

    with pytest.raises(ValueError) as exc:
        load_config(tuning, balance)
    # The hint must name the balance file (not tuning) for a balance value.
    assert "config/balance.toml" in str(exc.value)


@pytest.mark.parametrize(
    "old, new",
    [
        ("= 12.0", "= 0"),                       # weapon.damage -> 0
        ("spawn_weight = 2.0", "spawn_weight = 0"),  # enemy.spawn_weight -> 0
        ("spawn_weight = 2.0", "spawn_weight = -1"),  # enemy.spawn_weight -> negative
    ],
)
def test_nonpositive_balance_field_raises(tmp_path, old, new):
    """weapon.damage and enemy.spawn_weight must be strictly positive."""
    assert old in VALID_BALANCE  # guard: the mutated line actually exists
    tuning = _write(tmp_path / "tuning.toml", VALID_TUNING)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE.replace(old, new))
    with pytest.raises(ValueError):
        load_config(tuning, balance)


def test_invalid_render_mode_raises_valueerror(tmp_path):
    """A render_mode outside {'full','diff'} raises a clear ValueError."""
    bad_tuning = VALID_TUNING.replace('render_mode  = "full"', 'render_mode  = "fancy"')
    tuning = _write(tmp_path / "tuning.toml", bad_tuning)
    balance = _write(tmp_path / "balance.toml", VALID_BALANCE)

    with pytest.raises(ValueError) as exc:
        load_config(tuning, balance)
    assert "render_mode" in str(exc.value)
