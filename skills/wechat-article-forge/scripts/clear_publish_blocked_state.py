#!/usr/bin/env python3
"""Clear stale blocked-state fields after publish moves past human handoff."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


CLEAR_TOP_LEVEL = [
    "waiting_for",
    "required_user_action",
    "safe_check_qr_path",
    "safe_check_qr_url",
    "relay_status",
    "relay_dedupe_key",
    "boss_notified_at",
    "qr_updated_at",
    "blocking_since",
    "timeout_at",
    "timeout_escalated_at",
    "resume_context",
    "resume_point",
    "state_node",
    "authoritative_signal_kind",
    "authoritative_signal_summary",
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
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def mirror_run_lock(run_lock_path: Optional[str], state: Dict[str, Any]) -> Tuple[bool, str]:
    if not run_lock_path:
        return False, "run_lock_not_provided"
    path = Path(run_lock_path).expanduser().resolve()
    if not path.exists():
        return False, "run_lock_missing"
    try:
        lock = load_json(path)
    except Exception as exc:
        return False, f"run_lock_unparseable:{exc}"
    if lock.get("run_id") != state.get("run_id"):
        return False, f"run_lock_run_id_mismatch:{lock.get('run_id')!r}"

    for key in CLEAR_TOP_LEVEL:
        lock[key] = None
    lock["blocking"] = None
    lock["handoff"] = None
    lock["control_plane_sync"] = "complete"
    for key in ["status", "phase", "current_step", "state", "updated_at", "last_transition_at", "last_progress_at", "note"]:
        if key in state:
            lock[key] = state[key]
    atomic_write_json(path, lock)
    return True, "run_lock_updated"


def main() -> int:
    ap = argparse.ArgumentParser(description="Clear stale blocked publish state after resume/success/failure")
    ap.add_argument("--state-path", required=True)
    ap.add_argument("--run-lock-path")
    ap.add_argument("--status", required=True, help="authoritative status after clearing, e.g. in_review|published|failed|cancelled")
    ap.add_argument("--phase", required=True, help="authoritative phase after clearing")
    ap.add_argument("--current-step", required=True)
    ap.add_argument("--state", help="optional run-level state, e.g. done|error")
    ap.add_argument("--note", default="blocked publish state cleared after terminal/post-submit transition")
    args = ap.parse_args()

    state_path = Path(args.state_path).expanduser().resolve()
    try:
        state = load_json(state_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    now = iso_now()
    for key in CLEAR_TOP_LEVEL:
        state[key] = None
    state["blocking"] = None
    state["handoff"] = None
    state["status"] = args.status
    state["phase"] = args.phase
    state["current_step"] = args.current_step
    state["state_node"] = args.current_step
    if args.current_step in {"reader_side_in_review", "reader_side_published"}:
        state["authoritative_signal_kind"] = "recent_publish_status"
        state["authoritative_signal_summary"] = args.current_step
    if args.state:
        state["state"] = args.state
    state["pending_action"] = None
    state["control_plane_sync"] = "partial"
    state["last_transition_at"] = now
    state["last_progress_at"] = now
    state["updated_at"] = now
    state["note"] = args.note

    try:
        atomic_write_json(state_path, state)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    run_lock_updated, run_lock_status = mirror_run_lock(args.run_lock_path, state)
    if run_lock_updated:
        state["control_plane_sync"] = "complete"
        state["updated_at"] = iso_now()
        atomic_write_json(state_path, state)

    print(
        json.dumps(
            {
                "ok": True,
                "status": state["status"],
                "phase": state["phase"],
                "current_step": state["current_step"],
                "state_path": str(state_path),
                "run_lock_updated": run_lock_updated,
                "run_lock_status": run_lock_status,
                "control_plane_sync": state["control_plane_sync"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
