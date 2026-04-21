#!/usr/bin/env python3
import argparse
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
STEP_ORDER = ["researcher", "writer", "reviewer", "humanizer", "layout"]

_ALIAS_PATTERNS = [
    (re.compile(r"^research(er)?(_v\d+)?$"), "researcher"),
    (re.compile(r"^writer($|_v\d+$|_revision(_v\d+)?$|_revise$|_rewrite$|_rework$|_factfix$)"), "writer"),
    (re.compile(r"^review(er)?($|_v\d+$|_round\d+$)"), "reviewer"),
    (re.compile(r"^fact(_?checker|check)?($|_v\d+$|_round\d+$)"), "fact_checker"),
    (re.compile(r"^humani[sz](er)?($|_v\d+$)"), "humanizer"),
    (re.compile(r"^layout($|_v\d+$)"), "layout"),
]


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
    if step in STEP_ORDER:
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


def choose_artifact(step: str, draft_dir: Path, state: Dict[str, Any]) -> List[str]:
    if step == "researcher":
        names = ["research.json", "outline.md"]
        return [n for n in names if (draft_dir / n).exists()]
    if step == "writer":
        cand = state.get("last_draft_file") or latest_matching(draft_dir, ["draft.md", "draft-v*.md"])
        return [cand] if cand and (draft_dir / cand).exists() else []
    if step == "reviewer":
        cand = state.get("last_review_file") or latest_matching(draft_dir, ["review-v*.json", "review-v*.md"])
        return [cand] if cand and (draft_dir / cand).exists() else []
    if step == "humanizer":
        return ["final.md"] if (draft_dir / "final.md").exists() else []
    if step == "layout":
        layout_skipped = bool(state.get("layout_skipped") or state.get("layout", {}).get("skipped"))
        if layout_skipped:
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


def audit(draft_dir: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    children = normalize_children(state.get("children"))
    prov = normalize_artifact_provenance(state.get("artifact_provenance"))
    issues: List[str] = []
    last_clean_step: Optional[str] = None
    repair_action = "fresh_run"

    for step in STEP_ORDER:
        artifacts = choose_artifact(step, draft_dir, state)
        if step == "layout" and not artifacts and bool(state.get("layout_skipped") or state.get("layout", {}).get("skipped")):
            last_clean_step = "humanizer"
            continue
        if not artifacts:
            issues.append(f"missing artifact for step {step}")
            repair_action = {
                "researcher": "fresh_run",
                "writer": "rerun_writer",
                "reviewer": "rerun_reviewer",
                "humanizer": "rerun_humanizer",
                "layout": "rerun_layout",
            }[step]
            break

        if not child_has_evidence(children.get(step, []), artifacts):
            issues.append(f"missing child-session evidence for step {step}: {', '.join(artifacts)}")
            repair_action = {
                "researcher": "fresh_run",
                "writer": "rerun_writer",
                "reviewer": "rerun_reviewer",
                "humanizer": "rerun_humanizer",
                "layout": "rerun_layout",
            }[step]
            break

        for artifact in artifacts:
            ok, reason = provenance_ok(step, artifact, prov)
            if not ok:
                issues.append(reason or f"bad provenance for {artifact}")
                repair_action = {
                    "researcher": "fresh_run",
                    "writer": "rerun_writer",
                    "reviewer": "rerun_reviewer",
                    "humanizer": "rerun_humanizer",
                    "layout": "rerun_layout",
                }[step]
                return {
                    "schema_version": SCHEMA_VERSION,
                    "clean": False,
                    "publish_allowed": False,
                    "lineage_status": "dirty",
                    "last_clean_step": last_clean_step,
                    "repair_action": repair_action,
                    "issues": issues,
                    "publish_candidate": state.get("publish_file") or ("final-layout.md" if (draft_dir / "final-layout.md").exists() else "final.md"),
                }
        last_clean_step = step

    clean = len(issues) == 0
    return {
        "schema_version": SCHEMA_VERSION,
        "clean": clean,
        "publish_allowed": clean,
        "lineage_status": "clean" if clean else "dirty",
        "last_clean_step": last_clean_step,
        "repair_action": None if clean else repair_action,
        "issues": issues,
        "publish_candidate": state.get("publish_file") or ("final-layout.md" if (draft_dir / "final-layout.md").exists() else "final.md"),
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
        if producer_step:
            clean["producer_step"] = producer_step
        clean.pop("producer", None)
        written[artifact] = clean
    return written



def maybe_write_state(state_path: Path, state: Dict[str, Any], result: Dict[str, Any]) -> None:
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
        maybe_write_state(state_path, state, result)

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
