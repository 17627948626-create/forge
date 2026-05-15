# Hermes Orchestrator Configuration

This document describes the recommended Hermes profile settings for running `wechat-article-forge`.

## Core Rules

- Run the skill from the active Hermes profile workspace.
- Keep skill code shared and article data profile-local.
- Persist progress to `pipeline-state.json`; do not rely on chat memory for pipeline state.
- Stop and ask when the target 公众号名称 is missing.
- Stop on real human checkpoints such as login QR, safe check, and boss confirmation.
- Reviewer pass/fail uses only `config.json.review_pass_threshold`.

## Profile Config

Recommended profile settings:

```yaml
terminal:
  cwd: /root/.hermes/profiles/<profile>/workspace/<profile>

skills:
  external_dirs:
    - /root/.hermes/shared-skills/forge/skills
  template_vars: true
  inline_shell: false

agent:
  gateway_timeout: 7200
  gateway_timeout_warning: 1800

delegation:
  child_timeout_seconds: 3600
  max_concurrent_children: 3
```

`child_timeout_seconds` must be long enough for Writer, Reviewer, and Layout child agents. A 600-second default is too short for long-form article runs.

## Model Strategy

| Task | Model |
| --- | --- |
| Main conversation and orchestration | Active profile default model |
| Writer | `config.json.writer_model` when set, otherwise inherit active Hermes model |
| Reviewer | Active profile default or explicit reviewer child model if the operator chooses one |
| Layout | Active profile default |

Do not add a separate external Writer runtime unless the skill explicitly documents and tests that runtime.

## Account Routing

Each Hermes profile should have its own:

```text
$HERMES_HOME/workspace/<profile>/wechat-article-writer/config.json
$HERMES_HOME/workspace/<profile>/wechat-article-writer/profiles.json
```

The orchestrator must:

1. Read the active profile-local `config.json`.
2. Resolve `profiles_path`.
3. Match the user-specified 公众号名称 exactly.
4. Persist `profile`, `wechat_author`, `published_log_path`, `mcp_server`, and `mcp_config_file` into `pipeline-state.json` before publish.

Cross-profile fallback is forbidden.

## MCP Publishing

Publisher MCP config is profile data, not shared skill data. Store it under the active article workspace, for example:

```text
$HERMES_HOME/workspace/<profile>/wechat-article-writer/mcp-<account>.json
```

Before publish, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/publish_profile_preflight.py \
  --profile <公众号名称> \
  --state-path <draft-dir>/pipeline-state.json \
  --publish-md <draft-dir>/publish.md
```

The preflight must fail when the MCP config or published log resolves outside the active article workspace.

## Automation Policy

Automatic:

- Hot-topic pre-scan and topic selection when the user asks for scheduled/daily runs
- Research and outline
- Mechanical gates
- Writer child draft
- Reviewer child scoring
- Up to two Writer revision rounds
- Layout child
- Draft-box publish preparation

Human-gated:

- Missing target account
- User-provided manual revision direction
- WeChat login QR
- safe_check QR
- boss confirmation
- Any profile/account mismatch

## Heartbeat

If a profile uses Hermes cron or gateway heartbeat, check:

```text
<article-workspace>/drafts/*/pipeline-state.json
```

- Continue if the latest run is active and not awaiting human action.
- Do not auto-continue if `phase` is `awaiting_human` or `blocked`.
- Remind the user if an active pipeline has not updated for more than 24 hours.

## Install Check

```bash
HERMES_HOME=/root/.hermes/profiles/xiaolongxia hermes skills list --enabled-only | rg wechat-article-forge
HERMES_HOME=/root/.hermes/profiles/money hermes skills list --enabled-only | rg wechat-article-forge
HERMES_HOME=/root/.hermes/profiles/xiaolongxia hermes mcp list
HERMES_HOME=/root/.hermes/profiles/money hermes mcp list
```

Run profile-local preflight checks before the first real publish.
