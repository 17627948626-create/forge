# Data Layout & Schemas

## Directory Structure

```
agent workspace `wechat-article-writer/`（例如 `/root/.openclaw/workspace-money/wechat-article-writer/` 或 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/`）
├── config.json              # User configuration (global defaults; no implicit default公众号 routing)
├── profiles.json            # Multi-account profile registry
├── published-log.jsonl      # 《不上班也有Money》发布台账
├── published-logs/          # Optional per-profile publish logs
├── voice-profile.json       # Writing style profile (from forge voice train)
├── session.json             # Current active session (topic handoff)
└── drafts/
    └── <slug-YYYYMMDD>/
        ├── meta.json        # Status, title, type, timestamps
        ├── pipeline-state.json  # Compaction-safe state machine
        ├── outline.md       # Section outline
        ├── research.json    # Internal research bundle for grounding/checking (Step 1, not for article output)
        ├── draft.md         # Raw Markdown draft (+ draft-v2.md, v3, ...)
        ├── review-v1.json   # Reviewer scores (+ v2, v3, ...)
        └── formatted.html   # WeChat HTML
```

## Slug Generation

1. Convert Chinese title to pinyin (first 6 syllables, hyphen-separated, lowercase).
2. Keep ASCII portions as-is (e.g., `AI`, `Rust`).
3. Append `-YYYYMMDD`.
4. Replace non-`[a-z0-9-]` with hyphen. Collapse consecutive hyphens.
5. If the resulting draft directory already exists and the run is `fresh`, append `-v2`, `-v3`, ... until the slug is unique.

**Examples:**
- `本周技术周报` → `ben-zhou-ji-shu-zhou-bao-20260217`
- `AI编程工具深度评测` → `ai-bian-cheng-gong-ju-shen-20260217`

## session.json Schema

```json
{
  "topic": {
    "title": "本周AI工具精选",
    "angle": "news_hook",
    "type": "资讯",
    "hook": "上周有三个AI产品同时发布……",
    "subject": "AI工具"
  },
  "selected_at": "2026-02-17T21:00:00Z",
  "slug": "ben-zhou-ai-gong-ju-20260217"
}
```

Handoff: `forge topic` writes → `forge write`/`forge draft` reads (expires after 24h).

## config.json

```json
{
  "profiles_path": "agent workspace `wechat-article-writer/`（例如 `/root/.openclaw/workspace-money/wechat-article-writer/` 或 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/`）profiles.json",
  "default_theme": "sspai",
  "default_article_type": "观点",
  "auto_publish_types": [],
  "cover_style": "unsplash_search",
  "unsplash_access_key": "<Unsplash Access Key>",
  "cover_fallback_url": "https://picsum.photos/1200/800",
  "review_pass_threshold": "<single authority value from active config>",
  "wechat_author": "",
  "wechat_secrets_path": "agent workspace `wechat-article-writer/`（例如 `/root/.openclaw/workspace-money/wechat-article-writer/` 或 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/`）secrets.json",
  "published_log_path": "",
  "writer_model": "",
  "word_count_targets": {
    "资讯": [800, 1500],
    "周报": [1000, 2000],
    "教程": [1500, 3000],
    "观点": [1200, 2500],
    "科普": [1500, 3000]
  }
}
```

**cover_style 取值说明：**

| 值 | 行为 |
|----|------|
| `unsplash_search` | 根据文章标题自动搜图 + LLM 视觉安全审核（推荐） |
| `from_content` | 占位符，使用 `cover_fallback_url` |

**封面选图字段：**
- `unsplash_access_key`：Unsplash API Access Key
- `cover_fallback_url`：全部候选图审核不过时的兜底 URL
- `review_pass_threshold`：**唯一权威的评分通过门槛数字**。Reviewer 是否通过、自动 revise 是否继续，都只认这个字段；其他文档不得再写死具体数字
- `writer_model`：只作为 Writer 子代理（Step 2 初稿 + Step 4 改稿）的**可选覆盖字段**；由 Orchestrator 在 `sessions_spawn` 时显式传入 `model`。若为空，则 Writer 默认继承父级/主会话模型
- `wechat_author` / `published_log_path`（顶层 config）：仅保留给历史兼容读取；**新写路径不得**把它们当成 profile 缺失时的静默 fallback

## profiles.json（可选，多公众号）

当你需要一套 forge 同时服务多个公众号时，新增 `profiles.json`，并用**实际公众号名称**作为 key。`write` / `draft` / `publish` 时必须显式指定其中一个名称；**不再允许默认号**。

```json
{
  "profiles": {
    "不上班也有Money": {
      "label": "不上班也有Money",
      "wechat_author": "不上班也有Money",
      "default_theme": "sspai",
      "cover_style": "unsplash_search",
      "cover_fallback_url": "https://picsum.photos/1200/800",
      "wechat_secrets_path": "agent workspace `wechat-article-writer/`（例如 `/root/.openclaw/workspace-money/wechat-article-writer/` 或 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/`）secrets.json",
      "published_log_path": "agent workspace `wechat-article-writer/`（例如 `/root/.openclaw/workspace-money/wechat-article-writer/` 或 `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/`）published-log.jsonl",
      "publisher": {
        "mcp_server": "wenyan-mcp",
        "mcp_config_file": "~/.openclaw/mcp.json"
      }
    },
    "小龙虾有话说": {
      "label": "小龙虾有话说",
      "wechat_author": "小龙虾有话说",
      "default_theme": "sspai",
      "published_log_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/published-logs/xiaolongxia-youhuashuo.jsonl",
      "publisher": {
        "mcp_server": "wenyan-mcp-alt",
        "mcp_config_file": "~/.openclaw/mcp-alt.json"
      }
    }
  }
}
```

**建议的覆盖优先级：**
1. 显式命令参数（尤其是用户明确指定的公众号名称或 theme）
2. `profiles.json` 中对应公众号
3. `config.json` 全局默认值（**仅限非公众号路由字段**，绝不用于 profile / author / published_log_path / publisher.mcp_config_file 猜测）

**多公众号规则：**
- 发布台账优先按 profile 分离，避免不同号互相去重。
- `wechat_author`、`default_theme`、`publisher.mcp_server`、`publisher.mcp_config_file` 都可以按 profile 覆盖。
- 如果某个 profile 需要独立公众号凭证，优先使用 `publisher.mode = "local"` + 本机 `wenyan-mcp` 配置；**不要指望同一个远端 `--server` 实例按请求切换公众号**。
- 对公众号路由而言，`profiles.json` 现在是强依赖；没有它就不应执行 `write` / `draft` / `publish`。
- `run` / `pipeline-state.json` / `publish.md` frontmatter / publish preflight 必须显式携带同一个 `profile`；缺失或不一致时应 fail-closed。
