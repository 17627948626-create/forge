#!/usr/bin/env bash
# 远程发布文章到微信公众号草稿箱
# 兼容新版 wenyan-mcp：直接调用 publish_article(file=...)
# 支持可选 profile：为多公众号场景切换作者、主题、MCP 配置与发布台账

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${SKILL_ROOT}/wechat.env"
MCP_CONFIG_FILE_ENV="${MCP_CONFIG_FILE:-}"
WORKSPACE_ROOT="${WECHAT_ARTICLE_WRITER_ROOT:-}"
PROFILES_FILE_RAW="${WECHAT_PROFILES_FILE:-}"
MCP_CONFIG_FILE_RAW="$MCP_CONFIG_FILE_ENV"
DEFAULT_THEME="sspai"
DEFAULT_COVER_URL="https://picsum.photos/1200/800"
DEFAULT_MCP_SERVER="wenyan-mcp"
DEFAULT_PUBLISHED_LOG_PATH=""

expand_path() {
  python3 - <<'PY' "$1"
import os, sys
print(os.path.expandvars(os.path.expanduser(sys.argv[1])))
PY
}

resolve_path_from_base() {
  python3 - <<'PY' "$1" "$2"
import os, pathlib, sys
raw, base = sys.argv[1], sys.argv[2]
p = pathlib.Path(os.path.expandvars(os.path.expanduser(raw)))
if not p.is_absolute():
    p = pathlib.Path(base) / p
print(p.resolve())
PY
}

infer_workspace_root() {
  python3 - <<'PY' "$1"
import pathlib, sys
raw = sys.argv[1]
candidates = []
if raw:
    p = pathlib.Path(raw).expanduser().resolve()
    candidates.append(p if p.is_dir() else p.parent)
candidates.append(pathlib.Path.cwd().resolve())
for start in candidates:
    for p in [start, *start.parents]:
        if p.name == "wechat-article-writer" and (p / "profiles.json").exists():
            print(p)
            raise SystemExit(0)
print("")
PY
}

PROFILES_FILE=""
MCP_CONFIG_FILE=""
refresh_runtime_paths() {
  if [ -z "$WORKSPACE_ROOT" ]; then
    WORKSPACE_ROOT="$(infer_workspace_root "${FILE_PATH:-}")"
  fi
  if [ -z "$WORKSPACE_ROOT" ]; then
    echo "❌ 无法推断 article workspace。请设置 WECHAT_ARTICLE_WRITER_ROOT=<...>/wechat-article-writer。"
    exit 1
  fi
  PROFILES_FILE_RAW="${WECHAT_PROFILES_FILE:-${WORKSPACE_ROOT}/profiles.json}"
  MCP_CONFIG_FILE_RAW="$MCP_CONFIG_FILE_ENV"
  PROFILES_FILE="$(expand_path "$PROFILES_FILE_RAW")"
  if [ -n "$MCP_CONFIG_FILE_RAW" ]; then
    MCP_CONFIG_FILE="$(expand_path "$MCP_CONFIG_FILE_RAW")"
  else
    MCP_CONFIG_FILE=""
  fi
  DEFAULT_PUBLISHED_LOG_PATH="${WORKSPACE_ROOT}/published-log.jsonl"
}

check_deps() {
  local missing=0
  for cmd in mcporter jq curl; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "❌ 缺少依赖: $cmd"
      missing=1
    fi
  done
  if [ "$missing" -eq 1 ]; then
    echo "请先安装缺失依赖后再试。"
    exit 1
  fi
}

load_optional_env() {
  if [ -f "$CONFIG_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
  fi
}

show_help() {
  cat <<EOF
Usage: $(basename "$0") <path/to/article.md> [theme_id] <公众号名称>

Examples:
  $(basename "$0") ./my-post.md sspai 不上班也有Money
  $(basename "$0") ./my-post.md sspai 小龙虾有话说

Notes:
  - 当前脚本适配新版 wenyan-mcp，直接调用 publish_article。
  - 如远程 MCP 已托管公众号凭证，则无需本地传入 WECHAT_APP_ID / WECHAT_APP_SECRET。
  - MCP 配置文件从 <article-workspace>/profiles.json 的 publisher.mcp_config_file 读取。
  - 第 3 个参数必须显式填写公众号名称（与 profiles.json 中的 key 完全一致）。
EOF
}

resolve_profile() {
  local profile_name="$1"
  if [ -z "$profile_name" ]; then
    return 0
  fi

  if [ ! -f "$PROFILES_FILE" ]; then
    echo "❌ 找不到 profile 配置文件: $PROFILES_FILE"
    echo "请创建 profiles.json，或通过 WECHAT_PROFILES_FILE 指定路径。"
    exit 1
  fi

  if ! jq -e . "$PROFILES_FILE" >/dev/null 2>&1; then
    echo "❌ profile 配置文件不是合法 JSON: $PROFILES_FILE"
    exit 1
  fi

  if ! jq -e --arg p "$profile_name" '.profiles[$p]' "$PROFILES_FILE" >/dev/null 2>&1; then
    echo "❌ 未找到公众号 profile: $profile_name"
    echo "可用 profiles:"
    jq -r '.profiles | keys[]?' "$PROFILES_FILE" | sed 's/^/  - /'
    exit 1
  fi

  local theme_from_profile
  local author_from_profile
  local mcp_config_from_profile
  local mcp_server_from_profile
  local published_log_from_profile
  local wechat_app_id_from_profile
  local wechat_app_secret_from_profile

  theme_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].default_theme // empty' "$PROFILES_FILE")"
  author_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].wechat_author // empty' "$PROFILES_FILE")"
  mcp_config_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].publisher.mcp_config_file // empty' "$PROFILES_FILE")"
  mcp_server_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].publisher.mcp_server // empty' "$PROFILES_FILE")"
  published_log_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].published_log_path // empty' "$PROFILES_FILE")"
  wechat_app_id_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].publisher.wechat_app_id // empty' "$PROFILES_FILE")"
  wechat_app_secret_from_profile="$(jq -r --arg p "$profile_name" '.profiles[$p].publisher.wechat_app_secret // empty' "$PROFILES_FILE")"

  if [ -n "$theme_from_profile" ] && [ -z "$THEME_ID" ]; then
    THEME_ID="$theme_from_profile"
  fi
  if [ -n "$author_from_profile" ] && [ -z "$RESOLVED_AUTHOR" ]; then
    RESOLVED_AUTHOR="$author_from_profile"
  fi
  if [ -n "$mcp_config_from_profile" ] && [ -z "${MCP_CONFIG_FILE_OVERRIDE:-}" ]; then
    MCP_CONFIG_FILE="$(resolve_path_from_base "$mcp_config_from_profile" "$(dirname "$PROFILES_FILE")")"
  fi
  if [ -n "$mcp_server_from_profile" ] && [ -z "${MCP_SERVER_OVERRIDE:-}" ]; then
    MCP_SERVER="$mcp_server_from_profile"
  fi
  if [ -n "$published_log_from_profile" ] && [ -z "${WECHAT_PUBLISHED_LOG:-}" ]; then
    PUBLISHED_LOG_PATH="$(resolve_path_from_base "$published_log_from_profile" "$(dirname "$PROFILES_FILE")")"
  elif [ -z "${WECHAT_PUBLISHED_LOG:-}" ]; then
    PUBLISHED_LOG_PATH="${WORKSPACE_ROOT}/published-logs/${profile_name}.jsonl"
  fi
  if [ -n "$wechat_app_id_from_profile" ]; then
    export WECHAT_APP_ID="$wechat_app_id_from_profile"
    PROFILE_HAS_INLINE_CREDS=1
  fi
  if [ -n "$wechat_app_secret_from_profile" ]; then
    export WECHAT_APP_SECRET="$wechat_app_secret_from_profile"
    PROFILE_HAS_INLINE_CREDS=1
  fi
}

load_optional_env
MCP_CONFIG_FILE_ENV="${MCP_CONFIG_FILE:-$MCP_CONFIG_FILE_ENV}"

FILE_PATH="${1:-}"
THEME_ID="${2:-}"
CLI_PROFILE="${3:-}"
SELECTED_PROFILE="$CLI_PROFILE"
MCP_SERVER="${WECHAT_MCP_SERVER:-$DEFAULT_MCP_SERVER}"
RESOLVED_AUTHOR="${WECHAT_AUTHOR:-}"
PUBLISHED_LOG_PATH="${WECHAT_PUBLISHED_LOG:-}"
PROFILE_HAS_INLINE_CREDS=0

if [ -n "$MCP_CONFIG_FILE_ENV" ]; then
  MCP_CONFIG_FILE_OVERRIDE=1
fi
if [ -n "${WECHAT_MCP_SERVER:-}" ]; then
  MCP_SERVER_OVERRIDE=1
fi

if [ -z "$FILE_PATH" ] || [ "$FILE_PATH" = "-h" ] || [ "$FILE_PATH" = "--help" ]; then
  show_help
  exit 0
fi

check_deps
refresh_runtime_paths
if [ -z "$PUBLISHED_LOG_PATH" ]; then
  PUBLISHED_LOG_PATH="$DEFAULT_PUBLISHED_LOG_PATH"
fi

if [ -z "$SELECTED_PROFILE" ]; then
  echo "❌ 必须显式指定公众号名称；不再允许 default 或隐式默认号。"
  echo "用法: $(basename "$0") <path/to/article.md> [theme_id] <公众号名称>"
  if [ -f "$PROFILES_FILE" ] && jq -e . "$PROFILES_FILE" >/dev/null 2>&1; then
    echo "可用公众号名称:"
    jq -r '.profiles | keys[]?' "$PROFILES_FILE" | sed 's/^/  - /'
  fi
  exit 1
fi

resolve_profile "$SELECTED_PROFILE"

if [ -z "$THEME_ID" ]; then
  THEME_ID="$DEFAULT_THEME"
fi
if [ -z "${MCP_CONFIG_FILE:-}" ]; then
  echo "❌ 当前 profile 未配置 publisher.mcp_config_file，且未通过 MCP_CONFIG_FILE 显式指定。"
  exit 1
fi
MCP_CONFIG_FILE="$(expand_path "$MCP_CONFIG_FILE")"
PUBLISHED_LOG_PATH="$(expand_path "$PUBLISHED_LOG_PATH")"

if [ ! -f "$MCP_CONFIG_FILE" ]; then
  echo "❌ 找不到 MCP 配置文件: $MCP_CONFIG_FILE"
  echo "请创建该文件，或通过 MCP_CONFIG_FILE 指定路径。"
  exit 1
fi

if [ "$PROFILE_HAS_INLINE_CREDS" -eq 1 ] && jq -e '.mcpServers | to_entries[]? | ((.value.args // []) | index("--server")) != null' "$MCP_CONFIG_FILE" >/dev/null 2>&1; then
  echo "❌ 当前 profile 提供了独立公众号凭证，但 MCP 配置仍是远端 --server 模式。"
  echo "   这类远端发布请求不会按 profile 切换公众号，容易误发到默认号。"
  echo "   解决方式："
  echo "   1. 改用本机 local mode 的 wenyan-mcp 配置"
  echo "   2. 或为该公众号部署独立的远端 Wenyan Server / 独立 API key"
  exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
  echo "❌ 文件不存在: $FILE_PATH"
  exit 1
fi

PUBLISH_FILE="$FILE_PATH"
TEMP_FILE="$(mktemp /tmp/wechat-publish.XXXXXX.md)"
TEMP_COVER_FILE=""
HAS_TITLE=0
HAS_COVER=0
HAS_AUTHOR=0

grep -Eq '^title:' "$FILE_PATH" && HAS_TITLE=1 || true
grep -Eq '^cover:' "$FILE_PATH" && HAS_COVER=1 || true
grep -Eq '^author:' "$FILE_PATH" && HAS_AUTHOR=1 || true

AUTO_TITLE="$(sed -n 's/^# \+//p' "$FILE_PATH" | head -n 1)"
[ -z "$AUTO_TITLE" ] && AUTO_TITLE="未命名文章"
FINAL_TITLE="$AUTO_TITLE"
if [ "$HAS_TITLE" -eq 1 ]; then
  FINAL_TITLE="$(sed -n 's/^title:[[:space:]]*//p' "$FILE_PATH" | head -n 1)"
fi
NORM_TITLE="$(python3 - <<'PY' "$FINAL_TITLE"
import sys, unicodedata
QUOTE_PAIRS={'"':'"', "'":"'", '“':'”', '‘':'’', '《':'》', '「':'」', '『':'』'}
s=unicodedata.normalize('NFKC', sys.argv[1] or '').strip()
while len(s)>=2 and QUOTE_PAIRS.get(s[0]) == s[-1]:
    s=s[1:-1].strip()
print(s)
PY
)"
BODY_FILE="$FILE_PATH"
BODY_TEMP=""
FIRST_H1="$(sed -n 's/^# \+//p' "$FILE_PATH" | head -n 1)"
NORM_H1="$(python3 - <<'PY' "$FIRST_H1"
import sys, unicodedata
QUOTE_PAIRS={'"':'"', "'":"'", '“':'”', '‘':'’', '《':'》', '「':'」', '『':'』'}
s=unicodedata.normalize('NFKC', sys.argv[1] or '').strip()
while len(s)>=2 and QUOTE_PAIRS.get(s[0]) == s[-1]:
    s=s[1:-1].strip()
print(s)
PY
)"
if [ -n "$NORM_H1" ] && [ "$NORM_H1" = "$NORM_TITLE" ]; then
  BODY_TEMP="$(mktemp /tmp/wechat-body.XXXXXX.md)"
  python3 - <<'PY' "$FILE_PATH" "$BODY_TEMP"
import sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, 'r', encoding='utf-8').read().splitlines()
out = []
skipped = False
skip_blank_after_h1 = False
in_frontmatter = False
for i, line in enumerate(text):
    if i == 0 and line.strip() == '---':
        in_frontmatter = True
        out.append(line)
        continue
    if in_frontmatter:
        out.append(line)
        if line.strip() == '---':
            in_frontmatter = False
        continue
    if not skipped and line.startswith('# '):
        skipped = True
        skip_blank_after_h1 = True
        continue
    if skip_blank_after_h1 and line.strip() == '':
        skip_blank_after_h1 = False
        continue  # skip the first blank line immediately after removed H1
    skip_blank_after_h1 = False
    out.append(line)
open(dst, 'w', encoding='utf-8').write('\n'.join(out).lstrip('\n') + ('\n' if out else ''))
PY
  BODY_FILE="$BODY_TEMP"
fi
{
  printf '%s\n' '---'
  printf 'title: %s\n' "$FINAL_TITLE"
  if [ "$HAS_AUTHOR" -eq 1 ]; then
    sed -n 's/^author:[[:space:]]*//p' "$FILE_PATH" | head -n 1 | sed 's/^/author: /'
  elif [ -n "$RESOLVED_AUTHOR" ]; then
    printf 'author: %s\n' "$RESOLVED_AUTHOR"
  fi
  if [ "$HAS_COVER" -eq 1 ]; then
    sed -n 's/^cover:[[:space:]]*//p' "$FILE_PATH" | head -n 1 | sed 's/^/cover: /'
  else
    printf 'cover: %s\n' "$DEFAULT_COVER_URL"
  fi
  printf '%s\n' '---'
  if [ "$HAS_TITLE" -eq 1 ] || [ "$HAS_COVER" -eq 1 ] || [ "$HAS_AUTHOR" -eq 1 ]; then
    python3 - <<'PY' "$BODY_FILE"
import sys
p=sys.argv[1]
lines=open(p,'r',encoding='utf-8').read().splitlines()
out=[]
in_frontmatter=False
for i,line in enumerate(lines):
    if i==0 and line.strip()=='---':
        in_frontmatter=True
        continue
    if in_frontmatter:
        if line.strip()=='---':
            in_frontmatter=False
        continue
    out.append(line)
print('\n'.join(out).lstrip('\n'))
PY
  else
    cat "$BODY_FILE"
  fi
} > "$TEMP_FILE"
[ -n "$BODY_TEMP" ] && rm -f "$BODY_TEMP"
PUBLISH_FILE="$TEMP_FILE"

REMOTE_SERVER_MODE=0
if jq -e '.mcpServers | to_entries[]? | ((.value.args // []) | index("--server")) != null' "$MCP_CONFIG_FILE" >/dev/null 2>&1; then
  REMOTE_SERVER_MODE=1
fi

# REMOTE_SERVER_MODE: WeChat API requires covers to be uploaded to WeChat CDN first.
# External URLs (e.g. Unsplash) are rejected by WeChat as cover images.
# Strategy: download cover on this VPS (which can reach external URLs via its own proxy),
# then upload to the remote wenyan-serve /upload endpoint, replace cover with the returned WeChat URL.
if [ "$REMOTE_SERVER_MODE" -eq 1 ]; then
  COVER_VALUE="$(sed -n 's/^cover:[[:space:]]*//p' "$PUBLISH_FILE" | head -n 1)"
  if printf '%s' "$COVER_VALUE" | grep -Eq '^https?://'; then
    # Derive server base URL and API key from mcp.json --server arg
    WENYAN_SERVER_URL="$(jq -r '.mcpServers | to_entries[] | .value.args // [] | to_entries[] | select(.value == "--server") | .key' "$MCP_CONFIG_FILE" 2>/dev/null | head -1)"
    WENYAN_SERVER_URL="$(jq -r '.mcpServers | to_entries[0].value.args | . as $a | range(length) | select($a[.] == "--server") | $a[.+1]' "$MCP_CONFIG_FILE" 2>/dev/null | head -1)"
    WENYAN_API_KEY="$(jq -r '.mcpServers | to_entries[0].value.args | . as $a | range(length) | select($a[.] == "--api-key") | $a[.+1]' "$MCP_CONFIG_FILE" 2>/dev/null | head -1)"
    if [ -n "$WENYAN_SERVER_URL" ]; then
      TEMP_COVER_FILE="$(mktemp /tmp/wechat-cover.XXXXXX.jpg)"
      echo "   下载封面图: $COVER_VALUE"
      if curl -L --fail --max-time 30 -o "$TEMP_COVER_FILE" "$COVER_VALUE" 2>/dev/null; then
        UPLOAD_RESULT="$(curl -s --max-time 30 \
          -X POST "${WENYAN_SERVER_URL}/upload" \
          -H "x-api-key: ${WENYAN_API_KEY}" \
          -F "file=@${TEMP_COVER_FILE};type=image/jpeg" 2>&1)"
        FILE_ID="$(printf '%s' "$UPLOAD_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('fileId',''))" 2>/dev/null)"
        if [ -n "$FILE_ID" ]; then
          ASSET_COVER="asset://$FILE_ID"
          python3 - <<'PY' "$PUBLISH_FILE" "$ASSET_COVER"
import sys
p, new_cover = sys.argv[1], sys.argv[2]
lines = open(p, 'r', encoding='utf-8').read().splitlines()
out = []
in_fm = False
replaced = False
for i, line in enumerate(lines):
    if i == 0 and line.strip() == '---':
        in_fm = True
        out.append(line)
        continue
    if in_fm and line.strip() == '---':
        out.append(line)
        in_fm = False
        continue
    if in_fm and line.startswith('cover:') and not replaced:
        out.append(f'cover: {new_cover}')
        replaced = True
        continue
    out.append(line)
open(p, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
PY
          echo "   封面已上传至服务器: $ASSET_COVER"
        else
          echo "   警告: 封面上传失败，输出: $UPLOAD_RESULT"
          echo "   使用原始 URL 继续..."
        fi
        rm -f "$TEMP_COVER_FILE"
        TEMP_COVER_FILE=""
      else
        rm -f "$TEMP_COVER_FILE"
        TEMP_COVER_FILE=""
        echo "   警告: 封面 URL 下载失败，使用原始 URL 继续..."
      fi
    fi
  fi
fi

echo "🚀 正在发布到微信公众号草稿箱..."
echo "   文件: $PUBLISH_FILE"
echo "   主题: $THEME_ID"
echo "   MCP 服务: $MCP_SERVER"
if [ -n "$SELECTED_PROFILE" ]; then
  echo "   公众号名称: $SELECTED_PROFILE"
fi

RESULT=$(mcporter call "${MCP_SERVER}.publish_article" \
  file:"$PUBLISH_FILE" \
  theme_id:"$THEME_ID" \
  --config "$MCP_CONFIG_FILE" 2>&1)
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
  [ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"
  [ -n "$TEMP_COVER_FILE" ] && rm -f "$TEMP_COVER_FILE"

  echo "❌ 发布失败。"
  echo "$RESULT"
  echo "\n排查建议："
  echo "  1. 远程 MCP 服务是否可用"
  echo "  2. MCP 服务所在公网 IP 是否已加入公众号白名单"
  echo "  3. Markdown frontmatter 是否包含 title / cover"
  echo "  4. cover 是否为远程服务可访问的公网 URL"
  exit "$STATUS"
fi

echo "$RESULT"
MEDIA_ID="$(printf '%s\n' "$RESULT" | sed -n 's/.*media ID is \([^ .]*\).*/\1/p' | head -n 1)"
if printf '%s\n' "$RESULT" | grep -qi 'Remote Publish Failed:\|执行工具失败:' || [ -z "$MEDIA_ID" ]; then
  [ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"
  [ -n "$TEMP_COVER_FILE" ] && rm -f "$TEMP_COVER_FILE"
  echo "❌ 发布失败。"
  exit 1
fi
TITLE_FOR_LOG="$(sed -n 's/^title:[[:space:]]*//p' "$PUBLISH_FILE" | head -n 1)"
python3 - <<'PY' "$PUBLISH_FILE" "$FILE_PATH" "$MEDIA_ID" "$TITLE_FOR_LOG" "$PUBLISHED_LOG_PATH" "$SELECTED_PROFILE"
import sys, json, datetime, pathlib, os
pfile, orig_file, media_id, title, log_path, profile = sys.argv[1:7]
publish_path = pathlib.Path(pfile)
source_path = pathlib.Path(orig_file)
text = publish_path.read_text(encoding='utf-8')
body = []
in_fm = False
for i, line in enumerate(text.splitlines()):
    if i == 0 and line.strip() == '---':
        in_fm = True
        continue
    if in_fm:
        if line.strip() == '---':
            in_fm = False
        continue
    body.append(line)
content = '\n'.join(body)
keywords = []
for kw in ['黄金','金价','A股','美股','理财','ETF','银行理财','基金','债券','AI','楼市','美元']:
    if kw in content or kw in title:
        keywords.append(kw)
meta = {}
pipeline = {}
if source_path.exists():
    draft_dir = source_path.parent
    meta_path = draft_dir / 'meta.json'
    pipeline_path = draft_dir / 'pipeline-state.json'
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except Exception:
            meta = {}
    if pipeline_path.exists():
        try:
            pipeline = json.loads(pipeline_path.read_text(encoding='utf-8'))
        except Exception:
            pipeline = {}
selected = pipeline.get('selected_topic', {}) if isinstance(pipeline, dict) else {}
entry = {
  'ts': datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(),
  'slug': meta.get('slug') or pipeline.get('slug') or source_path.parent.name,
  'title': title.strip('"\'“”‘’ '),
  'topic': pipeline.get('topic') or meta.get('topic') or selected.get('title'),
  'angle': selected.get('angle') or pipeline.get('angle') or meta.get('angle'),
  'purpose': pipeline.get('purpose') or meta.get('purpose'),
  'type': meta.get('type') or pipeline.get('type') or pipeline.get('article_type'),
  'profile': profile or pipeline.get('profile') or meta.get('profile'),
  'media_id': media_id,
  'keywords': keywords,
  'source_file': str(source_path),
}
log = pathlib.Path(os.path.expanduser(log_path))
log.parent.mkdir(parents=True, exist_ok=True)
with log.open('a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
PY
[ -n "$TEMP_FILE" ] && rm -f "$TEMP_FILE"
[ -n "$TEMP_COVER_FILE" ] && rm -f "$TEMP_COVER_FILE"
echo "✅ 发布命令执行完成，请到公众号草稿箱确认。"
