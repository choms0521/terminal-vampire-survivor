#!/usr/bin/env bash
# run.sh - launch terminal_vs (Phase 1 entry).
#
# Activates a local virtualenv if present (.venv or venv), then runs the package
# entry point. The Phase 1 entry is minimal until the Day 5 game loop lands.
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

exec python -m terminal_vs "$@"
