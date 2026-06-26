"""JSON save/load for :class:`MetaState` with schema validation.

Format is JSON (Python stdlib ``json``, read+write) rather than TOML: ``tomllib``
(3.11+ stdlib) is read-only, and writing TOML would add a third-party dependency
(Phase 4 plan section 3.2). The on-disk envelope carries a ``version`` so a
future schema change can migrate old saves instead of silently mis-reading them.

``save_meta``/``load_meta`` are file IO and are called only at run boundaries
(run start loads, game over accrues+saves) -- never inside a sim tick.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import MetaSaveError, MetaState

# Bump when the on-disk schema changes; add a migration in ``_validate``/``load``.
CURRENT_VERSION = 1

# Default location: a top-level saves/ dir (gitignored), NOT under config/ --
# config/ holds human-edited balance/tuning TOML; saves/ holds runtime state.
DEFAULT_SAVE_PATH = Path("saves/meta.json")


def save_meta(state: MetaState, path: Path = DEFAULT_SAVE_PATH) -> None:
    """Write ``state`` to ``path`` as JSON. Called post-run, never mid-tick.

    ``unlocked`` is sorted and keys are written in sorted order so the file is
    byte-stable across runs with the same state (no spurious diffs).
    """
    payload = {
        "version": CURRENT_VERSION,
        "gold": state.gold,
        "upgrades": dict(state.upgrades),
        "unlocked": sorted(state.unlocked),
        "total_runs": state.total_runs,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def load_meta(path: Path = DEFAULT_SAVE_PATH) -> MetaState:
    """Return the ``MetaState`` at ``path``; a default state if the file is absent.

    Raises :class:`MetaSaveError` if the file exists but is unreadable, not valid
    JSON, or fails schema validation -- callers surface a clear error rather than
    starting a run from a silently-wrong save.
    """
    if not path.exists():
        return MetaState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise MetaSaveError(f"could not read save at {path}: {exc}") from exc
    _validate(raw)
    return MetaState(
        gold=raw["gold"],
        upgrades=dict(raw["upgrades"]),
        unlocked=frozenset(raw["unlocked"]),
        total_runs=raw.get("total_runs", 0),
    )


def _validate(raw: object) -> None:
    """Check required keys, types, and ranges; raise MetaSaveError on any miss.

    ``bool`` is rejected for integer fields even though it is an ``int`` subclass
    -- ``true``/``false`` in a save is corruption, not a 1/0 gold value.
    """
    if not isinstance(raw, dict):
        raise MetaSaveError(f"save root must be an object, got {type(raw).__name__}")

    required = {"version", "gold", "upgrades", "unlocked"}
    missing = required - raw.keys()
    if missing:
        raise MetaSaveError(f"save missing keys: {sorted(missing)}")

    version = raw["version"]
    if not _is_int(version) or version > CURRENT_VERSION or version < 1:
        raise MetaSaveError(f"unknown save version: {version!r}")

    if not _is_int(raw["gold"]) or raw["gold"] < 0:
        raise MetaSaveError(f"invalid gold: {raw['gold']!r}")

    upgrades = raw["upgrades"]
    if not isinstance(upgrades, dict):
        raise MetaSaveError(f"upgrades must be an object: {upgrades!r}")
    for key, level in upgrades.items():
        if not _is_int(level) or level < 0:
            raise MetaSaveError(f"invalid upgrade level for {key!r}: {level!r}")

    unlocked = raw["unlocked"]
    if not isinstance(unlocked, list) or not all(isinstance(u, str) for u in unlocked):
        raise MetaSaveError(f"unlocked must be a list of strings: {unlocked!r}")

    total_runs = raw.get("total_runs", 0)
    if not _is_int(total_runs) or total_runs < 0:
        raise MetaSaveError(f"invalid total_runs: {total_runs!r}")


def _is_int(value: object) -> bool:
    """True for a real int, False for bool (an int subclass) and everything else."""
    return isinstance(value, int) and not isinstance(value, bool)
