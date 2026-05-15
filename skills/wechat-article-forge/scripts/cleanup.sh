#!/usr/bin/env bash
set -euo pipefail

draft_dir="${1:?Usage: cleanup.sh <draft-directory>}"

if [[ ! -d "$draft_dir" ]]; then
  echo "Error: directory not found: $draft_dir" >&2
  exit 1
fi

cd "$draft_dir"

if [[ -f "pipeline-state.json" ]]; then
  python3 - "pipeline-state.json" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if state.get('lineage_status') != 'clean' or not state.get('lineage_audited_at'):
    raise SystemExit('cleanup blocked: lineage_audit must run and persist clean status before cleanup')
PY
fi

rm -f draft*.md outline.md research.json review-v*.json fact-check-v*.json \
      final.md final-layout.md formatted.html
