#!/usr/bin/env python3
"""Mechanical gate for outline.md shape.

Purpose:
- fail before Writer if outline still contains backstage cues / placeholders
- keep this separate from writer_lite_preflight, which only checks writer output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


FORBIDDEN_PATTERNS = [
    ("placeholder_label", re.compile(r"\[(截图级段落位置|具体情绪场景位置|可转述判断位置)[^\]]*\]")),
    ("note_to_writer", re.compile(r"\b(note[- ]?to[- ]?writer|placeholder|todo|tbd)\b", re.IGNORECASE)),
    ("writer_meta", re.compile(r"(Writer 额外提醒|给 writer 留出|额外提醒)")),
    ("backstage_cue", re.compile(r"(结尾别升太大|不要写成|最后一节只做两件事)")),
]


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_issue(code: str, line_no: int, line: str) -> Dict[str, Any]:
    return {
        "code": code,
        "line": line_no,
        "excerpt": line.strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical outline gate for prose-safe outline.md")
    ap.add_argument("outline_path")
    ap.add_argument("--output")
    ap.add_argument(
        "--change-reason",
        default="pre-writer outline gate; fail if outline still carries backstage cues",
    )
    args = ap.parse_args()

    outline_path = Path(args.outline_path).expanduser().resolve()
    if not outline_path.exists():
        print(json.dumps({"ok": False, "error": f"outline not found: {outline_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    text = outline_path.read_text(encoding="utf-8")
    issues: List[Dict[str, Any]] = []

    for idx, line in enumerate(text.splitlines(), start=1):
        for code, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                issues.append(build_issue(code, idx, line))
                break

    result = {
        "ok": len(issues) == 0,
        "hard_fail": len(issues) > 0,
        "scope": "outline_shape_only",
        "change_reason": args.change_reason,
        "updated_at": iso_now(),
        "issues": issues,
        "repair_direction": "move backstage cues into writer-lite-brief or delete them; keep outline.md prose-safe only",
    }

    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(output_text + "\n", encoding="utf-8")
    print(output_text)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
