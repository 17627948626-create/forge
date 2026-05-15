#!/usr/bin/env python3
"""Authorial style lint for writer drafts.

This script sits between writer and reviewer. It checks only style-shaped red
lights that are mechanically enumerable enough to be useful as a pre-review
gate. It does not judge factuality or final publish quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


OPENING_BAD_PATTERNS = [
    re.compile(r"随着.{0,8}发展"),
    re.compile(r"今天我们来聊"),
    re.compile(r"近年来"),
    re.compile(r"行业正在发生"),
]

TEMPLATE_MARKERS = [
    "值得注意的是",
    "值得一提的是",
    "具体来说",
    "具体而言",
    "换言之",
    "也就是说",
    "总之",
    "总而言之",
    "综上所述",
    "我们不难发现",
    "由此可见",
    "未来已来",
]

ENDING_BAD_PATTERNS = [
    re.compile(r"值得我们持续关注"),
    re.compile(r"拥抱变化"),
    re.compile(r"未来已来"),
    re.compile(r"持续关注"),
]

SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;]\s*")


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_paragraphs(text: str) -> List[str]:
    blocks = []
    current = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        if line.startswith("#"):
            continue
        current.append(line)
    if current:
        blocks.append(" ".join(current))
    return blocks


def split_sentences(text: str) -> List[str]:
    return [x.strip() for x in SENTENCE_SPLIT_RE.split(text) if len(x.strip()) >= 4]


def add_issue(issues: List[Dict[str, object]], code: str, summary: str, evidence: Dict[str, object]) -> None:
    issues.append(
        {
            "code": code,
            "severity": "hard_block",
            "summary": summary,
            "evidence": evidence,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint writer drafts for template dependence and weak author presence.")
    parser.add_argument("draft_path")
    parser.add_argument("--output")
    parser.add_argument("--check-mode", choices=["blocking", "advisory"], default="blocking")
    parser.add_argument("--voice-asset-source", default="unresolved")
    args = parser.parse_args()

    draft_path = Path(args.draft_path).expanduser().resolve()
    text = draft_path.read_text(encoding="utf-8")
    paragraphs = split_paragraphs(text)
    sentences = split_sentences("\n".join(paragraphs))
    issues: List[Dict[str, object]] = []

    opening = " ".join(paragraphs[:2])[:300]
    ending = paragraphs[-1] if paragraphs else ""

    if any(pattern.search(opening) for pattern in OPENING_BAD_PATTERNS):
        add_issue(
            issues,
            "opening_interchangeability",
            "开头过于泛化，像类目模板而不是这篇文章自己的入口。",
            {"opening_excerpt": opening},
        )

    marker_hits = []
    for marker in TEMPLATE_MARKERS:
        count = text.count(marker)
        if count:
            marker_hits.append((marker, count))
    total_marker_count = sum(count for _, count in marker_hits)
    per_1000 = round(total_marker_count * 1000 / max(len(text), 1), 2)
    if per_1000 >= 6 or len(marker_hits) >= 3:
        add_issue(
            issues,
            "transition_template_dependence",
            "正文主要靠模板连接词推进，而不是靠因果、冲突、场景或代价推进。",
            {"marker_hits": marker_hits, "per_1000_chars": per_1000},
        )

    if any(pattern.search(ending) for pattern in ENDING_BAD_PATTERNS):
        add_issue(
            issues,
            "ending_sloganism",
            "结尾落成了口号或横幅句，没有落到具体代价、选择或下一步。",
            {"ending_excerpt": ending},
        )

    normalized_paragraphs = [re.sub(r"\s+", "", paragraph) for paragraph in paragraphs if paragraph]
    repeated = {}
    for paragraph in normalized_paragraphs:
        repeated[paragraph] = repeated.get(paragraph, 0) + 1
    repeated = {paragraph[:60]: count for paragraph, count in repeated.items() if count >= 2}
    if repeated:
        add_issue(
            issues,
            "repeated_scaffold_phrase",
            "同一骨架或整段表达重复出现，像在重复回放模板段落。",
            {"repeated": repeated},
        )

    sentence_lengths = [len(sentence) for sentence in sentences]
    cv = 0.0
    if sentence_lengths:
        avg = sum(sentence_lengths) / len(sentence_lengths)
        if avg:
            variance = sum((length - avg) ** 2 for length in sentence_lengths) / len(sentence_lengths)
            cv = round((variance ** 0.5) / avg, 3)
    if len(sentence_lengths) >= 4 and cv < 0.18:
        add_issue(
            issues,
            "rhythm_too_uniform",
            "句长波动过小，节奏过匀，读感像模板加工件。",
            {"sentence_length_cv": cv, "sentence_lengths": sentence_lengths},
        )

    blocking = bool(issues)
    blocking_enforced = blocking and args.check_mode == "blocking"
    now = iso_now()
    result = {
        "ok": not blocking_enforced,
        "blocking": blocking,
        "blocking_enforced": blocking_enforced,
        "generated_at": now,
        "updated_at": now,
        "artifact_contract": "script_generated_only",
        "style_scope": "authorial_presence_and_template_dependence_only",
        "max_pre_review_bounces": 1,
        "voice_asset_source": args.voice_asset_source,
        "input_fingerprints": {
            "draft_path": str(draft_path),
            "draft_sha256": sha256_file(draft_path),
        },
        "metrics": {
            "template_marker_per_1000_chars": per_1000,
            "sentence_length_cv": cv,
        },
        "issues": issues,
        "generator": {
            "name": "style_fingerprint_lint.py",
            "version": "1.0",
        },
    }

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 1 if blocking_enforced else 0


if __name__ == "__main__":
    raise SystemExit(main())
