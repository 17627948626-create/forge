#!/usr/bin/env python3
"""Escalate durable blocked/need-user-action state when timeout_at has expired."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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


def parse_iso(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw).astimezone(timezone.utc)


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
    for key in [
        "status",
        "phase",
        "current_step",
        "waiting_for",
        "required_user_action",
        "timeout_at",
        "timeout_escalated_at",
        "resume_context",
        "updated_at",
        "last_transition_at",
        "last_progress_at",
        "note",
    ]:
        if key in state:
            lock[key] = state[key]
    lock["control_plane_sync"] = "complete"
    try:
        atomic_write_json(path, lock)
    except Exception as exc:
        return False, f"run_lock_write_failed:{exc}"
    return True, "run_lock_updated"


def main() -> int:
    ap = argparse.ArgumentParser(description="Escalate blocked state when timeout_at has expired")
    ap.add_argument("--state-path", required=True)
    ap.add_argument("--run-lock-path")
    ap.add_argument("--now")
    args = ap.parse_args()

    state_path = Path(args.state_path).expanduser().resolve()
    try:
        state = load_json(state_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    now_dt = parse_iso(args.now) if args.now else parse_iso(iso_now())
    timeout_at_raw = state.get("timeout_at")
    if not isinstance(timeout_at_raw, str) or not timeout_at_raw.strip():
        print(json.dumps({"ok": True, "escalated": False, "reason": "timeout_at_missing"}, ensure_ascii=False))
        return 0

    try:
        timeout_dt = parse_iso(timeout_at_raw)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"invalid timeout_at: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1

    if now_dt < timeout_dt:
        print(json.dumps({"ok": True, "escalated": False, "reason": "not_expired", "timeout_at": timeout_at_raw}, ensure_ascii=False))
        return 0

    now_iso = now_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    waiting_for = state.get("waiting_for") or "user_action"
    state["status"] = "blocked"
    state["phase"] = "blocked"
    state["current_step"] = f"blocked_timeout_wait_{waiting_for}"
    state["timeout_escalated_at"] = now_iso
    state["last_transition_at"] = now_iso
    state["last_progress_at"] = now_iso
    state["updated_at"] = now_iso
    prior_note = str(state.get("note") or "").strip()
    timeout_note = f"blocked-state timeout escalation fired after waiting_for={waiting_for}"
    state["note"] = f"{prior_note} | {timeout_note}" if prior_note else timeout_note
    if isinstance(state.get("blocking"), dict):
        state["blocking"]["phase"] = "blocked"
        state["blocking"]["current_step"] = state["current_step"]
        state["blocking"]["timeout_at"] = timeout_at_raw
        state["blocking"]["timeout_escalated_at"] = now_iso
    state["control_plane_sync"] = "partial"

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
                "escalated": True,
                "status": state["status"],
                "phase": state["phase"],
                "current_step": state["current_step"],
                "timeout_at": timeout_at_raw,
                "timeout_escalated_at": state["timeout_escalated_at"],
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
