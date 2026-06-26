"""Tests for terminal_vs.meta: MetaState save/load round-trip + schema validation.

Phase 4A. Uses tmp_path so the real saves/meta.json is never touched. The save
format is JSON (stdlib, read+write) -- TOML's stdlib reader (tomllib) is
read-only, see the Phase 4 plan section 3.2.
"""

from __future__ import annotations

import json

import pytest

from terminal_vs.meta.accrue import RunResult, accrue_meta, spend_gold, upgrade_cost
from terminal_vs.meta.save import CURRENT_VERSION, load_meta, save_meta
from terminal_vs.meta.schema import MetaSaveError, MetaState
from terminal_vs.rules.defs import MetaUpgradeDef

from .conftest import make_defs


def test_roundtrip_preserves_all_fields(tmp_path):
    path = tmp_path / "meta.json"
    state = MetaState(
        gold=150,
        upgrades={"haste": 2, "fury": 1},
        unlocked=frozenset({"lance", "nova"}),
        total_runs=3,
    )
    save_meta(state, path)
    assert load_meta(path) == state


def test_default_state_roundtrips(tmp_path):
    path = tmp_path / "meta.json"
    save_meta(MetaState(), path)
    assert load_meta(path) == MetaState()


def test_missing_file_returns_default(tmp_path):
    assert load_meta(tmp_path / "absent.json") == MetaState()


def test_save_is_json_with_version_envelope(tmp_path):
    path = tmp_path / "meta.json"
    save_meta(MetaState(gold=10), path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == CURRENT_VERSION
    assert raw["gold"] == 10


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("gold"),
        lambda d: d.pop("version"),
        lambda d: d.pop("upgrades"),
        lambda d: d.pop("unlocked"),
        lambda d: d.update(gold=-5),
        lambda d: d.update(gold="lots"),
        lambda d: d.update(gold=True),  # bool is an int subclass; must be rejected
        lambda d: d.update(version=999),  # newer than CURRENT_VERSION
        lambda d: d.update(upgrades=["not", "a", "map"]),
        lambda d: d.update(upgrades={"haste": -1}),  # negative level
        lambda d: d.update(unlocked="lance"),  # must be a list, not a bare str
    ],
)
def test_schema_validation_rejects_corrupt_save(tmp_path, mutate):
    path = tmp_path / "meta.json"
    save_meta(
        MetaState(gold=10, upgrades={"haste": 1}, unlocked=frozenset({"lance"})),
        path,
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MetaSaveError):
        load_meta(path)


def test_unreadable_save_raises_meta_save_error(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    with pytest.raises(MetaSaveError):
        load_meta(path)


def test_save_creates_parent_dir_under_saves_not_config(tmp_path):
    # AC-9: the save is its own file under a saves/ dir, never under config/.
    path = tmp_path / "saves" / "meta.json"
    save_meta(MetaState(gold=1), path)
    assert path.exists()
    assert "config" not in path.parts


# --- accrue_meta: the pure post-run progression update ----------------------


def test_accrue_adds_gold_and_increments_run_count():
    old = MetaState(
        gold=100, upgrades={"haste": 1}, unlocked=frozenset({"lance"}), total_runs=2
    )
    new = accrue_meta(old, RunResult(gold_earned=50))
    assert new.gold == 150
    assert new.total_runs == 3
    assert new.upgrades == {"haste": 1}  # carried over unchanged
    assert new.unlocked == frozenset({"lance"})  # carried over unchanged (v1: no gating)


def test_accrue_does_not_mutate_the_old_meta():
    old = MetaState(gold=100, total_runs=2)
    accrue_meta(old, RunResult(gold_earned=50))
    assert old.gold == 100  # frozen + a new object is returned, old is untouched
    assert old.total_runs == 2


def test_accrue_from_default_meta_counts_the_first_run():
    new = accrue_meta(MetaState(), RunResult(gold_earned=0))
    assert new == MetaState(total_runs=1)


def test_accrue_result_survives_save_round_trip(tmp_path):
    # The post-run pipeline: accrue -> save -> load returns the same state.
    path = tmp_path / "meta.json"
    new = accrue_meta(MetaState(gold=10), RunResult(gold_earned=25))
    save_meta(new, path)
    assert load_meta(path) == new


def test_run_result_rejects_negative_gold():
    with pytest.raises(ValueError):
        RunResult(gold_earned=-1)


# --- spend_gold: the pure permanent-upgrade purchase --------------------------


def _defs_with_swift(*, max_level=5, cost_base=50, cost_growth=2.0):
    return make_defs(
        upgrades={
            "swift": MetaUpgradeDef(
                "swift", max_level, "move_speed", 1.1, cost_base, cost_growth
            )
        }
    )


def test_upgrade_cost_is_geometric_in_owned_level():
    udef = MetaUpgradeDef("swift", 5, "move_speed", 1.1, 50, 2.0)
    assert upgrade_cost(udef, 0) == 50  # base price for the first level
    assert upgrade_cost(udef, 1) == 100  # base * growth
    assert upgrade_cost(udef, 2) == 200


def test_spend_gold_buys_one_level_and_deducts_cost():
    new = spend_gold(MetaState(gold=100), "swift", _defs_with_swift())
    assert new.upgrades["swift"] == 1
    assert new.gold == 50  # 100 - cost_base(50)


def test_spend_gold_cost_grows_with_owned_level():
    new = spend_gold(
        MetaState(gold=1000, upgrades={"swift": 1}), "swift", _defs_with_swift()
    )
    assert new.upgrades["swift"] == 2
    assert new.gold == 900  # next level costs 50 * 2**1 = 100


def test_spend_gold_insufficient_funds_is_noop():
    meta = MetaState(gold=10)
    assert spend_gold(meta, "swift", _defs_with_swift()) == meta


def test_spend_gold_at_max_level_is_noop():
    meta = MetaState(gold=10_000, upgrades={"swift": 2})
    assert spend_gold(meta, "swift", _defs_with_swift(max_level=2)) == meta


def test_spend_gold_unknown_upgrade_raises_keyerror():
    with pytest.raises(KeyError):
        spend_gold(MetaState(gold=100), "ghost", make_defs())


def test_spend_gold_does_not_mutate_old_meta():
    old = MetaState(gold=100)
    spend_gold(old, "swift", _defs_with_swift())
    assert old.gold == 100
    assert dict(old.upgrades) == {}
