#!/usr/bin/env python3
"""Write canonical formal-publish tail state.

Purpose:
- make formal publish tail transitions explicit instead of ad-hoc
- keep a small set of state nodes with authoritative signal metadata
- mirror to run lock on best effort only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

STATE_NODES = {
    "edit_ready",
    "prepublish_config_ready",
    "publish_entry_dialog",
    "publish_confirm_dialog",
    "submitted_pending_result",
    "waiting_safe_check_scan",
    "waiting_login_scan",
    "waiting_boss_confirm",
    "reader_side_in_review",
    "reader_side_published",
    "failed",
}

SIGNAL_KINDS = {
    "editor_page",
    "prepublish_gate",
    "visible_dialog_text",
    "visible_qr",
    "login_page",
    "recent_publish_status",
    "error_text",
    "manual_override",
}

DEFAULTS = {
    "edit_ready": {"phase": "publishing", "status": "running", "current_step": "edit_ready"},
    "prepublish_config_ready": {"phase": "publishing", "status": "running", "current_step": "prepublish_config_ready"},
    "publish_entry_dialog": {"phase": "publishing", "status": "running", "current_step": "publish_entry_dialog"},
    "publish_confirm_dialog": {"phase": "publishing", "status": "running", "current_step": "publish_confirm_dialog"},
    "submitted_pending_result": {"phase": "publishing", "status": "running", "current_step": "submitted_pending_result"},
    "waiting_safe_check_scan": {"phase": "awaiting_human", "status": "need_user_action", "current_step": "waiting_safe_check_scan", "waiting_for": "boss_scan", "required_user_action": "safe_check_scan", "resume_point": "submitted_pending_result"},
    "waiting_login_scan": {"phase": "awaiting_human", "status": "need_user_action", "current_step": "waiting_login_scan", "waiting_for": "boss_scan", "required_user_action": "login_scan", "resume_point": "edit_ready"},
    "waiting_boss_confirm": {"phase": "awaiting_human", "status": "need_user_action", "current_step": "waiting_boss_confirm", "waiting_for": "boss_confirm", "required_user_action": "boss_confirm", "resume_point": "publish_confirm_dialog"},
    "reader_side_in_review": {"phase": "published", "status": "in_review", "current_step": "reader_side_in_review"},
    "reader_side_published": {"phase": "published", "status": "published", "current_step": "reader_side_published", "state": "done"},
    "failed": {"phase": "blocked", "status": "blocked", "current_step": "publish_failed", "state": "error"},
}

CLEAR_ON_SUCCESS = [
    "waiting_for",
    "required_user_action",
    "pending_action",
    "safe_check_qr_path",
    "safe_check_qr_url",
    "qr_verified",
    "qr_verification_method",
    "relay_status",
    "relay_dedupe_key",
    "boss_notified_at",
    "qr_updated_at",
    "blocking_since",
    "timeout_at",
    "timeout_escalated_at",
    "resume_context",
    "resume_point",
    "blocking",
    "handoff",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
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
    for key in [
        "state",
        "phase",
        "status",
        "current_step",
        "waiting_for",
        "required_user_action",
        "pending_action",
        "safe_check_qr_path",
        "safe_check_qr_url",
        "qr_verified",
        "qr_verification_method",
        "relay_status",
        "relay_dedupe_key",
        "boss_notified_at",
        "qr_updated_at",
        "blocking_since",
        "timeout_at",
        "timeout_escalated_at",
        "resume_context",
        "last_progress_at",
        "last_transition_at",
        "updated_at",
        "note",
        "state_node",
        "resume_point",
        "authoritative_signal_kind",
        "authoritative_signal_summary",
        "blocking",
        "handoff",
    ]:
        if key in state:
            lock[key] = state[key]
    lock["control_plane_sync"] = "complete"
    atomic_write_json(path, lock)
    return True, "run_lock_updated"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Write canonical formal-publish tail state")
    ap.add_argument("--state-path", required=True)
    ap.add_argument("--state-node", required=True, choices=sorted(STATE_NODES))
    ap.add_argument("--signal-kind", required=True, choices=sorted(SIGNAL_KINDS))
    ap.add_argument("--signal-summary", required=True)
    ap.add_argument("--run-lock-path")
    ap.add_argument("--note", default="")
    ap.add_argument("--safe-check-qr-path")
    ap.add_argument("--resume-context-json")
    ap.add_argument("--retry-waiting-for")
    ap.add_argument("--force-status")
    ap.add_argument("--force-phase")
    ap.add_argument("--force-current-step")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path).expanduser().resolve()
    try:
        state = load_json(state_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    now = iso_now()
    defaults = dict(DEFAULTS[args.state_node])
    if args.force_status:
        defaults["status"] = args.force_status
    if args.force_phase:
        defaults["phase"] = args.force_phase
    if args.force_current_step:
        defaults["current_step"] = args.force_current_step

    state.update(defaults)
    state["state_node"] = args.state_node
    state["authoritative_signal_kind"] = args.signal_kind
    state["authoritative_signal_summary"] = args.signal_summary
    state["last_transition_at"] = now
    state["last_progress_at"] = now
    state["updated_at"] = now
    if args.note:
        state["note"] = args.note

    if args.resume_context_json:
        resume_context = json.loads(args.resume_context_json)
        if not isinstance(resume_context, dict):
            print(json.dumps({"ok": False, "error": "resume_context_json must decode to an object"}, ensure_ascii=False), file=sys.stderr)
            return 1
        state["resume_context"] = resume_context
    if args.safe_check_qr_path:
        state["safe_check_qr_path"] = args.safe_check_qr_path
    if args.retry_waiting_for:
        state["waiting_for"] = args.retry_waiting_for

    if args.state_node in {"reader_side_in_review", "reader_side_published", "edit_ready", "prepublish_config_ready", "publish_entry_dialog", "publish_confirm_dialog", "submitted_pending_result", "failed"}:
        for key in CLEAR_ON_SUCCESS:
            if key not in {"resume_context"} or args.resume_context_json is None:
                if key in state:
                    state[key] = None
        if args.state_node in {"edit_ready", "prepublish_config_ready", "publish_entry_dialog", "publish_confirm_dialog", "submitted_pending_result"}:
            state["phase"] = defaults["phase"]
            state["status"] = defaults["status"]

    if args.state_node in {"waiting_safe_check_scan", "waiting_login_scan", "waiting_boss_confirm"}:
        state.setdefault("blocking_since", now)
        state["blocking"] = {
            "current_step": state.get("current_step"),
            "waiting_for": state.get("waiting_for"),
            "required_user_action": state.get("required_user_action"),
            "resume_point": state.get("resume_point"),
            "safe_check_qr_path": state.get("safe_check_qr_path"),
        }

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
        try:
            atomic_write_json(state_path, state)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"state sync marker write failed: {exc}"}, ensure_ascii=False), file=sys.stderr)
            return 1

    print(json.dumps({
        "ok": True,
        "state_path": str(state_path),
        "state_node": args.state_node,
        "signal_kind": args.signal_kind,
        "run_lock_updated": run_lock_updated,
        "run_lock_status": run_lock_status,
        "control_plane_sync": state.get("control_plane_sync"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
