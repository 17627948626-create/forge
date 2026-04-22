#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/testlib.sh"
SCRIPT="$REPO_ROOT/scripts/resolve_voice_assets.py"
TEST_ROOT="$(make_test_root resolve_voice_assets)"
trap 'rm -rf "$TEST_ROOT"' EXIT

mkdir -p "$TEST_ROOT/profile-assets" "$TEST_ROOT/workspace-assets"

cat > "$TEST_ROOT/config.json" <<JSON
{
  "profiles_path": "$TEST_ROOT/profiles.json"
}
JSON

cat > "$TEST_ROOT/profiles.json" <<JSON
{
  "profiles": {
    "小龙虾有话说": {
      "label": "小龙虾有话说",
      "voice_pack_path": "$TEST_ROOT/profile-assets/voice-pack.json",
      "voice_profile_path": "$TEST_ROOT/profile-assets/voice-profile.json"
    }
  }
}
JSON

cat > "$TEST_ROOT/profile-assets/voice-pack.json" <<'JSON'
{"meta":{"created_at":"2026-04-22T00:00:00Z","updated_at":"2026-04-22T00:00:00Z","article_count":1,"version":"1.0"},"persona":{"persona_mode":"mixed","reader_relationship":"peer_to_peer","opinion_strength":"clear_stance"},"rhythm":{"avg_sentence_chars":20,"short_sentence_ratio":0.3,"long_sentence_ratio":0.1,"variation_score":0.7},"openings":[{"text":"开头"}],"turns":[{"text":"转折"}],"endings":[{"text":"结尾"}],"sharp_lines":[{"text":"金句"}],"anti_examples":{"openings":[],"transitions":[],"endings":[]},"signature_phrases":[],"avoid_phrases":[],"prompt_injection":"profile pack"}
JSON

cat > "$TEST_ROOT/profile-assets/voice-profile.json" <<'JSON'
{"meta":{"created_at":"2026-04-22T00:00:00Z","updated_at":"2026-04-22T00:00:00Z","article_count":1,"version":"1.0"},"persona":{"persona_mode":"mixed","reader_relationship":"peer_to_peer","opinion_strength":"clear_stance"},"rhythm":{"avg_sentence_chars":20,"avg_paragraph_sentences":2,"short_sentence_ratio":0.3,"long_sentence_ratio":0.1,"variation_score":0.7},"structure":{"preferred_section_count":5,"uses_subheadings":false,"opening_style":"bold_claim","closing_style":"summary","avg_word_count":1500},"rhetoric":{"dominant_devices":["contrast"],"uses_technical_deep_dives":false,"simplification_style":"step_by_step","self_reference_frequency":"occasional"},"vocabulary":{"formality_level":"semi_formal","english_loanword_style":"parenthetical","signature_phrases":[],"avoid_phrases":[],"domain_focus":["general"]},"punctuation":{"prefers_chinese_comma":false,"uses_em_dash":false,"uses_ellipsis":false,"book_title_marks":true,"emoji_usage":"none","emoji_style":[]},"tone":{"primary_tone":"conversational","secondary_tone":"neutral_informative","reader_relationship":"peer_to_peer","humor_level":"occasional_wit","opinion_strength":"clear_stance"},"writing_prompt_injection":"profile summary"}
JSON

cat > "$TEST_ROOT/workspace-assets/voice-pack.json" <<'JSON'
{"meta":{"created_at":"2026-04-22T00:00:00Z","updated_at":"2026-04-22T00:00:00Z","article_count":1,"version":"1.0"},"persona":{"persona_mode":"human_like","reader_relationship":"peer_to_peer","opinion_strength":"mild_opinion"},"rhythm":{"avg_sentence_chars":20,"short_sentence_ratio":0.3,"long_sentence_ratio":0.1,"variation_score":0.7},"openings":[{"text":"workspace pack"}],"turns":[{"text":"转折"}],"endings":[{"text":"结尾"}],"sharp_lines":[{"text":"金句"}],"anti_examples":{"openings":[],"transitions":[],"endings":[]},"signature_phrases":[],"avoid_phrases":[],"prompt_injection":"workspace pack"}
JSON

cat > "$TEST_ROOT/workspace-assets/voice-profile.json" <<'JSON'
{"meta":{"created_at":"2026-04-22T00:00:00Z","updated_at":"2026-04-22T00:00:00Z","article_count":1,"version":"1.0"},"persona":{"persona_mode":"human_like","reader_relationship":"peer_to_peer","opinion_strength":"mild_opinion"},"rhythm":{"avg_sentence_chars":20,"avg_paragraph_sentences":2,"short_sentence_ratio":0.3,"long_sentence_ratio":0.1,"variation_score":0.7},"structure":{"preferred_section_count":5,"uses_subheadings":false,"opening_style":"bold_claim","closing_style":"summary","avg_word_count":1500},"rhetoric":{"dominant_devices":["contrast"],"uses_technical_deep_dives":false,"simplification_style":"step_by_step","self_reference_frequency":"occasional"},"vocabulary":{"formality_level":"semi_formal","english_loanword_style":"parenthetical","signature_phrases":[],"avoid_phrases":[],"domain_focus":["general"]},"punctuation":{"prefers_chinese_comma":false,"uses_em_dash":false,"uses_ellipsis":false,"book_title_marks":true,"emoji_usage":"none","emoji_style":[]},"tone":{"primary_tone":"conversational","secondary_tone":"neutral_informative","reader_relationship":"peer_to_peer","humor_level":"occasional_wit","opinion_strength":"clear_stance"},"writing_prompt_injection":"workspace summary"}
JSON

"$PYTHON_BIN" "$SCRIPT" \
  --config-path "$TEST_ROOT/config.json" \
  --workspace-path "$TEST_ROOT/workspace-assets" \
  --profile "小龙虾有话说" > "$TEST_ROOT/result-profile.json"

"$PYTHON_BIN" - "$TEST_ROOT/result-profile.json" "$TEST_ROOT/profile-assets/voice-pack.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding='utf-8'))
assert result["ok"] is True
assert result["preferred_asset"] == "voice-pack"
assert result["preferred_source"] == "profile"
assert result["preferred_path"] == sys.argv[2]
print("PASS")
PY

rm -f "$TEST_ROOT/profile-assets/voice-pack.json" "$TEST_ROOT/profile-assets/voice-profile.json"

"$PYTHON_BIN" "$SCRIPT" \
  --config-path "$TEST_ROOT/config.json" \
  --workspace-path "$TEST_ROOT/workspace-assets" \
  --profile "小龙虾有话说" > "$TEST_ROOT/result-workspace.json"

"$PYTHON_BIN" - "$TEST_ROOT/result-workspace.json" "$TEST_ROOT/workspace-assets/voice-pack.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding='utf-8'))
assert result["ok"] is True
assert result["preferred_asset"] == "voice-pack"
assert result["preferred_source"] == "workspace"
assert result["preferred_path"] == sys.argv[2]
print("PASS")
PY

rm -f "$TEST_ROOT/workspace-assets/voice-pack.json" "$TEST_ROOT/workspace-assets/voice-profile.json"

"$PYTHON_BIN" "$SCRIPT" \
  --config-path "$TEST_ROOT/config.json" \
  --workspace-path "$TEST_ROOT/workspace-assets" \
  --profile "小龙虾有话说" > "$TEST_ROOT/result-default.json"

"$PYTHON_BIN" - "$TEST_ROOT/result-default.json" "$REPO_ROOT/references/default-voice-pack.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding='utf-8'))
assert result["ok"] is True
assert result["preferred_asset"] == "voice-pack"
assert result["preferred_source"] == "default"
assert result["preferred_path"] == sys.argv[2]
print("PASS")
PY

echo "test_resolve_voice_assets.sh: ALL TESTS PASSED"
