#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/build_voice_pack.py"
TEST_ROOT="$(make_test_root build_voice_pack)"
trap 'rm -rf "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/articles"

cat > "$TEST_ROOT/SOUL.md" <<'MD'
# SOUL

我是一个 AI 作者，但不靠身份设定硬撑全篇。
如果 AI 身份能让判断更锋利，可以直接写出来。
不要写“随着AI的发展”这种空话。
也不要高频使用“不是……而是……”。
MD

cat > "$TEST_ROOT/AGENTS.md" <<'MD'
# AGENTS

写作必须有明确判断，先把结论放前面。
开头不要寒暄，不要背景铺垫半天。
结尾必须落到具体代价、选择或下一步，不能写成口号。
MD

cat > "$TEST_ROOT/articles/a1.md" <<'MD'
---
title: 真正值钱的，不是模型会不会说话
---

很多人盯着模型会不会聊天，但真正决定结果的，往往是它能不能进到真实工作流里。

问题到这里才刚开始。因为一旦把场景放回公司流程，你会发现纸面上的能力很快就撞上成本、协作和责任边界。

说白了，会回答问题不稀缺，能在混乱现场里稳定交付才稀缺。

最后真正留给团队的，不是一个抽象态度题，而是一个很具体的选择题：你准备先补判断，还是先补动作。
MD

cat > "$TEST_ROOT/articles/a2.md" <<'MD'
---
title: 这波 Agent 热，不该只看演示视频
---

如果你这两天也被 Agent 演示刷屏，先别急着站队。真正值得看的，不是热闹本身，而是热闹背后的代价和门槛。

再往下看一层，决定成败的往往不是模型参数，而是你有没有把接入、维护和兜底机制一起算进去。

问题到这里才刚开始。因为真正难的不是演示视频，而是把它放进日常工作流以后谁来兜底。

很多内容看上去信息很多，真落到手上，能用的其实没几句。

你现在未必要立刻下注，但至少该知道，真正值得警惕和真正值得下注的，已经开始分叉了。
MD

"$PYTHON_BIN" "$SCRIPT" \
  --article "$TEST_ROOT/articles/a1.md" \
  --article "$TEST_ROOT/articles/a2.md" \
  --persona-file "$TEST_ROOT/SOUL.md" \
  --persona-file "$TEST_ROOT/AGENTS.md" \
  --voice-pack-output "$TEST_ROOT/voice-pack.json" \
  --voice-profile-output "$TEST_ROOT/voice-profile.json"

"$PYTHON_BIN" - "$TEST_ROOT/voice-pack.json" "$TEST_ROOT/voice-profile.json" <<'PY'
import json, sys
voice_pack = json.load(open(sys.argv[1], encoding='utf-8'))
voice_profile = json.load(open(sys.argv[2], encoding='utf-8'))

assert voice_pack["meta"]["article_count"] == 2
assert voice_pack["persona"]["persona_mode"] == "ai_native"
assert len(voice_pack["openings"]) >= 2
assert len(voice_pack["turns"]) >= 1
assert len(voice_pack["endings"]) >= 2
assert len(voice_pack["sharp_lines"]) >= 1
assert "openings" in voice_pack["anti_examples"]
assert "transitions" in voice_pack["anti_examples"]
assert "endings" in voice_pack["anti_examples"]
assert "随着AI的发展" in voice_pack["avoid_phrases"]
assert "不是……而是……" in voice_pack["avoid_phrases"]
assert isinstance(voice_pack["prompt_injection"], str) and voice_pack["prompt_injection"]
assert not any(phrase.startswith("问题到这里才刚") for phrase in voice_pack["signature_phrases"])

assert voice_profile["meta"]["article_count"] == 2
assert voice_profile["persona"]["persona_mode"] == "ai_native"
assert "rhythm" in voice_profile
assert "structure" in voice_profile
assert "writing_prompt_injection" in voice_profile
print("PASS")
PY

echo "test_build_voice_pack.sh: ALL TESTS PASSED"
