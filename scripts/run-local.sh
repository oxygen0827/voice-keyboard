#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-"$ROOT/.venv/bin/python"}"
LOG_DIR="$ROOT/.local/logs"
RUN_DIR="$ROOT/.local/run"
PID_FILE="$RUN_DIR/voice-keyboard-local.pid"
LOG_FILE="$LOG_DIR/voice-keyboard-local.log"
LAUNCH_AGENT_LABEL="${VOICE_KEYBOARD_LAUNCH_AGENT_LABEL:-com.voicekeyboard.agent}"

KILL_FIRST=1
KILL_ONLY=0
BACKGROUND=0
LIST_DEVICES=0
HEADLESS=0
STATUS_ONLY=0
PERMISSIONS_ONLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/run-local.sh [options] [-- extra agent.main args]

Starts Voice Keyboard Engine locally with the Software Capture Path.
By default it kills existing local agent.main processes, then runs:
  .venv/bin/python -m agent.main --no-serial --no-ui

Options:
  --no-kill       Do not kill existing agent.main processes first.
  --kill-only     Kill existing agent.main processes and exit.
  --background    Start in background and write a log under .local/logs/.
  --headless      Disable the floating status window and run terminal-only.
  --status        Show whether the local engine PID file points to a running process.
  --permissions   Print macOS permission status JSON and exit.
  --list-devices  List microphone devices and exit.
  -h, --help      Show this help.

Examples:
  scripts/run-local.sh
  scripts/run-local.sh --background
  scripts/run-local.sh --status
  scripts/run-local.sh --permissions
  scripts/run-local.sh --headless
  scripts/run-local.sh --kill-only
  scripts/run-local.sh -- --headless
USAGE
}

AGENT_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-kill)
      KILL_FIRST=0
      shift
      ;;
    --kill-only)
      KILL_ONLY=1
      shift
      ;;
    --background)
      BACKGROUND=1
      shift
      ;;
    --headless)
      HEADLESS=1
      shift
      ;;
    --status)
      STATUS_ONLY=1
      KILL_FIRST=0
      shift
      ;;
    --permissions)
      PERMISSIONS_ONLY=1
      KILL_FIRST=0
      shift
      ;;
    --list-devices)
      LIST_DEVICES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      AGENT_ARGS+=("$@")
      break
      ;;
    *)
      AGENT_ARGS+=("$1")
      shift
      ;;
  esac
done

cd "$ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[run-local] Python not found or not executable: $PYTHON_BIN" >&2
  echo "[run-local] Create .venv first or set PYTHON=/path/to/python." >&2
  exit 1
fi

process_cwd() {
  local pid="$1"
  local cwd=""

  if command -v lsof >/dev/null 2>&1; then
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
  fi

  if [[ -z "$cwd" && -e "/proc/$pid/cwd" ]]; then
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
  fi

  printf '%s\n' "$cwd"
}

find_engine_pids() {
  local pid cmd cwd

  pgrep -f 'agent\.main|agent/main\.py' 2>/dev/null | while read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    [[ "$pid" != "$$" ]] || continue

    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    [[ "$cmd" == *"agent.main"* || "$cmd" == *"agent/main.py"* ]] || continue

    cwd="$(process_cwd "$pid")"
    [[ "$cwd" == "$ROOT" ]] || continue

    printf '%s\n' "$pid"
  done
}

pid_file_pid() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  printf '%s\n' "$pid"
}

is_pid_running() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

launch_agent_pid() {
  if [[ "$(uname -s)" != "Darwin" ]] || ! command -v launchctl >/dev/null 2>&1; then
    return 1
  fi

  local output pid
  output="$(launchctl print "gui/$(id -u)/$LAUNCH_AGENT_LABEL" 2>/dev/null || true)"
  [[ "$output" == *"state = running"* ]] || return 1
  [[ "$output" == *"agent.main"* ]] || return 1
  [[ "$output" == *"working directory = $ROOT"* ]] || return 1

  pid="$(printf '%s\n' "$output" | sed -n 's/^[[:space:]]*pid = \([0-9][0-9]*\).*$/\1/p' | head -n 1)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$pid"
}

print_permission_hint() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return
  fi
  echo "[run-local] Permissions: scripts/run-local.sh --permissions"
  echo "[run-local] System Settings grants apply to the launching app (Terminal/Python for source runs, Voice Keyboard.app for packaged runs)."
}

show_status() {
  local pid
  pid="$(pid_file_pid || true)"
  if [[ -n "${pid:-}" ]] && is_pid_running "$pid"; then
    echo "[run-local] Status: running"
    echo "[run-local] PID: $pid"
    echo "[run-local] PID file: $PID_FILE"
    echo "[run-local] Log: $LOG_FILE"
    return 0
  fi

  local pids
  pids="$(find_engine_pids | tr '\n' ' ' | xargs || true)"
  if [[ -n "$pids" ]]; then
    echo "[run-local] Status: running"
    echo "[run-local] PID(s): $pids"
    echo "[run-local] PID file: $PID_FILE"
    echo "[run-local] Log: $LOG_FILE"
    return 0
  fi

  pid="$(launch_agent_pid || true)"
  if [[ -n "${pid:-}" ]]; then
    echo "[run-local] Status: running"
    echo "[run-local] PID: $pid"
    echo "[run-local] LaunchAgent: $LAUNCH_AGENT_LABEL"
    echo "[run-local] PID file: $PID_FILE"
    echo "[run-local] Log: $HOME/Library/Logs/VoiceKeyboard.log"
    return 0
  fi

  echo "[run-local] Status: not running"
  echo "[run-local] PID file: $PID_FILE"
  echo "[run-local] Log: $LOG_FILE"
  return 1
}

kill_existing() {
  local pids
  pids="$(find_engine_pids | tr '\n' ' ' | xargs || true)"
  if [[ -z "$pids" ]]; then
    echo "[run-local] No existing agent.main process found."
    return
  fi

  echo "[run-local] Killing existing agent.main process(es): $pids"
  kill $pids 2>/dev/null || true
  sleep 0.8

  local survivors
  survivors="$(find_engine_pids | tr '\n' ' ' | xargs || true)"
  if [[ -n "$survivors" ]]; then
    echo "[run-local] Force killing remaining process(es): $survivors"
    kill -9 $survivors 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
}

if [[ "$STATUS_ONLY" == "1" ]]; then
  show_status
  exit $?
fi

if [[ "$KILL_FIRST" == "1" ]]; then
  kill_existing
fi

if [[ "$KILL_ONLY" == "1" ]]; then
  exit 0
fi

if [[ "$PERMISSIONS_ONLY" == "1" ]]; then
  exec "$PYTHON_BIN" -m agent.main --permissions-json
fi

if [[ "$LIST_DEVICES" == "1" ]]; then
  if [[ ${#AGENT_ARGS[@]} -gt 0 ]]; then
    exec "$PYTHON_BIN" -m agent.main --list-devices "${AGENT_ARGS[@]}"
  fi
  exec "$PYTHON_BIN" -m agent.main --list-devices
fi

CMD=("$PYTHON_BIN" -u -m agent.main --no-serial)
if [[ "$HEADLESS" == "1" ]]; then
  CMD+=(--headless)
else
  CMD+=(--no-ui)
fi
if [[ ${#AGENT_ARGS[@]} -gt 0 ]]; then
  CMD+=("${AGENT_ARGS[@]}")
fi
echo "[run-local] Starting: ${CMD[*]}"

if [[ "$BACKGROUND" == "1" ]]; then
  mkdir -p "$LOG_DIR" "$RUN_DIR"
  nohup "${CMD[@]}" >"$LOG_FILE" 2>&1 &
  pid="$!"
  printf '%s\n' "$pid" >"$PID_FILE"
  echo "[run-local] Started PID=$pid"
  echo "[run-local] PID file: $PID_FILE"
  echo "[run-local] Log: $LOG_FILE"
  print_permission_hint
else
  print_permission_hint
  exec "${CMD[@]}"
fi
