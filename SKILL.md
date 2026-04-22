---
name: wechat-article-forge
description: End-to-end 微信公众号 (WeChat Official Account) article writing and publishing pipeline. Multi-agent workflow (active mainline): researcher subagent (topic + outline) → writer subagent (draft) → reviewer subagent (primary adjudication) → revise loop (max 2) → layout subagent (WeChat render adapter) → publish. Reviewer pass is the final content authority; no downstream prose rewriting. Use when user asks to write, draft, or publish a WeChat article, or says "forge write/draft/publish/topic/voice/status". For write/draft/publish requests, require the user to explicitly name the target公众号; never assume a default account.
---

# wechat-article-forge

> 从选题到发布的公众号一体化写作工作流

Multi-agent pipeline: Orchestrator delegates writing and reviewing to independent subagents. The orchestrator never writes or reviews — it routes, tracks versions, and enforces quality gates.

## Scope

**Handles:** Topic research (researcher subagent) → Chinese-first writing → quality review → revise loop → Reviewer-approved final draft → WeChat render-adapter layout (layout subagent) → publishing to WeChat draft box via `wechat-mp-publisher`, and in cron / worker production flows may continue into formal reader-side publish via `wechat-mp-formal-publish`.

**Does NOT handle:** Git/version control, non-WeChat platforms, post-publish analytics, WeChat messaging/customer service.

**Ends at:** By default, article saved to WeChat draft box. In cron / worker production flows that explicitly require reader-side publication, the pipeline must continue into `wechat-mp-formal-publish` until the article is actually submitted / published / in-review on the reader side.

---

## Commands

Trigger any command below, or see `skill.yml` for the full trigger pattern list.

| Command | What it does |
|---------|-------------|
| `forge topic X` | Research trending angles, propose 3 options with hooks |
| `forge write X for <公众号名称>` | Full pipeline: research → reviewed draft → layout → publish；必须显式指定公众号名称 |
| `forge draft X for <公众号名称>` | Write and review only, stop before publish；必须显式指定公众号名称 |
| `forge publish <slug> for <公众号名称>` | Publish an existing draft to WeChat draft box；必须显式指定公众号名称 |
| `forge voice train` | Analyze past articles to extract a concrete `voice-pack.json` plus fallback `voice-profile.json` |
| `forge status` | Show pipeline status and pending drafts |

If no subject given, loads from `session.json` (set by `forge topic`). See `references/data-layout.md`.

For `write` / `draft` / `publish`: if the user did not explicitly name the target公众号, stop and ask. Never route to a default account, never substitute `default`.

---

## Pipeline (6 Main Steps + Cover)

State persists to `pipeline-state.json` — survives compaction. See `references/pipeline-state.md`.

| # | Step | Who | Output |
|---|------|-----|--------|
| 1 | Research + Outline | Researcher subagent | `research.json`, `outline.md` |
| 1b | Cover Image | Orchestrator (inline) | `cover_url` in `pipeline-state.json` |
| 2 | Write | Writer subagent | `draft.md` |
| 3 | Review | Reviewer subagent | `review-v*.json` |
| 4 | Revise | Writer subagent | `draft-v*.md` (max 2 rounds; still below `config.json.review_pass_threshold` ⇒ restart from fresh first-draft branch) |
| 5 | Layout | Layout subagent | `final-layout.md` |
| 6 | Publish + Cleanup | Orchestrator | `publish.md` → draft box |

### Step 1: Research + Outline

Orchestrator creates the slug/draft directory and initial `pipeline-state.json`, then spawns a Researcher child (`runTimeoutSeconds: 1320`):

1. **Dedup:** Scan the effective publish log for the explicitly selected公众号 over the last 14 days. Same topic + angle = reject. **Keyword hard-cap:** if any core keyword appears in 2+ articles within 7 days, reject outright. If all candidates blocked, pick lowest-overlap and record `topic_dedup_override_reason`.
2. **Topic strategy for scheduled/daily runs:** unless the user explicitly locks a different direction, prefer a **24-72h hot-topic entrypoint** in the target domain (new model, new product, major company move, viral demo, failure/controversy, financing/org signal). Do **not** turn this into a roundup. One hot hook only. Hot topic is the shell; the thesis/judgment is the core.
   - **Caller-precheck override (new default for xiaolongxia main flow):** if the parent/main agent already passes a hot-topic precheck result (event name / keywords / why-now / thesis seed), treat that as the starting candidate pack. Researcher should verify and sharpen it, not ignore it and rediscover the topic from scratch, unless the evidence clearly collapses.
   - **Authority boundary:** main agent has first topic-pick authority; Orchestrator has process authority only; Researcher has verification + limited re-route authority only. Writer/Layout have no topic-change authority.
3. **Sources:** use the personal skill `jj-search-stack` as the operational search policy. That stack requires URL-encoding queries before applying any URL template, defines the boundary with native `web_search`, keeps only the validated free entrypoints (Sogou WeChat / Sogou Web / DuckDuckGo HTML / Startpage / Brave Search), requires `web_fetch` on the candidate source page itself for verification/extraction, and uses `tavily-search` (`search` / `extract`) as the stable enhancement + fallback layer. It explicitly avoids Bing search result pages and Eastmoney search pages as primary entrypoints in this environment. For market topics: ≥1 macro trigger, ≥1 market-structure/flow, ≥1 investor-position source with concrete numbers. For daily/hot-topic articles: include at least one timely trigger source proving why this should be published now.
4. **Eligibility gate:** Finalize only if ≥2 hard evidence anchors support the thesis. Prefer observable data over broad commentary.
5. **Outline:** 6-8 sections, 1 main insight + 2 named sub-insights → `outline.md`.
   - `outline.md` is **prose-safe only**: section headings + body-ready content points.
   - Never let placeholders / planning labels / note-to-writer text enter the outline. Those belong in `writer-lite-brief`, not in `outline.md`.
   - **Mechanical gate before Writer:** run `python /root/.openclaw/skills/wechat-article-forge/scripts/outline_gate.py <draft-dir>/outline.md --output <draft-dir>/outline-gate.json` and fail closed if it reports backstage cues.
6. **Persist:** Researcher saves `research.json` and `outline.md` before final answer.
   - For high-risk facts, `research.json` should also carry a minimal structured sidecar (recommended: `fact_records`) so Writer + lite preflight can distinguish `api_snapshot`, `paraphrase_only` / `verbatim`, `readme_claim`, and `file_size_bytes` cases.
   - Researcher should also write a **small style-aware sidecar** when voice assets are available or can be derived. Recommended fields are `style_exemplar_pack`, `anti_exemplars`, `entity_alias_map`, `must_attribute_claims`, `title_directions`, `angle_risks`. This pack must contain **short functional examples**, not entire historical articles and not raw `SOUL.md` / `AGENTS.md` / `MEMORY.md` dumps.
   - **Mechanical gate before Writer:** run `python /root/.openclaw/skills/wechat-article-forge/scripts/validate_research_artifact.py <draft-dir>/research.json --output <draft-dir>/research-gate.json` and fail closed if high-risk claims lack structured fact records.
7. **Prompt policy:** Researcher must follow `references/researcher-prompt.md`, especially the validated search stack / avoid-list rules.

See `references/researcher-prompt.md` for the detailed, validated search policy.

### Steps 2-4: Write → Review → Revise

- **Step 2 (Write):** Chinese-first draft anchored to `research.json`. Each section adds a distinct idea backed by evidence. When spawning the Writer child (`runTimeoutSeconds: 3600`), read `writer_model` from `<workspace>/wechat-article-writer/config.json` as an **optional override only**. If `writer_model` is empty / omitted, Step 2 / Step 4 Writer must simply **inherit the parent/main session model**.
- **Writer input contract (new default):** Initial drafting should rely on the current topic, `writer-lite-brief.json`, `research.json`, `outline.md`, plus the strongest available voice asset resolved in this exact order: `profiles.json.voice_pack_path` → `profiles.json.voice_profile_path` → workspace `voice-pack.json` → workspace `voice-profile.json` → `references/default-voice-pack.json` → `references/default-voice-profile.json`. Within each source, `voice-pack.json` is preferred because it contains concrete author evidence (openings, turns, endings, sharp lines, anti-patterns, persona boundary). Use `scripts/resolve_voice_assets.py` when the source order is ambiguous.
- **Allowed style evidence:** compact `style_exemplar_pack` and `anti_exemplars` may be injected into the Writer prompt when they are explicitly derived from the selected profile / account's past writing and stored as short functional examples. **Do not inject full historical top articles or raw prior high-score article packs into the Writer prompt.** The rule is: learn the author's moves, not copy entire old articles. See `references/writer-prompt.md`.
- **Authoring responsibility:** Writer owns the article's human-likeness from the first draft onward. In the active pipeline there is **no downstream Humanizer**. Writer must internally perform: factual skeleton → authorial rewrite → candidate selection for opening / ending / title direction.
- **Writer execution path:** Keep the Writer child/session boundary exactly as-is, but generate正文 through the Writer subagent itself. The active forge flow has **no CLI writer path and no separate API writer executor path**. Writer / Revise are ordinary subagent steps like Researcher / Reviewer / Layout. Do **not** move正文 generation back to the parent orchestrator.
- **Pre-review style lint (inline gate, not a child step):** After every Writer draft and before every Reviewer spawn, run `python /root/.openclaw/skills/wechat-article-forge/scripts/style_fingerprint_lint.py <draft-path> --output <draft-dir>/style-lint.json`. This lint only checks authorial red lights such as `opening_interchangeability`, `transition_template_dependence`, `ending_sloganism`, repeated scaffold phrases, and overly uniform rhythm. If it blocks, the orchestrator may trigger **one** `style-only` Writer bounce before the first review. Track this under `pipeline-state.json.style_lint`; do **not** mint a new canonical child step.
- **Step 3 (Review):** Reviewer is the primary adjudicator and uses a **single scoring gate**. Severe issues are expressed as score damage plus `critical_issues`, not as a separate blocker gate. The threshold number is **not duplicated in this skill**: the sole authority is `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json` → `review_pass_threshold`. The reviewer must always output `weighted_total` in decision rounds, and must explicitly evaluate `opening_interchangeability`, `author_presence`, `transition_template_dependence`, and `ending_sloganism`. Spawn Reviewer child with `runTimeoutSeconds: 3600`. See `references/reviewer-rubric.md`.
- **Post-review freeze:** once Reviewer returns pass for the latest draft, that draft is the final body. If it still needs a downstream tone-cleaning pass to be publishable, Reviewer must return revise. No post-review prose rewriter exists in the active pipeline.
- **Step 4 (Revise):** Max **2** automated Writer→Reviewer rounds. Spawn each Writer revision child with `runTimeoutSeconds: 3600`. **Every revise round must use a newly spawned independent Writer subagent; never reuse the previous Writer session for continuing edits.** Continue revising while `weighted_total` is below the effective `review_pass_threshold` from `config.json` and `revision_cycle < 2`. If the second revise still fails, stop extending the same branch and restart from a **fresh first-draft branch** using the locked topic / brief / research pack.

Each step spawns a child session. Each child writes its artifact before returning.

### Step 5: Layout

**Reviewer pass = content final.** The latest Reviewer-approved `draft.md` / `draft-v*.md` is the final content authority. No downstream child may rewrite prose, facts, thesis, argument strength, or voice. Reviewer pass must durably persist `reviewed_draft_file` + `reviewed_draft_sha256` at review completion; audit does not backfill them from current disk bytes.

Spawns Layout child (`runTimeoutSeconds: 3600`) with the Reviewer-approved draft recorded in `pipeline-state.json:reviewed_draft_file` (fallback for legacy recovery only: `last_draft_file`). Layout is a **render adapter**, not a second writer. It may identify implicit headings, scanability anchors, visual emphasis, and WeChat-safe structure adaptation, as long as those changes are **semantically preserving**. Writes `final-layout.md`.

Before spawning Layout, persist `layout_input_file` and `layout_input_sha256` in `pipeline-state.json`. The lineage helper must fail closed if reviewer-approved bytes are missing or if Layout input does not match them. The publish lineage audit also fails closed if Layout cannot be proven to have consumed the exact Reviewer-approved draft bytes.

Layout **没有文风权，也没有改论权**：若文风、逻辑、事实有问题，只能退回 Writer/Reviewer；Layout 不得借格式化之名继续改写 thesis、facts、arguments、语气或作者人格。

### Key Rules (selected additions for authorial writing)

- **Concrete author evidence beats abstract style description.** When both exist, prefer `voice-pack.json` over `voice-profile.json`.
- **Compact exemplars are allowed; raw historical article stuffing is not.** Exemplars must be short, functional, and profile-specific.
- **Workspace persona stays private to the workspace.** `SOUL.md`, `AGENTS.md`, `MEMORY.md`, and other account-specific persona materials are source material for `forge voice train`, not direct Writer prompt payloads for the shared repo skill.
- **Reviewer judges author presence, not only banned phrase count.** Avoid turning human-likeness into a pure blacklist game.
- **Mechanical preflight stays mechanical.** `writer_lite_preflight.py` only checks finite red lights; it must not evolve into a style judge.
- **Style lint stays style-only.** `style_fingerprint_lint.py` may block template-sounding prose, but it must not score facts, provenance, or policy compliance.
- **Layout cannot rescue weak voice.** If the article still sounds generic after review, the pipeline must go back to Writer.

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

**Scores:** `weighted_total` is the single active hard gate. Severe issues no longer live in a separate blocker gate; they must be fused into scoring and surfaced through `critical_issues`.

Full rubric with scoring criteria: `references/reviewer-rubric.md`

---

## Architecture

```text
Orchestrator (Child Pipeline Coordinator) — routes, tracks, enforces gates
    ├── Researcher Subagent — topic discovery, source gathering, outline
    ├── Writer Subagent — factual skeleton → authorial rewrite → candidate selection
    ├── Reviewer Subagent — unified scoring adjudication and final content authority
    └── Layout Subagent — WeChat render adapter
```

---

## Configuration

Configure via `/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/config.json`:

| Field | Default | Description |
|-------|---------|-------------|
| `profiles_path` | `"/root/.openclaw/workspace-xiaolongxia/wechat-article-writer/profiles.json"` | 公众号注册表；`write` / `draft` / `publish` 时必须从这里的名称中显式选择 |
| `default_article_type` | `"教程"` | Default article type (科普/教程/观点/资讯) |
| `cover_style` | `"unsplash_search"` | `unsplash_search` = auto search + LLM vision audit; `from_content` = use fallback URL |
| `review_pass_threshold` | see active `config.json` | 唯一权威的评分通过门槛数字 |
| `writer_model` | Optional | Optional override for Writer subagent only; if empty, Writer inherits the parent/main session model |
| `word_count_targets` | See defaults | Min/max word counts per article type |

Voice assets live in the article workspace and are account-specific whenever possible:
- `profiles.json.voice_pack_path` / `profiles.json.voice_profile_path` — profile-specific compiled assets
- workspace `voice-pack.json` / `voice-profile.json` — workspace-level compiled assets
- `default-voice-pack.json` / `default-voice-profile.json` — last resort fallback assets shipped with the skill

OpenClaw workspace persona materials such as `SOUL.md`, `AGENTS.md`, and `MEMORY.md` remain **outside** the shared repo contract. They should be compiled into `voice-pack.json` / `voice-profile.json`, then consumed through the resolution order above.

See `references/data-layout.md` for full config schema.

---

## References

| File | When to load |
|------|-------------|
| `references/writer-prompt.md` | Step 2 (writing) and Step 4 (revision) |
| `references/reviewer-rubric.md` | Step 3 (review) — full scoring rubric / unified scoring gate criteria |
| `references/researcher-prompt.md` | Step 1 — topic research / evidence / style-sidecar rules |
| `references/data-layout.md` | Directory structure, config, session, voice asset schemas |
| `references/voice-pack-schema.json` | Voice-pack field definitions — preferred authorial asset |
| `references/voice-profile-schema.json` | Voice-profile field definitions — fallback summary asset |
| `references/default-voice-pack.json` | Fallback authorial asset |
| `references/default-voice-profile.json` | Fallback summary asset |
| `references/voice-train-prompt.md` | `forge voice train` — how to build voice-pack + voice-profile |
| `references/layout-prompt.md` | Step 5 — render-adapter rules |
