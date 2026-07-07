"""Integration tests for run.sh glyph-set convenience flags (--ascii / --emoji).

run.sh is bash-only (no Python change), so these drive the REAL script through a
subprocess with a stub ``python`` on PATH that echoes ``TVS_GLYPH_SET`` and its
args, then exits 0 -- so nothing opens a terminal and the run is fully
deterministic (no RNG). The script is copied into ``tmp_path`` so its
``cd "$(dirname "$0")"`` lands in a venv-free directory: a developer's local
``.venv`` / ``venv`` must not shadow the stub interpreter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUN_SH = _REPO_ROOT / "run.sh"

# A stub invoked under the name `python`: a POSIX shell script (no real REPL, no
# terminal) that reports the env var run.sh set and the args it forwarded.
_STUB = (
    "#!/bin/sh\n"
    'echo "GLYPH=${TVS_GLYPH_SET:-<unset>}"\n'
    'echo "ARGS=$*"\n'
    "exit 0\n"
)


def _run(tmp_path: Path, *flags: str, env_glyph: str | None = None):
    """Run run.sh with ``flags`` and return ``(glyph, args)`` the stub observed.

    ``glyph`` is the TVS_GLYPH_SET the child saw ("<unset>" if none); ``args`` is
    the space-joined argument line reaching ``python``.
    """
    # Copy run.sh so `cd "$(dirname "$0")"` lands in a venv-free directory.
    script = tmp_path / "run.sh"
    shutil.copy(_RUN_SH, script)

    # Stub `python` first on PATH: a shell script, so it never starts a REPL.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "python"
    stub.write_text(_STUB)
    stub.chmod(0o755)

    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("TVS_GLYPH_SET", None)  # start from a clean slate unless asked otherwise
    if env_glyph is not None:
        env["TVS_GLYPH_SET"] = env_glyph

    result = subprocess.run(
        ["bash", str(script), *flags],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    glyph = args = None
    for line in result.stdout.splitlines():
        if line.startswith("GLYPH="):
            glyph = line[len("GLYPH=") :]
        elif line.startswith("ARGS="):
            args = line[len("ARGS=") :]
    return glyph, args


def test_ascii_flag_exports_ascii(tmp_path):
    glyph, _ = _run(tmp_path, "--ascii")
    assert glyph == "ascii"


def test_emoji_flag_exports_emoji(tmp_path):
    glyph, _ = _run(tmp_path, "--emoji")
    assert glyph == "emoji"


def test_no_flag_leaves_glyph_set_unset(tmp_path):
    """No flag -> run.sh sets nothing, so config falls back to TOML/auto-detect.

    Also exercises the empty-PASS_ARGS path that must not trip `set -u` on the
    bash 3.2 macOS ships (the ${PASS_ARGS[@]+...} guard).
    """
    glyph, args = _run(tmp_path)
    assert glyph == "<unset>"
    assert args == "-m terminal_vs"  # no stray empty argument appended


def test_last_glyph_flag_wins(tmp_path):
    glyph, _ = _run(tmp_path, "--emoji", "--ascii")
    assert glyph == "ascii"


def test_unknown_args_forwarded_and_flag_consumed(tmp_path):
    glyph, args = _run(tmp_path, "--ascii", "foo", "--bar")
    assert glyph == "ascii"
    assert args == "-m terminal_vs foo --bar"
    assert "--ascii" not in args  # the glyph flag is consumed, not forwarded
