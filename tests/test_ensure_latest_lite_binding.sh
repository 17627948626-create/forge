#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/ensure_latest_lite_binding.py"
PRECHECK="$REPO_ROOT/scripts/writer_lite_preflight.py"
TEST_ROOT="$(make_test_root ensure_latest_lite_binding)"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/draft-v2.md" <<'MD'
## 标题
这是一版旧稿。
MD

cat > "$TEST_ROOT/draft-v4.md" <<'MD'
## 标题
这是最新版稿子，内容里没有脚手架，也没有动态数字。
MD

cat > "$TEST_ROOT/research.json" <<'JSON'
{
  "fact_records": []
}
JSON

cat > "$TEST_ROOT/writer-lite-brief.json" <<'JSON'
{
  "draft_version": "draft-v1",
  "updated_at": "2026-04-07T12:00:00Z",
  "change_reason": "seed"
}
JSON

"$PYTHON_BIN" "$PRECHECK" "$TEST_ROOT/draft-v2.md" \
  --research-path "$TEST_ROOT/research.json" \
  --brief-path "$TEST_ROOT/writer-lite-brief.json" \
  --output "$TEST_ROOT/writer-lite-check.json" \
  --check-mode blocking > /dev/null

cat > "$TEST_ROOT/pipeline-state.json" <<JSON
{
  "last_draft_file": "draft-v4.md",
  "updated_at": "2026-04-07T12:00:00Z"
}
JSON

"$PYTHON_BIN" "$SCRIPT" \
  --state-path "$TEST_ROOT/pipeline-state.json" \
  --mode rerun \
  --check-mode advisory \
  --change-reason "latest draft changed; refresh lite preflight binding" > "$TEST_ROOT/binding.stdout.json"

cmp -s "$TEST_ROOT/binding.stdout.json" "$TEST_ROOT/writer-lite-binding.json"

"$PYTHON_BIN" - "$TEST_ROOT" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
state = json.load(open(root / 'pipeline-state.json'))
check = json.load(open(root / 'writer-lite-check.json'))
binding = json.load(open(root / 'writer-lite-binding.json'))
expected_sha = hashlib.sha256(open(root / 'draft-v4.md', 'rb').read()).hexdigest()
assert binding['status'] == 'rerun_completed'
assert binding['match'] is True
assert binding['previous_check_draft_version'] == 'draft-v2'
assert binding['latest_check_draft_version'] == 'draft-v4'
assert binding['latest_check_draft_sha256'] == expected_sha
assert check['draft_version'] == 'draft-v4'
assert check['input_fingerprints']['draft_sha256'] == expected_sha
assert state['lite_preflight']['binding_status'] == 'rerun_completed'
assert state['lite_preflight']['match'] is True
assert state['lite_preflight']['previous_check_draft_version'] == 'draft-v2'
assert state['lite_preflight']['latest_check_draft_sha256'] == expected_sha
print('PASS')
PY

echo "Test 1: PASS"

cat > "$TEST_ROOT/draft-v5.md" <<'MD'
## 标题
[截图级段落位置]
MD

"$PYTHON_BIN" - "$TEST_ROOT/pipeline-state.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
state = json.loads(path.read_text())
state['last_draft_file'] = 'draft-v5.md'
path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
PY

if "$PYTHON_BIN" "$SCRIPT" \
  --state-path "$TEST_ROOT/pipeline-state.json" \
  --mode rerun \
  --check-mode blocking \
  --change-reason "latest draft changed; refresh lite preflight binding" > "$TEST_ROOT/binding-fail.stdout.json"; then
  echo "Expected blocking rerun to fail when refreshed preflight hard-fails" >&2
  exit 1
fi

"$PYTHON_BIN" - "$TEST_ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
state = json.load(open(root / 'pipeline-state.json'))
check = json.load(open(root / 'writer-lite-check.json'))
binding = json.load(open(root / 'writer-lite-binding.json'))
assert binding['status'] == 'rerun_completed_preflight_failed'
assert binding['match'] is True
assert binding['resolution']['preflight_returncode'] == 2
assert binding['resolution']['preflight_hard_fail'] is True
assert check['draft_version'] == 'draft-v5'
assert check['hard_fail'] is True
assert state['lite_preflight']['binding_status'] == 'rerun_completed_preflight_failed'
assert state['lite_preflight']['match'] is True
print('PASS')
PY

echo "Test 2: PASS"
echo "test_ensure_latest_lite_binding.sh: ALL TESTS PASSED"
