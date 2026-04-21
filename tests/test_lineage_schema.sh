#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
AUDIT_SCRIPT="$REPO_ROOT/scripts/lineage_audit.py"
WRITE_SCRIPT="$REPO_ROOT/scripts/update_pipeline_lineage.py"
TEST_ROOT="$(make_test_root lineage_schema)"
trap 'rm -rf "$TEST_ROOT"' EXIT

sha256_file() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], 'rb') as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b''):
        h.update(chunk)
print(h.hexdigest())
PY
}

# ────────────────────────────────────────────────────────────────────────────
# Test 1: audit wide-reads legacy Humanizer aliases but active lineage is
# Researcher -> Writer -> Reviewer -> Layout, anchored to reviewed_draft_file.
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t1"
mkdir -p "$D"
printf '{}' > "$D/research.json"
printf '## O\n' > "$D/outline.md"
printf 'draft\n' > "$D/draft-v2.md"
printf '{}' > "$D/review-v2.json"
printf 'legacy final\n' > "$D/final.md"
printf 'layout\n' > "$D/final-layout.md"
DRAFT_HASH="$(sha256_file "$D/draft-v2.md")"

cat > "$D/pipeline-state.json" <<JSON
{
  "last_draft_file": "draft-v2.md",
  "last_review_file": "review-v2.json",
  "reviewed_draft_file": "draft-v2.md",
  "reviewed_draft_sha256": "$DRAFT_HASH",
  "content_finalized_by": "reviewer",
  "content_final_artifact": "draft-v2.md",
  "layout_input_file": "draft-v2.md",
  "layout_input_sha256": "$DRAFT_HASH",
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

"$PYTHON_BIN" "$AUDIT_SCRIPT" "$D" --json --write-state > "$D/result.json"
"$PYTHON_BIN" - "$D/result.json" "$D/pipeline-state.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
state=json.load(open(sys.argv[2]))
assert result['clean'] is True, result
assert result['schema_version'] == '2026-04-09.lineage-v2'
assert result['publish_candidate'] == 'final-layout.md'
assert state['lineage_status'] == 'clean'
assert state['lineage_audited_at']
assert state['schema_version'] == '2026-04-09.lineage-v2'
assert sorted(state['children'].keys()) == ['layout', 'researcher', 'reviewer', 'writer']
assert 'humanizer' not in state['children']
assert 'final.md' not in state['artifact_provenance']
assert state['artifact_provenance']['draft-v2.md']['producer_step'] == 'writer'
assert state['artifact_provenance']['review-v2.json']['producer_step'] == 'reviewer'
assert state['artifact_provenance']['final-layout.md']['producer_step'] == 'layout'
assert state['content_finalized_by'] == 'reviewer'
assert state['content_final_artifact'] == 'draft-v2.md'
print('PASS')
PY

echo "Test 1: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 2: strict-write helper canonicalizes aliases, rejects inactive Humanizer,
# and records Layout's reviewed-draft input identity.
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t2"
mkdir -p "$D"
printf 'draft\n' > "$D/draft-v2.md"
printf 'layout\n' > "$D/final-layout.md"
cat > "$D/pipeline-state.json" <<'JSON'
{
  "last_draft_file": "draft-v2.md"
}
JSON

"$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step reviewer_v2 \
  --session-key s-review \
  --model m-review \
  --artifacts review-v2.json \
  --approved-artifact draft-v2.md > "$D/write-review-result.json"

"$PYTHON_BIN" - "$D/pipeline-state.json" "$D/draft-v2.md" <<'PY'
import hashlib,json,sys
state=json.load(open(sys.argv[1]))
expected=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest()
assert list(state['children'].keys()) == ['reviewer']
assert state['children']['reviewer'][0]['artifacts'] == ['review-v2.json']
assert state['artifact_provenance']['review-v2.json']['producer_step'] == 'reviewer'
assert state['reviewed_draft_file'] == 'draft-v2.md'
assert state['reviewed_draft_sha256'] == expected
assert state['content_finalized_by'] == 'reviewer'
assert state['content_final_artifact'] == 'draft-v2.md'
assert state['schema_version'] == '2026-04-09.lineage-v2'
print('PASS')
PY

echo "Test 2a: PASS"

if "$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step layout_v1 \
  --session-key s-layout-missing \
  --model m-layout \
  --artifacts final-layout.md >/dev/null 2>&1; then
  echo "Expected layout write without input-artifact to fail, but command succeeded" >&2
  exit 1
fi

echo "Test 2b: PASS"

if "$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step layout_v1 \
  --session-key s-layout-bad \
  --model m-layout \
  --artifacts final-layout.md \
  --input-artifact missing-draft.md >/dev/null 2>&1; then
  echo "Expected layout write with missing input-artifact to fail, but command succeeded" >&2
  exit 1
fi

echo "Test 2c: PASS"

"$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step layout_v1 \
  --session-key s-layout \
  --model m-layout \
  --artifacts final-layout.md \
  --input-artifact draft-v2.md > "$D/write-layout-result.json"

"$PYTHON_BIN" - "$D/pipeline-state.json" "$D/draft-v2.md" <<'PY'
import hashlib,json,sys
state=json.load(open(sys.argv[1]))
expected=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest()
assert state['layout_input_file'] == 'draft-v2.md'
assert state['layout_input_sha256'] == expected
assert state['artifact_provenance']['final-layout.md']['producer_step'] == 'layout'
print('PASS')
PY

echo "Test 2d: PASS"

if "$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step writer-lite \
  --session-key s-bad \
  --model m-bad \
  --artifacts bad.md >/dev/null 2>&1; then
  echo "Expected unknown step rejection, but command succeeded" >&2
  exit 1
fi

echo "Test 2e: PASS"

if "$PYTHON_BIN" "$WRITE_SCRIPT" \
  --state-path "$D/pipeline-state.json" \
  --step humanizer_v1 \
  --session-key s-human \
  --model m-human \
  --artifacts final.md >/dev/null 2>&1; then
  echo "Expected inactive Humanizer rejection, but command succeeded" >&2
  exit 1
fi

echo "Test 2f: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 3: audit fails closed when Layout cannot prove it consumed the exact
# Reviewer-approved draft.
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t3"
mkdir -p "$D"
printf '{}' > "$D/research.json"
printf '## O\n' > "$D/outline.md"
printf 'draft\n' > "$D/draft-v2.md"
printf '{}' > "$D/review-v2.json"
printf 'layout\n' > "$D/final-layout.md"
DRAFT_HASH="$(sha256_file "$D/draft-v2.md")"

cat > "$D/pipeline-state.json" <<JSON
{
  "last_draft_file": "draft-v2.md",
  "last_review_file": "review-v2.json",
  "reviewed_draft_file": "draft-v2.md",
  "reviewed_draft_sha256": "$DRAFT_HASH",
  "children": {
    "researcher": [{"session_key": "s-research", "artifacts": ["research.json", "outline.md"], "status": "done"}],
    "writer": [{"session_key": "s-writer", "artifacts": ["draft-v2.md"], "status": "done"}],
    "reviewer": [{"session_key": "s-reviewer", "artifacts": ["review-v2.json"], "status": "done"}],
    "layout": [{"session_key": "s-layout", "artifacts": ["final-layout.md"], "status": "done"}]
  },
  "artifact_provenance": {
    "research.json": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "outline.md": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "draft-v2.md": {"producer_type": "child", "producer_step": "writer", "session_key": "s-writer", "model": "m-w"},
    "review-v2.json": {"producer_type": "child", "producer_step": "reviewer", "session_key": "s-reviewer", "model": "m-rev"},
    "final-layout.md": {"producer_type": "child", "producer_step": "layout", "session_key": "s-layout", "model": "m-l"}
  }
}
JSON

if "$PYTHON_BIN" "$AUDIT_SCRIPT" "$D" --json > "$D/result.json"; then
  echo "Expected layout input contract failure, but audit passed" >&2
  exit 1
fi

"$PYTHON_BIN" - "$D/result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['clean'] is False, result
assert result['repair_action'] == 'rerun_layout', result
assert result['last_clean_step'] == 'reviewer', result
assert any('layout_input_file' in issue for issue in result['issues']), result
print('PASS')
PY

echo "Test 3: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 4: audit fails closed when reviewer-approved bytes were never persisted
# at review time, even if last_draft_file and layout input point to the same
# current draft.
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t4"
mkdir -p "$D"
printf '{}' > "$D/research.json"
printf '## O\n' > "$D/outline.md"
printf 'draft old\n' > "$D/draft-v2.md"
printf 'draft newer\n' > "$D/draft-v3.md"
printf '{}' > "$D/review-v2.json"
printf 'layout\n' > "$D/final-layout.md"
DRAFT_HASH="$(sha256_file "$D/draft-v3.md")"

cat > "$D/pipeline-state.json" <<JSON
{
  "last_draft_file": "draft-v3.md",
  "last_review_file": "review-v2.json",
  "layout_input_file": "draft-v3.md",
  "layout_input_sha256": "$DRAFT_HASH",
  "children": {
    "researcher": [{"session_key": "s-research", "artifacts": ["research.json", "outline.md"], "status": "done"}],
    "writer": [{"session_key": "s-writer", "artifacts": ["draft-v3.md"], "status": "done"}],
    "reviewer": [{"session_key": "s-reviewer", "artifacts": ["review-v2.json"], "status": "done"}],
    "layout": [{"session_key": "s-layout", "artifacts": ["final-layout.md"], "status": "done"}]
  },
  "artifact_provenance": {
    "research.json": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "outline.md": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "draft-v3.md": {"producer_type": "child", "producer_step": "writer", "session_key": "s-writer", "model": "m-w"},
    "review-v2.json": {"producer_type": "child", "producer_step": "reviewer", "session_key": "s-reviewer", "model": "m-rev"},
    "final-layout.md": {"producer_type": "child", "producer_step": "layout", "session_key": "s-layout", "model": "m-l"}
  }
}
JSON

if "$PYTHON_BIN" "$AUDIT_SCRIPT" "$D" --json > "$D/result.json"; then
  echo "Expected reviewer-approved hash enforcement failure, but audit passed" >&2
  exit 1
fi

"$PYTHON_BIN" - "$D/result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['clean'] is False, result
assert result['repair_action'] == 'rerun_reviewer', result
assert any('reviewed_draft_file' in issue or 'reviewed_draft_sha256' in issue for issue in result['issues']), result
print('PASS')
PY

echo "Test 4: PASS"

# ────────────────────────────────────────────────────────────────────────────
# Test 5: stale legacy publish_file must not override the active reviewer/layout
# authority chain.
# ────────────────────────────────────────────────────────────────────────────
D="$TEST_ROOT/t5"
mkdir -p "$D"
printf '{}' > "$D/research.json"
printf '## O\n' > "$D/outline.md"
printf 'draft\n' > "$D/draft-v2.md"
printf '{}' > "$D/review-v2.json"
DRAFT_HASH="$(sha256_file "$D/draft-v2.md")"

cat > "$D/pipeline-state.json" <<JSON
{
  "last_draft_file": "draft-v2.md",
  "last_review_file": "review-v2.json",
  "reviewed_draft_file": "draft-v2.md",
  "reviewed_draft_sha256": "$DRAFT_HASH",
  "content_finalized_by": "reviewer",
  "content_final_artifact": "draft-v2.md",
  "layout_skipped": true,
  "publish_file": "final.md",
  "children": {
    "researcher": [{"session_key": "s-research", "artifacts": ["research.json", "outline.md"], "status": "done"}],
    "writer": [{"session_key": "s-writer", "artifacts": ["draft-v2.md"], "status": "done"}],
    "reviewer": [{"session_key": "s-reviewer", "artifacts": ["review-v2.json"], "status": "done"}]
  },
  "artifact_provenance": {
    "research.json": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "outline.md": {"producer_type": "child", "producer_step": "researcher", "session_key": "s-research", "model": "m-r"},
    "draft-v2.md": {"producer_type": "child", "producer_step": "writer", "session_key": "s-writer", "model": "m-w"},
    "review-v2.json": {"producer_type": "child", "producer_step": "reviewer", "session_key": "s-reviewer", "model": "m-rev"}
  }
}
JSON

"$PYTHON_BIN" "$AUDIT_SCRIPT" "$D" --json > "$D/result.json"

"$PYTHON_BIN" - "$D/result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['clean'] is True, result
assert result['publish_candidate'] == 'draft-v2.md', result
print('PASS')
PY

echo "Test 5: PASS"

echo "test_lineage_schema.sh: ALL TESTS PASSED"
