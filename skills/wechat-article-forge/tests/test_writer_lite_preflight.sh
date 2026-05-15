#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/writer_lite_preflight.py"
TEST_ROOT="$(make_test_root writer_lite_preflight)"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/research.json" <<'JSON'
{
  "fact_records": [
    {
      "id": "F1",
      "kind": "api_snapshot",
      "needle": "539 stars",
      "claim": "539 stars",
      "observed_at": null
    },
    {
      "id": "F2",
      "quote_mode": "paraphrase_only",
      "needle": "真正被公开竞争的，不是几段 prompt"
    },
    {
      "id": "F3",
      "kind": "readme_claim",
      "attribution_required": true,
      "needle": "可安装到 Claude Code、Hermes、Codex 等工具"
    },
    {
      "id": "F4",
      "file_size_bytes": 16790,
      "unit": "bytes",
      "needle": "16790"
    }
  ]
}
JSON

cat > "$TEST_ROOT/draft-v2.md" <<'MD'
## 开头
这个仓库 539 stars，已经说明一切。
[截图级段落位置]
他原话说：“真正被公开竞争的，不是几段 prompt”。
这个项目可安装到 Claude Code、Hermes、Codex 等工具，已经证明它是成熟标准。
其中一份资料大概有 16790 字。
MD

if "$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/draft-v2.md" \
  --research-path "$TEST_ROOT/research.json" \
  --output "$TEST_ROOT/writer-lite-check.json" \
  --check-mode blocking > "$TEST_ROOT/stdout.json"; then
  echo "Expected blocking preflight failure, but command succeeded" >&2
  exit 1
fi

cmp -s "$TEST_ROOT/stdout.json" "$TEST_ROOT/writer-lite-check.json"

"$PYTHON_BIN" - "$TEST_ROOT/writer-lite-check.json" "$TEST_ROOT/draft-v2.md" "$TEST_ROOT/research.json" <<'PY'
import hashlib, json, sys
result=json.load(open(sys.argv[1]))
draft_path=sys.argv[2]
research_path=sys.argv[3]
assert result['hard_fail'] is True
assert result['ok'] is False
assert result['artifact_contract'] == 'script_generated_only'
assert result['blocking_enforced'] is True
assert result['generated_at'] == result['updated_at']
codes=set(result['hard_fail_reasons'])
expected={
  'placeholder_residue',
  'dynamic_number_missing_timepoint',
  'paraphrase_only_rendered_as_quote',
  'readme_claim_presented_as_verified_fact',
  'bytes_misread_as_human_text_units',
  'api_snapshot_missing_observed_at',
}
missing=expected-codes
assert not missing, missing
assert result['preflight_scope'] == 'mechanical_red_lights_only'
assert result['style_suggestions'] == []
assert result['max_pre_review_bounces'] == 1
assert result['generator']['name'] == 'writer_lite_preflight.py'
assert result['input_fingerprints']['draft_path'] == draft_path
assert result['input_fingerprints']['research_path'] == research_path
assert result['input_fingerprints']['draft_sha256'] == hashlib.sha256(open(draft_path,'rb').read()).hexdigest()
assert result['input_fingerprints']['research_sha256'] == hashlib.sha256(open(research_path,'rb').read()).hexdigest()
print('PASS')
PY

echo "Test 1: PASS"

cat > "$TEST_ROOT/research-nested.json" <<'JSON'
{
  "fact_records": [],
  "evidence_contract": {
    "fact_records": [
      {
        "id": "F-nested",
        "quote_mode": "paraphrase_only",
        "needle": "只能转述这一句"
      }
    ]
  }
}
JSON

cat > "$TEST_ROOT/draft-v3.md" <<'MD'
## 开头
他写道：『只能转述这一句』。
MD

if "$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/draft-v3.md" \
  --research-path "$TEST_ROOT/research-nested.json" \
  --output "$TEST_ROOT/writer-lite-check-nested.json" \
  --check-mode blocking > "$TEST_ROOT/stdout-nested.json"; then
  echo "Expected nested paraphrase-only quote failure, but command succeeded" >&2
  exit 1
fi

"$PYTHON_BIN" - "$TEST_ROOT/writer-lite-check-nested.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
codes=set(result['hard_fail_reasons'])
assert 'paraphrase_only_rendered_as_quote' in codes
assert result['ok'] is False
print('PASS')
PY

echo "Test 2: PASS"
echo "test_writer_lite_preflight.sh: ALL TESTS PASSED"
