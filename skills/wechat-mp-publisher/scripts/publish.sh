#!/usr/bin/env bash
# 本地入口，转调远程发布脚本
# Usage: ./publish.sh <markdown-file> [theme]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec "$SCRIPT_DIR/publish-remote.sh" "$@"
