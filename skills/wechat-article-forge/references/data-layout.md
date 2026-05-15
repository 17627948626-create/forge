# Data Layout & Schemas

This skill is designed for Hermes profile-local execution. The shared skill owns prompts, scripts, schemas, and fallback voice defaults. Each Hermes profile owns its own account registry, drafts, publish logs, voice assets, publisher config, and secrets.

## Runtime Layout

```text
/root/.hermes/shared-skills/forge/skills/wechat-article-forge/
├── SKILL.md
├── references/
└── scripts/

$HERMES_HOME/
├── SOUL.md
├── memories/
├── config.yaml
└── workspace/<profile-name>/
    └── wechat-article-writer/
        ├── config.json
        ├── profiles.json
        ├── mcp-<account>.json
        ├── secrets.json
        ├── published-logs/
        ├── voice-pack.json
        ├── voice-profile.json
        ├── session.json
        ├── media/wechat-safe-check/
        └── drafts/<slug-YYYYMMDD>/
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
            └── publish.md
```

Do not treat `SOUL.md`, `AGENTS.md`, `MEMORY.md`, or raw historical articles as shared skill interfaces. Compile them into `voice-pack.json` / `voice-profile.json` first.

## Slug Generation

1. Convert Chinese title to pinyin, lowercase and hyphen-separated.
2. Keep ASCII portions as-is.
3. Append `-YYYYMMDD`.
4. Replace non-`[a-z0-9-]` with hyphen and collapse repeats.
5. If the fresh-run draft directory already exists, append `-v2`, `-v3`, and so on.

## `session.json`

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

`forge topic` writes this file. `forge write` / `forge draft` may read it for 24 hours when the user gives no subject.

## `config.json`

Prefer profile-local relative paths. Relative paths resolve from the directory containing `config.json`.

```json
{
  "profiles_path": "profiles.json",
  "default_theme": "sspai",
  "default_article_type": "观点",
  "auto_publish_types": [],
  "cover_style": "unsplash_search",
  "unsplash_access_key": "",
  "cover_fallback_url": "https://picsum.photos/1200/800",
  "review_pass_threshold": 8.5,
  "wechat_author": "",
  "wechat_secrets_path": "secrets.json",
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

Rules:

- `review_pass_threshold` is the only pass/fail threshold authority.
- `writer_model` is an optional Writer child override. Empty means inherit the active Hermes model.
- Top-level `wechat_author` and `published_log_path` are legacy compatibility fields only. New routing must use `profiles.json`.
- Do not add `writer_runtime` unless the skill explicitly supports that runtime. The GitHub mainline uses Hermes child agents only.

## `profiles.json`

```json
{
  "profiles": {
    "小龙虾有话说": {
      "label": "小龙虾有话说",
      "wechat_author": "小龙虾有话说",
      "default_theme": "sspai",
      "wechat_secrets_path": "secrets.json",
      "published_log_path": "published-logs/xiaolongxia-youhuashuo.jsonl",
      "voice_pack_path": "voice-pack.json",
      "voice_profile_path": "voice-profile.json",
      "publisher": {
        "mcp_server": "wenyan-mcp",
        "mcp_config_file": "mcp-xiaolongxia-youhuashuo.json",
        "mode": "remote"
      }
    }
  }
}
```

Rules:

- `profiles.json` is the first-class account registry.
- The user must explicitly choose one profile key for `write`, `draft`, and `publish`.
- `published_log_path`, `wechat_secrets_path`, and `publisher.mcp_config_file` must resolve inside the active article workspace.
- A profile may define `voice_pack_path` and `voice_profile_path`. These are account-specific and should not point into another Hermes profile.

## Voice Asset Resolution Order

1. `profiles.json.voice_pack_path`
2. `profiles.json.voice_profile_path`
3. workspace `voice-pack.json`
4. workspace `voice-profile.json`
5. skill `references/default-voice-pack.json`
6. skill `references/default-voice-profile.json`

Use:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/resolve_voice_assets.py \
  --config-path <article-workspace>/config.json \
  --profile <公众号名称>
```

## Research Sidecar Fields

`research.json` may contain:

- `style_exemplar_pack`: short profile-specific openings, turns, endings, or sharp lines
- `anti_exemplars`: short negative examples
- `entity_alias_map`: canonical-name map
- `must_attribute_claims`: claims that require explicit attribution
- `title_directions`: candidate title directions
- `angle_risks`: ways the angle can drift into cliché, hype, or overclaiming

These fields are functional hints, not raw historical article stuffing.

## Routing Priority

1. Explicit command arguments, especially target 公众号名称 and theme.
2. Matching `profiles.json` entry.
3. `config.json` global defaults only for non-account-routing fields.

Missing profile, author mismatch, publish-log mismatch, or publisher config outside the active workspace must fail closed.
