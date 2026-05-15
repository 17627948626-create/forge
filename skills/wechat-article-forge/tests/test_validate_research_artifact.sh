#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/validate_research_artifact.py"
TEST_ROOT="$(make_test_root validate_research_artifact)"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/research-missing.json" <<'JSON'
{
  "why_now": "不到 24 小时拿到 539 stars、115 forks。",
  "anchors": [
    {
      "claim": "README 明确写可安装到 Claude Code、Hermes、Codex 等工具。",
      "evidence": [
        "原文写：『把我自己在用的内容创作 Skill，完整的，一字不改地开源了。』",
        "style_examples.md 是 16790 bytes"
      ],
      "source_urls": [
        "https://api.github.com/repos/demo/repo",
        "https://raw.githubusercontent.com/demo/repo/main/README.md"
      ]
    }
  ]
}
JSON

if "$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/research-missing.json" > "$TEST_ROOT/missing-result.json"; then
  echo "Expected research validator failure, but command succeeded" >&2
  exit 1
fi

"$PYTHON_BIN" - "$TEST_ROOT/missing-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['hard_fail'] is True
codes={x['code'] for x in result['issues']}
assert 'fact_records_missing' in codes
assert set(result['detected_categories']) >= {'api_snapshot','readme_claim','quote_mode','file_size_bytes'}
print('PASS')
PY

echo "Test 1: PASS"

cat > "$TEST_ROOT/research-good.json" <<'JSON'
{
  "why_now": "不到 24 小时拿到 539 stars、115 forks。",
  "anchors": [
    {
      "claim": "README 明确写可安装到 Claude Code、Hermes、Codex 等工具。",
      "evidence": [
        "原文写：『把我自己在用的内容创作 Skill，完整的，一字不改地开源了。』",
        "style_examples.md 是 16790 bytes"
      ],
      "source_urls": [
        "https://api.github.com/repos/demo/repo",
        "https://raw.githubusercontent.com/demo/repo/main/README.md"
      ]
    }
  ],
  "fact_records": [
    {
      "id": "F1",
      "kind": "api_snapshot",
      "observed_at": "2026-04-07T06:52:30Z",
      "needle": "539 stars、115 forks"
    },
    {
      "id": "F2",
      "kind": "readme_claim",
      "attribution_required": true,
      "needle": "可安装到 Claude Code、Hermes、Codex 等工具"
    },
    {
      "id": "F3",
      "quote_mode": "verbatim",
      "needle": "把我自己在用的内容创作 Skill，完整的，一字不改地开源了。"
    },
    {
      "id": "F4",
      "file_size_bytes": 16790,
      "unit": "bytes",
      "needle": "16790 bytes"
    }
  ]
}
JSON

"$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/research-good.json" > "$TEST_ROOT/good-result.json"
"$PYTHON_BIN" - "$TEST_ROOT/good-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['ok'] is True
assert result['hard_fail'] is False
assert result['issues'] == []
print('PASS')
PY

echo "Test 2: PASS"
cat > "$TEST_ROOT/research-nested.json" <<'JSON'
{
  "why_now": "截至 2026-04-07，API snapshot 显示 539 stars。",
  "anchors": [
    {
      "claim": "README 自称可安装到 Claude Code。",
      "evidence": ["原文写：『把我自己在用的内容创作 Skill，完整的，一字不改地开源了。』", "style_examples.md 是 16790 bytes"]
    }
  ],
  "fact_records": [],
  "evidence_contract": {
    "fact_records": [
      {"id":"F1","kind":"api_snapshot","observed_at":"2026-04-07T06:52:30Z","needle":"539 stars"},
      {"id":"F2","kind":"readme_claim","attribution_required":true,"needle":"可安装到 Claude Code"},
      {"id":"F3","quote_mode":"verbatim","needle":"把我自己在用的内容创作 Skill，完整的，一字不改地开源了。"},
      {"id":"F4","file_size_bytes":16790,"unit":"bytes","needle":"16790 bytes"}
    ]
  }
}
JSON

"$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/research-nested.json" > "$TEST_ROOT/nested-result.json"
"$PYTHON_BIN" - "$TEST_ROOT/nested-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['ok'] is True
assert result['hard_fail'] is False
assert result['fact_record_count'] == 4
print('PASS')
PY

echo "Test 3: PASS"
echo "test_validate_research_artifact.sh: ALL TESTS PASSED"
