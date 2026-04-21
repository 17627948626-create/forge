#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/outline_gate.py"
TEST_ROOT="$(mktemp -d "$HOME/.openclaw/skills/wechat-article-forge/tests/tmp.outline_gate.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/bad-outline.md" <<'MD'
## 1. 先把误会掐掉
- [截图级段落位置]
- 这里要写 repo 结构

## 2. 收尾
- 结尾别升太大
- 最后一节只做两件事
MD

if python3 "$SCRIPT" "$TEST_ROOT/bad-outline.md" > "$TEST_ROOT/bad-result.json"; then
  echo "Expected outline gate failure, but command succeeded" >&2
  exit 1
fi

python3 - "$TEST_ROOT/bad-result.json" <<'PY'
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

python3 "$SCRIPT" "$TEST_ROOT/good-outline.md" > "$TEST_ROOT/good-result.json"
python3 - "$TEST_ROOT/good-result.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
assert result['ok'] is True
assert result['hard_fail'] is False
assert result['issues'] == []
print('PASS')
PY

echo "Test 2: PASS"
echo "test_outline_gate.sh: ALL TESTS PASSED"
