# Data Layout & Schemas

This skill is designed for **direct OpenClaw consumption**.

The shared repo owns:
- prompt contracts
- artifact schemas
- helper scripts
- fallback defaults

The workspace owns:
- concrete account persona
- long-term memory
- operating preferences
- historical article corpus

Do **not** treat workspace persona files as shared repo interfaces. Compile them into `voice-pack.json` / `voice-profile.json`, then let the skill consume those compiled assets.

## Directory Structure

```text
/root/.openclaw/skills/wechat-article-forge/
├── SKILL.md
├── skill.yml
├── references/
│   ├── default-voice-pack.json
│   ├── default-voice-profile.json
│   ├── voice-pack-schema.json
│   └── voice-profile-schema.json
└── scripts/
    ├── build_voice_pack.py
    ├── resolve_voice_assets.py
    └── style_fingerprint_lint.py

/root/.openclaw/workspace-<account>/
├── SOUL.md                  # private persona source material
├── AGENTS.md                # private agent behavior/source material
├── MEMORY.md                # private long-term memory/source material
├── published/               # optional historical article corpus
└── wechat-article-writer/
    ├── config.json
    ├── profiles.json
    ├── published-log.jsonl
    ├── published-logs/
    ├── voice-pack.json      # workspace-level compiled author asset
    ├── voice-profile.json   # workspace-level fallback summary
    ├── session.json
    └── drafts/
        └── <slug-YYYYMMDD>/
            ├── meta.json
            ├── pipeline-state.json
            ├── outline.md
            ├── outline-gate.json
            ├── research.json
            ├── research-gate.json
            ├── writer-lite-brief.json
            ├── writer-lite-check.json
            ├── style-lint.json
            ├── draft.md
            ├── draft-v2.md
            ├── review-v1.json
            ├── final-layout.md
            ├── publish.md
            └── formatted.html
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

## `config.json`

```json
{
  "profiles_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/profiles.json",
  "default_theme": "sspai",
  "default_article_type": "观点",
  "auto_publish_types": [],
  "cover_style": "unsplash_search",
  "unsplash_access_key": "<Unsplash Access Key>",
  "cover_fallback_url": "https://picsum.photos/1200/800",
  "review_pass_threshold": "<single authority value from active config>",
  "wechat_author": "",
  "wechat_secrets_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/secrets.json",
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
- `profiles_path`：OpenClaw workspace 内的 profile registry。`write` / `draft` / `publish` 路由必须以它为准

## `profiles.json`

`profiles.json` is the profile registry and the **first-class hook** for account-specific compiled voice assets.

```json
{
  "profiles": {
    "小龙虾有话说": {
      "label": "小龙虾有话说",
      "wechat_author": "小龙虾有话说",
      "default_theme": "sspai",
      "published_log_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/published-logs/xiaolongxia-youhuashuo.jsonl",
      "voice_pack_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/voice-pack.json",
      "voice_profile_path": "/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/voice-profile.json",
      "publisher": {
        "mcp_server": "wenyan-mcp-alt",
        "mcp_config_file": "~/.openclaw/mcp-alt.json"
      }
    }
  }
}
```

### Profile-specific voice asset fields

- `voice_pack_path`: optional absolute or `~`-expanded path to the preferred compiled `voice-pack.json`
- `voice_profile_path`: optional absolute or `~`-expanded path to the fallback `voice-profile.json`

These fields let a single workspace host multiple accounts without forcing them to share one writer voice asset.

## Voice Asset Resolution Order

Resolve voice assets in this exact order:

1. `profiles.json.voice_pack_path`
2. `profiles.json.voice_profile_path`
3. workspace `voice-pack.json`
4. workspace `voice-profile.json`
5. skill `references/default-voice-pack.json`
6. skill `references/default-voice-profile.json`

Use `scripts/resolve_voice_assets.py` when choosing the effective asset.

Interpretation rules:
- source specificity beats genericity
- within the same source, `voice-pack.json` beats `voice-profile.json`
- `voice-profile.json` is a fallback summary, not the primary authorial asset

## `forge voice train` Outputs

`forge voice train` should compile workspace persona and article evidence into:

- `voice-pack.json`: primary concrete author asset for Writer/Reviewer
- `voice-profile.json`: fallback diagnostic/summary asset for compatibility and observability

The training input may read:
- published article markdown
- approved historical drafts
- private persona sources such as `SOUL.md`, `AGENTS.md`, `MEMORY.md`

The training output must **not** embed entire historical articles or raw persona files verbatim. It should extract short functional fragments and boundaries.

## `research.json` Sidecar Fields

Beyond thesis/evidence/source data, `research.json` may contain:

- `style_exemplar_pack`: short profile-specific openings / turns / endings for Writer inspiration
- `anti_exemplars`: short negative examples that sound too templated or off-voice
- `entity_alias_map`: canonical-name map for entities that should be referred to consistently
- `must_attribute_claims`: claims that must retain explicit attribution in the draft
- `title_directions`: candidate title directions rather than one fixed title
- `angle_risks`: ways the chosen angle can drift into cliché, hype, or overclaiming

## Legacy Compatibility Notes

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
