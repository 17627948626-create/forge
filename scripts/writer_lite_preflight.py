#!/usr/bin/env python3
"""Mechanical red-light preflight for xiaolongxia writer-lite.

This script intentionally does NOT score style, rhetoric, or overall quality.
It only checks a finite set of mechanically enumerable red lights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PLACEHOLDER_PATTERNS = [
    re.compile(r"\[(截图级段落位置|具体情绪场景位置|可转述判断位置)[^\]]*\]"),
    re.compile(r"\b(note[- ]?to[- ]?writer|placeholder|todo|tbd)\b", re.IGNORECASE),
    re.compile(r"(结尾别升太大|不要写成|最后一节只做两件事)"),
]

DYNAMIC_MARKERS = re.compile(
    r"(stars?|forks?|下载量|下载|活跃用户|用户数|粉丝|关注者|播放量|调用量|请求量|仓库|GitHub|API|市值|估值|浏览量)",
    re.IGNORECASE,
)
TIME_MARKERS = re.compile(r"(截至|observed_at|as of|观察于|更新于|于\s*20\d{2}-\d{2}-\d{2}|20\d{2}-\d{2}-\d{2}|\d+\s*月\s*\d+\s*日|今天|昨日|刚刚|不到\s*\d+\s*(小时|天))", re.IGNORECASE)
QUOTE_LINE = re.compile(r"[\"“「『].{6,}[\"”」』]")
QUOTE_CUE = re.compile(r"(原话|原文|写道|表示|称|说)")
README_ATTRIBUTION = re.compile(r"(README|仓库介绍|项目主页|项目说明|自称|官方文档|文档写着)")
BYTES_AS_TEXT = re.compile(r"(字数|汉字|字符|字\b)")


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Optional[Path]) -> Optional[str]:
    if not path or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json_if_exists(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def get_fact_records(research: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate_keys = [
        "fact_records",
        "high_risk_fact_records",
        "high_risk_facts",
        "structured_facts",
        "evidence_contract",
    ]
    records: List[Dict[str, Any]] = []
    for key in candidate_keys:
        value = research.get(key)
        if isinstance(value, list):
            records.extend(x for x in value if isinstance(x, dict))
        elif isinstance(value, dict):
            nested = value.get("fact_records")
            if isinstance(nested, list):
                records.extend(x for x in nested if isinstance(x, dict))
    return records


def add_issue(issues: List[Dict[str, Any]], code: str, severity: str, summary: str, evidence: Dict[str, Any]) -> None:
    issues.append(
        {
            "code": code,
            "severity": severity,
            "summary": summary,
            "evidence": evidence,
        }
    )


def extract_lines(text: str) -> List[str]:
    return text.splitlines()


def line_number(text: str, needle: str) -> Optional[int]:
    for idx, line in enumerate(extract_lines(text), start=1):
        if needle in line:
            return idx
    return None


def contains_time_marker(line: str) -> bool:
    return bool(TIME_MARKERS.search(line))


def draft_version_from_path(path: Path) -> str:
    name = path.name
    if name == "draft.md":
        return "draft-v1"
    m = re.search(r"draft-v(\d+)\.md$", name)
    if m:
        return f"draft-v{m.group(1)}"
    return name


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanical writer-lite preflight")
    ap.add_argument("draft_path")
    ap.add_argument("--brief-path")
    ap.add_argument("--research-path")
    ap.add_argument("--output")
    ap.add_argument("--draft-version")
    ap.add_argument("--change-reason", default="writer first draft completed; run lite preflight before review")
    ap.add_argument("--check-mode", choices=["blocking", "advisory"], default="blocking")
    args = ap.parse_args()

    draft_path = Path(args.draft_path).expanduser().resolve()
    if not draft_path.exists():
        print(json.dumps({"ok": False, "error": f"draft not found: {draft_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    draft_text = draft_path.read_text(encoding="utf-8")
    research_path = Path(args.research_path).expanduser().resolve() if args.research_path else None
    brief_path = Path(args.brief_path).expanduser().resolve() if args.brief_path else None
    research = read_json_if_exists(research_path) if research_path else {}
    _brief = read_json_if_exists(brief_path) if brief_path else {}
    fact_records = get_fact_records(research)

    issues: List[Dict[str, Any]] = []

    for idx, line in enumerate(extract_lines(draft_text), start=1):
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(line)
            if match:
                add_issue(
                    issues,
                    "placeholder_residue",
                    "hard_block",
                    "正文残留脚手架 / note-to-writer / placeholder。",
                    {"line": idx, "excerpt": line.strip()},
                )
                break

        if re.search(r"\d", line) and DYNAMIC_MARKERS.search(line) and not contains_time_marker(line):
            add_issue(
                issues,
                "dynamic_number_missing_timepoint",
                "hard_block",
                "动态数字出现但缺少明确时点。",
                {"line": idx, "excerpt": line.strip()},
            )

        if QUOTE_LINE.search(line) and QUOTE_CUE.search(line):
            if fact_records:
                supported = False
                for record in fact_records:
                    quote_mode = str(record.get("quote_mode") or record.get("quotation") or "").lower()
                    snippet = str(record.get("verbatim_text") or record.get("needle") or record.get("claim") or "")
                    if quote_mode == "verbatim" and snippet and snippet[:12] in line:
                        supported = True
                        break
                if not supported:
                    add_issue(
                        issues,
                        "fake_verbatim_quote",
                        "hard_block",
                        "发现疑似直引，但 research 里没有对应 verbatim 支撑。",
                        {"line": idx, "excerpt": line.strip()},
                    )
            else:
                add_issue(
                    issues,
                    "quote_without_structured_support",
                    "advisory",
                    "发现直引样式，但当前 research 缺少可核对的 structured verbatim 支撑。",
                    {"line": idx, "excerpt": line.strip()},
                )

    for record in fact_records:
        kind = str(record.get("kind") or record.get("type") or "").lower()
        quote_mode = str(record.get("quote_mode") or record.get("quotation") or "").lower()
        observed_at = record.get("observed_at")
        attribution_required = bool(record.get("attribution_required"))
        needle = str(record.get("needle") or record.get("claim") or record.get("text") or "").strip()
        file_size = record.get("file_size_bytes")

        if kind == "api_snapshot" and not observed_at:
            add_issue(
                issues,
                "api_snapshot_missing_observed_at",
                "hard_block",
                "research 中存在 api_snapshot，但缺少 observed_at。",
                {"record": record.get("id") or needle or kind},
            )

        if quote_mode == "paraphrase_only" and needle:
            for idx, line in enumerate(extract_lines(draft_text), start=1):
                if needle[:12] and needle[:12] in line and QUOTE_LINE.search(line):
                    add_issue(
                        issues,
                        "paraphrase_only_rendered_as_quote",
                        "hard_block",
                        "只允许转述的材料被写成了直引。",
                        {"line": idx, "excerpt": line.strip(), "record": record.get("id") or needle},
                    )

        if kind == "readme_claim" and attribution_required and needle:
            for idx, line in enumerate(extract_lines(draft_text), start=1):
                if needle[:12] and needle[:12] in line and not README_ATTRIBUTION.search(line):
                    add_issue(
                        issues,
                        "readme_claim_presented_as_verified_fact",
                        "hard_block",
                        "README / 自述性材料被写成已验证实证，但正文缺少 attribution。",
                        {"line": idx, "excerpt": line.strip(), "record": record.get("id") or needle},
                    )

        if file_size is not None:
            try:
                file_size_int = int(file_size)
            except Exception:
                file_size_int = None
            if file_size_int is not None:
                needles = [str(file_size_int)]
                if isinstance(record.get("unit"), str) and record.get("unit"):
                    needles.append(f"{file_size_int} {record['unit']}")
                for idx, line in enumerate(extract_lines(draft_text), start=1):
                    if any(n in line for n in needles) and BYTES_AS_TEXT.search(line):
                        add_issue(
                            issues,
                            "bytes_misread_as_human_text_units",
                            "hard_block",
                            "bytes / size 被误写成人类字数 / 字符数。",
                            {"line": idx, "excerpt": line.strip(), "record": record.get("id") or str(file_size_int)},
                        )

    blocking_codes = sorted({x["code"] for x in issues if x["severity"] == "hard_block"})
    generated_at = iso_now()
    blocking_enforced = args.check_mode == "blocking" and bool(blocking_codes)
    result = {
        "ok": not blocking_enforced,
        "draft_version": args.draft_version or draft_version_from_path(draft_path),
        "generated_at": generated_at,
        "updated_at": generated_at,
        "change_reason": args.change_reason,
        "check_mode": args.check_mode,
        "hard_fail": bool(blocking_codes),
        "hard_fail_reasons": blocking_codes,
        "checks": issues,
        "preflight_scope": "mechanical_red_lights_only",
        "artifact_contract": "script_generated_only",
        "blocking_enforced": blocking_enforced,
        "generator": {
            "script": str(Path(__file__).resolve()),
            "name": "writer_lite_preflight.py",
        },
        "input_fingerprints": {
            "draft_path": str(draft_path),
            "draft_sha256": sha256_file(draft_path),
            "brief_path": str(brief_path) if brief_path else None,
            "brief_sha256": sha256_file(brief_path),
            "research_path": str(research_path) if research_path else None,
            "research_sha256": sha256_file(research_path),
        },
        "style_suggestions": [],
        "max_pre_review_bounces": 1,
        "rerun_required_only_when": ["title", "lead_300", "thesis", "structure_spine"],
    }

    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(output_text + "\n", encoding="utf-8")
    print(output_text)
    return 2 if blocking_enforced else 0


if __name__ == "__main__":
    raise SystemExit(main())
