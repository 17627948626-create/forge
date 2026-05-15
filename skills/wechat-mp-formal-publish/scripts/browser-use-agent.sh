#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
REGISTRY="${BROWSER_USE_AGENT_REGISTRY:-${SKILL_ROOT}/references/browser-use-agent-profiles.json}"
GUARD="${BROWSER_USE_PROFILE_GUARD:-${SCRIPT_DIR}/browser_use_profile_guard.py}"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <agent-id> <browser-use args...>" >&2
  echo "Example: $0 xiaolongxia open 'https://mp.weixin.qq.com/'" >&2
  exit 2
fi

AGENT_ID="$1"
shift

if [[ ! -f "$REGISTRY" ]]; then
  echo "ERROR: registry not found: $REGISTRY" >&2
  exit 2
fi

readarray -t META < <(python3 - "$REGISTRY" "$AGENT_ID" <<'PY'
import json, sys
reg, agent = sys.argv[1], sys.argv[2]
data = json.load(open(reg, 'r', encoding='utf-8'))
entry = (data.get('agents') or {}).get(agent)
if not entry:
    raise SystemExit(f'ERROR: agent {agent!r} not found in {reg}')
print(entry['session'])
print(entry['user_data_dir'])
PY
)

SESSION="${META[0]}"
USER_DATA_DIR="${META[1]}"
mkdir -p "$USER_DATA_DIR"
export BROWSER_USE_USER_DATA_DIR="$USER_DATA_DIR"

GUARD_JSON="$(python3 "$GUARD" --agent "$AGENT_ID" --registry "$REGISTRY" --json || true)"
if ! GUARD_JSON="$GUARD_JSON" python3 -c 'import json, os, sys; report=json.loads(os.environ["GUARD_JSON"]); raise SystemExit(0 if report.get("ok") else 1)'
then
  if GUARD_JSON="$GUARD_JSON" python3 -c 'import json, os, sys; report=json.loads(os.environ["GUARD_JSON"]); okay=bool(report.get("session_dir_mismatch")) and not report.get("conflicting_sessions") and not report.get("orphan_holders"); raise SystemExit(0 if okay else 1)'
  then
    PID_FILE="/root/.browser-use/${SESSION}.pid"
    if [[ -f "$PID_FILE" ]]; then
      OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
      if [[ -n "$OLD_PID" ]]; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
      fi
    fi
  else
    echo "$GUARD_JSON" >&2
    exit 1
  fi
fi

exec browser-use --session "$SESSION" "$@"
