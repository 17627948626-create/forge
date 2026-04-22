# Quality Checks Reference

This file describes the **active** quality gates for `forge write` / `forge draft` under the OpenClaw deployment model:

- one shared GPT-5.4 model family
- no tuning / temperature / decoding parameter strategy layer
- no downstream humanizer after Reviewer pass
- repo-level helpers for mechanical checks and style red lights

The core rule is simple: **keep each gate narrow and auditable**.

## Active Gates

### 1. Research artifact gates

Run before Writer:

- `outline_gate.py` checks that `outline.md` is prose-safe and free of backstage instructions
- `validate_research_artifact.py` checks that risky claims in `research.json` have the minimum structured fact sidecar needed for attribution and preflight

These gates are about **grounding and contract shape**, not voice.

### 2. Writer lite preflight

Run on the Writer draft before review:

- `writer_lite_preflight.py`

This remains a **mechanical red-light checker only**. It may block:

- placeholder residue
- unsupported fake quotes
- missing attribution for high-risk source claims
- dynamic numbers without timestamps when evidence requires one
- README claim overreach
- bytes/size unit misuse

It must **not** become a style scorer or human-likeness judge.

### 3. Style fingerprint lint

Run after Writer and before Reviewer:

- `style_fingerprint_lint.py <draft> --output <draft-dir>/style-lint.json`

This lint is the pre-review style gate. It only checks authorial red lights such as:

- `opening_interchangeability`
- `transition_template_dependence`
- `ending_sloganism`
- repeated scaffold phrases
- rhythm that is too uniform to feel authored

If it blocks:

- the orchestrator may trigger **one** `style-only` bounce back to Writer
- the bounce still belongs to the existing `writer` step
- no new canonical child step may be introduced

This lint does **not** score facts, citations, or review threshold pass/fail.

### 4. Reviewer final gate

Reviewer is the **only** scoring authority for draft acceptance.

Reviewer must:

- score against the current rubric in `references/reviewer-rubric.md`
- use the threshold from the active workspace `config.json`
- explicitly judge `opening_interchangeability`, `author_presence`, `transition_template_dependence`, and `ending_sloganism`

If the draft still needs voice cleanup, Reviewer must return `revise`. There is no post-review prose fixer.

### 5. Layout and lineage gate

Layout may adapt the reviewed draft for WeChat rendering, but it may not rewrite facts, thesis, argument strength, or author voice.

Lineage checks must prove:

- Reviewer-approved bytes are frozen before Layout
- Layout consumed the exact approved draft
- publish-time artifacts trace back to canonical child outputs

## Explicitly Out Of Scope

The following are **not** active quality mechanisms anymore:

- post-review automatic tone rewrites
- a separate `humanizer` or `styler` child step
- a synthetic `voice match` percentage score
- automatic hook insertion after review
- model-parameter tuning as a style strategy

Those approaches either blur authority boundaries or depend on knobs OpenClaw does not expose.

## Manual Commands

```bash
# Mechanical draft red lights
python scripts/writer_lite_preflight.py /path/to/draft.md --output /path/to/writer-lite-check.json

# Authorial style red lights
python scripts/style_fingerprint_lint.py /path/to/draft.md --output /path/to/style-lint.json

# Research contract validation
python scripts/validate_research_artifact.py /path/to/research.json --output /path/to/research-gate.json

# Outline contract validation
python scripts/outline_gate.py /path/to/outline.md --output /path/to/outline-gate.json
```

## Design Principle

Optimize for:

- blind naturalness
- author similarity
- concrete paragraph density
- reader sense that a specific author is present on the page

Do **not** optimize for:

- generic AI detector evasion
- keyword blacklist gaming
- fake persona roleplay that lives only in the prompt
