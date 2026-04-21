#!/usr/bin/env bash
set -euo pipefail

AUDIT_SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/lineage_audit.py"
WRITE_SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/update_pipeline_lineage.py"
TEST_ROOT="$(mktemp -d "$HOME/.openclaw/skills/wechat-article-forge/tests/tmp.lineage_schema.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

# ────────────────────────────────────────────────────────────────────────────
# Test 1: wide-read lineage audit accepts legacy aliases when provenance exists
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t1"
mkdir -p "$D"
cat > "$D/pipeline-state.json" <<'JSON'
{
  "last_draft_file": "draft-v2.md",
  "last_review_file": "review-v2.json",
  "children": {
    "research": {
      "session_key": "s-research",
      "artifacts": ["research.json", "outline.md"],
      "status": "complete"
    },
    "writer_v2": {
      "session_key": "s-writer",
      "artifacts": ["draft-v2.md"],
      "status": "complete"
    },
    "reviewer_round2": {
      "session_key": "s-reviewer",
      "artifacts": ["review-v2.json"],
      "status": "complete"
    },
    "humanizer_v1": {
      "session_key": "s-human",
      "artifacts": ["final.md"],
      "status": "complete"
    },
    "layout_v1": {
      "session_key": "s-layout",
      "artifacts": ["final-layout.md"],
      "status": "complete"
    }
  },
  "artifact_provenance": {
    "research.json": {"producer_type": "child", "producer_step": "research", "session_key": "s-research", "model": "m-r"},
    "outline.md": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "draft-v2.md": {"producer_type": "child", "producer_step": "writer_v2", "session_key": "s-writer", "model": "m-w"},
    "review-v2.json": {"producer_type": "child", "producer_step": "reviewer_round2", "session_key": "s-reviewer", "model": "m-rev"},
    "final.md": {"producer_type": "child", "producer_step": "humanizer_v1", "session_key": "s-human", "model": "m-h"},
    "final-layout.md": {"producer_type": "child", "producer_step": "layout_v1", "session_key": "s-layout", "model": "m-l"}
  }
}
JSON

printf '{}' > "$D/research.json"
printf '## O\n' > "$D/outline.md"
printf 'draft\n' > "$D/draft-v2.md"
printf '{}' > "$D/review-v2.json"
printf 'final\n' > "$D/final.md"
printf 'layout\n' > "$D/final-layout.md"

python3 "$AUDIT_SCRIPT" "$D" --json --write-state > "$D/result.json"
python3 - "$D/result.json" "$D/pipeline-state.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
state=json.load(open(sys.argv[2]))
assert result['clean'] is True, result
assert result['schema_version'] == '2026-04-09.lineage-v2'
assert state['lineage_status'] == 'clean'
assert state['lineage_audited_at']
assert state['schema_version'] == '2026-04-09.lineage-v2'
assert sorted(state['children'].keys()) == ['humanizer', 'layout', 'researcher', 'reviewer', 'writer']
assert 'writer_v2' not in state['children']
assert 'reviewer_round2' not in state['children']
assert 'fact_checker_v1' not in state['children']
assert state['artifact_provenance']['draft-v2.md']['producer_step'] == 'writer'
assert state['artifact_provenance']['review-v2.json']['producer_step'] == 'reviewer'
print('PASS')
PY

echo "Test 1: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 2: strict-write helper canonicalizes aliases and rejects unknown steps
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t2"
mkdir -p "$D"
printf '{}' > "$D/pipeline-state.json"

python3 "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step reviewer_v2 \
  --session-key s-review \
  --model m-review \
  --artifacts review-v2.json > "$D/write-result.json"

python3 - "$D/pipeline-state.json" <<'PY'
import json,sys
state=json.load(open(sys.argv[1]))
assert list(state['children'].keys()) == ['reviewer']
assert state['children']['reviewer'][0]['artifacts'] == ['review-v2.json']
assert state['artifact_provenance']['review-v2.json']['producer_step'] == 'reviewer'
assert state['schema_version'] == '2026-04-09.lineage-v2'
print('PASS')
PY

echo "Test 2a: PASS"

if python3 "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step writer-lite \
  --session-key s-bad \
  --model m-bad \
  --artifacts bad.md >/dev/null 2>&1; then
  echo "Expected unknown step rejection, but command succeeded" >&2
  exit 1
fi

echo "Test 2b: PASS"

echo "test_lineage_schema.sh: ALL TESTS PASSED"
