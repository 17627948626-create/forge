---
name: wechat-article-forge
description: End-to-end 微信公众号 (WeChat Official Account) article writing and publishing pipeline. Multi-agent workflow (active mainline): researcher subagent (topic + outline) → writer subagent (draft) → reviewer subagent (primary adjudication) → revise loop (max 2) → humanizer subagent (tone) → layout subagent (WeChat render adapter) → publish. Use when user asks to write, draft, or publish a WeChat article, or says "forge write/draft/publish/topic/voice/status". For write/draft/publish requests, require the user to explicitly name the target公众号; never assume a default account.
---

# wechat-article-forge

> 从选题到发布的公众号一体化写作工作流

Multi-agent pipeline: Orchestrator delegates writing and reviewing to independent subagents. The orchestrator never writes or reviews — it routes, tracks versions, and enforces quality gates.

## Scope

**Handles:** Topic research (researcher subagent) → Chinese-first writing → quality review → revise loop → humanize (humanizer subagent) → WeChat render-adapter layout (layout subagent) → publishing to WeChat draft box via `wechat-mp-publisher`, and in cron / worker production flows may continue into formal reader-side publish via `wechat-mp-formal-publish`.

**Does NOT handle:** Git/version control, non-WeChat platforms, post-publish analytics, WeChat messaging/customer service.

**Ends at:** By default, article saved to WeChat draft box. In cron / worker production flows that explicitly require reader-side publication, the pipeline must continue into `wechat-mp-formal-publish` until the article is actually submitted / published / in-review on the reader side.

---

## Commands

Trigger any command below, or see `skill.yml` for the full trigger pattern list.

| Command | What it does |
|---------|-------------|
| `forge topic X` | Research trending angles, propose 3 options with hooks |
| `forge write X for <公众号名称>` | Full pipeline: research → publish (8 steps)；必须显式指定公众号名称 |
| `forge draft X for <公众号名称>` | Write only, stop before publish (steps 1-7, skip step 8)；必须显式指定公众号名称 |
| `forge publish <slug> for <公众号名称>` | Publish an existing draft to WeChat draft box；必须显式指定公众号名称 |
| `forge voice train` | Analyze past articles to extract voice profile |
| `forge status` | Show pipeline status and pending drafts |

If no subject given, loads from `session.json` (set by `forge topic`). See `references/data-layout.md`.

For `write` / `draft` / `publish`: if the user did not explicitly name the target公众号, stop and ask. Never route to a default account, never substitute `default`.

---

## Pipeline (7 Steps)

State persists to `pipeline-state.json` — survives compaction. See `references/pipeline-state.md`.

| # | Step | Who | Output |
|---|------|-----|--------|
| 1 | Research + Outline | Researcher subagent | `research.json`, `outline.md` |
| 1b | Cover Image | Orchestrator (inline) | `cover_url` in `pipeline-state.json` |
| 2 | Write | Writer subagent | `draft.md` |
| 3 | Review | Reviewer subagent | `review-v*.json` |
| 4 | Revise | Writer subagent | `draft-v*.md` (max 2 rounds; still below `config.json.review_pass_threshold` ⇒ restart from fresh first-draft branch) |
| 5 | Humanize | Humanizer subagent | `final.md` |
| 6 | Layout | Layout subagent | `final-layout.md` |
| 7 | Publish + Cleanup | Orchestrator | `publish.md` → draft box |

### Step 1: Research + Outline

Orchestrator creates the slug/draft directory and initial `pipeline-state.json`, then spawns a Researcher child (`runTimeoutSeconds: 1320`):

1. **Dedup:** Scan the effective publish log for the explicitly selected公众号 over the last 14 days. Same topic + angle = reject. **Keyword hard-cap:** if any core keyword appears in 2+ articles within 7 days, reject outright. If all candidates blocked, pick lowest-overlap and record `topic_dedup_override_reason`.
2. **Topic strategy for scheduled/daily runs:** unless the user explicitly locks a different direction, prefer a **24-72h hot-topic entrypoint** in the target domain (new model, new product, major company move, viral demo, failure/controversy, financing/org signal). Do **not** turn this into a roundup. One hot hook only. Hot topic is the shell; the thesis/judgment is the core.
   - **Caller-precheck override (new default for xiaolongxia main flow):** if the parent/main agent already passes a hot-topic precheck result (event name / keywords / why-now / thesis seed), treat that as the starting candidate pack. Researcher should verify and sharpen it, not ignore it and rediscover the topic from scratch, unless the evidence clearly collapses.
   - **Authority boundary:** main agent has first topic-pick authority; Orchestrator has process authority only; Researcher has verification + limited re-route authority only. Writer/Humanizer/Layout have no topic-change authority.
3. **Sources:** use the personal skill `jj-search-stack` as the operational search policy. That stack requires URL-encoding queries before applying any URL template, defines the boundary with native `web_search`, keeps only the validated free entrypoints (Sogou WeChat / Sogou Web / DuckDuckGo HTML / Startpage / Brave Search), requires `web_fetch` on the candidate source page itself for verification/extraction, and uses `tavily-search` (`search` / `extract`) as the stable enhancement + fallback layer. It explicitly avoids Bing search result pages and Eastmoney search pages as primary entrypoints in this environment. For market topics: ≥1 macro trigger, ≥1 market-structure/flow, ≥1 investor-position source with concrete numbers. For daily/hot-topic articles: include at least one timely trigger source proving why this should be published now.
4. **Eligibility gate:** Finalize only if ≥2 hard evidence anchors support the thesis. Prefer observable data over broad commentary.
5. **Outline:** 6-8 sections, 1 main insight + 2 named sub-insights → `outline.md`.
   - `outline.md` is **prose-safe only**: section headings + body-ready content points.
   - Never let placeholders / planning labels / note-to-writer text enter the outline. Those belong in `writer-lite-brief`, not in `outline.md`.
   - **Mechanical gate before Writer:** run `python /root/.openclaw/skills/wechat-article-forge/scripts/outline_gate.py <draft-dir>/outline.md --output <draft-dir>/outline-gate.json` and fail closed if it reports backstage cues.
6. **Persist:** Researcher saves `research.json` and `outline.md` before final answer.
   - For high-risk facts, `research.json` should also carry a minimal structured sidecar (recommended: `fact_records`) so Writer + lite preflight can distinguish `api_snapshot`, `paraphrase_only` / `verbatim`, `readme_claim`, and `file_size_bytes` cases.
   - **Mechanical gate before Writer:** run `python /root/.openclaw/skills/wechat-article-forge/scripts/validate_research_artifact.py <draft-dir>/research.json --output <draft-dir>/research-gate.json` and fail closed if high-risk claims lack structured fact records.
7. **Prompt policy:** Researcher must follow `references/researcher-prompt.md`, especially the validated search stack / avoid-list rules.

See `references/researcher-prompt.md` for the detailed, validated search policy.

**Researcher 启动失败 / 超时处理（Orchestrator 职责）：**

若出现以下任一情况，均按**可重试的运行时故障**处理，而不是直接把整轮判死：
- `sessions_spawn` 返回 timeout error
- Researcher 超时被终止
- `GatewayDrainingError`
- `task not accepted`
- 其他明显发生在 child 真正开始研究前的启动级拒单错误（例如 accepted 前失败、0 token、几乎无消息即终止）

Orchestrator 进入以下重试流程（最多3次），不得挂起等待：

**评估标准（机械可判断）：** `research.json` 存在 + JSON 合法 + `anchors` 数组长度 ≥ 2。不做语义判断，只计数。

**流程：**

0. **若是启动级拒单错误（如 GatewayDraining / task not accepted）：**
   - 先等待一个短退避窗口后原样重试 Researcher spawn：第1次 3 秒，第2次 8 秒，第3次 15 秒
   - 在 `pipeline-state.json` 记录 `researcher_spawn_retry_count`、`last_spawn_error_kind`
   - 只要 child 还没真正开始研究，就不要切到“快研究模式”或把问题误报为 research 质量失败

1. 第1次超时后：检查 `<draft-dir>/research.json`
   - 满足评估标准 → 进入正常路径（Step 1b → Step 2），Writer 完全不知道有过超时
   - 不满足 → 进入第2次重试

2. 第2次重试：spawn 快研究模式 Researcher（`runTimeoutSeconds: 600`），在 task 中内联以下指令：
   ```
   快研究模式（fast_research_mode=true）
   时间预算：8分钟研究 + 2分钟写文件，共10分钟。
   已有产物路径：<draft-dir>/research.json（如存在）
   操作要求：
   1. 先读取已有 research.json（如存在），保留所有现有 anchors，禁止从零重写
   2. 只补充缺少的 evidence anchors，目标：anchors 数组达到 ≥2 条
   3. 补充完成后，合并写回 research.json（merge overwrite，不是覆盖清空）
   4. 若 outline.md 不存在或为空，补写一份最简 outline
   5. 第8分钟必须停止收集，立即写文件
   ```
   第2次完成后重新评估；满足标准 → 正常路径；不满足 → 进入第3次重试

3. 第3次重试：同第2次，spawn 快研究模式 Researcher（`runTimeoutSeconds: 600`），task 完全相同
   第3次完成后重新评估；满足标准 → 正常路径；不满足 → 进入失败上报

4. 3次全不满足：
   - 更新 `pipeline-state.json` 为 `{ state: "error", current_step: "researcher_failed_after_retries", attempt_count: 3, last_artifact_path: "<draft-dir>/research.json" }`
   - **return 结构化错误给 parent/main agent**（不得由 Orchestrator 直接发 message 给老板）
   - 由 parent/main agent 负责通知老板"研究阶段3次重试均失败，本轮需人工决定是否重跑"

**注：** 所有重试均在已有产物基础上补充，不推倒重来。Step 1b 封面图始终在研究阶段通过后才执行（正常路径：走 Unsplash 搜索；若 Orchestrator 判断时间紧张，可使用 cover_fallback_url 快速通过）。

### Step 1b: Cover Image

Runs inline in Orchestrator after researcher artifacts arrive (when `cover_style == "unsplash_search"`):

1. Derive 2-3 English keywords from title via LLM
2. Unsplash API search (`per_page=5`, landscape)
3. Download each candidate, LLM vision audit via `read` tool (not browser — VPS has none). Pass: `safe=true AND relevance>=6`. Stop at first pass.
4. Fallback: `cover_fallback_url` if all fail
5. Save `cover_url` + `cover_audit` to `pipeline-state.json`, clean up temp files

### Steps 2-4: Write → Review → Revise

- **Step 2 (Write):** Chinese-first draft anchored to `research.json`. Each section adds a distinct idea backed by evidence. When spawning the Writer child (`runTimeoutSeconds: 3600`), read `writer_model` from `<workspace>/wechat-article-writer/config.json` as an **optional override only**. If `writer_model` is empty / omitted, Step 2 / Step 4 Writer must simply **inherit the parent/main session model**. Initial drafting should rely on the current topic, `writer-lite-brief.json`, `research.json`, `outline.md`, and `voice-profile.json` only. Do not inject historical top articles or prior high-score article packs into the Writer prompt. See `references/writer-prompt.md`.
- **Writer execution path:** Keep the Writer child/session boundary exactly as-is, but generate正文 through the Writer subagent itself. The active forge flow has **no CLI writer path and no separate API writer executor path**. Writer / Revise are ordinary subagent steps like Researcher / Reviewer / Humanizer / Layout. Do **not** move正文 generation back to the parent orchestrator.
- **Step 3 (Review):** Reviewer is the primary adjudicator and now uses a **single scoring gate**. Severe issues are expressed as score damage plus `critical_issues`, not as a separate blocker gate. The threshold number is **not duplicated in this skill**: the sole authority is `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json` → `review_pass_threshold`. The reviewer must always output `weighted_total` in decision rounds. Spawn Reviewer child with `runTimeoutSeconds: 3600`. See `references/reviewer-rubric.md`.
- **Run-specific release rule:** if a single run needs temporary threshold relaxation or special release approval, record it as a run-specific waiver / override in durable run state or artifacts. Do **not** silently reinterpret that as a global default, and do **not** use memory files to override `config.json`.
- **Step 4 (Revise):** Max **2** automated Writer→Reviewer rounds. Spawn each Writer revision child with `runTimeoutSeconds: 3600`. **Every revise round must use a newly spawned independent Writer subagent; never reuse the previous Writer session for continuing edits.** Continue revising while `weighted_total` is below the effective `review_pass_threshold` from `config.json` and `revision_cycle < 2`. If the second revise still fails, stop extending the same branch and restart from a **fresh first-draft branch** using the locked topic / brief / research pack. Do not revive old `max 3`, `max 5`, `revise-human`, or writer-competition residue as current policy.

Each step spawns a child session. Each child writes its artifact before returning.

**Completion-first orchestration rule (hard requirement):** when any key child step finishes (`researcher` / `writer` / `reviewer` / `humanizer` / `layout`), the orchestrator's **first priority** is to advance the control plane, not to narrate progress. The required order is: **(1)** update `pipeline-state.json`, **(2)** update the run lock, **(3)** write canonical lineage (`children` / `artifact_provenance`), **(4)** move `pending_action` / `current_step` / `phase` to the next step, **(5)** spawn the next child when applicable. Do **not** stop after merely reading or summarizing the child result, and do **not** send a progress-style reply before this state advance is complete.

For xiaolongxia main flow, Writer first draft should also go through a **mechanical-only lite preflight** before Reviewer:
- command: `python /root/.openclaw/skills/wechat-article-forge/scripts/writer_lite_preflight.py <draft-path> --brief-path <writer-lite-brief.json> --research-path <research.json> --output <writer-lite-check.json>`
- `writer-lite-check.json` is a **durable script artifact**, not a hand-written sidecar. The file on disk must be the raw output of `writer_lite_preflight.py`; stale/manual JSON must not stand in for a completed preflight.
- required stable fields: `draft_version`, `checks`, `hard_fail`, `hard_fail_reasons`, `preflight_scope`, `max_pre_review_bounces`
- required provenance fields: `generated_at`, generator metadata, and input fingerprints (`draft_sha256` at minimum; brief/research fingerprints when provided)
- scope is fixed: placeholder residue, dynamic numbers missing timepoint, fake direct quote, README/self-description presented as verified fact, bytes/size misread as human word count
- no scoring, no style advice, max one pre-review bounce
- latest-draft binding is mandatory: if `pipeline-state.json:last_draft_file` and canonical `writer-lite-check.json` do not match on `draft_version` + `draft_sha256`, the stale check may not silently cover the newer draft
- required command: `python /root/.openclaw/skills/wechat-article-forge/scripts/ensure_latest_lite_binding.py --state-path <draft-dir>/pipeline-state.json --mode rerun|waiver [--waiver-reason "..."]`
- the helper must durably do one of two things: (1) rerun preflight and refresh `writer-lite-check.json`, or (2) persist an explicit waiver; in both cases it must write `writer-lite-binding.json` and update `pipeline-state.json` `lite_preflight` fields

### Step 5: Humanize

Spawns Humanizer child (`runTimeoutSeconds: 3600`) with latest draft. Uses `content-humanizer-zh` (`wechat` mode): removes 套话、模板腔、翻译腔、机械连接词, improves rhythm. Preserves all facts, data, structure, thesis. Writes `final.md`.

**Orchestrator 必须在 spawn Humanizer subagent 时，将 `references/humanizer-prompt.md` 的完整内容作为 task prompt 的一部分显式传入。** Humanizer 的权限是“清理 AI 味 + 顺节奏”，不是重写论点，更不是把 Writer 的基础声音抹平成 generic GPT 风格。

### Step 6: Layout

Spawns Layout child (`runTimeoutSeconds: 3600`) with `final.md`. Layout is a **render adapter**, not a second writer. It may identify implicit headings, scanability anchors, visual emphasis, and WeChat-safe structure adaptation, as long as those changes are **semantically preserving**. Writes `final-layout.md`.

Layout **没有文风权，也没有改论权**：若文风、逻辑、事实有问题，只能上游修；Layout 不得借格式化之名继续改写 thesis、facts、arguments、语气或作者人格。

**Orchestrator 必须在 spawn Layout subagent 时，将 `references/layout-prompt.md` 的完整内容作为 task prompt 的一部分显式传入。** 不能依赖 Layout 子 agent 自行读取 SKILL.md — 它运行在 minimal 上下文，不会自动加载。

排版规则详见 `references/layout-prompt.md`，包括：
- 分隔线（字符型，每个 `##` 标题前，首个除外）
- 列表（`·` / `1.` 纯字符，禁用 `-`/`*`/`+` 语法）
- Blockquote `>` 保留不转换
- 加粗（每段最多1处，选最值得停顿的内容；标点/符号必须放在 `**` 外，禁止 `**...。**后文` 这类危险写法）
- 微信不支持语法转换表（行内代码/代码块/表格/删除线/超链接）

---

### Progress Lock Updates (Orchestrator responsibility)

When a parent/main agent has created a run lock (for example `/root/.openclaw/workspace-xiaolongxia/runtime/evening-run.lock.json`), the Orchestrator **must** update it at each step completion. The lock path must be **explicitly passed in** by the caller/context; do **not** guess `morning` / `evening` by probing the filesystem.

Normal progress-lock updates remain **best-effort, non-blocking**: if the lock file does not exist or the write fails, the writing pipeline continues.

**When to update the lock:**
- After Researcher completes → `current_step: "research_done"`, `phase: "researching"`
- After Writer completes → `current_step: "draft_done"`, `phase: "drafting"`
- After Reviewer completes → `current_step: "review_done"`, `phase: "reviewing"`
- After Humanizer completes → `current_step: "humanize_done"`, `phase: "finalizing"`
- After Layout completes → `current_step: "layout_done"`, `phase: "finalizing"`
- On error → `state: "error"`, `note: "<error summary>"`
- On publish-time human handoff (`safe_check`, `login_scan`, `boss_confirm`) → use `scripts/mark_publish_blocked.py` first; see Step 7 below

**Hard orchestration rule:** the orchestrator may not leave a completed child reflected as `subagent_status=pending`, `pending_action=spawn_<same_child>`, or equivalent pre-completion state once the child's required artifact(s) already exist and the child has returned normally. A child completion must be consumed immediately into control-plane state before any commentary or yield-like waiting behavior.

**Fields to update each time (atomic write via .tmp → rename):**
```json
{
  "state": "running",
  "phase": "<current phase>",
  "current_step": "<step_done>",
  "last_progress_at": "<now ISO>",
  "last_transition_at": "<now ISO>",
  "progress_seq": "<previous + 1>",
  "progress_source": "orchestrator",
  "expected_silence_ttl_minutes": 25,
  "max_run_minutes": 45,
  "note": "<optional short note>"
}
```

**Blocked publish handoff rule (Step 7 special case):**
- `pipeline-state.json` is the **strong requirement** and the authoritative control plane.
- Run-lock mirroring is **best-effort** only.
- Before returning `need_user_action`, the orchestrator must first persist a blocked state with at least: `phase`, `step=8`, `current_step`, `waiting_for`, `required_user_action`, stable `safe_check_qr_path`, `relay_status`, `relay_dedupe_key`, `boss_notified_at`, `qr_updated_at`, `blocking_since`, `control_plane_sync`.
- Use the helper: `python3 /root/.openclaw/skills/wechat-article-forge/scripts/mark_publish_blocked.py ...`
- The helper must receive the `pipeline-state.json` path explicitly, and the run-lock path only if the caller explicitly knows it.

**Rules:**
- Always use atomic write: write to `.tmp` file first, then rename to final path.
- Never roll back `phase` or `progress_seq` (single-direction progression only).
- Never use ordinary lock update failures to block the writing pipeline.
- For publish-time human handoff, do **not** treat a text-only child return as sufficient; durable blocked-state persistence comes first.
- Do **not** set `state: "done"` or `phase: "published"` — that is the parent/main agent's responsibility.

---

### Step 7: Publish + Cleanup

0. **Run a lineage audit before publish.** Do not treat "there is a markdown file on disk" as sufficient. The orchestrator must verify that the current publish candidate came from the intended child pipeline, not from parent-session improvisation.
   - Required command: `python /root/.openclaw/skills/wechat-article-forge/scripts/lineage_audit.py <draft-dir> --json --write-state`
   - Exit code `0` = clean lineage; exit code `2` = dirty lineage / repair required.
   - Cleanup must happen only after this audit has been persisted (`lineage_audited_at`).
1. **Required provenance check:** before writing `publish.md`, confirm there is child-session evidence for every required content step already completed in this run: Researcher → Writer → Reviewer → Humanizer → Layout (if layout is not intentionally skipped). Evidence means both: (a) recorded child/session metadata in `pipeline-state.json`, and (b) the expected artifact written by that child.
2. **If lineage is clean:** write `publish.md` with front matter (`cover_url` from state, or fallback) and the resolved `author` for the selected公众号 profile when available. Treat `front matter.title` as the **only** document title. The article body must not carry a duplicate H1 of the same title.
   - Required command immediately after writing `publish.md`: `python /root/.openclaw/skills/wechat-article-forge/scripts/normalize_publish_md.py <draft-dir>/publish.md`
   - If the body still contains an H1 or H2 identical to the frontmatter title after normalization, treat it as a publish-blocking contract violation and repair before publish.
   - `normalize_publish_md.py` now does two things: (a) removes duplicate H1/H2 title headings, and (b) sanitizes dangerous inline bold like `**一句话。**后文` / `**1.1%。**后文` by moving trailing punctuation/symbols outside the bold span before publish.
3. **If lineage is dirty or incomplete:** do **not** publish yet. Instead, enter a repair/rerun branch:
   - Missing Writer evidence → re-spawn Writer from the latest clean checkpoint.
   - Missing Reviewer / Humanizer / Layout evidence → re-spawn only the missing downstream step from the latest clean checkpoint.
   - If the latest available content artifact was written or modified by the parent/orchestrator directly, mark the lineage as contaminated and roll back to the last clean upstream checkpoint.
   - If no trustworthy checkpoint exists, start a fresh run and regenerate the article; do not stop at failure if article output is still required.
4. Publish via `wechat-mp-publisher` using the resolved profile/theme/MCP target only after the lineage audit passes. Falls back to `final.md` if layout was intentionally skipped and that skip is explicitly recorded in state. **Do not call raw `wenyan-mcp.publish_article` directly.** Production theme is singular: **`sspai` only**. Do not use `default`, `shaoshupai`, or any ad-hoc theme alias.
   - **Profile is first-class and fail-closed.** Before draft-box publish, run:
     `python /root/.openclaw/skills/wechat-article-forge/scripts/publish_profile_preflight.py --profile <profile> --state-path <draft-dir>/pipeline-state.json --publish-md <draft-dir>/publish.md`
   - Missing / unknown profile must fail; do not guess config and do not fallback to a default MCP config.
   - The actual `profile` / `mcp_config_file` / `mcp_server` chosen by preflight must be persisted into state/logs for observability.
   - **Mandatory: immediately after wenyan push succeeds, atomically write `draft_box_saved` to `pipeline-state.json`** before doing anything else (no editor page checks, no metadata repair). At minimum persist: `current_step=draft_box_saved`, `appmsgid` (from draft list lookup), `wenyan_push_status=success`, `draft_saved_at=<now-iso>`. Failure to persist this checkpoint is publish-blocking — do not proceed to formal publish until the state is written.
   - This checkpoint is the authoritative proof that the draft exists in WeChat backend. Any recovery flow must first check `pipeline-state.json` for `draft_box_saved` before deciding whether to re-push the draft.
5. If the current run is a cron / worker production flow that explicitly requires reader-side delivery, continue immediately with `wechat-mp-formal-publish`.
   - **`safe_check` / `login_scan` / `boss_confirm` = Orchestrator task endpoint.** When any human checkpoint appears, the Orchestrator must immediately:
     1. Capture the QR code URL/screenshot and save to a stable path: `/root/.openclaw/media/wechat-safe-check/<sanitized-run-id>/safe-check.png`
     2. Call `mark_publish_blocked.py` to persist blocked state to `pipeline-state.json` (required) and run-lock (best-effort)
     3. **Return `need_user_action` immediately — do NOT wait for the scan result, do NOT poll the page, do NOT continue the publish flow**
   - The Orchestrator's session ends here. The parent/main agent receives the `need_user_action` completion event, forwards the QR to the user, waits for confirmation, then resumes formal publish directly (not by re-spawning Orchestrator).
   - Required command pattern before returning:
     ```bash
     python3 /root/.openclaw/skills/wechat-article-forge/scripts/mark_publish_blocked.py \
       --state-path <draft-dir>/pipeline-state.json \
       --run-lock-path <explicit-run-lock-path-if-known> \
       --run-id <run_id> \
       --waiting-for boss_scan \
       --required-user-action safe_check_scan \
       --current-step waiting_safe_check_scan \
       --phase awaiting_human \
       --status need_user_action \
       --safe-check-qr-path /root/.openclaw/media/wechat-safe-check/<sanitized-run-id>/safe-check.png \
       --note "WeChat safe_check detected, QR saved, orchestrator task complete" \
       --relay-status pending_parent_forward \
       --relay-dedupe-key <stable-dedupe-key> \
       --boss-notified-at "" \
       --qr-updated-at <now-iso> \
       --blocking-since <now-iso> \
       --timeout-minutes 10 \
       --resume-context-json '{"browser_session":"default","current_url":"<editor-page-url>","appmsgid":"<appmsgid>","token":"<token>","draft_title":"<title>","detected_at":"<now-iso>"}'
     ```
   - `pipeline-state.json` write failure is publish-blocking. Run-lock failure is not.
   - **Return payload must include `resume_context` + `timeout_at`** so the parent agent can resume formal publish without re-spawning Orchestrator, and so the blocked state can escalate instead of hanging forever:
     ```json
     {
       "status": "need_user_action",
       "waiting_for": "boss_scan",
       "safe_check_qr_url": "https://mp.weixin.qq.com/safe/safeqrcode?...",
       "safe_check_qr_path": "/root/.openclaw/media/wechat-safe-check/<run-id>/safe-check.png",
       "timeout_at": "<now-plus-10m-iso>",
       "resume_context": {
         "browser_session": "default",
         "current_url": "<editor-page-url>",
         "appmsgid": "<appmsgid>",
         "token": "<token>",
         "draft_title": "<title>",
         "detected_at": "<now-iso>"
       }
     }
     ```
6. **External visibility ownership (strict):**
   - The Orchestrator and all downstream child agents are **internal executors only**. They must **never** directly send `message` to the boss / end user, must **never** externally announce “完工 / 成功 / 已发表 / 已提交”, and must **never** treat a child-step completion as business completion.
   - The Orchestrator and all downstream child agents must **never** write `MEMORY.md` or `memory/*.md` in the current workspace. Long-term memory updates belong to the parent/main agent only.
   - If inherited workspace rules mention notifying the boss or writing memory after publish, child agents must interpret those duties as **main-agent-only** unless the parent explicitly delegates them for an internal-only artifact.
   - For formal-publish flows, the Orchestrator must return a **structured internal status** to the parent agent, with enough detail for business judgment. At minimum, use one of: `draft_box_saved`, `need_user_action`, `reader_side_submitted`, `reader_side_published`, `reader_side_in_review`, `failed`.
   - For `need_user_action`, include enough durable detail for parent forwarding/recovery: `waiting_for`, `required_user_action`, `safe_check_qr_path`, `relay_status`, `relay_dedupe_key`, `boss_notified_at`, `qr_updated_at`, `blocking_since`, `control_plane_sync`, plus a one-line instruction for the parent agent to forward.
   - If `wechat-mp-formal-publish` surfaces a `safe_check` / QR-code action, the Orchestrator must not message the user directly. Instead it must save the QR artifact to a stable path and return the structured blocked-state payload after the helper write succeeds.
7. Cleanup: first clear stale blocked-state fields when the run moves to `in_review` / `published` / `done` / `failed` / `cancelled`:
   - `python /root/.openclaw/skills/wechat-article-forge/scripts/clear_publish_blocked_state.py --state-path <draft-dir>/pipeline-state.json --run-lock-path <explicit-run-lock-if-known> --status <in_review|published|failed|cancelled> --phase <published|done> --current-step <reader_side_in_review|reader_side_published|publish_failed|publish_cancelled> [--state done|error]`
   - Then run `bash /root/.openclaw/skills/wechat-article-forge/scripts/cleanup.sh <draft-dir>` — removes intermediate files, retains `pipeline-state.json` + `publish.md`
   - Do **not** delete the active QR/evidence artifact while the run is still in `awaiting_human` / `blocked`.
   - Old blocked-state fields and old QR artifacts may be cleared only after the publish flow resumes, reaches `in-review` / `published` / `done`, fails/cancels, or a newer QR has been durably written for the same run.
8. Delete `session.json` from workspace root (stale topic handoff)

---

### Key Rules

Grouped by concern. Each explains *why* — rigid directives without context are fragile and break on edge cases.

#### Subagent Execution

- **Steps 1-7 each run in their own child session.** The orchestrator routes and enforces gates — it never writes content. Inline execution degrades quality because the orchestrator's context (outlines, prior feedback) bleeds into output, breaking blind review. Follow `spawn-subagent-guardrails` for spawn → yield → collect protocol.
- **Children self-persist artifacts.** Pass each child an explicit target path. This makes dropped completion events survivable — the orchestrator recovers from disk.
- **Child outputs are verbatim.** The orchestrator must not synthesize or edit article/review/body artifacts.
- **Parent write prohibition is literal, not aspirational.** The orchestrator must not directly author or overwrite `draft*.md`, `review*.json|md`, `final*.md`, `final-layout*.md`, or any other body artifact that is supposed to come from a child session. Parent-owned files are limited to control/state/metadata artifacts such as `pipeline-state.json`, `publish.md`, and lightweight routing metadata.
- **External communication prohibition is literal too.** The orchestrator and its descendants must not directly contact the end user/boss via `message`; all user-visible communication is owned by the parent/main agent. Child sessions may only return internal results upward.
- **Memory ownership belongs to the parent/main agent.** The orchestrator and its descendants must not write `MEMORY.md` or `memory/*.md`; they may emit internal summaries for the parent agent to decide what is worth remembering.
- **Spawn failure = pipeline failure for that step.** If a child cannot be created because `sessions_spawn` errors, the gateway closes, or transport/websocket setup fails, the orchestrator must stop and report the failure. It must not continue by writing the missing child artifact itself.

#### Session & State

- **Wait by completion event, not polling.** Polling (`sessions_list`, `exec sleep`) wastes resources and races with concurrent writes. A child is failed only on explicit error, abort, or after the 1-hour budget.
- **`pipeline-state.json`: full-file overwrite only.** The edit tool's exact-match breaks when concurrent children modify the file. Read → merge in memory → write.
- **Canonical lineage writes only.** New writes to `children[...]` + `artifact_provenance` must go through `scripts/update_pipeline_lineage.py`, which writes canonical step keys only and rejects unknown steps. When `lineage_audit.py --write-state` is used on an existing run, it may wide-read legacy aliases but must write back canonical `children` / `artifact_provenance` keys plus `schema_version` / `lineage_audited_at`.
- **Record provenance.** `run_id`, `source_mode`, session keys per artifact. Successful content step = output file + child-session evidence, not file presence alone.
- **Human-blocked publish state is durable control plane, not chat garnish.** On `safe_check` / login / boss-confirm checkpoints, write `pipeline-state.json` first, then optionally mirror to the run lock, then return `need_user_action` upward.
- **Blocked state must carry timeout + resume context.** Persist at least `status`, `waiting_for`, `required_user_action`, `resume_context`, `updated_at`, and `timeout_at`. If the timeout is crossed, escalate state instead of hanging silently.
- **Do not overload `pending_action` with user verbs.** Use `required_user_action` for the human action, and if `pending_action` must change, keep it as a wait-state such as `wait_boss_scan` / `wait_boss_confirm`.
- **Return status upward with business-safe semantics.** Child completion should describe internal step state, not user-facing business success. Use explicit states such as `need_user_action` / `reader_side_in_review` / `failed` instead of vague “done” summaries when the business process is not actually finished.
- **Publish is fail-closed, not fail-stop.** If provenance is missing, inconsistent, or contaminated by parent-written body text, the pipeline must block direct publish and switch into repair/rerun mode from the last clean checkpoint. The system should still aim to produce an article, but only through a clean lineage.

#### Fresh Run vs Resume

- **Cron/scheduled jobs start fresh.** New slug; suffix on collision. Dropped-completion recovery is the only exception — see `references/recovery-protocol.md`.
- **Fresh runs must not inherit old blocked publish state.** New slug + new `run_id` means no carry-over of old `safe_check_qr_path`, `relay_status`, or other wait-for-human fields.
- **Resume requires explicit user intent** (provide `draft_id` or ask to continue a named draft).

#### Content Integrity

- **Writer never self-reviews.** Reviewer remains independent from long upstream context. By default do not pass outline / full brief; if a consistency check is truly needed, only a **minimal brief summary** may be passed, and it never becomes the scoring rubric.
- **Humanizer: tone only.** Never add facts, remove evidence, rewrite arguments, or flatten the Writer's base voice into generic platform copy. Completion requires a text diff or explicit `noop_reason`.
- **Topic fidelity.** Every revision preserves the 初心 (purpose in `pipeline-state.json`). Drift = FAIL.

#### Research

- **exec + public RSS, not browser.** Keyless paths are more reliable in cron/VPS. Merge across queries; if extraction fails, switch sources and note substitution.

#### Publish

- **Default path:** `wechat-mp-publisher` writes to the WeChat draft box. In ordinary manual workflows, the user may publish manually afterward.
- **Cron / worker production path:** when the run explicitly requires reader-side delivery, the pipeline must continue into `wechat-mp-formal-publish` and must not report success until the article is actually submitted / published / in-review in the official account backend.
- **Blocked publish cleanup is mandatory.** Once the boss has scanned/confirmed, the article reaches `in-review` / `published` / `done`, the run fails/cancels, or a newer QR replaces the older one, stale blocked-state fields must be cleared or overwritten so resume logic does not keep waiting on a dead handoff.
- Theme/MCP target must come from the explicitly selected公众号 unless the user explicitly overrides it. If cron delivery status needs to be reported to Feishu, that outward notification is owned by the parent/main agent via the explicit Feishu target context. The only allowed production theme ID is `sspai`.
- **公众号必须显式指定。** `write` / `draft` / `publish` 三类动作里，只接受明确写出的公众号名称（例如《不上班也有Money》《小龙虾有话说》）。没有名称就先问，不得使用 `default` 或任何隐式默认号。
- `run` / `pipeline-state.json` / `publish.md frontmatter` / `publish_profile_preflight` 必须显式携带同一个标准字段 `profile`，不得擅自用 `公众号` 等自然语言字段替代，也不得回退到顶层默认作者/发布配置猜测账号。
- `publish.md` 的 `front matter.title` 是文章唯一标题真源；正文禁止重复该标题的 H1/H2。
- `publish.md` 禁止保留危险行内加粗：`**...。**后文`、`**...%**后文`、以及其他"加粗 span 以标点/符号结尾且后面立即续正文"的模式；标点/符号必须放在 `**` 外。
- **`publish.md` frontmatter 强制字段（wenyan-mcp 协议要求，缺一不可）：**
  > ⚠️ 此规范仅适用于最终 `publish.md`，不适用于写作过程中的草稿文件（`draft*.md`、`final*.md` 等）。草稿 frontmatter 与发布 frontmatter 是两套独立格式，不要混淆。
  ```yaml
  ---
  title: "文章标题"
  author: "公众号名称"       # 显示署名（读者可见）；通常等于公众号名称，必要时可为真实作者名
  profile: "公众号名称"      # 账号路由键，必须与 profiles.json 中的 name 字段精确匹配
  cover: "https://..."      # 封面 URL，不得为空；若主封面不可达，使用 https://picsum.photos/1200/800 作为 fallback
  theme: "sspai"            # 唯一允许的 production theme；不得使用 default、shaoshupai 或其他别名
  slug: "slug-string"       # 与草稿目录名一致
  ---
  ```
  **`publish.md` 只允许以上 6 个标准字段，任何额外字段均视为协议违规。** 禁止使用的常见错误字段：`account`、`date`、`公众号`、`default`、`profile_name`。子 agent 写 `publish.md` 时必须严格遵守此格式，否则 wenyan-mcp 将报"未能找到文章标题"并拒绝发布。

---

## Review Dimensions

Reviewer scores 0-10 on **craft-observable** dimensions (not outcome predictions):

| Dimension | Weight |
|-----------|--------|
| Insight Density (洞察密度) | 14% |
| Originality (新鲜感) | 14% |
| Emotional Resonance (情感共鸣) | 20% |
| Completion Power (完读力) | 18% |
| Voice (语感) | 18% |
| Title (标题) | 16% |

**Pass/Fail source of truth:** A draft passes only when Reviewer reports `weighted_total >= review_pass_threshold`, where `review_pass_threshold` is read from `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json`.

**Scores:** `weighted_total` is the single active hard gate. Severe issues no longer live in a separate blocker gate; they must be fused into scoring and surfaced through `critical_issues`. Per-dimension floors and `Originality` thresholds remain diagnostic / advisory unless explicitly re-enabled by caller policy.

**Severe issues (must heavily damage score):** 教材腔, 翻译腔, 鸡汤腔, 灌水, 模板化, 标题党, 失焦, 论证失撑, 事实边界越界.

Full rubric with scoring criteria: `references/reviewer-rubric.md`

---

## Architecture

```
Orchestrator (Child Pipeline Coordinator) — routes, tracks, enforces gates
    ├── Researcher Subagent — topic discovery, source gathering, outline
    ├── Writer Subagent — drafts + revises
    ├── Reviewer Subagent — unified scoring adjudication
    ├── Humanizer Subagent — removes AI tone, improves rhythm
    └── Layout Subagent — WeChat render adapter
```

---

## Configuration

Configure via `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json`:

| Field | Default | Description |
|-------|---------|-------------|
| `profiles_path` | `"/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/profiles.json"` | 公众号注册表；`write` / `draft` / `publish` 时必须从这里的名称中显式选择 |
| `default_article_type` | `"教程"` | Default article type (科普/教程/观点/资讯) |
| `wechat_author` | `""` | 不提供全局默认作者；必须使用显式选中的公众号 profile 中的作者 |
| `published_log_path` | `""` | 不提供全局默认台账路径；必须使用显式选中的公众号 profile 中的台账 |
| `cover_style` | `"unsplash_search"` | `unsplash_search` = auto search + LLM vision audit; `from_content` = use fallback URL |
| `unsplash_access_key` | — | Unsplash API Access Key (required when cover_style=unsplash_search) |
| `cover_fallback_url` | `"https://picsum.photos/1200/800"` | Fallback cover URL when all candidates fail audit |
| `review_pass_threshold` | see active `config.json` | **唯一权威的评分通过门槛数字**；Reviewer 是否通过、自动 revise 是否继续，只认这个字段。当前若 `config.json` 为 `7.8`，那 `7.8` 就是现行默认线；单轮特批必须走 run-specific waiver，不得嘴上说特批、实际却改全局默认 |
| `writer_model` | Optional | Optional override for Writer subagent only; if empty, Orchestrator should omit `sessions_spawn.model` and let Writer inherit the parent/main session model for Step 2 and Step 4 |
| `word_count_targets` | See defaults | Min/max word counts per article type |

For multiple公众号, define each account in `profiles.json` using its actual公众号名称 as the key. Every `write` / `draft` / `publish` run must explicitly specify one of those names.

See `references/data-layout.md` for full config schema.

---

## References

| File | When to load |
|------|-------------|
| `references/writer-prompt.md` | Step 2 (writing) and Step 4 (revision) |
| `references/reviewer-rubric.md` | Step 3 (review) — full scoring rubric / unified scoring gate criteria |
| `references/humanizer-prompt.md` | Step 5 — Humanizer boundary: clean AI smell without overwriting writer voice |
| `/root/.openclaw/skills/content-humanizer-zh/SKILL.md` | Step 5 — Humanizer subagent tone-cleaning rules |
| `references/viral-article-traits.md` | Step 2 — Writer self-check list |
| `references/pipeline-state.md` | On resume or compaction — state machine schema + protocol |
| `references/recovery-protocol.md` | On cron resume — dropped-completion recovery rules |
| `references/data-layout.md` | Directory structure, slug generation, config/session schemas |
| `references/agent-config.md` | Setup — Gateway, AGENTS.md, environment config |
| `references/quality-checks.md` | Step 3 — content quality gates |
| `references/templates.md` | Step 1 — starting templates by article type |
| `references/voice-profile-schema.json` | Step 1 — voice profile field definitions |
| `references/default-voice-profile.json` | Step 1 — fallback voice profile |
