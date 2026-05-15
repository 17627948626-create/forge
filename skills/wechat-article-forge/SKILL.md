---
name: wechat-article-forge
description: >-
  Use when the user asks to research, draft, review, lay out, or publish a
  WeChat Official Account article, or says forge topic, forge write, forge
  draft, forge publish, forge voice train, or forge status. This Hermes skill
  runs a profile-local article pipeline: research and outline, writer child,
  reviewer child, bounded revise loop, layout child, and optional WeChat draft
  box publishing. For write, draft, and publish requests, require the target
  公众号名称 explicitly and never assume a default account.
version: 3.0.0
author: 17627948626-create
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [wechat, writing, publishing, hermes-profile, multi-agent]
---

# wechat-article-forge

微信公众号选题、写作、评审、排版和发布流水线。This Hermes version is profile-aware: the skill code can be shared, but every draft, profile registry, voice asset, log, secret, and publisher config must live inside the active Hermes profile workspace.

## Scope

**Handles:** topic research, outline, Chinese-first draft writing, quality review, bounded revision, WeChat-safe layout, WeChat draft-box publishing, and optional reader-side formal-publish handoff when explicitly required by the run.

**Does not handle:** non-WeChat platforms, post-publish analytics, WeChat customer-service messaging, or cross-profile data sharing.

**Profile boundary:** xiaolongxia and money may load the same shared skill directory, but each profile must read only its own `wechat-article-writer` workspace.

## Commands

| Command | What it does |
| --- | --- |
| `forge topic X` | Research timely angles and propose topic options |
| `forge write X for <公众号名称>` | Full pipeline: research, reviewed draft, layout, publish to draft box |
| `forge draft X for <公众号名称>` | Write and review only, stop before publish |
| `forge publish <slug> for <公众号名称>` | Publish an existing draft to the selected WeChat account draft box |
| `forge voice train` | Build `voice-pack.json` and fallback `voice-profile.json` from existing writing |
| `forge status` | Show pipeline state and pending drafts in the active profile workspace |

For `write`, `draft`, and `publish`, if the user did not explicitly name the target 公众号, stop and ask. Never route to a default account, never infer from the current Hermes profile name, and never reuse another profile's account registry.

## Hermes Paths

Resolve paths in this order:

1. **Skill directory:** `${HERMES_SKILL_DIR}`. Run helpers as `python3 ${HERMES_SKILL_DIR}/scripts/<script>.py ...`.
2. **Profile home:** `$HERMES_HOME`, for example `/root/.hermes/profiles/xiaolongxia`.
3. **Article workspace:** the current Hermes `terminal.cwd` plus `wechat-article-writer`, normally `$HERMES_HOME/workspace/<profile-name>/wechat-article-writer`.
4. **Article config:** `<article-workspace>/config.json`.
5. **Account registry:** `config.json.profiles_path`, resolved relative to `config.json` if not absolute.

Fail closed if `config.json`, `profiles.json`, publisher config, voice assets, or publish logs resolve outside the active Hermes profile workspace unless the user explicitly asks for a read-only migration audit.

## Pipeline

State persists to `<article-workspace>/drafts/<slug>/pipeline-state.json`. This file is the durable control plane across context compaction, gateway restart, or child-agent completion loss. See `references/pipeline-state.md`.

| # | Step | Producer | Output |
| --- | --- | --- | --- |
| 1 | Research + Outline | Hermes child agent | `research.json`, `outline.md` |
| 1b | Cover Image | Orchestrator inline | `cover_url` in `pipeline-state.json` |
| 2 | Write | Hermes writer child | `draft.md` |
| 3 | Review | Hermes reviewer child | `review-v*.json` |
| 4 | Revise | New Hermes writer child per revision | `draft-v*.md` |
| 5 | Layout | Hermes layout child | `final-layout.md` |
| 6 | Publish + Cleanup | Orchestrator | `publish.md` to draft box |

### Step 1: Research + Outline

Create the draft directory and initial `pipeline-state.json` before spawning the Researcher child. Researcher must save `research.json` and `outline.md` before returning.

Run mechanical gates before Writer:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/outline_gate.py <draft-dir>/outline.md --output <draft-dir>/outline-gate.json
python3 ${HERMES_SKILL_DIR}/scripts/validate_research_artifact.py <draft-dir>/research.json --output <draft-dir>/research-gate.json
```

Fail closed if the outline contains backstage cues or high-risk claims lack structured fact records. Researcher should follow `references/researcher-prompt.md`.

### Steps 2-4: Write, Review, Revise

- Writer and Reviewer run as isolated Hermes child agents. The orchestrator routes, persists state, and enforces gates; it does not write or review article prose.
- Read `writer_model` from `<article-workspace>/config.json` as an optional Writer model override. If it is empty or absent, the Writer inherits the active Hermes session model.
- Writer input should include the topic, `writer-lite-brief.json`, `research.json`, `outline.md`, and the strongest resolved voice asset: `profiles.json.voice_pack_path`, then `profiles.json.voice_profile_path`, then workspace `voice-pack.json`, then workspace `voice-profile.json`, then bundled defaults.
- Use `python3 ${HERMES_SKILL_DIR}/scripts/resolve_voice_assets.py --config-path <article-workspace>/config.json --profile <公众号名称>` when the voice source is ambiguous.
- After every Writer draft and before every Reviewer child, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/style_fingerprint_lint.py <draft-path> --output <draft-dir>/style-lint.json
```

- Reviewer is the release gate. A draft passes only when `weighted_total >= review_pass_threshold`, where `review_pass_threshold` is read from the active profile's `config.json`.
- Continue revise while below threshold and `revision_cycle < 2`. Every revise round uses a newly spawned Writer child.
- If the second revision still fails, stop that branch and restart from a fresh first-draft branch with the locked topic, brief, and research pack.

### Step 5: Layout

Reviewer pass freezes content. The latest Reviewer-approved `draft.md` or `draft-v*.md` is the final content authority. Layout is a render adapter, not a second writer. It may improve scanability and WeChat-safe structure while preserving thesis, facts, argument strength, and voice.

Before Layout, persist `layout_input_file` and `layout_input_sha256`. Publish audit fails closed if Layout cannot be proven to have consumed the exact Reviewer-approved draft bytes.

### Step 6: Publish

Before publishing, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/publish_profile_preflight.py \
  --profile <公众号名称> \
  --state-path <draft-dir>/pipeline-state.json \
  --publish-md <draft-dir>/publish.md
```

The preflight must validate the explicit account, author, profile-local publish log, profile-local publisher MCP config, and `publish.md` front matter. Publishing must not use ambient global MCP config or another Hermes profile's registry.

## Configuration

Configure each Hermes profile separately in `<article-workspace>/config.json`.

| Field | Description |
| --- | --- |
| `profiles_path` | Account registry. Prefer `profiles.json` relative to `config.json`. |
| `default_article_type` | Default article type, such as 科普, 教程, 观点, or 资讯. |
| `cover_style` | Cover image strategy. |
| `review_pass_threshold` | Sole release threshold for Reviewer pass/fail. |
| `writer_model` | Optional Writer child model override. Empty means inherit active Hermes model. |
| `word_count_targets` | Min/max word count ranges by article type. |

Each `profiles.json` entry must explicitly define the target account's `wechat_author`, `published_log_path`, and `publisher` block. Profile-specific `voice_pack_path`, `voice_profile_path`, and `wechat_secrets_path` are recommended. Do not rely on top-level fallback fields for account routing.

## References

| File | When to load |
| --- | --- |
| `references/data-layout.md` | Directory structure, config schema, profile isolation |
| `references/pipeline-state.md` | Durable state, recovery, lineage, publish handoff |
| `references/researcher-prompt.md` | Topic research and evidence rules |
| `references/writer-prompt.md` | Writer instructions for draft and revision |
| `references/reviewer-rubric.md` | Reviewer scoring and pass/fail rubric |
| `references/layout-prompt.md` | WeChat render-adapter rules |
| `references/recovery-protocol.md` | Resuming incomplete or blocked runs |
| `references/voice-train-prompt.md` | Building voice-pack and voice-profile assets |
| `references/quality-checks.md` | Active quality gates and anti-patterns |

## Verification

After installing or updating this skill for a profile, verify:

```bash
HERMES_HOME=/root/.hermes/profiles/xiaolongxia hermes skills list --enabled-only | rg wechat-article-forge
HERMES_HOME=/root/.hermes/profiles/money hermes skills list --enabled-only | rg wechat-article-forge
```

Then run a legacy-path grep and positive plus cross-profile negative `publish_profile_preflight.py` checks before any real publish.
