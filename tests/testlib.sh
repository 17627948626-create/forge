#!/usr/bin/env bash
# Shared test helpers. Tests can run from any checkout path and with PYTHON=/path/to/python.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

make_test_root() {
  local name="${1:-test}"
  local requested="${TEST_TMPDIR:-}"
  local fallback="$REPO_ROOT/tests/.tmp"
  local base="${TMPDIR:-$fallback}"

  if [[ -n "$requested" ]]; then
    if mkdir -p "$requested" 2>/dev/null && [[ -w "$requested" ]]; then
      base="$requested"
    fi
  fi

  if [[ ! -d "$base" ]] || [[ ! -w "$base" ]]; then
    base="$fallback"
  fi

  mkdir -p "$base"

  mktemp -d "$base/wechat-article-forge.${name}.XXXXXX"
}

write_minimal_png() {
  local path="$1"
  printf '\211PNG\r\n\032\n' > "$path"
}
