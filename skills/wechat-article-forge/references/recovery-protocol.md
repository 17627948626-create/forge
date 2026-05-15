# Recovery Protocol

Rules for handling interrupted pipelines, especially in cron/scheduled runs.

## Fresh vs Resume

- **Fresh-run default:** Scheduled/cron jobs always create a brand-new slug. Ignore prior failed/incomplete drafts except as historical reference.
- **Resume requires explicit intent:** Only resume an older draft when the user provides `draft_id` or clearly asks to continue.
- **Slug collision:** If the preferred slug already exists in fresh mode, append `-v2`, `-v3`, or a timestamp suffix. Never reuse an existing draft directory for a fresh run.
- **Fresh runs do not inherit stale blocked state:** a new `run_id` must start with a clean control plane. Do not reuse an older run's `safe_check` / login / boss-confirm wait state.

## Dropped Completion Recovery

The only exception to the fresh-run rule: recovery from an in-flight pipeline stuck because a child completion event was missed.

**All four conditions must be true:**

1. Most recent draft for the same scheduled job on the same day
2. `published=false`
3. `pending_action` is a wait state for a child
4. The expected child artifact already exists on disk

### Artifact-first recovery table

At pipeline start, inspect `pipeline-state.json` + on-disk artifacts before deciding the pipeline is stuck:

| `pending_action` | Required artifact(s) | Action |
|---|---|---|
| `wait_researcher` | `research.json` + `outline.md` | Run cover selection inline, advance to write (research output must comply with `references/researcher-prompt.md` search policy) |
| `wait_writer` | `draft.md` or `draft-v*.md` | Advance to review |
| `wait_reviewer` | `review-v*.json` | Advance to next gate |
| `wait_layout` | `final-layout.md` | Advance to publish |

Record `recovered_from_missed_completion=true` in state instead of duplicating the child step.

## Transcript Salvage (recovery only)

When `pending_action` is `wait_reviewer`, the expected child session is already `done`, but the artifact is still missing:

1. One-time recovery read of that specific child session/transcript
2. Persist the child's final result verbatim into the missing artifact
3. Update state and continue

This is a recovery exception, not normal workflow. Do not use transcript reads as a substitute for completion events during normal operation.

## Human-Blocked Publish Recovery (MANDATORY for publish phase)

When `pipeline-state.json` shows a publish-time human handoff (`phase=awaiting_human|blocked` with `required_user_action` set), treat it as a **durable control-plane state**, not as a best-effort chat hint.

### First inspection checklist

Check these fields first:

- `run_id`
- `status`
- `phase`
- `step` (should be `8`)
- `current_step`
- `waiting_for`
- `required_user_action`
- `safe_check_qr_path`
- `relay_status`
- `relay_dedupe_key`
- `boss_notified_at`
- `qr_updated_at`
- `blocking_since`
- `timeout_at`
- `resume_context`
- `control_plane_sync`

### Recovery branches

#### A. Blocked state still matches live backend (`safe_check` / login / boss confirm still present)

If the backend is still waiting for the same human action:

1. Keep the run in `awaiting_human` / `blocked`
2. If `relay_status=pending_parent_forward`, return/retain `need_user_action` so the parent can forward it
3. If `relay_status=forwarded` but there is no human acknowledgement yet, continue waiting
4. Do **not** spawn a fresh publish run just because the child→parent completion message was unreliable

#### B. Backend has already moved past the block

If the article is now `审核中`, `已发表`, `已提交`, or the safe-check dialog is gone and publish clearly progressed:

1. Clear or overwrite the old blocked-state fields
   - recommended helper: `python3 ${HERMES_SKILL_DIR}/scripts/clear_publish_blocked_state.py --state-path <draft-dir>/pipeline-state.json --status in_review|published --phase published|done --current-step reader_side_in_review|reader_side_published`
2. Set the authoritative publish status (`reader_side_in_review`, `reader_side_published`, `done`, etc.)
3. Do not keep stale `safe_check_qr_path` / `relay_status=pending_parent_forward` in the active state

#### C. QR expired or file missing, but backend is still blocked

If the backend is still at the same checkpoint but the persisted QR is stale/missing:

1. Re-capture the **latest** QR/evidence file
2. Save it to a new stable non-`/tmp` path unique to the same `run_id`
3. Overwrite the blocked state with the latest `safe_check_qr_path`, `qr_updated_at`, and a **new** `relay_dedupe_key`
4. Reset `relay_status` to `pending_parent_forward` unless the parent has already explicitly acknowledged the replacement QR

This overwrite is intentional: the newest QR must become authoritative.

#### D. Blocker changed from human handoff to platform-side retry

If the backend has already moved past the human checkpoint, but publish is still blocked by a **platform-side** condition such as:

- originality timeout
- temporary send-rate limit / cooldown
- system busy / retry later
- a deterministic pre-submit warning that now requires retry instead of another user action

then do **not** leave the run in `waiting_for=boss_scan` or another stale human-handoff state.

Required action:

1. Overwrite the durable state to match the new blocker
2. Set `phase=publishing`
3. Set `status=waiting_retry`
4. Set `waiting_for=system_retry` (or a comparably explicit machine wait target)
5. Clear `required_user_action` unless the backend still truly needs a human
6. Clear or replace `safe_check_qr_path`
7. Set `relay_status=internal_retry`
8. Refresh `note`, `resume_context`, and timeout fields for the retry window

Intent: heartbeat / resume must read **"platform cooldown, retry later"**, not **"still waiting for boss scan"**.

#### E. Explicit failure, deterministic content fix, or cancellation

If publish is cancelled, irrecoverably failed, or blocked by a deterministic content issue such as `链接不合法`:

1. Clear or overwrite the old blocked state
   - recommended helper: `python3 ${HERMES_SKILL_DIR}/scripts/clear_publish_blocked_state.py --state-path <draft-dir>/pipeline-state.json --status failed|cancelled|blocked --phase done|blocked --current-step publish_failed|publish_cancelled|waiting_content_fix --state error`
2. Mark the run `failed` / `cancelled` / `blocked_for_content_fix`
3. If this is a deterministic content fix branch, do not keep `waiting_for=boss_scan` or another stale human-handoff field in the active state
4. Do not let resume logic misread the run as still waiting for a QR scan

#### F. Timeout escalation

If `timeout_at` has passed and the run is still waiting on the same human action:

1. Escalate the durable state instead of silently hanging
2. Recommended command:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/check_publish_blocked_timeout.py \
  --state-path <draft-dir>/pipeline-state.json \
  --run-lock-path <explicit-run-lock-if-known>
```

3. After escalation, the state should read `status=blocked` / `phase=blocked` with `timeout_escalated_at` recorded
4. Preserve `waiting_for`, `required_user_action`, and `resume_context` so the parent can still recover the run instead of losing context

### Partial-success semantics

`pipeline-state.json` and the run lock are a **dual write, not a transaction**.

- `control_plane_sync=complete` → durable state + matching run lock updated
- `control_plane_sync=partial` → durable state updated, but run-lock mirror absent/skipped/failed

Recovery must trust `pipeline-state.json` first. A stale or missing run lock must not erase a durable blocked state already written to disk.


## Content Finality Recovery

After Reviewer pass, the reviewed draft is the final body authority. Recovery must not insert a post-review prose rewrite step.

- If `reviewed_draft_file` is present and its hash matches, re-spawn Layout from that file.
- If `reviewed_draft_file` or `reviewed_draft_sha256` is missing, treat the run as not yet bound to reviewer-approved bytes and re-run Reviewer before publish.
- If `layout_input_file` or `layout_input_sha256` is missing/mismatched, treat Layout as dirty and re-run Layout from `reviewed_draft_file`.
- If the reviewed draft is missing or hash-mismatched, roll back to the Writer/Reviewer checkpoint and re-run Reviewer as needed.
- Legacy `final.md` is not a trusted checkpoint for active publish recovery.

## Dirty Lineage Recovery (MANDATORY before publish)

A pipeline is **dirty** when the current body artifact cannot be traced to the intended child-session path for that step.

Examples:
- `draft.md` exists but there is no Writer child/session evidence for it
- `final-layout.md` exists but cannot be traced to Layout consuming the Reviewer-approved draft
- a downstream artifact exists, but the upstream checkpoint it depends on is already contaminated

### Rule

Dirty lineage must **never** publish directly. But it also must **not** simply stop if the task still requires an article output.

Instead, do this:

1. Find the **last clean checkpoint** with both required artifact(s) and child-session evidence.
2. Re-spawn the first missing/dirty downstream child step from that checkpoint.
3. Continue the remaining downstream steps normally.
4. If no clean checkpoint exists, start a **fresh run** and regenerate the article.

### Repair table

| Dirty / missing stage | Last clean checkpoint to trust | Repair action |
|---|---|---|
| Writer missing/dirty | `research.json` + `outline.md` from Researcher | Re-spawn Writer |
| Reviewer missing/dirty | Latest clean `draft*.md` from Writer | Re-spawn Reviewer |
| Layout missing/dirty | Reviewer-approved `reviewed_draft_file` / latest clean reviewed draft | Re-spawn Layout |
| No clean checkpoint | none | Fresh run |

### Intent

This is **fail-closed + rerun**, not fail-stop:
- block dirty publish
- preserve the requirement to still produce an article
- regenerate from the last trustworthy step instead of letting the parent improvise body text

### Audit command

Before any publish attempt, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/lineage_audit.py <draft-dir> --json --write-state
```

Interpretation:
- exit code `0` → clean lineage, publish may proceed
- exit code `2` → dirty lineage, use `repair_action` from the JSON output and rerun from the last clean checkpoint
- `--write-state` also persists `lineage_audited_at` so cleanup can fail closed if audit never ran
