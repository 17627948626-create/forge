# Pipeline State Machine (Compaction-Safe)

The orchestrator persists state to `<article-workspace>/drafts/<slug>/pipeline-state.json` **before every child agent spawn and after every step completion**. This file is the single source of truth for resuming after context compaction or session restart.

For publish-time human handoff (`safe_check`, `login_scan`, `boss_confirm`), `pipeline-state.json` is the **durable control plane**. Text-only child completion is not enough.

## Base Schema

```json
{
  "schema_version": "2026-04-09.lineage-v2",
  "slug": "growth-mindset-ai-20260219",
  "run_id": "manual:example:123",
  "source_mode": "fresh",
  "profile": "不上班也有Money",
  "published_log_path": "<article-workspace>/published-log.jsonl",
  "step": 5,
  "phase": "reviewing",
  "purpose": "One-sentence 初心 statement",
  "revision_cycle": 2,
  "max_revisions": 2,
  "pass_threshold": "mirror of config.review_pass_threshold (optional snapshot, not authority)",
  "min_dimension": 6,
  "last_score": 8.60,
  "last_review_file": "review-v2.json",
  "last_draft_file": "draft-v3.md",
  "reviewed_draft_file": "draft-v3.md",
  "reviewed_draft_sha256": "abc123",
  "review_passed_at": "2026-02-19T13:49:50Z",
  "content_finalized_by": "reviewer",
  "content_final_artifact": "draft-v3.md",
  "layout_input_file": "draft-v3.md",
  "layout_input_sha256": "abc123",
  "layout_output_file": "final-layout.md",
  "lite_preflight": {
    "binding_status": "matched",
    "binding_checked_at": "2026-02-19T13:49:31Z",
    "binding_artifact": "<article-workspace>/drafts/growth-mindset-ai-20260219/writer-lite-binding.json",
    "last_draft_file": "draft-v3.md",
    "last_draft_version": "draft-v3",
    "last_draft_sha256": "abc123",
    "latest_check_path": "<article-workspace>/drafts/growth-mindset-ai-20260219/writer-lite-check.json",
    "previous_check_draft_version": "draft-v2",
    "previous_check_draft_sha256": "old456",
    "latest_check_draft_version": "draft-v3",
    "latest_check_draft_sha256": "abc123",
    "match": true,
    "waiver": null,
    "resolution": {
      "action": "rerun_preflight"
    }
  },
  "style_lint": {
    "artifact": "<article-workspace>/drafts/growth-mindset-ai-20260219/style-lint.json",
    "draft_file": "draft-v3.md",
    "draft_sha256": "abc123",
    "status": "pass",
    "bounce_count": 0,
    "blocking_codes": []
  },
  "child_label": "reviewer-growth-mindset-v3",
  "child_status": "pending",
  "pending_action": "spawn_reviewer",
  "lineage_status": "clean",
  "lineage_audited_at": "2026-02-19T13:49:30Z",
  "last_clean_step": "writer",
  "repair_attempts": 0,
  "children": {
    "writer": [{
      "session_key": "agent:main:child:writer-example",
      "label": "writer-growth-mindset-v3",
      "model": "github-copilot/claude-opus-4.6",
      "status": "done",
      "artifacts": ["draft-v3.md"]
    }],
    "reviewer": [{
      "session_key": "agent:main:child:reviewer-example",
      "label": "reviewer-growth-mindset-v3",
      "model": "openai-codex/gpt-5.4",
      "status": "done",
      "artifacts": ["review-v2.json"]
    }]
  },
  "artifact_provenance": {
    "draft-v3.md": {
      "producer_type": "child",
      "producer_step": "writer",
      "session_key": "agent:main:child:writer-example",
      "model": "github-copilot/claude-opus-4.6"
    },
    "review-v2.json": {
      "producer_type": "child",
      "producer_step": "reviewer",
      "session_key": "agent:main:child:reviewer-example",
      "model": "openai-codex/gpt-5.4"
    }
  },
  "cover_url": "https://images.unsplash.com/photo-xxx",
  "cover_audit": {"safe": true, "relevance": 8, "reason": "..."},
  "html_rendered": false,
  "published": false,
  "error": null,
  "updated_at": "2026-02-19T13:50:00Z"
}
```

## Human-Blocked Publish Schema (Publish phase)

When reader-side publish hits a human checkpoint (`safe_check`, login QR, boss confirmation), the orchestrator must **first** durably write a blocked state, then return `need_user_action` upward.

Recommended durable QR location: `<article-workspace>/media/wechat-safe-check/<sanitized-run-id>/safe-check.png`

- Must be a **stable absolute path**
- Must **not** be under `/tmp`
- Must be **unique per run** (directory or filename contains `run_id` or its sanitized form)
- Must not rely on a shared fixed path reused across runs

### Required blocked-state fields

```json
{
  "run_id": "cron:evening:2026-04-02T20:00:00+08:00",
  "status": "need_user_action",
  "step": 8,
  "phase": "awaiting_human",
  "current_step": "waiting_safe_check_scan",
  "waiting_for": "boss_scan",
  "required_user_action": "safe_check_scan",
  "pending_action": "wait_boss_scan",
  "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/cron-evening-2026-04-02T20-00-00-08-00/safe-check.png",
  "qr_verified": true,
  "qr_verification_method": "manual",
  "relay_status": "pending_parent_forward",
  "relay_dedupe_key": "cron:evening:2026-04-02T20:00:00+08:00:safe_check_scan:1",
  "boss_notified_at": null,
  "qr_updated_at": "2026-04-02T12:01:11Z",
  "blocking_since": "2026-04-02T12:01:11Z",
  "timeout_at": "2026-04-02T12:11:11Z",
  "control_plane_sync": "complete",
  "note": "WeChat safe_check popped after clicking continue publish",
  "resume_context": {
    "browser_session": "default",
    "current_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?...",
    "appmsgid": "100000148"
  },
  "blocking": {
    "step": 8,
    "phase": "awaiting_human",
    "current_step": "waiting_safe_check_scan",
    "waiting_for": "boss_scan",
    "required_user_action": "safe_check_scan",
    "safe_check_qr_path": "<article-workspace>/media/wechat-safe-check/cron-evening-2026-04-02T20-00-00-08-00/safe-check.png",
    "qr_updated_at": "2026-04-02T12:01:11Z",
    "blocking_since": "2026-04-02T12:01:11Z",
    "timeout_at": "2026-04-02T12:11:11Z",
    "note": "WeChat safe_check popped after clicking continue publish"
  },
  "handoff": {
    "relay_status": "pending_parent_forward",
    "relay_dedupe_key": "cron:evening:2026-04-02T20:00:00+08:00:safe_check_scan:1",
    "boss_notified_at": null
  },
  "updated_at": "2026-04-02T12:01:11Z"
}
```

### Handoff semantics

| Field | Meaning |
|-------|---------|
| `relay_status` | Parent-forwarding status for the human handoff. Allowed: `pending_parent_forward` \| `forwarded` \| `acknowledged` \| `internal_retry` \| `completed` |
| `relay_dedupe_key` | Stable dedupe key for this specific handoff event. Use a new value when a newer QR replaces an older QR. |
| `boss_notified_at` | Timestamp when the parent/main agent actually forwarded the handoff outward. `null` means not yet confirmed. |
| `control_plane_sync` | `complete` = `pipeline-state.json` and matching run lock both updated; `partial` = `pipeline-state.json` updated but run lock missing/skipped/failed. `partial` is still durable enough to fail closed. |

### Blocker-transition overwrite rule (MANDATORY)

Publish-time control-plane state must track the **current blocker**, not the first blocker seen in the run.

If the live publish path moves from one blocker class to another, the durable state must be **overwritten in place** so resume / heartbeat reads the latest truth.

Common transitions:

- `login_scan` → `safe_check_scan`
- `safe_check_scan` → `boss_confirm`
- `need_user_action` → `waiting_retry` (example: originality timeout / send-rate limit / temporary platform cooldown)
- `waiting_retry` → `need_user_action` (example: cooldown passed and a fresh QR appears)
- any blocked state → `reader_side_in_review` / `reader_side_published`

Required overwrite behavior when the blocker changes:

- replace `current_step`
- replace `waiting_for`
- replace `required_user_action`
- replace `safe_check_qr_path`
- replace `qr_verified` / `qr_verification_method`
- reset `blocking_since` unless caller explicitly pins a carry-over window
- regenerate `timeout_at` unless caller explicitly pins the old window
- replace `relay_status`
- replace `relay_dedupe_key`
- replace `note`
- replace `blocking.*`
- refresh `resume_context`
- refresh `updated_at` / `last_transition_at` / `last_progress_at`

Stale blocked fields from an older blocker must not remain authoritative after the transition.

### `pending_action` compatibility rule

Do **not** overload `pending_action` with user-facing verbs like `safe_check_scan`.

- ✅ allowed: `wait_boss_scan`, `wait_boss_confirm`
- ❌ forbidden: `safe_check_scan`, `login_scan`

`required_user_action` is the authoritative field for what the human must do. `pending_action` stays as a wait-state compatibility hint only.

## Field Reference

| Field | Values |
|-------|--------|
| `phase` | `preparing` \| `writing` \| `reviewing` \| `revising` \| `awaiting_human` \| `publishing` \| `done` \| `blocked` |
| `status` | `need_user_action` \| `waiting_retry` \| `blocked` \| other caller-defined business-safe state |
| `schema_version` | Current canonical write schema marker; reader should be wide, writer should be strict |
| `source_mode` | `fresh` \| `resume` |
| `profile` | Selected公众号名称。`write` / `draft` / `publish` 时必须存在，且应与 `profiles.json` 的 key 完全一致；不得回退到顶层默认作者/发布配置猜测账号 |
| `child_status` | `pending` \| `done` \| `failed` \| `null` |
| `pass_threshold` / `min_dimension` | `pass_threshold` is only an optional mirror/snapshot for observability. The sole authoritative threshold lives in `<article-workspace>/config.json` → `review_pass_threshold`. `min_dimension` remains optional unless caller policy explicitly enforces it. |
| `lineage_status` | `clean` \| `dirty` \| `repairing` |
| `last_clean_step` | Last trustworthy step name with both artifact + child evidence |
| `repair_attempts` | Non-negative integer; increment on each dirty-lineage recovery attempt |
| `lite_preflight.binding_status` | `matched` \| `rerun_completed` \| `waived` \| `mismatch_requires_action` |
`rerun_completed` only means the latest draft has been durably rebound to a refreshed `writer-lite-check.json`. If that refreshed preflight still hard-fails, keep the enum unchanged and inspect `lite_preflight.resolution.preflight_*` plus the helper exit code.
| `lite_preflight.binding_artifact` | Durable artifact path, typically `<draft-dir>/writer-lite-binding.json` |
| `lite_preflight.last_draft_*` | Current latest-draft identity used for binding (`file` / `version` / `sha256`) |
| `lite_preflight.previous_check_*` | The stale/previous canonical check identity seen before rerun or waiver handling |
| `lite_preflight.latest_check_*` | Canonical `writer-lite-check.json` identity currently bound (or stale) |
| `lite_preflight.waiver` | Explicit waiver payload when rerun is intentionally skipped |
| `children` | Per-step child-session evidence: `session_key`, `label`, `model`, `status`, `artifacts`. Active canonical steps are `researcher`, `writer`, `reviewer`, `layout`; `style_lint` is an inline gate and must **not** be written as a child step. `humanizer` is legacy read-only and must not be written by new runs. |
| `artifact_provenance` | Per-artifact producer record; publish audit requires `producer_type=child`, correct active `producer_step`, `session_key`, and `model` |
| `reviewed_draft_file` / `reviewed_draft_sha256` | Reviewer-approved draft identity, recorded at Reviewer pass time. This draft is the final body authority after Reviewer pass, and audit must verify these fields instead of minting them from current disk bytes. |
| `content_finalized_by` / `content_final_artifact` | Must be `reviewer` and the same reviewed draft file for active runs. |
| `layout_input_file` / `layout_input_sha256` | Exact reviewed draft consumed by Layout. Publish audit fails closed if these are missing or do not match. |
| `layout_output_file` | Layout artifact, normally `final-layout.md`. |
| `style_lint` | Pre-review authorial lint state. Must record the current lint artifact, the exact draft identity it evaluated, the current `status` (`pass` / `blocked` / `waived`), and `bounce_count` (max 1 before first review). |
| `waiting_for` | Human-side wait target, e.g. `boss_scan`, `boss_confirm` |
| `required_user_action` | Human action verb, e.g. `safe_check_scan`, `login_scan`, `boss_confirm` |
| `safe_check_qr_path` | Stable local QR/evidence path for the current blocked event; may be `null` for non-QR confirmations |
| `qr_verified` / `qr_verification_method` | Whether the currently persisted QR artifact was explicitly verified before outward relay, and by which method (`manual`, `vision`, etc.) |
| `relay_status` | Parent handoff status: `pending_parent_forward` \| `forwarded` \| `acknowledged` \| `internal_retry` \| `completed` |
| `relay_dedupe_key` | Stable dedupe key for the current blocked event |
| `boss_notified_at` | Parent-forward confirmation timestamp; `null` until confirmed |
| `qr_updated_at` | Timestamp for the currently persisted QR/evidence artifact |
| `blocking_since` | First timestamp when the current human-blocked state became active |
| `timeout_at` | Escalation threshold for a waiting human handoff; when crossed, state must upgrade instead of hanging silently |
| `resume_context` | Durable context for continuing formal publish after the human action |
| `control_plane_sync` | `complete` \| `partial` |
| `blocking` | Optional nested mirror of the blocked-state fields for grouped readers |
| `handoff` | Optional nested mirror of relay/handoff state for grouped readers |

## Resume Protocol (MANDATORY at start of every turn)

1. First determine whether the current task is `fresh` or `resume`.
   - If the user explicitly provided `draft_id` or clearly asked to continue a named draft → `resume`.
   - Otherwise, for scheduled daily/topic-generation work, default to `fresh`.
2. Only in `resume` mode, check whether an existing `pipeline-state.json` should be continued.
3. In `fresh` mode, create a brand-new slug/run record immediately and do **not** attach the task to an older failed/incomplete draft.
4. If the preferred slug directory already exists, generate a new unique slug and fresh directory; never reuse the existing one in `fresh` mode.
5. Write initial `pipeline-state.json` for the fresh slug before research or child spawning.
6. Fresh runs must **not** inherit old blocked-state fields from a previous run. New slug + new `run_id` means a clean control plane.
7. If `child_label` is set and `child_status` is `pending`:
   - Check via `Hermes delegation/session status` or completion event.
   - Done → read result, save output verbatim, advance step.
   - Running → report and wait (up to 1 hour for child-session completion unless there is an explicit unrecoverable error). Do NOT re-spawn. Do NOT kill purely because early `sessions_history` is sparse or empty.
   - Failed → set `error`, set `phase: "blocked"`, notify user.
8. If `phase` is `awaiting_human` or `blocked`, inspect `waiting_for`, `required_user_action`, `safe_check_qr_path`, `relay_status`, and `control_plane_sync` before doing anything else.
9. If no child agent pending → execute `pending_action`.
10. Resolve the target公众号 profile before research/publish. Persist `profile` + the effective `published_log_path` into state so resume runs keep using the same account context.
10.5. **Before Reviewer consumes a newer draft (and again before downstream use of a changed latest draft):** ensure latest-draft vs latest-lite-check binding is durable.
   - Command: `python3 ${HERMES_SKILL_DIR}/scripts/ensure_latest_lite_binding.py --state-path <draft-dir>/pipeline-state.json --mode rerun|waiver [--waiver-reason "..."]`
   - If `last_draft_file` and canonical `writer-lite-check.json` mismatch on `draft_version` / `draft_sha256`, the caller must either rerun lite preflight or persist an explicit waiver. Silent stale-check carry-over is forbidden.
   - The helper must write both `writer-lite-binding.json` and `pipeline-state.json.lite_preflight` so resume logic can see the binding decision.
11. **Before draft-box publish**: run explicit profile preflight; do not guess/fallback.
   - Command: `python3 ${HERMES_SKILL_DIR}/scripts/publish_profile_preflight.py --profile <profile> --state-path <draft-dir>/pipeline-state.json --publish-md <draft-dir>/publish.md`
   - This must validate `publisher.mcp_config_file`, confirm the config explicitly contains `wenyan-mcp`, and ensure `publish.md` frontmatter carries the same explicit `profile` / `author` contract.
12. **Before spawning**: write state with label + `pending` FIRST, plus `run_id` / `source_mode`.
13. **After completion**: save output verbatim, update state, then proceed.
14. **After every child-step completion**: immediately write canonical lineage at the top level.
   - Required command: `python3 ${HERMES_SKILL_DIR}/scripts/update_pipeline_lineage.py --state-path <draft-dir>/pipeline-state.json --step <researcher|writer|reviewer|layout> --session-key <child-session-key> --model <model> --label <label> --artifacts <artifact1> [<artifact2> ...]`
   - On Reviewer pass, pass the exact approved draft: `--approved-artifact <last_draft_file>` so the helper records `reviewed_draft_file`, `reviewed_draft_sha256`, and `content_finalized_by=reviewer`.
   - For Layout, pass the exact reviewed draft: `--input-artifact <reviewed_draft_file>`. The helper must fail closed if reviewer-approved bytes are missing or if the input does not match them.
   - Canonical artifact keys must use **draft-dir relative file names / basenames only** (for example `research.json`, `draft-v4.md`, `review-v3.json`, `final-layout.md`). Do not mix absolute paths, alias keys like `draft_v3_md`, `final.md`, or nested `artifact_paths` as publish authority.
   - Top-level `children` + `artifact_provenance` are the publish-control authority. Nested `lineage.*` may remain as compatibility/debug mirrors only.
15. **Before publish**: run a lineage audit and persist the audit marker before cleanup.
   - Command: `python3 ${HERMES_SKILL_DIR}/scripts/lineage_audit.py <draft-dir> --json --write-state`
   - `--write-state` is the canonical lazy-migration path: it may wide-read legacy aliases, but it must write back canonical `children` / `artifact_provenance` keys plus `schema_version` / `lineage_audited_at`.
   - If a required body artifact lacks matching child-session evidence, set `lineage_status: "dirty"`, record `last_clean_step`, increment `repair_attempts`, and switch `pending_action` to a repair/rerun branch instead of publishing.
16. **Dirty lineage never publishes directly.** Resume from the last clean checkpoint, or start a fresh run if no clean checkpoint exists.

## State Transitions

```text
research+prep (1) → write (2) → review (3)
  ↓ (`weighted_total < effective review_pass_threshold` AND cycle < max)
revise-auto (4) → review (3) [loop, max 2 automated]
  ↓ (`weighted_total < effective review_pass_threshold` AND cycle >= 2)
restart_from_fresh_first_draft_branch → write (2)
  ↓ (`weighted_total >= effective review_pass_threshold`)
content_finalized_by=reviewer; reviewed_draft_file=last_draft_file
  ↓
layout (5) → publish_to_draft (6a) → formal_publish (6b)
  ↓ (safe_check / login_scan / boss_confirm)
awaiting_human / blocked (step 6 persists durable handoff state)
  ↓ (human action confirmed or latest QR refreshed)
formal_publish resumes → reader_side_in_review / reader_side_published / failed
```

## Cleanup Rules for Blocked State

Blocked-state fields must be cleared or overwritten when any of these happens:

1. **Boss already scanned / confirmed and the flow continues**
   - clear or overwrite `waiting_for`, `required_user_action`, `safe_check_qr_path`, `relay_status`, `relay_dedupe_key`, `boss_notified_at`, `qr_updated_at`, `blocking_since`, `blocking`, `handoff`
   - recommended helper: `python3 ${HERMES_SKILL_DIR}/scripts/clear_publish_blocked_state.py --state-path <draft-dir>/pipeline-state.json --status in_review --phase published --current-step reader_side_in_review [--run-lock-path ...]`
2. **Reader-side publish reaches `in-review`, `published`, or `done`**
   - blocked-state fields must not remain authoritative after terminal or post-submit states
   - recommended helper: `clear_publish_blocked_state.py` with `--status in_review|published --phase published|done`
3. **Explicit failure / cancel**
   - clear or overwrite the old blocked state so resume logic does not mistake it for an active wait
   - recommended helper: `clear_publish_blocked_state.py` with `--status failed|cancelled --phase done --current-step publish_failed|publish_cancelled`
4. **Fresh run starts**
   - never reuse the prior run's blocked state; create a new slug and fresh state record
5. **`timeout_at` is crossed while still waiting**
   - escalate state to `blocked` (or keep `need_user_action` with a refreshed timeout if the caller explicitly re-issues the wait)
   - do not leave the run hanging in an unqualified waiting state forever

Do **not** delete a still-needed QR file early. Old QR artifacts may be removed only after a newer QR has been durably written, or after the blocked event is definitively over.

## File Naming

- Drafts: `draft.md` (initial), `draft-v2.md`, `draft-v3.md`, `draft-v4.md`, ...
- Reviews: `review-v1.json`, `review-v2.json`, ...
- `last_draft_file` and `last_review_file` always point to current version.
- `reviewed_draft_file` points to the Reviewer-approved body authority after pass.
- `final-layout.md` is the render-adapted layout artifact, not a content rewrite.
- New active runs do not generate `final.md`; legacy `final.md` is ignored by publish lineage.
