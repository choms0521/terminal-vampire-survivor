#!/usr/bin/env bash
# run.sh - launch terminal_vs (Phase 1 entry).
#
# Activates a local virtualenv if present (.venv or venv), then runs the package
# entry point, which starts the Phase 1 game loop (move, auto-fight, level up).
# Quit in-game with 'q' or ESC.
set -euo pipefail

cd "$(dirname "$0")"

# Activate a virtualenv if one exists; otherwise rely on the ambient interpreter.
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
elif [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "venv/bin/activate"
fi

# Render glyph set convenience flags: --ascii / --emoji set TVS_GLYPH_SET without
# needing to know the env var (last one wins). Emoji is the shipped default, so
# `./run.sh --ascii` is the escape hatch on a terminal/font that cannot render
# 2-column emoji. Any other arguments are forwarded to the package entry point.
PASS_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --ascii) export TVS_GLYPH_SET=ascii ;;
    --emoji) export TVS_GLYPH_SET=emoji ;;
    *) PASS_ARGS+=("$arg") ;;
  esac
done

# ${PASS_ARGS[@]+"..."} guards the empty-array expansion under `set -u` (bash 3.2).
exec python -m terminal_vs ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}
