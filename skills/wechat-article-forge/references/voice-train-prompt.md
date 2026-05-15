# Voice Train Prompt Contract

Use this contract for `forge voice train`.

The goal is not to invent a persona. The goal is to **compile** existing workspace persona and historical writing into assets the Writer and Reviewer can use directly inside Hermes.

## Inputs

Allowed source inputs:

- published article markdown
- approved historical drafts
- workspace persona materials such as `SOUL.md`, `AGENTS.md`, `MEMORY.md`
- profile notes or account-specific operating guidance

## Outputs

`forge voice train` must generate:

- `voice-pack.json`
- `voice-profile.json`

`voice-pack.json` is the primary asset.
`voice-profile.json` is the fallback summary / diagnostic asset.

## Extraction Rules

1. Extract **short functional fragments**, not whole articles.
2. Bucket the fragments by what they do:
   - openings
   - turns
   - endings
   - sharp lines
   - explanation moves
3. Extract anti-patterns:
   - generic openings
   - template transitions
   - slogan endings
4. Infer only portable persona boundaries:
   - `persona_mode`
   - `reader_relationship`
   - `opinion_strength`
   - `humor_level`
   - `boundary_notes`
5. Preserve concrete phrases only when they are truly reusable and characteristic.
6. Do not copy raw `SOUL.md` language into `prompt_injection`.
7. Do not encode fake biography or one-off campaign context into the shared asset.

## Output Quality Bar

Good `voice-pack.json` output should let Writer answer:

- how does this author usually open?
- how does this author turn an argument?
- how does this author end without sounding like a slogan?
- what phrases or moves feel signature?
- what kinds of wording instantly sound fake or templated for this author?

Good `voice-profile.json` output should summarize:

- pacing and structure
- rhetoric and vocabulary tendencies
- fallback persona/tone hints

## Hermes Boundary

The repo contract stops at compiled assets.

That means:

- workspace persona files remain private workspace state
- the shared repo should consume `voice-pack.json` / `voice-profile.json`
- profile-specific asset paths should be wired through `profiles.json`

## Writer / Reviewer Reminder

`voice-pack.json` is evidence for authored moves, not permission to imitate entire old articles.
