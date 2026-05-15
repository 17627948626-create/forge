#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/outline_gate.py"
TEST_ROOT="$(make_test_root outline_gate)"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/bad-outline.md" <<'MD'
## 1. 先把误会掐掉
- [截图级段落位置]
- 这里要写 repo 结构

## 2. 收尾
- 结尾别升太大
- 最后一节只做两件事
MD

if "$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/bad-outline.md" > "$TEST_ROOT/bad-result.json"; then
  echo "Expected outline gate failure, but command succeeded" >&2
  exit 1
fi

"$PYTHON_BIN" - "$TEST_ROOT/bad-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['hard_fail'] is True
assert result['scope'] == 'outline_shape_only'
codes={x['code'] for x in result['issues']}
assert 'placeholder_label' in codes
assert 'backstage_cue' in codes
print('PASS')
PY

echo "Test 1: PASS"

cat > "$TEST_ROOT/good-outline.md" <<'MD'
## 1. 先把误会掐掉
- 把 repo 结构写实，说明这不是单段 prompt，而是一整套方法系统。

## 2. 收尾
- 回扣为什么今天值得看。
- 回扣方法可开源、神之一手不可开源。
MD

"$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/good-outline.md" > "$TEST_ROOT/good-result.json"
"$PYTHON_BIN" - "$TEST_ROOT/good-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['ok'] is True
assert result['hard_fail'] is False
assert result['issues'] == []
print('PASS')
PY

echo "Test 2: PASS"
echo "test_outline_gate.sh: ALL TESTS PASSED"
