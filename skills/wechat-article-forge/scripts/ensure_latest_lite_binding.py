#!/usr/bin/env python3
"""Ensure latest draft is durably bound to the latest writer-lite check.

If the current latest draft does not match the canonical writer-lite-check.json
(on draft_version + draft_sha256), callers must either:
1. rerun writer_lite_preflight.py for the latest draft, or
2. persist an explicit waiver explaining why a rerun is skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_PRECHECK_SCRIPT = Path(__file__).resolve().with_name("writer_lite_preflight.py")


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise


def sha256_file(path: Optional[Path]) -> Optional[str]:
    if not path or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draft_version_from_name(name: str) -> str:
    if name == "draft.md":
        return "draft-v1"
    if name.startswith("draft-v") and name.endswith(".md"):
        return name[:-3]
    return name


def normalize_state_path(path: Path) -> Path:
    return path.expanduser().resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ensure latest draft matches latest lite check or record waiver")
    ap.add_argument("--state-path", required=True)
    ap.add_argument("--check-path")
    ap.add_argument("--binding-path")
    ap.add_argument("--brief-path")
    ap.add_argument("--research-path")
    ap.add_argument("--draft-path")
    ap.add_argument("--precheck-script", default=str(DEFAULT_PRECHECK_SCRIPT), help="writer_lite_preflight.py path; defaults to sibling script")
    ap.add_argument("--mode", choices=["check", "rerun", "waiver"], default="check")
    ap.add_argument("--check-mode", choices=["blocking", "advisory"])
    ap.add_argument("--change-reason", default="latest draft changed; refresh lite preflight binding")
    ap.add_argument("--waiver-reason")
    args = ap.parse_args()

    state_path = normalize_state_path(Path(args.state_path))
    if not state_path.exists():
        print(json.dumps({"ok": False, "error": f"state not found: {state_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    draft_dir = state_path.parent
    state = load_json(state_path)

    last_draft_file = args.draft_path or state.get("last_draft_file")
    if not last_draft_file:
        print(json.dumps({"ok": False, "error": "last_draft_file missing from state and --draft-path not provided"}, ensure_ascii=False), file=sys.stderr)
        return 1

    if args.draft_path:
        draft_path = normalize_state_path(Path(args.draft_path))
    else:
        draft_path = normalize_state_path(draft_dir / str(last_draft_file))
    if not draft_path.exists():
        print(json.dumps({"ok": False, "error": f"latest draft not found: {draft_path}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    check_path = normalize_state_path(Path(args.check_path)) if args.check_path else normalize_state_path(draft_dir / "writer-lite-check.json")
    binding_path = normalize_state_path(Path(args.binding_path)) if args.binding_path else normalize_state_path(draft_dir / "writer-lite-binding.json")
    brief_path = normalize_state_path(Path(args.brief_path)) if args.brief_path else normalize_state_path(draft_dir / "writer-lite-brief.json")
    research_path = normalize_state_path(Path(args.research_path)) if args.research_path else normalize_state_path(draft_dir / "research.json")
    precheck_script = normalize_state_path(Path(args.precheck_script))

    existing_check = load_json(check_path)
    current_draft_version = draft_version_from_name(draft_path.name)
    current_draft_sha256 = sha256_file(draft_path)
    existing_check_version = existing_check.get("draft_version")
    existing_check_sha256 = (
        existing_check.get("input_fingerprints", {}).get("draft_sha256")
        if isinstance(existing_check.get("input_fingerprints"), dict)
        else None
    )
    existing_check_mode = existing_check.get("check_mode") if isinstance(existing_check.get("check_mode"), str) else None
    match = bool(existing_check) and existing_check_version == current_draft_version and existing_check_sha256 == current_draft_sha256

    checked_at = iso_now()
    binding: Dict[str, Any] = {
        "checked_at": checked_at,
        "status": "matched" if match else "mismatch_requires_action",
        "match": match,
        "draft_dir": str(draft_dir),
        "last_draft_file": draft_path.name,
        "last_draft_version": current_draft_version,
        "last_draft_sha256": current_draft_sha256,
        "latest_check_path": str(check_path),
        "latest_check_exists": check_path.exists(),
        "previous_check_draft_version": existing_check_version,
        "previous_check_draft_sha256": existing_check_sha256,
        "latest_check_draft_version": existing_check_version,
        "latest_check_draft_sha256": existing_check_sha256,
        "resolution": None,
        "waiver": None,
    }

    exit_code = 0

    if not match:
        if args.mode == "waiver":
            if not args.waiver_reason:
                print(json.dumps({"ok": False, "error": "--waiver-reason is required when --mode waiver"}, ensure_ascii=False), file=sys.stderr)
                return 1
            binding["status"] = "waived"
            binding["waiver"] = {
                "reason": args.waiver_reason,
                "waived_at": checked_at,
            }
            binding["resolution"] = {
                "action": "waiver",
                "reason": args.waiver_reason,
            }
        elif args.mode == "rerun":
            if not precheck_script.exists():
                print(json.dumps({"ok": False, "error": f"preflight script missing: {precheck_script}"}, ensure_ascii=False), file=sys.stderr)
                return 1
            chosen_check_mode = args.check_mode or existing_check_mode or "blocking"
            cmd = [
                sys.executable,
                str(precheck_script),
                str(draft_path),
                "--output",
                str(check_path),
                "--draft-version",
                current_draft_version,
                "--change-reason",
                args.change_reason,
                "--check-mode",
                chosen_check_mode,
            ]
            if brief_path.exists():
                cmd.extend(["--brief-path", str(brief_path)])
            if research_path.exists():
                cmd.extend(["--research-path", str(research_path)])
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if completed.returncode not in (0, 2):
                sys.stderr.write(completed.stderr)
                return completed.returncode
            refreshed_check = load_json(check_path)
            if not refreshed_check:
                sys.stderr.write(completed.stderr)
                print(json.dumps({"ok": False, "error": "rerun did not produce writer-lite-check.json"}, ensure_ascii=False), file=sys.stderr)
                return 1
            refreshed_sha256 = (
                refreshed_check.get("input_fingerprints", {}).get("draft_sha256")
                if isinstance(refreshed_check.get("input_fingerprints"), dict)
                else None
            )
            refreshed_version = refreshed_check.get("draft_version")
            refreshed_match = refreshed_version == current_draft_version and refreshed_sha256 == current_draft_sha256
            if not refreshed_match:
                print(json.dumps({"ok": False, "error": "rerun completed but refreshed check still does not match latest draft"}, ensure_ascii=False), file=sys.stderr)
                return 1
            # Keep the durable enum focused on binding state. Preflight failure
            # remains observable via exit code + resolution.preflight_* details.
            binding["status"] = "rerun_completed"
            binding["match"] = True
            binding["latest_check_draft_version"] = refreshed_version
            binding["latest_check_draft_sha256"] = refreshed_sha256
            binding["resolution"] = {
                "action": "rerun_preflight",
                "check_mode": refreshed_check.get("check_mode"),
                "change_reason": refreshed_check.get("change_reason"),
                "check_output_path": str(check_path),
                "completed_at": checked_at,
                "preflight_returncode": completed.returncode,
                "preflight_hard_fail": bool(refreshed_check.get("hard_fail")),
                "preflight_hard_fail_reasons": refreshed_check.get("hard_fail_reasons") or [],
            }
            if completed.returncode == 2:
                exit_code = 2
        else:
            exit_code = 2

    lite_preflight_state = {
        "binding_status": binding["status"],
        "binding_checked_at": checked_at,
        "binding_artifact": str(binding_path),
        "last_draft_file": draft_path.name,
        "last_draft_version": current_draft_version,
        "last_draft_sha256": current_draft_sha256,
        "latest_check_path": str(check_path),
        "previous_check_draft_version": binding.get("previous_check_draft_version"),
        "previous_check_draft_sha256": binding.get("previous_check_draft_sha256"),
        "latest_check_draft_version": binding.get("latest_check_draft_version"),
        "latest_check_draft_sha256": binding.get("latest_check_draft_sha256"),
        "match": binding["match"],
        "waiver": binding.get("waiver"),
        "resolution": binding.get("resolution"),
    }
    state["lite_preflight"] = lite_preflight_state
    state["updated_at"] = checked_at

    write_json_atomic(binding_path, binding)
    write_json_atomic(state_path, state)
    print(json.dumps(binding, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
