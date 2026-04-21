#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$HOME/.openclaw/skills/wechat-article-forge/scripts/publish_profile_preflight.py"
TEST_ROOT="$(mktemp -d "$HOME/.openclaw/skills/wechat-article-forge/tests/tmp.publish_profile_preflight.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

cat > "$TEST_ROOT/mcp-good.json" <<'JSON'
{
  "mcpServers": {
    "wenyan-mcp": {
      "command": "/usr/local/bin/wenyan-mcp"
    }
  }
}
JSON

cat > "$TEST_ROOT/mcp-bad.json" <<'JSON'
{
  "mcpServers": {
    "other": {
      "command": "/bin/true"
    }
  }
}
JSON

cat > "$TEST_ROOT/profiles.json" <<JSON
{
  "profiles": {
    "小龙虾有话说": {
      "wechat_author": "小龙虾有话说",
      "default_theme": "sspai",
      "published_log_path": "$TEST_ROOT/published.jsonl",
      "publisher": {
        "mcp_server": "wenyan-mcp",
        "mcp_config_file": "$TEST_ROOT/mcp-good.json",
        "mode": "remote"
      }
    },
    "坏配置": {
      "publisher": {
        "mcp_config_file": "$TEST_ROOT/mcp-bad.json"
      }
    }
  }
}
JSON

cat > "$TEST_ROOT/config.json" <<JSON
{
  "profiles_path": "$TEST_ROOT/profiles.json"
}
JSON

printf '{}' > "$TEST_ROOT/pipeline-state.json"
cat > "$TEST_ROOT/publish.md" <<'MD'
---
title: "测试标题"
author: "小龙虾有话说"
profile: "小龙虾有话说"
cover: "https://picsum.photos/1200/800"
theme: "sspai"
slug: "test-slug"
---

正文
MD

python3 "$SCRIPT" \
  --config-path "$TEST_ROOT/config.json" \
  --profile "小龙虾有话说" \
  --state-path "$TEST_ROOT/pipeline-state.json" \
  --publish-md "$TEST_ROOT/publish.md" > "$TEST_ROOT/result.json"

python3 - "$TEST_ROOT/result.json" "$TEST_ROOT/pipeline-state.json" <<'PY'
import json,sys
result=json.load(open(sys.argv[1]))
state=json.load(open(sys.argv[2]))
assert result['ok'] is True
assert result['profile'] == '小龙虾有话说'
assert result['mcp_config_file'].endswith('mcp-good.json')
assert result['wenyan_mcp_present'] is True
assert state['profile'] == '小龙虾有话说'
assert state['mcp_config_file'].endswith('mcp-good.json')
assert state['publish_profile_preflight']['status'] == 'ok'
assert state['publish_profile_preflight']['publish_md_checked'] is True
assert result['publish_frontmatter_checked'] is True
print('PASS')
PY

echo "Test 1: PASS"

if python3 "$SCRIPT" --config-path "$TEST_ROOT/config.json" --profile "不存在的号" >/dev/null 2>&1; then
  echo "Expected unknown profile failure, but command succeeded" >&2
  exit 1
fi

echo "Test 2: PASS"

if python3 "$SCRIPT" --config-path "$TEST_ROOT/config.json" --profile "坏配置" >/dev/null 2>&1; then
  echo "Expected wenyan-mcp missing failure, but command succeeded" >&2
  exit 1
fi

echo "Test 3: PASS"

cat > "$TEST_ROOT/bad-publish.md" <<'MD'
---
title: "测试标题"
author: "小龙虾有话说"
profile: "不上班也有Money"
cover: "https://picsum.photos/1200/800"
theme: "sspai"
slug: "test-slug"
---

正文
MD

if python3 "$SCRIPT" --config-path "$TEST_ROOT/config.json" --profile "小龙虾有话说" --publish-md "$TEST_ROOT/bad-publish.md" >/dev/null 2>&1; then
  echo "Expected publish.md profile mismatch failure, but command succeeded" >&2
  exit 1
fi

echo "Test 4: PASS"

echo "test_publish_profile_preflight.sh: ALL TESTS PASSED"
