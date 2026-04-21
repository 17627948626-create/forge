#!/usr/bin/env python3
"""Mechanical validation for research.json high-risk fact sidecars.

Rule:
- when research artifact contains high-risk claim categories,
  structured fact_records (or equivalent schema) must exist.
- this does not ban inference; it blocks unlabelled strong statements.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


API_DYNAMIC_RE = re.compile(
    r"(stars?|forks?|stargazers_count|forks_count|api snapshot|快照|snapshot|created_at|pushed_at|下载量|用户数|调用量|请求量)",
    re.IGNORECASE,
)
README_RE = re.compile(r"(README|readme_claim|项目说明|仓库介绍|自称|官方文档)", re.IGNORECASE)
QUOTE_RE = re.compile(r"[“\"].{6,}[”\"]")
QUOTE_CUE_RE = re.compile(r"(原话|原文|写道|表示|称|一字不改|quote|verbatim)", re.IGNORECASE)
FILE_SIZE_RE = re.compile(r"\b(\d{3,})\s*(bytes?|字节)\b", re.IGNORECASE)
RAW_README_URL_RE = re.compile(r"raw\.githubusercontent\.com/.+/README\.md|/README\.md", re.IGNORECASE)
API_URL_RE = re.compile(r"api\.github\.com", re.IGNORECASE)


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from walk_strings(v)


def get_fact_records(research: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate_keys = [
        "fact_records",
        "high_risk_fact_records",
        "high_risk_facts",
        "structured_facts",
        "evidence_contract",
    ]
    for key in candidate_keys:
        value = research.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = value.get("fact_records")
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, dict)]
    return []


def detect_categories(strings: Iterable[str]) -> Dict[str, Any]:
    categories: Set[str] = set()
    byte_values: Set[int] = set()
    for s in strings:
        if API_DYNAMIC_RE.search(s) or API_URL_RE.search(s):
            categories.add("api_snapshot")
        if README_RE.search(s) or RAW_README_URL_RE.search(s):
            categories.add("readme_claim")
        if QUOTE_RE.search(s) or QUOTE_CUE_RE.search(s):
            categories.add("quote_mode")
        for m in FILE_SIZE_RE.finditer(s):
            categories.add("file_size_bytes")
            try:
                byte_values.add(int(m.group(1)))
            except Exception:
                pass
    return {"categories": categories, "byte_values": byte_values}


def has_api_snapshot_record(records: List[Dict[str, Any]]) -> bool:
    for record in records:
        if str(record.get("kind") or record.get("type") or "").lower() == "api_snapshot" and record.get("observed_at"):
            return True
    return False


def has_readme_claim_record(records: List[Dict[str, Any]]) -> bool:
    for record in records:
        if str(record.get("kind") or record.get("type") or "").lower() == "readme_claim":
            if "attribution_required" in record:
                return True
    return False


def has_quote_mode_record(records: List[Dict[str, Any]]) -> bool:
    for record in records:
        if str(record.get("quote_mode") or record.get("quotation") or "").lower() in {"verbatim", "paraphrase_only"}:
            return True
    return False


def missing_file_size_values(records: List[Dict[str, Any]], byte_values: Set[int]) -> List[int]:
    covered = set()
    for record in records:
        if record.get("file_size_bytes") is None:
            continue
        try:
            covered.add(int(record.get("file_size_bytes")))
        except Exception:
            continue
    return sorted(v for v in byte_values if v not in covered)


def add_issue(issues: List[Dict[str, Any]], code: str, summary: str, evidence: Dict[str, Any]) -> None:
    issues.append(
        {
            "code": code,
            "severity": "hard_block",
            "summary": summary,
            "evidence": evidence,
        }
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate research.json high-risk fact sidecars")
    ap.add_argument("research_path")
    ap.add_argument("--output")
    args = ap.parse_args()

    research_path = Path(args.research_path).expanduser().resolve()
    if not research_path.exists():
        print(json.dumps({"ok": False, "error": f"research not found: {research_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        research = load_json(research_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    strings = list(walk_strings(research))
    detected = detect_categories(strings)
    categories: Set[str] = detected["categories"]
    byte_values: Set[int] = detected["byte_values"]
    records = get_fact_records(research)
    issues: List[Dict[str, Any]] = []

    if categories and not records:
        add_issue(
            issues,
            "fact_records_missing",
            "research.json contains high-risk claim categories but has no structured fact_records sidecar.",
            {"categories": sorted(categories)},
        )
    else:
        if "api_snapshot" in categories and not has_api_snapshot_record(records):
            add_issue(
                issues,
                "api_snapshot_fact_record_missing",
                "Dynamic/API snapshot claim present but no api_snapshot fact_record with observed_at.",
                {},
            )
        if "readme_claim" in categories and not has_readme_claim_record(records):
            add_issue(
                issues,
                "readme_claim_fact_record_missing",
                "README/self-description claim present but no readme_claim fact_record with attribution boundary.",
                {},
            )
        if "quote_mode" in categories and not has_quote_mode_record(records):
            add_issue(
                issues,
                "quote_mode_fact_record_missing",
                "Quoted/verbatim-paraphrase-sensitive claim present but no quote_mode fact_record.",
                {},
            )
        if "file_size_bytes" in categories:
            missing_values = missing_file_size_values(records, byte_values)
            if missing_values:
                add_issue(
                    issues,
                    "file_size_fact_record_missing",
                    "Byte-size claim present but not all file_size_bytes values are covered by fact_records.",
                    {"missing_values": missing_values},
                )

    result = {
        "ok": len(issues) == 0,
        "hard_fail": len(issues) > 0,
        "updated_at": iso_now(),
        "scope": "research_artifact_high_risk_fact_records",
        "detected_categories": sorted(categories),
        "issues": issues,
        "fact_record_count": len(records),
    }

    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(output_text + "\n", encoding="utf-8")
    print(output_text)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
