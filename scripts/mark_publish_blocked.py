#!/usr/bin/env python3
"""Persist a durable publish-blocked control-plane state.

Strong requirement:
- pipeline-state.json must be updated successfully or the command exits non-zero.

Best-effort requirement:
- run lock is updated only when the caller explicitly passes a path AND the file
  already exists AND it is valid JSON AND its run_id exactly matches.
- run-lock update failures never cause a non-zero exit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


RELAY_STATUS_CHOICES = {
    "pending_parent_forward",
    "forwarded",
    "acknowledged",
    "internal_retry",
    "completed",
}
PHASE_CHOICES = {"awaiting_human", "blocked", "publishing"}
STATUS_CHOICES = {"need_user_action", "blocked", "waiting_retry"}


DEFAULT_STATUS_BY_PHASE = {
    "awaiting_human": "need_user_action",
    "blocked": "blocked",
    "publishing": "waiting_retry",
}
QR_REQUIRED_ACTIONS = {"safe_check_scan", "login_scan"}


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def iso_after_minutes(minutes: int) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(minutes=minutes))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sanitize_run_id_for_path(run_id: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-._")
    return sanitized or "run"


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


def load_json(path: Path, *, must_exist: bool) -> Dict[str, Any]:
    if not path.exists():
        if must_exist:
            raise FileNotFoundError(f"JSON file not found: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def looks_like_image_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            header = fh.read(16)
    except OSError:
        return False

    return (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"GIF87a")
        or header.startswith(b"GIF89a")
        or header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    )


def validate_qr_path(qr_path: Optional[str], run_id: str) -> Optional[str]:
    if qr_path is None:
        return None

    p = Path(qr_path)
    if not p.is_absolute():
        raise ValueError("safe_check_qr_path must be an absolute path")

    path_text = str(p)
    if path_text == "/tmp" or path_text.startswith("/tmp/"):
        raise ValueError("safe_check_qr_path must not be under /tmp")

    run_tokens = {run_id, sanitize_run_id_for_path(run_id)}
    if not any(token and token in path_text for token in run_tokens):
        raise ValueError(
            "safe_check_qr_path must be unique per run; include run_id or its sanitized form in the path"
        )

    if not p.exists() or not p.is_file():
        raise ValueError("safe_check_qr_path must point to an existing file")

    if not looks_like_image_file(p):
        raise ValueError("safe_check_qr_path must point to an image file")

    return path_text


def parse_resume_context(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if raw is None or raw == "":
        return None
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("resume_context_json must decode to an object")
    return value


def build_state_overlay(existing: Dict[str, Any], args: argparse.Namespace, now: str) -> Dict[str, Any]:
    qr_path = validate_qr_path(args.safe_check_qr_path, args.run_id)
    status = args.status or DEFAULT_STATUS_BY_PHASE.get(args.phase, "blocked")

    old_signature = (
        existing.get("phase"),
        existing.get("status"),
        existing.get("current_step"),
        existing.get("waiting_for"),
        existing.get("required_user_action"),
    )
    new_signature = (
        args.phase,
        status,
        args.current_step,
        args.waiting_for,
        args.required_user_action,
    )
    blocker_changed = old_signature != (None, None, None, None, None) and old_signature != new_signature

    if args.required_user_action in QR_REQUIRED_ACTIONS:
        if not qr_path:
            raise ValueError("safe_check_qr_path is required for QR-based human actions")
        if not args.qr_verified:
            raise ValueError("--qr-verified is required before persisting QR-based human handoff state")

    blocking_since = (
        args.blocking_since
        or (now if blocker_changed else existing.get("blocking_since"))
        or now
    )
    qr_updated_at = args.qr_updated_at or (now if qr_path else None)
    boss_notified_at = args.boss_notified_at or None
    pending_action = f"wait_{args.waiting_for}" if args.waiting_for else existing.get("pending_action")
    timeout_at = (
        args.timeout_at
        or (iso_after_minutes(args.timeout_minutes) if blocker_changed else existing.get("timeout_at"))
        or iso_after_minutes(args.timeout_minutes)
    )
    resume_context = parse_resume_context(args.resume_context_json) or existing.get("resume_context")
    qr_verification_method = args.qr_verification_method or ("manual" if args.qr_verified else None)

    state_node = args.current_step
    resume_point = None
    if args.current_step == "waiting_safe_check_scan":
        resume_point = "submitted_pending_result"
    elif args.current_step == "waiting_login_scan":
        resume_point = "edit_ready"
    elif args.current_step == "waiting_boss_confirm":
        resume_point = "publish_confirm_dialog"

    overlay: Dict[str, Any] = {
        "run_id": args.run_id,
        "status": status,
        "step": 8,
        "phase": args.phase,
        "current_step": args.current_step,
        "state_node": state_node,
        "resume_point": resume_point,
        "authoritative_signal_kind": "visible_qr" if args.required_user_action in QR_REQUIRED_ACTIONS else "visible_dialog_text",
        "authoritative_signal_summary": args.note or args.current_step,
        "waiting_for": args.waiting_for,
        "required_user_action": args.required_user_action,
        "pending_action": pending_action,
        "safe_check_qr_path": qr_path,
        "qr_verified": args.qr_verified,
        "qr_verification_method": qr_verification_method,
        "relay_status": args.relay_status,
        "relay_dedupe_key": args.relay_dedupe_key,
        "boss_notified_at": boss_notified_at,
        "qr_updated_at": qr_updated_at,
        "blocking_since": blocking_since,
        "timeout_at": timeout_at,
        "control_plane_sync": "partial",
        "blocker_changed": blocker_changed,
        "last_transition_at": now,
        "last_progress_at": now,
        "updated_at": now,
        "note": args.note,
        "resume_context": resume_context,
        "blocking": {
            "status": status,
            "step": 8,
            "phase": args.phase,
            "current_step": args.current_step,
            "state_node": state_node,
            "resume_point": resume_point,
            "waiting_for": args.waiting_for,
            "required_user_action": args.required_user_action,
            "safe_check_qr_path": qr_path,
            "qr_verified": args.qr_verified,
            "qr_verification_method": qr_verification_method,
            "qr_updated_at": qr_updated_at,
            "blocking_since": blocking_since,
            "timeout_at": timeout_at,
            "note": args.note,
        },
        "handoff": {
            "relay_status": args.relay_status,
            "relay_dedupe_key": args.relay_dedupe_key,
            "boss_notified_at": boss_notified_at,
        },
    }

    return overlay


def merge_dict(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        merged[key] = value
    return merged


def try_update_run_lock(run_lock_path: Optional[str], overlay: Dict[str, Any]) -> Tuple[bool, str]:
    if not run_lock_path:
        return False, "run_lock_not_provided"

    path = Path(run_lock_path).expanduser()
    if not path.exists():
        return False, "run_lock_missing"

    try:
        current = load_json(path, must_exist=True)
    except Exception as exc:
        return False, f"run_lock_unparseable:{exc}"

    current_run_id = current.get("run_id")
    if current_run_id != overlay["run_id"]:
        return False, f"run_lock_run_id_mismatch:{current_run_id!r}"

    lock_overlay = {
        "state": current.get("state", "running"),
        "status": overlay["status"],
        "phase": overlay["phase"],
        "step": overlay["step"],
        "current_step": overlay["current_step"],
        "waiting_for": overlay["waiting_for"],
        "required_user_action": overlay["required_user_action"],
        "pending_action": overlay["pending_action"],
        "safe_check_qr_path": overlay["safe_check_qr_path"],
        "qr_verified": overlay["qr_verified"],
        "qr_verification_method": overlay["qr_verification_method"],
        "relay_status": overlay["relay_status"],
        "relay_dedupe_key": overlay["relay_dedupe_key"],
        "boss_notified_at": overlay["boss_notified_at"],
        "qr_updated_at": overlay["qr_updated_at"],
        "blocking_since": overlay["blocking_since"],
        "timeout_at": overlay["timeout_at"],
        "resume_context": overlay["resume_context"],
        "control_plane_sync": "complete",
        "last_progress_at": overlay["last_progress_at"],
        "last_transition_at": overlay["last_transition_at"],
        "updated_at": overlay["updated_at"],
        "note": overlay["note"],
        "blocking": overlay["blocking"],
        "handoff": overlay["handoff"],
    }

    merged = merge_dict(current, lock_overlay)
    try:
        atomic_write_json(path, merged)
    except Exception as exc:
        return False, f"run_lock_write_failed:{exc}"

    return True, "run_lock_updated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist a durable publish-blocked control-plane state.")
    parser.add_argument("--state-path", required=True, help="Path to pipeline-state.json")
    parser.add_argument("--run-lock-path", help="Optional run lock path; best-effort only")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--waiting-for", required=True, help="e.g. boss_scan, boss_confirm, system_retry")
    parser.add_argument("--required-user-action", help="e.g. safe_check_scan, login_scan; omit for platform-side retry waits")
    parser.add_argument("--current-step", required=True, help="e.g. waiting_safe_check_scan")
    parser.add_argument("--phase", choices=sorted(PHASE_CHOICES), default="awaiting_human")
    parser.add_argument("--status", choices=sorted(STATUS_CHOICES), help="Defaults from phase: awaiting_human→need_user_action, blocked→blocked, publishing→waiting_retry")
    parser.add_argument("--safe-check-qr-path", help="Absolute non-/tmp path; should be unique per run")
    parser.add_argument("--qr-verified", action="store_true", help="Required for QR-based human handoffs; confirms the operator has verified the file is an actual QR image")
    parser.add_argument("--qr-verification-method", help="Optional verification note, e.g. manual or vision")
    parser.add_argument("--note", default="")
    parser.add_argument("--relay-status", required=True, choices=sorted(RELAY_STATUS_CHOICES))
    parser.add_argument("--relay-dedupe-key", required=True)
    parser.add_argument("--boss-notified-at", help="ISO timestamp or empty")
    parser.add_argument("--qr-updated-at", help="ISO timestamp")
    parser.add_argument("--blocking-since", help="ISO timestamp")
    parser.add_argument("--timeout-at", help="ISO timestamp for escalation threshold")
    parser.add_argument("--timeout-minutes", type=int, default=10, help="Used only when --timeout-at is omitted")
    parser.add_argument("--resume-context-json", help="JSON object persisted for post-scan resume")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state_path).expanduser()
    now = iso_now()

    try:
        current_state = load_json(state_path, must_exist=False)
        overlay = build_state_overlay(current_state, args, now)
        merged_state = merge_dict(current_state, overlay)
        atomic_write_json(state_path, merged_state)
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

    run_lock_updated, run_lock_status = try_update_run_lock(args.run_lock_path, overlay)

    if run_lock_updated:
        merged_state["control_plane_sync"] = "complete"
        merged_state["updated_at"] = iso_now()
        try:
            atomic_write_json(state_path, merged_state)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"pipeline-state second write failed after run-lock update: {exc}",
                        "state_path": str(state_path),
                        "run_lock_path": args.run_lock_path,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1
    else:
        merged_state["control_plane_sync"] = "partial"

    print(
        json.dumps(
            {
                "ok": True,
                "state_path": str(state_path),
                "run_lock_path": args.run_lock_path,
                "run_lock_updated": run_lock_updated,
                "run_lock_status": run_lock_status,
                "control_plane_sync": merged_state["control_plane_sync"],
                "status": merged_state["status"],
                "phase": merged_state["phase"],
                "current_step": merged_state["current_step"],
                "waiting_for": merged_state["waiting_for"],
                "required_user_action": merged_state["required_user_action"],
                "safe_check_qr_path": merged_state["safe_check_qr_path"],
                "qr_verified": merged_state["qr_verified"],
                "qr_verification_method": merged_state["qr_verification_method"],
                "relay_status": merged_state["relay_status"],
                "relay_dedupe_key": merged_state["relay_dedupe_key"],
                "timeout_at": merged_state["timeout_at"],
                "resume_context": merged_state.get("resume_context"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
