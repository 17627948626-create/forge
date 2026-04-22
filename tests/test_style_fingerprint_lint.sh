#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/style_fingerprint_lint.py"
TEST_ROOT="$(make_test_root style_fingerprint_lint)"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/draft-generic.md" <<'MD'
随着AI的发展，行业正在发生深刻变化。

值得注意的是，这说明了问题的复杂性。具体来说，这会带来很多深远影响。换言之，我们必须重新思考。

值得注意的是，这说明了问题的复杂性。具体来说，这会带来很多深远影响。换言之，我们必须重新思考。

总之，这件事值得我们持续关注。未来已来，我们都要拥抱变化。
MD

if "$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/draft-generic.md" \
  --output "$TEST_ROOT/style-lint-generic.json" \
  --check-mode blocking > "$TEST_ROOT/stdout-generic.json"; then
  echo "Expected style lint failure, but command succeeded" >&2
  exit 1
fi

cmp -s "$TEST_ROOT/stdout-generic.json" "$TEST_ROOT/style-lint-generic.json"

"$PYTHON_BIN" - "$TEST_ROOT/style-lint-generic.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding='utf-8'))
codes = {issue["code"] for issue in result["issues"]}
assert result["ok"] is False
assert result["blocking"] is True
assert result["artifact_contract"] == "script_generated_only"
assert "opening_interchangeability" in codes
assert "transition_template_dependence" in codes
assert "ending_sloganism" in codes
assert result["style_scope"] == "authorial_presence_and_template_dependence_only"
assert result["max_pre_review_bounces"] == 1
print("PASS")
PY

cat > "$TEST_ROOT/draft-natural.md" <<'MD'
如果你这两天也被 Agent 演示刷屏，先别急着站队。真正值得看的，不是热闹本身，而是热闹背后的代价和门槛。

问题到这里才刚开始。因为一旦把场景放回真实业务里，你会发现纸面上的优势很快就会碰到成本、协作和稳定性。

很多内容看上去信息很多，真落到手上，能用的其实没几句。

最后留给团队的，不是一个抽象态度题，而是一个很具体的选择题：你接下来准备先补判断，还是先补动作。
MD

"$PYTHON_BIN" "$SCRIPT" "$TEST_ROOT/draft-natural.md" \
  --output "$TEST_ROOT/style-lint-natural.json" \
  --check-mode blocking > "$TEST_ROOT/stdout-natural.json"

"$PYTHON_BIN" - "$TEST_ROOT/style-lint-natural.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding='utf-8'))
assert result["ok"] is True
assert result["blocking"] is False
assert result["issues"] == []
print("PASS")
PY

echo "test_style_fingerprint_lint.sh: ALL TESTS PASSED"
