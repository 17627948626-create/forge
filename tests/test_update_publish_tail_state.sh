#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/update_publish_tail_state.py"
TEST_ROOT="$(make_test_root update_publish_tail_state)"
trap 'rm -rf "$TEST_ROOT"' EXIT

D="$TEST_ROOT/tail"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/run.lock.json"

cat > "$state_path" <<'JSON'
{
  "run_id": "run-tail-1",
  "state": "running",
  "phase": "awaiting_human",
  "status": "need_user_action",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "pending_action": "wait_boss_scan",
  "safe_check_qr_path": "/durable/qr.png",
  "safe_check_qr_url": "https://example.test/qr.png",
  "qr_verified": true,
  "qr_verification_method": "manual",
  "relay_status": "pending_parent_forward",
  "relay_dedupe_key": "run-tail-1:safe_check_scan:1",
  "boss_notified_at": "2026-04-02T12:00:00Z",
  "qr_updated_at": "2026-04-02T12:00:00Z",
  "blocking_since": "2026-04-02T12:00:00Z",
  "timeout_at": "2026-04-02T12:10:00Z",
  "timeout_escalated_at": "2026-04-02T12:11:00Z",
  "resume_context": {"browser_session":"default"},
  "resume_point": "submitted_pending_result",
  "blocking": {"current_step":"waiting_safe_check_scan"},
  "handoff": {"relay_status":"pending_parent_forward"}
}
JSON

cat > "$lock_path" <<'JSON'
{
  "run_id": "run-tail-1",
  "phase": "awaiting_human",
  "status": "need_user_action",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "pending_action": "wait_boss_scan",
  "safe_check_qr_path": "/durable/qr.png",
  "qr_verified": true,
  "timeout_at": "2026-04-02T12:10:00Z",
  "timeout_escalated_at": "2026-04-02T12:11:00Z",
  "resume_context": {"browser_session":"default"},
  "blocking": {"current_step":"waiting_safe_check_scan"},
  "handoff": {"relay_status":"pending_parent_forward"}
}
JSON

"$PYTHON_BIN" "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --state-node reader_side_in_review \
  --signal-kind recent_publish_status \
  --signal-summary "reader side shows in review" > "$D/result.json"

"$PYTHON_BIN" - "$state_path" "$lock_path" "$D/result.json" <<'PY'
import json, sys
from pathlib import Path
state=json.loads(Path(sys.argv[1]).read_text())
lock=json.loads(Path(sys.argv[2]).read_text())
result=json.loads(Path(sys.argv[3]).read_text())
assert result['ok'] is True
assert result['run_lock_updated'] is True
assert result['control_plane_sync'] == 'complete'
assert state['phase'] == 'published'
assert state['status'] == 'in_review'
assert state['current_step'] == 'reader_side_in_review'
assert state['control_plane_sync'] == 'complete'
assert lock['control_plane_sync'] == 'complete'
for obj in (state, lock):
    for key in [
        'waiting_for','required_user_action','pending_action','safe_check_qr_path','safe_check_qr_url',
        'qr_verified','qr_verification_method','relay_status','relay_dedupe_key','boss_notified_at',
        'qr_updated_at','blocking_since','timeout_at','timeout_escalated_at','resume_context',
        'resume_point','blocking','handoff'
    ]:
        assert obj.get(key) is None, (key, obj.get(key))
print('PASS')
PY

echo "test_update_publish_tail_state.sh: PASS"
