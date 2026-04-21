#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/mark_publish_blocked.py"
TEST_ROOT="$(mktemp -d "$HOME/.openclaw/skills/wechat-article-forge/tests/tmp.mark_publish_blocked.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

RUN_ID="cron:evening:2026-04-02T20:00:00+08:00"
SANITIZED="cron-evening-2026-04-02T20-00-00-08-00"

# ────────────────────────────────────────────────────────────────────────────
# Test 1: happy path – run lock matches, control_plane_sync = complete
# ────────────────────────────────────────────────────────────────────────────
echo "--- Test 1: happy path (run_lock updated, control_plane_sync=complete) ---"

D="$TEST_ROOT/t1"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/evening-run.lock.json"
qr_dir="$D/media/wechat-safe-check/$SANITIZED"
qr_path="$qr_dir/safe-check.png"
mkdir -p "$qr_dir"
printf 'fakepng' > "$qr_path"

cat > "$state_path" <<'JSON'
{
  "slug": "example-slug",
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "phase": "finalizing",
  "current_step": "layout_done",
  "step": 7,
  "note": "before block",
  "unknown_field": {
    "keep": true
  }
}
JSON

cat > "$lock_path" <<'JSON'
{
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "state": "running",
  "phase": "finalizing",
  "current_step": "layout_done",
  "progress_seq": 6,
  "lock_unknown": "preserve-me"
}
JSON

python3 "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --run-id "$RUN_ID" \
  --waiting-for boss_scan \
  --required-user-action safe_check_scan \
  --current-step waiting_safe_check_scan \
  --phase awaiting_human \
  --status need_user_action \
  --safe-check-qr-path "$qr_path" \
  --note "WeChat safe_check after continue publish" \
  --relay-status pending_parent_forward \
  --relay-dedupe-key "$RUN_ID:safe_check_scan:1" \
  --boss-notified-at "" \
  --qr-updated-at 2026-04-02T12:01:11Z \
  --blocking-since 2026-04-02T12:01:11Z \
  --timeout-at 2026-04-02T12:11:11Z \
  --resume-context-json '{"browser_session":"default","appmsgid":"100000148"}' > "$D/result.json"

python3 - "$state_path" "$lock_path" "$qr_path" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text())
lock = json.loads(Path(sys.argv[2]).read_text())
qr_path = sys.argv[3]

assert state["status"] == "need_user_action"
assert state["phase"] == "awaiting_human"
assert state["step"] == 8
assert state["current_step"] == "waiting_safe_check_scan"
assert state["waiting_for"] == "boss_scan"
assert state["required_user_action"] == "safe_check_scan"
assert state["pending_action"] == "wait_boss_scan"
assert state["safe_check_qr_path"] == qr_path
assert state["relay_status"] == "pending_parent_forward"
assert state["relay_dedupe_key"].endswith(":safe_check_scan:1")
assert state["control_plane_sync"] == "complete"
assert state["timeout_at"] == "2026-04-02T12:11:11Z"
assert state["resume_context"] == {"browser_session": "default", "appmsgid": "100000148"}
assert state["unknown_field"] == {"keep": True}
assert state["blocking"]["safe_check_qr_path"] == qr_path
assert state["blocking"]["timeout_at"] == "2026-04-02T12:11:11Z"
assert state["handoff"]["relay_status"] == "pending_parent_forward"

assert lock["run_id"] == state["run_id"]
assert lock["status"] == "need_user_action"
assert lock["phase"] == "awaiting_human"
assert lock["current_step"] == "waiting_safe_check_scan"
assert lock["required_user_action"] == "safe_check_scan"
assert lock["safe_check_qr_path"] == qr_path
assert lock["timeout_at"] == "2026-04-02T12:11:11Z"
assert lock["resume_context"] == {"browser_session": "default", "appmsgid": "100000148"}
assert lock["control_plane_sync"] == "complete"
assert lock["lock_unknown"] == "preserve-me"

print("PASS")
PY

echo "Test 1: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 2: run_id mismatch – lock belongs to a different run
#   Assertions:
#   - exit code = 0          (enforced by set -e: script must not fail)
#   - state written as blocked  (phase=awaiting_human, step=8)
#   - control_plane_sync = partial  (in both state file and result JSON)
#   - run_lock_updated = false
#   - run_lock_status contains "run_lock_run_id_mismatch"
#   - lock file content is byte-for-byte unchanged
# ────────────────────────────────────────────────────────────────────────────
echo "--- Test 2: run_id mismatch (best-effort skip, state durable write preserved) ---"

D="$TEST_ROOT/t2"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/evening-run.lock.json"
lock_orig_path="$D/evening-run.lock.orig.json"
qr_dir="$D/media/wechat-safe-check/$SANITIZED"
qr_path="$qr_dir/safe-check.png"
mkdir -p "$qr_dir"
printf 'fakepng' > "$qr_path"

cat > "$state_path" <<'JSON'
{
  "slug": "mismatch-test",
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "phase": "finalizing",
  "current_step": "layout_done",
  "step": 7
}
JSON

# Lock file intentionally has a different run_id (morning run, not evening)
cat > "$lock_path" <<'JSON'
{
  "run_id": "cron:morning:2026-04-02T08:00:00+08:00",
  "state": "running",
  "lock_sentinel": "must-be-preserved-unchanged"
}
JSON
# Save original for immutability check
cp "$lock_path" "$lock_orig_path"

# exit code must be 0 (set -e will catch non-zero automatically)
python3 "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --run-id "$RUN_ID" \
  --waiting-for boss_scan \
  --required-user-action safe_check_scan \
  --current-step waiting_safe_check_scan \
  --phase awaiting_human \
  --safe-check-qr-path "$qr_path" \
  --note "mismatch test" \
  --relay-status pending_parent_forward \
  --relay-dedupe-key "$RUN_ID:safe_check_scan:1" \
  --boss-notified-at "" \
  --qr-updated-at 2026-04-02T12:01:11Z \
  --blocking-since 2026-04-02T12:01:11Z > "$D/result.json"

python3 - "$state_path" "$lock_path" "$lock_orig_path" "$D/result.json" <<'PY'
import json
import sys
from pathlib import Path

state    = json.loads(Path(sys.argv[1]).read_text())
lock_now = json.loads(Path(sys.argv[2]).read_text())
lock_orig= json.loads(Path(sys.argv[3]).read_text())
result   = json.loads(Path(sys.argv[4]).read_text())

# pipeline-state.json must have been written as blocked
assert state["phase"] == "awaiting_human", f"state.phase={state['phase']}"
assert state["step"] == 8, f"state.step={state['step']}"
assert state["current_step"] == "waiting_safe_check_scan", f"state.current_step={state['current_step']}"

# partial sync because lock update was skipped
assert state["control_plane_sync"] == "partial", f"state.control_plane_sync={state['control_plane_sync']}"

# result JSON
assert result["ok"] is True, f"result.ok={result['ok']}"
assert result["run_lock_updated"] is False, f"result.run_lock_updated={result['run_lock_updated']}"
assert "run_lock_run_id_mismatch" in result["run_lock_status"], \
    f"expected run_lock_run_id_mismatch in run_lock_status, got: {result['run_lock_status']}"
assert result["control_plane_sync"] == "partial", f"result.control_plane_sync={result['control_plane_sync']}"

# lock file must be completely unchanged (byte-identical content after JSON round-trip)
assert lock_now == lock_orig, \
    f"lock file was mutated!\nbefore={lock_orig}\nafter={lock_now}"

print("PASS")
PY

echo "Test 2: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 3: run_lock_missing – caller provides a lock path that does not exist
#   Assertions:
#   - exit code = 0
#   - state written as blocked
#   - control_plane_sync = partial
#   - run_lock_updated = false
#   - run_lock_status = "run_lock_missing"
#   - no lock file created at that path
# ────────────────────────────────────────────────────────────────────────────
echo "--- Test 3: run_lock_missing (no lock file, state durable write preserved) ---"

D="$TEST_ROOT/t3"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/nonexistent.lock.json"   # intentionally not created
qr_dir="$D/media/wechat-safe-check/$SANITIZED"
qr_path="$qr_dir/safe-check.png"
mkdir -p "$qr_dir"
printf 'fakepng' > "$qr_path"

cat > "$state_path" <<'JSON'
{
  "slug": "missing-lock-test",
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "phase": "finalizing",
  "current_step": "layout_done",
  "step": 7
}
JSON

python3 "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --run-id "$RUN_ID" \
  --waiting-for boss_scan \
  --required-user-action safe_check_scan \
  --current-step waiting_safe_check_scan \
  --phase awaiting_human \
  --safe-check-qr-path "$qr_path" \
  --note "missing lock test" \
  --relay-status pending_parent_forward \
  --relay-dedupe-key "$RUN_ID:safe_check_scan:1" \
  --boss-notified-at "" \
  --qr-updated-at 2026-04-02T12:01:11Z \
  --blocking-since 2026-04-02T12:01:11Z > "$D/result.json"

python3 - "$state_path" "$lock_path" "$D/result.json" <<'PY'
import json
import sys
from pathlib import Path

state      = json.loads(Path(sys.argv[1]).read_text())
lock_path  = Path(sys.argv[2])
result     = json.loads(Path(sys.argv[3]).read_text())

# pipeline-state.json must have been written as blocked
assert state["phase"] == "awaiting_human", f"state.phase={state['phase']}"
assert state["step"] == 8, f"state.step={state['step']}"
assert state["current_step"] == "waiting_safe_check_scan"

# partial sync because lock file was absent
assert state["control_plane_sync"] == "partial", f"state.control_plane_sync={state['control_plane_sync']}"

# result JSON
assert result["ok"] is True, f"result.ok={result['ok']}"
assert result["run_lock_updated"] is False, f"result.run_lock_updated={result['run_lock_updated']}"
assert result["run_lock_status"] == "run_lock_missing", \
    f"expected run_lock_missing, got: {result['run_lock_status']}"
assert result["control_plane_sync"] == "partial", f"result.control_plane_sync={result['control_plane_sync']}"

# script must NOT have created the lock file
assert not lock_path.exists(), f"lock file was unexpectedly created at {lock_path}"

print("PASS")
PY

echo "Test 3: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 4: run_lock_unparseable – lock file contains invalid JSON
#   Assertions:
#   - exit code = 0
#   - state written as blocked
#   - control_plane_sync = partial
#   - run_lock_updated = false
#   - run_lock_status contains "run_lock_unparseable"
#   - lock file content is byte-for-byte unchanged (bad bytes preserved)
# ────────────────────────────────────────────────────────────────────────────
echo "--- Test 4: run_lock_unparseable (invalid JSON, state durable write preserved) ---"

D="$TEST_ROOT/t4"
mkdir -p "$D"
state_path="$D/pipeline-state.json"
lock_path="$D/corrupt.lock.json"
lock_orig_path="$D/corrupt.lock.orig.json"
qr_dir="$D/media/wechat-safe-check/$SANITIZED"
qr_path="$qr_dir/safe-check.png"
mkdir -p "$qr_dir"
printf 'fakepng' > "$qr_path"

cat > "$state_path" <<'JSON'
{
  "slug": "unparseable-lock-test",
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "phase": "finalizing",
  "current_step": "layout_done",
  "step": 7
}
JSON

# Write deliberately broken JSON
printf '{ this is not valid json !!!' > "$lock_path"
cp "$lock_path" "$lock_orig_path"

python3 "$SCRIPT" \
  --state-path "$state_path" \
  --run-lock-path "$lock_path" \
  --run-id "$RUN_ID" \
  --waiting-for boss_scan \
  --required-user-action safe_check_scan \
  --current-step waiting_safe_check_scan \
  --phase awaiting_human \
  --safe-check-qr-path "$qr_path" \
  --note "unparseable lock test" \
  --relay-status pending_parent_forward \
  --relay-dedupe-key "$RUN_ID:safe_check_scan:1" \
  --boss-notified-at "" \
  --qr-updated-at 2026-04-02T12:01:11Z \
  --blocking-since 2026-04-02T12:01:11Z > "$D/result.json"

python3 - "$state_path" "$lock_path" "$lock_orig_path" "$D/result.json" <<'PY'
import sys
import json
from pathlib import Path

state     = json.loads(Path(sys.argv[1]).read_text())
lock_raw  = Path(sys.argv[2]).read_bytes()
orig_raw  = Path(sys.argv[3]).read_bytes()
result    = json.loads(Path(sys.argv[4]).read_text())

# pipeline-state.json must have been written as blocked
assert state["phase"] == "awaiting_human", f"state.phase={state['phase']}"
assert state["step"] == 8, f"state.step={state['step']}"
assert state["current_step"] == "waiting_safe_check_scan"

# partial sync because lock could not be parsed
assert state["control_plane_sync"] == "partial", f"state.control_plane_sync={state['control_plane_sync']}"

# result JSON
assert result["ok"] is True, f"result.ok={result['ok']}"
assert result["run_lock_updated"] is False, f"result.run_lock_updated={result['run_lock_updated']}"
assert "run_lock_unparseable" in result["run_lock_status"], \
    f"expected run_lock_unparseable in run_lock_status, got: {result['run_lock_status']}"
assert result["control_plane_sync"] == "partial", f"result.control_plane_sync={result['control_plane_sync']}"

# lock file must be completely unchanged
assert lock_raw == orig_raw, \
    f"lock file bytes changed!\nbefore={orig_raw!r}\nafter={lock_raw!r}"

print("PASS")
PY

echo "Test 4: PASS"

echo ""
echo "test_mark_publish_blocked.sh: ALL 4 TESTS PASSED"
