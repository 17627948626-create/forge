#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    '“': '”',
    '‘': '’',
    '《': '》',
    '「': '」',
    '『': '』',
}

TRAILING_BOLD_PUNCT = "。！？；：，、,.!?:;%％）)]】》」』”’"


def normalize_title(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").strip()
    while len(s) >= 2 and QUOTE_PAIRS.get(s[0]) == s[-1]:
        s = s[1:-1].strip()
    return s


def extract_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    meta: dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return meta, 0
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return meta, i + 1
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        i += 1
    return meta, 0


def find_first_heading(lines: list[str], start: int) -> tuple[int | None, str]:
    """Find first H1 (# ) or H2 (## ) in body that duplicates the frontmatter title."""
    for idx in range(start, len(lines)):
        line = lines[idx]
        stripped = line.lstrip()
        if stripped.startswith("## "):
            return idx, stripped[3:].strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return idx, stripped[2:].strip()
    return None, ""


def find_first_h1(lines: list[str], start: int) -> tuple[int | None, str]:
    """Legacy: find first H1 only (kept for compatibility)."""
    for idx in range(start, len(lines)):
        line = lines[idx]
        stripped = line.lstrip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return idx, stripped[2:].strip()
    return None, ""


def sanitize_dangerous_inline_bold(text: str) -> tuple[str, int]:
    """
    Wenyan/Marked can leak raw `**` when inline bold ends with punctuation/symbols
    and the sentence immediately continues, e.g. `**一句话。**后文`.
    Move the trailing punctuation outside the bold span to keep rendering stable.
    Keep `%/％` inside the bold when it is followed by sentence punctuation.
    """
    pattern = re.compile(
        rf"\*\*([^\n*]*?)([{re.escape(TRAILING_BOLD_PUNCT)}]+)\*\*(?=[^\s\n{re.escape(TRAILING_BOLD_PUNCT)}])"
    )

    def repl(match: re.Match[str]) -> str:
        body = match.group(1)
        suffix = match.group(2)
        keep_inside = ""
        move_outside = suffix
        if len(suffix) > 1 and suffix[0] in "%％":
            keep_inside = suffix[0]
            move_outside = suffix[1:]
        return f"**{body}{keep_inside}**{move_outside}"

    return pattern.subn(repl, text)


def normalize_publish_md(path: Path) -> tuple[bool, str]:
    original_text = path.read_text(encoding="utf-8")
    text = original_text
    lines = text.splitlines()
    meta, body_start = extract_frontmatter(lines)
    statuses: list[str] = []

    title = normalize_title(meta.get("title", ""))
    if title:
        h1_idx, h1_text = find_first_heading(lines, body_start)
        if h1_idx is None:
            statuses.append("skip:no_heading")
        elif normalize_title(h1_text) != title:
            statuses.append("skip:heading_differs")
        else:
            new_lines: list[str] = []
            for idx, line in enumerate(lines):
                if idx == h1_idx:
                    continue
                if idx == h1_idx + 1 and line.strip() == "":
                    continue
                new_lines.append(line)
            text = "\n".join(new_lines).lstrip("\n")
            statuses.append("deduped:removed_duplicate_heading")
    else:
        statuses.append("skip:no_frontmatter_title")

    normalized_text, bold_fix_count = sanitize_dangerous_inline_bold(text)
    if bold_fix_count:
        text = normalized_text
        statuses.append(f"sanitized:inline_bold_trailing_punct:{bold_fix_count}")
    else:
        statuses.append("skip:no_dangerous_inline_bold")

    if original_text.endswith("\n") and not text.endswith("\n"):
        text += "\n"

    if text != original_text:
        path.write_text(text, encoding="utf-8")
        return True, ";".join(statuses)

    return False, ";".join(statuses)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Normalize publish.md by removing duplicate headings and sanitizing dangerous inline bold."
    )
    ap.add_argument("file", help="Path to publish.md")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"error:file_not_found:{path}", file=sys.stderr)
        return 2

    changed, status = normalize_publish_md(path)
    print(status)
    return 0 if changed or status.startswith("skip:") else 1


if __name__ == "__main__":
    raise SystemExit(main())
