#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/check_publish_blocked_timeout.py"
TEST_ROOT="$(mktemp -d "$HOME/.openclaw/skills/wechat-article-forge/tests/tmp.check_publish_blocked_timeout.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/pipeline-state.json" <<'JSON'
{
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "status": "need_user_action",
  "phase": "awaiting_human",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "timeout_at": "2026-04-02T12:11:11Z",
  "resume_context": {
    "browser_session": "default",
    "appmsgid": "100000148"
  },
  "blocking": {
    "phase": "awaiting_human",
    "current_step": "waiting_safe_check_scan"
  }
}
JSON

python3 "$SCRIPT" \
  --state-path "$TEST_ROOT/pipeline-state.json" \
  --now 2026-04-02T12:12:11Z > "$TEST_ROOT/result.json"

python3 - "$TEST_ROOT/result.json" "$TEST_ROOT/pipeline-state.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
state=json.load(open(sys.argv[2]))
assert result['ok'] is True
assert result['escalated'] is True
assert state['status'] == 'blocked'
assert state['phase'] == 'blocked'
assert state['timeout_escalated_at'] == '2026-04-02T12:12:11Z'
assert state['resume_context'] == {'browser_session': 'default', 'appmsgid': '100000148'}
assert state['blocking']['phase'] == 'blocked'
print('PASS')
PY

echo "test_check_publish_blocked_timeout.sh: PASS"
