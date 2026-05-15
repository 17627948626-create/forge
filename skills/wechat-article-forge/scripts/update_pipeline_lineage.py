#!/usr/bin/env python3
"""Canonical pipeline lineage writer for wechat-article-forge.

Active content chain:
Researcher -> Writer -> Reviewer -> Layout.

Humanizer was removed from the active pipeline. This helper rejects Humanizer
writes so new runs cannot reintroduce post-review prose rewriting.
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
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "2026-04-09.lineage-v2"
CANONICAL_STEPS = ["researcher", "writer", "reviewer", "layout"]


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
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def file_sha256(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_required_artifact_path(draft_dir: Path, raw_path: str, *, label: str) -> Path:
    path = (draft_dir / Path(raw_path).name).resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


_ALIAS_PATTERNS = [
    (re.compile(r"^research(er)?(_v\d+)?$"), "researcher"),
    (re.compile(r"^writer($|_v\d+$|_revision(_v\d+)?$|_revise$|_rewrite$|_rework$|_factfix$)"), "writer"),
    (re.compile(r"^review(er)?($|_v\d+$|_round\d+$)"), "reviewer"),
    (re.compile(r"^layout($|_v\d+$)"), "layout"),
]


def canonicalize_step(raw_step: Any) -> Optional[str]:
    if not isinstance(raw_step, str):
        return None
    step = raw_step.strip().lower().replace("-", "_")
    if step in CANONICAL_STEPS:
        return step
    # Explicitly reject removed Humanizer writes instead of silently aliasing.
    if re.match(r"^humani[sz](er)?($|_v\d+$)", step):
        return None
    for pattern, canonical in _ALIAS_PATTERNS:
        if pattern.match(step):
            return canonical
    return None


def parse_artifacts(values: List[str]) -> List[str]:
    artifacts: List[str] = []
    for value in values:
        for item in re.split(r"\s*,\s*", value.strip()):
            if item:
                normalized = Path(item).name
                if normalized:
                    artifacts.append(normalized)
    deduped: List[str] = []
    for artifact in artifacts:
        if artifact not in deduped:
            deduped.append(artifact)
    return deduped


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Write canonical children[...] and artifact_provenance in one atomic helper")
    ap.add_argument("--state-path", required=True)
    ap.add_argument("--step", required=True, help="Canonical or supported alias step name; active steps only")
    ap.add_argument("--session-key", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--artifacts", nargs="+", required=True, help="Artifact file(s); helper canonicalizes to draft-dir basename keys only (comma-separated accepted)")
    ap.add_argument("--label")
    ap.add_argument("--status", default="done")
    ap.add_argument("--producer-type", default="child")
    ap.add_argument("--completed-at")
    ap.add_argument(
        "--input-artifact",
        help="For layout writes only: Reviewer-approved draft consumed by Layout. Records layout_input_file and layout_input_sha256.",
    )
    ap.add_argument(
        "--approved-artifact",
        help="For reviewer pass writes only: exact draft approved by Reviewer. Records reviewed_draft_file and reviewed_draft_sha256.",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    canonical_step = canonicalize_step(args.step)
    if canonical_step is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"unknown or inactive step: {args.step}",
                    "allowed_steps": CANONICAL_STEPS,
                    "note": "Humanizer is removed from the active pipeline; Reviewer-approved draft is the final content authority.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    artifacts = parse_artifacts(args.artifacts)
    if not artifacts:
        print(json.dumps({"ok": False, "error": "no artifacts provided"}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.input_artifact and canonical_step != "layout":
        print(json.dumps({"ok": False, "error": "--input-artifact is only valid for layout writes"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.approved_artifact and canonical_step != "reviewer":
        print(json.dumps({"ok": False, "error": "--approved-artifact is only valid for reviewer writes"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if canonical_step == "layout" and not args.input_artifact:
        print(json.dumps({"ok": False, "error": "--input-artifact is required for layout writes"}, ensure_ascii=False), file=sys.stderr)
        return 2

    state_path = Path(args.state_path).expanduser().resolve()
    draft_dir = state_path.parent
    now = iso_now()

    try:
        state = load_json(state_path)
        children = state.get("children") if isinstance(state.get("children"), dict) else {}
        artifact_provenance = state.get("artifact_provenance") if isinstance(state.get("artifact_provenance"), dict) else {}

        existing_entries = children.get(canonical_step)
        if isinstance(existing_entries, dict):
            canonical_entries: List[Dict[str, Any]] = [existing_entries]
        elif isinstance(existing_entries, list):
            canonical_entries = [x for x in existing_entries if isinstance(x, dict)]
        else:
            canonical_entries = []

        entry = {
            "session_key": args.session_key,
            "label": args.label,
            "model": args.model,
            "status": args.status,
            "artifacts": artifacts,
            "completed_at": args.completed_at or now,
        }
        canonical_entries.append({k: v for k, v in entry.items() if v is not None})
        children[canonical_step] = canonical_entries

        for artifact in artifacts:
            artifact_provenance[artifact] = {
                "producer_type": args.producer_type,
                "producer_step": canonical_step,
                "session_key": args.session_key,
                "model": args.model,
                "label": args.label,
                "updated_at": now,
            }

        if canonical_step == "reviewer" and args.approved_artifact:
            approved_path = resolve_required_artifact_path(draft_dir, args.approved_artifact, label="approved artifact")
            approved_name = approved_path.name
            approved_hash = file_sha256(approved_path)
            if not approved_hash:
                raise ValueError(f"unable to hash approved artifact: {approved_path}")
            last_draft_file = state.get("last_draft_file")
            if isinstance(last_draft_file, str) and last_draft_file.strip() and last_draft_file != approved_name:
                raise ValueError(
                    f"approved artifact must match state.last_draft_file ({last_draft_file!r}), got {approved_name!r}"
                )
            state["reviewed_draft_file"] = approved_name
            state["reviewed_draft_sha256"] = approved_hash
            state["review_passed_at"] = args.completed_at or now
            state["content_finalized_by"] = "reviewer"
            state["content_final_artifact"] = approved_name

        if canonical_step == "layout":
            input_path = resolve_required_artifact_path(draft_dir, args.input_artifact, label="layout input artifact")
            input_name = input_path.name
            input_hash = file_sha256(input_path)
            if not input_hash:
                raise ValueError(f"unable to hash layout input artifact: {input_path}")

            reviewed_name = state.get("reviewed_draft_file")
            reviewed_hash = state.get("reviewed_draft_sha256")
            if not isinstance(reviewed_name, str) or not reviewed_name.strip():
                raise ValueError("reviewed_draft_file missing; record reviewer pass before layout lineage write")
            if not isinstance(reviewed_hash, str) or not reviewed_hash.strip():
                raise ValueError("reviewed_draft_sha256 missing; record reviewer-approved bytes before layout lineage write")
            if input_name != reviewed_name:
                raise ValueError(
                    f"layout input artifact must match reviewed_draft_file ({reviewed_name!r}), got {input_name!r}"
                )
            if input_hash != reviewed_hash:
                raise ValueError(
                    f"layout input artifact hash does not match reviewed_draft_sha256 for {input_name!r}"
                )

            state["layout_input_file"] = input_name
            state["layout_input_sha256"] = input_hash

        state["schema_version"] = SCHEMA_VERSION
        state["children"] = children
        state["artifact_provenance"] = artifact_provenance
        state["updated_at"] = now
        atomic_write_json(state_path, state)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "state_path": str(state_path),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": SCHEMA_VERSION,
                "state_path": str(state_path),
                "canonical_step": canonical_step,
                "artifacts": artifacts,
                "reviewed_draft_file": state.get("reviewed_draft_file") if canonical_step == "reviewer" and args.approved_artifact else None,
                "layout_input_file": state.get("layout_input_file") if canonical_step == "layout" else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
