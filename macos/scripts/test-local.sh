#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-"$ROOT/.venv/bin/python"}"
INCLUDE_TYPING=0

usage() {
  cat <<'USAGE'
Usage: scripts/test-local.sh [options]

Runs local unittest files using unittest discovery.
By default it skips test_typing.py because that test can type into the focused input.

Options:
  --include-typing  Also run test_typing.py.
  -h, --help        Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --include-typing)
      INCLUDE_TYPING=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[test-local] Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[test-local] Python not found or not executable: $PYTHON_BIN" >&2
  echo "[test-local] Create .venv first or set PYTHON=/path/to/python." >&2
  exit 1
fi

"$PYTHON_BIN" -m py_compile agent/*.py

for test_file in test/test_*.py; do
  test_name="$(basename "$test_file")"
  if [[ "$test_name" == "test_typing.py" && "$INCLUDE_TYPING" != "1" ]]; then
    echo "[skip] $test_name (requires focused input; pass --include-typing to run)"
    continue
  fi
  echo "[test] $test_name"
  PYTHONPATH="$ROOT" "$PYTHON_BIN" -m unittest discover -s test -p "$test_name"
done
