## v2.5.0 — 2026-04-22

### Added
- `scripts/build_voice_pack.py` to compile `voice-pack.json` plus fallback `voice-profile.json`
- `scripts/resolve_voice_assets.py` to apply OpenClaw-aware voice asset fallback order
- `scripts/style_fingerprint_lint.py` plus `style-lint.json` artifact contract
- `references/voice-train-prompt.md` for the new voice asset training contract

### Changed
- Skill and reference docs now treat this repo as an OpenClaw skill base, with persona kept in workspace materials and compiled into voice assets
- Writer flow now documents the pre-review style lint and one-bounce style-only correction path
- `data-layout`, `pipeline-state`, `templates`, and `quality-checks` now reflect `voice-pack`-first routing and Reviewer finality
- `default-voice-profile.json` and `voice-profile-schema.json` are now explicitly fallback/diagnostic assets

## v2.4.1 — 2026-03-01

### Fixed
- skill.yml: add permissions block (exec/filesystem/network/credentials) to resolve OpenClaw security scan "Suspicious" flag
- Version bump for re-scan

## v2.4.0 — 2026-03-01

### Added
- Vendored baoyu-markdown-to-html renderer into `scripts/renderer/` — no longer requires separate clone
- `setup.sh`: installs bun runtime + renderer deps + systemd service in one step

### Changed
- `format.sh`: switched from wenyan-cli to bundled baoyu renderer (default theme: classic WeChat H2 headers)
- Theme selection: `bash format.sh <dir> <file> [default|grace|simple]`
- SKILL.md frontmatter: stripped to name+description only (skill-creator spec compliance)
- SKILL.md: Step 6/7 updated for new renderer and port 8898
- `REFERENCES/` renamed to `references/` (all lowercase)

### Removed
- Dependency on wenyan-cli
- Dependency on /tmp/baoyu-skills clone
