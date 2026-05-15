---
name: wechat-mp-publisher
version: 3.0.0
description: >-
  Use when the user asks to upload a Markdown article to a WeChat Official
  Account draft box, create a WeChat MP draft, publish Markdown through
  Wenyan/wenyan-mcp/mcporter, or says 草稿箱, 上传草稿, 创建草稿, Wenyan 发布.
  This Hermes skill creates drafts only; it does not click the final WeChat
  publish/group-send buttons.
metadata:
  hermes:
    tags:
      - wechat
      - wenyan
      - draft-box
      - publishing
---

# WeChat MP Draft Publisher

This skill uploads an existing Markdown article to a WeChat Official Account
draft box through the profile-local `wenyan-mcp` configuration.

Boundary:

- Use `wechat-mp-publisher` for Markdown → WeChat draft box.
- Use `wechat-mp-formal-publish` for draft box → reader-side publish/group-send.
- Use `wechat-article-forge` for research, drafting, review, layout, and pipeline state.

## Required Account Context

Never infer the account.

Before uploading a draft, resolve the active article workspace and explicit profile:

- xiaolongxia workspace:
  `/root/.hermes/profiles/xiaolongxia/workspace/xiaolongxia/wechat-article-writer`
- money workspace:
  `/root/.hermes/profiles/money/workspace/money/wechat-article-writer`
- profile names must exactly match `profiles.json`, for example:
  `小龙虾有话说` or `不上班也有Money`

The workspace must contain:

- `profiles.json`
- profile-local `mcp-*.json`
- the `publish.md` or other Markdown file to upload

Do not use any ambient global or legacy MCP config.

## Command

Run the bundled script with an explicit workspace and profile:

```bash
WECHAT_ARTICLE_WRITER_ROOT=<article-workspace> \
${HERMES_SKILL_DIR}/scripts/publish-remote.sh <publish.md> sspai <公众号名称>
```

Examples:

```bash
WECHAT_ARTICLE_WRITER_ROOT=/root/.hermes/profiles/xiaolongxia/workspace/xiaolongxia/wechat-article-writer \
${HERMES_SKILL_DIR}/scripts/publish-remote.sh \
  /root/.hermes/profiles/xiaolongxia/workspace/xiaolongxia/wechat-article-writer/drafts/<slug>/publish.md \
  sspai \
  小龙虾有话说
```

```bash
WECHAT_ARTICLE_WRITER_ROOT=/root/.hermes/profiles/money/workspace/money/wechat-article-writer \
${HERMES_SKILL_DIR}/scripts/publish-remote.sh \
  /root/.hermes/profiles/money/workspace/money/wechat-article-writer/drafts/<slug>/publish.md \
  sspai \
  不上班也有Money
```

The script also tries to infer the article workspace from `<publish.md>` if the
file lives under a `wechat-article-writer` directory, but explicit
`WECHAT_ARTICLE_WRITER_ROOT` is preferred.

## Preflight

Before running the upload:

1. Confirm the Markdown file exists and has frontmatter `title`, `author`,
   `profile`, `cover`, `theme`, and `slug`.
2. Run forge profile preflight if the file comes from `wechat-article-forge`:

```bash
python3 /root/.hermes/shared-skills/forge/skills/wechat-article-forge/scripts/publish_profile_preflight.py \
  --config-path <article-workspace>/config.json \
  --profile <公众号名称> \
  --publish-md <publish.md>
```

3. Confirm `mcporter`, `jq`, and `curl` exist.

## Output Handling

After success:

- Record the returned WeChat draft/media identifiers in the article state if the
  caller is a forge pipeline.
- Append to the profile-local published/draft log only through the script.
- Continue to `wechat-mp-formal-publish` only if the user asked for formal
  reader-side publish.

If `wenyan-mcp` reports an account or whitelist error, stop and report the
specific server/config being used. Do not retry with another profile.
