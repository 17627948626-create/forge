#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/clear_publish_blocked_state.py"
TEST_ROOT="$(make_test_root clear_publish_blocked_state)"
trap 'rm -rf "$TEST_ROOT"' EXIT

RUN_ID="manual:test:clear-blocked"

# Test 1: in_review clears stale blocked fields and mirrors matching run lock
D="$TEST_ROOT/t1"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/run.lock.json"

cat > "$state_path" <<'JSON'
{
  "run_id": "manual:test:clear-blocked",
  "status": "need_user_action",
  "phase": "awaiting_human",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/manual-test-clear-blocked/safe-check.png",
  "relay_status": "acknowledged",
  "boss_notified_at": "2026-04-07T07:39:00Z",
  "blocking_since": "2026-04-07T07:39:00Z",
  "timeout_at": "2026-04-07T07:49:00Z",
  "resume_context": {"appmsgid":"100000148"},
  "blocking": {"phase":"awaiting_human"},
  "handoff": {"relay_status":"acknowledged"},
  "state": "running"
}
JSON

cat > "$lock_path" <<'JSON'
{
  "run_id": "manual:test:clear-blocked",
  "status": "need_user_action",
  "phase": "awaiting_human",
  "current_step": "waiting_safe_check_scan",
  "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/manual-test-clear-blocked/safe-check.png",
  "lock_unknown": "preserve"
}
JSON

"$PYTHON_BIN" "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --status in_review \
  --phase published \
  --current-step reader_side_in_review \
  --state done > "$D/result.json"

"$PYTHON_BIN" - "$state_path" "$lock_path" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]))
lock=json.load(open(sys.argv[2]))
for key in [
    'waiting_for','required_user_action','safe_check_qr_path','relay_status',
    'boss_notified_at','blocking_since','timeout_at','resume_context'
]:
    assert state[key] is None, (key, state[key])
assert state['blocking'] is None
assert state['handoff'] is None
assert state['status'] == 'in_review'
assert state['phase'] == 'published'
assert state['current_step'] == 'reader_side_in_review'
assert state['state'] == 'done'
assert state['control_plane_sync'] == 'complete'
assert lock['safe_check_qr_path'] is None
assert lock['status'] == 'in_review'
assert lock['phase'] == 'published'
assert lock['current_step'] == 'reader_side_in_review'
assert lock['lock_unknown'] == 'preserve'
print('PASS')
PY

echo "Test 1: PASS"

# Test 2: run lock mismatch keeps durable state clear with partial sync
D="$TEST_ROOT/t2"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/run.lock.json"

cat > "$state_path" <<'JSON'
{
  "run_id": "manual:test:clear-blocked",
  "status": "need_user_action",
  "phase": "awaiting_human",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/manual-test-clear-blocked/safe-check.png"
}
JSON

cat > "$lock_path" <<'JSON'
{
  "run_id": "manual:other:run"
}
JSON

"$PYTHON_BIN" "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --status failed \
  --phase done \
  --current-step publish_failed \
  --state error > "$D/result.json"

"$PYTHON_BIN" - "$state_path" "$D/result.json" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]))
result=json.load(open(sys.argv[2]))
assert state['safe_check_qr_path'] is None
assert state['status'] == 'failed'
assert state['phase'] == 'done'
assert state['current_step'] == 'publish_failed'
assert state['control_plane_sync'] == 'partial'
assert result['run_lock_updated'] is False
assert 'run_lock_run_id_mismatch' in result['run_lock_status']
print('PASS')
PY

echo "Test 2: PASS"
echo "test_clear_publish_blocked_state.sh: ALL TESTS PASSED"
