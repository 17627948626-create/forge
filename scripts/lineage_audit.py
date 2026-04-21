#!/usr/bin/env python3
"""Audit publish lineage for wechat-article-forge.

Active content chain after Humanizer removal:
Researcher -> Writer -> Reviewer -> Layout.

Humanizer aliases are still wide-read as legacy metadata so old states can be
loaded, but Humanizer is not an active publish step and is never required for a
clean audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "2026-04-09.lineage-v2"
STEP_ORDER = ["researcher", "writer", "reviewer", "layout"]
LEGACY_STEPS = {"humanizer"}
KNOWN_STEPS = set(STEP_ORDER) | LEGACY_STEPS | {"fact_checker"}

_ALIAS_PATTERNS = [
    (re.compile(r"^research(er)?(_v\d+)?$"), "researcher"),
    (re.compile(r"^writer($|_v\d+$|_revision(_v\d+)?$|_revise$|_rewrite$|_rework$|_factfix$)"), "writer"),
    (re.compile(r"^review(er)?($|_v\d+$|_round\d+$)"), "reviewer"),
    (re.compile(r"^fact(_?checker|check)?($|_v\d+$|_round\d+$)"), "fact_checker"),
    (re.compile(r"^humani[sz](er)?($|_v\d+$)"), "humanizer"),
    (re.compile(r"^layout($|_v\d+$)"), "layout"),
]


REPAIR_ACTIONS = {
    "researcher": "fresh_run",
    "writer": "rerun_writer",
    "reviewer": "rerun_reviewer",
    "layout": "rerun_layout",
}


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def canonicalize_step(raw_step: Any) -> Optional[str]:
    if not isinstance(raw_step, str):
        return None
    step = raw_step.strip().lower().replace("-", "_")
    if step in KNOWN_STEPS:
        return step
    for pattern, canonical in _ALIAS_PATTERNS:
        if pattern.match(step):
            return canonical
    return None


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"pipeline-state.json not found: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid JSON in {path}: {e}")


def file_sha256(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_child_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    entry = dict(raw)
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, list):
        artifact = entry.get("artifact")
        if isinstance(artifact, str) and artifact.strip():
            artifacts = [x.strip() for x in re.split(r"\+|,", artifact) if x.strip()]
        else:
            artifacts = []
    entry["artifacts"] = artifacts
    return entry


def dedupe_child_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for entry in entries:
        key = (
            entry.get("session_key"),
            entry.get("status"),
            tuple(entry.get("artifacts") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def normalize_children(raw: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for step, value in raw.items():
        canonical = canonicalize_step(step)
        if not canonical:
            continue
        bucket = out.setdefault(canonical, [])
        if isinstance(value, list):
            bucket.extend(normalize_child_entry(x) for x in value if isinstance(x, dict))
        elif isinstance(value, dict):
            bucket.append(normalize_child_entry(value))
    for step, entries in list(out.items()):
        out[step] = dedupe_child_entries(entries)
    return out


def normalize_artifact_provenance(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for artifact, value in raw.items():
        if not isinstance(value, dict):
            continue
        entry = dict(value)
        producer_step = entry.get("producer_step") or entry.get("producer")
        canonical = canonicalize_step(producer_step)
        if canonical:
            entry["producer_step"] = canonical
        out[artifact] = entry
    return out


def parse_versioned_name(path: str) -> Tuple[int, str]:
    name = os.path.basename(path)
    m = re.search(r"-v(\d+)\.", name)
    version = int(m.group(1)) if m else 1
    return version, name


def latest_matching(draft_dir: Path, patterns: List[str]) -> Optional[str]:
    matches: List[str] = []
    for pattern in patterns:
        matches.extend(glob(str(draft_dir / pattern)))
    if not matches:
        return None
    matches = sorted(set(matches), key=parse_versioned_name)
    return os.path.basename(matches[-1])


def recorded_reviewed_draft_file(state: Dict[str, Any]) -> Optional[str]:
    cand = state.get("reviewed_draft_file")
    if not cand and state.get("content_finalized_by") == "reviewer":
        cand = state.get("content_final_artifact")
    return cand if isinstance(cand, str) and cand.strip() else None


def writer_artifact_file(draft_dir: Path, state: Dict[str, Any]) -> Optional[str]:
    cand = (
        recorded_reviewed_draft_file(state)
        or state.get("last_draft_file")
        or latest_matching(draft_dir, ["draft.md", "draft-v*.md"])
    )
    return cand if isinstance(cand, str) and cand.strip() else None


def layout_input_file(state: Dict[str, Any]) -> Optional[str]:
    cand = state.get("layout_input_file")
    if not cand and isinstance(state.get("layout"), dict):
        cand = state["layout"].get("input_file")
    return cand if isinstance(cand, str) and cand.strip() else None


def layout_input_sha256(state: Dict[str, Any]) -> Optional[str]:
    cand = state.get("layout_input_sha256")
    if not cand and isinstance(state.get("layout"), dict):
        cand = state["layout"].get("input_sha256")
    return cand if isinstance(cand, str) and cand.strip() else None


def layout_skipped(state: Dict[str, Any]) -> bool:
    return bool(state.get("layout_skipped") or state.get("layout", {}).get("skipped"))


def choose_artifact(step: str, draft_dir: Path, state: Dict[str, Any]) -> List[str]:
    if step == "researcher":
        names = ["research.json", "outline.md"]
        return [n for n in names if (draft_dir / n).exists()]
    if step == "writer":
        cand = writer_artifact_file(draft_dir, state)
        return [cand] if cand and (draft_dir / cand).exists() else []
    if step == "reviewer":
        cand = state.get("last_review_file") or latest_matching(draft_dir, ["review-v*.json", "review-v*.md"])
        return [cand] if cand and (draft_dir / cand).exists() else []
    if step == "layout":
        if layout_skipped(state):
            return []
        return ["final-layout.md"] if (draft_dir / "final-layout.md").exists() else []
    return []


def child_has_evidence(entries: List[Dict[str, Any]], required_artifacts: List[str]) -> bool:
    if not entries:
        return False
    for entry in entries:
        if entry.get("status") not in ("done", "completed", "complete", None):
            continue
        if not entry.get("session_key"):
            continue
        artifacts = entry.get("artifacts") or []
        if not isinstance(artifacts, list):
            artifacts = []
        if all(a in artifacts for a in required_artifacts):
            return True
    return False


def provenance_ok(step: str, artifact: str, prov: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    entry = prov.get(artifact)
    if not entry:
        return False, f"artifact_provenance missing for {artifact}"
    producer_type = entry.get("producer_type")
    producer_step = canonicalize_step(entry.get("producer_step") or entry.get("producer"))
    if producer_type not in ("child", "subagent"):
        return False, f"{artifact} was not produced by a child session (producer_type={producer_type!r})"
    if producer_step != step:
        return False, f"{artifact} expected producer {step!r}, got {producer_step!r}"
    if not entry.get("session_key"):
        return False, f"artifact_provenance for {artifact} missing session_key"
    if not entry.get("model"):
        return False, f"artifact_provenance for {artifact} missing model"
    return True, None


def publish_candidate(draft_dir: Path, state: Dict[str, Any]) -> Optional[str]:
    if not layout_skipped(state) and (draft_dir / "final-layout.md").exists():
        return "final-layout.md"
    return recorded_reviewed_draft_file(state) or writer_artifact_file(draft_dir, state)


def dirty_result(
    issues: List[str],
    last_clean_step: Optional[str],
    repair_action: str,
    draft_dir: Path,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "clean": False,
        "publish_allowed": False,
        "lineage_status": "dirty",
        "last_clean_step": last_clean_step,
        "repair_action": repair_action,
        "issues": issues,
        "publish_candidate": publish_candidate(draft_dir, state),
    }


def validate_content_finality(
    draft_dir: Path,
    state: Dict[str, Any],
    issues: List[str],
    last_clean_step: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Enforce: Reviewer-approved draft is final content authority.

    Layout may only consume that exact reviewed draft. Missing layout input
    identity is dirty because we cannot prove no post-review prose rewrite was
    introduced.
    """
    reviewed = recorded_reviewed_draft_file(state)
    if not reviewed:
        issues.append("reviewed_draft_file missing; reviewer-approved draft must be recorded at reviewer pass time")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)

    reviewed_path = draft_dir / reviewed
    if not reviewed_path.exists() or not reviewed_path.is_file():
        issues.append(f"reviewed_draft_file not found on disk: {reviewed}")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)
    reviewed_hash = file_sha256(reviewed_path)
    recorded_reviewed_hash = state.get("reviewed_draft_sha256")
    if not isinstance(recorded_reviewed_hash, str) or not recorded_reviewed_hash.strip():
        issues.append("reviewed_draft_sha256 missing; cannot prove reviewer-approved bytes")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)
    if reviewed_hash and recorded_reviewed_hash != reviewed_hash:
        issues.append(f"reviewed_draft_sha256 mismatch for {reviewed}")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)

    finalized_by = state.get("content_finalized_by")
    if finalized_by is not None and finalized_by != "reviewer":
        issues.append(f"content_finalized_by must be 'reviewer', got {finalized_by!r}")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)
    finalized_artifact = state.get("content_final_artifact")
    if finalized_artifact is not None and finalized_artifact != reviewed:
        issues.append(f"content_final_artifact must match reviewed_draft_file {reviewed!r}, got {finalized_artifact!r}")
        return dirty_result(issues, "reviewer", "rerun_reviewer", draft_dir, state)

    if layout_skipped(state):
        return None

    li = layout_input_file(state)
    if not li:
        issues.append("layout_input_file missing; cannot prove Layout consumed the Reviewer-approved draft")
        return dirty_result(issues, "reviewer", "rerun_layout", draft_dir, state)
    if li != reviewed:
        issues.append(f"Layout input must be Reviewer-approved draft {reviewed!r}, got {li!r}")
        return dirty_result(issues, "reviewer", "rerun_layout", draft_dir, state)

    recorded_input_hash = layout_input_sha256(state)
    if not recorded_input_hash:
        issues.append("layout_input_sha256 missing; cannot prove Layout used the exact reviewed draft bytes")
        return dirty_result(issues, "reviewer", "rerun_layout", draft_dir, state)
    if reviewed_hash and recorded_input_hash != reviewed_hash:
        issues.append(f"layout_input_sha256 mismatch for {reviewed}")
        return dirty_result(issues, "reviewer", "rerun_layout", draft_dir, state)

    return None


def audit(draft_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    children = normalize_children(state.get("children"))
    prov = normalize_artifact_provenance(state.get("artifact_provenance"))
    issues: List[str] = []
    last_clean_step: Optional[str] = None
    repair_action = "fresh_run"

    for step in STEP_ORDER:
        artifacts = choose_artifact(step, draft_dir, state)
        if step == "layout" and not artifacts and layout_skipped(state):
            last_clean_step = "reviewer"
            continue
        if not artifacts:
            issues.append(f"missing artifact for step {step}")
            repair_action = REPAIR_ACTIONS[step]
            break

        if not child_has_evidence(children.get(step, []), artifacts):
            issues.append(f"missing child-session evidence for step {step}: {', '.join(artifacts)}")
            repair_action = REPAIR_ACTIONS[step]
            break

        for artifact in artifacts:
            ok, reason = provenance_ok(step, artifact, prov)
            if not ok:
                issues.append(reason or f"bad provenance for {artifact}")
                repair_action = REPAIR_ACTIONS[step]
                return dirty_result(issues, last_clean_step, repair_action, draft_dir, state)
        last_clean_step = step

    if issues:
        return dirty_result(issues, last_clean_step, repair_action, draft_dir, state)

    finality_result = validate_content_finality(draft_dir, state, issues, last_clean_step)
    if finality_result is not None:
        return finality_result

    return {
        "schema_version": SCHEMA_VERSION,
        "clean": True,
        "publish_allowed": True,
        "lineage_status": "clean",
        "last_clean_step": last_clean_step,
        "repair_action": None,
        "issues": [],
        "publish_candidate": publish_candidate(draft_dir, state),
    }


def canonical_children_for_write(raw: Any) -> Dict[str, List[Dict[str, Any]]]:
    normalized = normalize_children(raw)
    written: Dict[str, List[Dict[str, Any]]] = {}
    for step in STEP_ORDER:
        entries = normalized.get(step)
        if entries:
            written[step] = entries
    return written


def canonical_provenance_for_write(raw: Any) -> Dict[str, Dict[str, Any]]:
    normalized = normalize_artifact_provenance(raw)
    written: Dict[str, Dict[str, Any]] = {}
    for artifact, entry in normalized.items():
        clean = dict(entry)
        producer_step = canonicalize_step(clean.get("producer_step") or clean.get("producer"))
        if producer_step not in STEP_ORDER:
            # Drop legacy Humanizer / non-active producers on canonical writeback.
            continue
        clean["producer_step"] = producer_step
        clean.pop("producer", None)
        written[artifact] = clean
    return written


def maybe_write_state(state_path: Path, state: Dict[str, Any], result: Dict[str, Any], draft_dir: Path) -> None:
    state = dict(state)
    now = iso_now()
    state["schema_version"] = SCHEMA_VERSION
    state["children"] = canonical_children_for_write(state.get("children"))
    state["artifact_provenance"] = canonical_provenance_for_write(state.get("artifact_provenance"))
    state["lineage_status"] = result["lineage_status"]
    state["last_clean_step"] = result["last_clean_step"]
    state["repair_action"] = result["repair_action"]
    state["publish_candidate"] = result["publish_candidate"]
    state["lineage_audited_at"] = now
    state["updated_at"] = now

    reviewed = recorded_reviewed_draft_file(state)
    reviewed_hash = file_sha256(draft_dir / reviewed) if reviewed else None
    if result.get("clean") and reviewed and reviewed_hash and reviewed_hash == state.get("reviewed_draft_sha256"):
        state["reviewed_draft_file"] = reviewed
        state["content_final_artifact"] = reviewed
        state["content_finalized_by"] = "reviewer"
        state["reviewed_draft_sha256"] = reviewed_hash
    atomic_write_json(state_path, state)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit wechat-article-forge lineage before publish")
    ap.add_argument("draft_dir", help="Draft directory containing pipeline-state.json")
    ap.add_argument("--json", action="store_true", help="Print JSON result")
    ap.add_argument("--write-state", action="store_true", help="Persist lineage_audited_at / lineage_status into pipeline-state.json")
    args = ap.parse_args()

    draft_dir = Path(args.draft_dir).expanduser().resolve()
    state_path = draft_dir / "pipeline-state.json"
    state = load_json(state_path)
    result = audit(draft_dir, state)

    if args.write_state:
        maybe_write_state(state_path, state, result, draft_dir)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result["clean"] else "FAIL"
        print(f"[{status}] lineage audit for {draft_dir.name}")
        print(f"schema_version: {result['schema_version']}")
        print(f"publish_allowed: {result['publish_allowed']}")
        print(f"publish_candidate: {result['publish_candidate']}")
        print(f"last_clean_step: {result['last_clean_step']}")
        if result["repair_action"]:
            print(f"repair_action: {result['repair_action']}")
        if result["issues"]:
            print("issues:")
            for issue in result["issues"]:
                print(f"- {issue}")
    return 0 if result["clean"] else 2


if __name__ == "__main__":
    sys.exit(main())
