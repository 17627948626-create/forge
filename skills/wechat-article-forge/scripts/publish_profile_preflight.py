#!/usr/bin/env python3
"""Resolve and validate the explicit publish profile for wenyan draft-box publish.

Fail-closed rules:
- profile is mandatory
- unknown profile is an error
- publisher.mcp_config_file must exist and be readable
- publisher.mcp_config_file and published_log_path must stay inside the active
  article workspace
- config must explicitly contain the requested MCP server
- no implicit fallback to global/default config or another Hermes profile
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


def resolve_config_path(raw: str, base_dir: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def ensure_within(path: Path, parent: Path, label: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        raise ValueError(f"{label} must be inside active article workspace: {path}")


def parse_frontmatter(path: Path) -> Dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"publish.md missing frontmatter start marker: {path}")
    frontmatter: Dict[str, str] = {}
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip('"').strip("'")
    if not closed:
        raise ValueError(f"publish.md missing frontmatter end marker: {path}")
    return frontmatter



def validate_publish_frontmatter(publish_md_path: Path, profile_result: Dict[str, Any]) -> Dict[str, Any]:
    frontmatter = parse_frontmatter(publish_md_path)
    required = ["title", "author", "profile", "cover", "theme", "slug"]
    missing = [key for key in required if not str(frontmatter.get(key) or "").strip()]
    if missing:
        raise ValueError(f"publish.md missing required frontmatter fields: {', '.join(missing)}")
    if frontmatter["profile"] != profile_result["profile"]:
        raise ValueError(
            f"publish.md profile mismatch: frontmatter={frontmatter['profile']!r} expected={profile_result['profile']!r}"
        )
    if frontmatter["author"] != profile_result["wechat_author"]:
        raise ValueError(
            f"publish.md author mismatch: frontmatter={frontmatter['author']!r} expected={profile_result['wechat_author']!r}"
        )
    if frontmatter["theme"] != "sspai":
        raise ValueError(f"publish.md theme must be 'sspai', got: {frontmatter['theme']!r}")
    return frontmatter


def validate_profile(config_path: Path, profile: str) -> Tuple[Dict[str, Any], Dict[str, Any], Path]:
    article_workspace = config_path.parent.resolve()
    config = load_json(config_path)
    profiles_path_raw = config.get("profiles_path")
    if not isinstance(profiles_path_raw, str) or not profiles_path_raw.strip():
        raise ValueError("config.json missing profiles_path")

    profiles_path = resolve_config_path(profiles_path_raw, config_path.parent)
    profiles_doc = load_json(profiles_path)
    profiles = profiles_doc.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError(f"profiles.json missing top-level profiles object: {profiles_path}")

    if not profile or profile not in profiles:
        raise KeyError(f"unknown profile: {profile}")

    profile_doc = profiles[profile]
    if not isinstance(profile_doc, dict):
        raise ValueError(f"profile entry is not an object: {profile}")

    publisher = profile_doc.get("publisher")
    if not isinstance(publisher, dict):
        raise ValueError(f"profile {profile!r} missing publisher block")

    wechat_author = profile_doc.get("wechat_author")
    if not isinstance(wechat_author, str) or not wechat_author.strip():
        raise ValueError(f"profile {profile!r} missing explicit wechat_author")

    published_log_path = profile_doc.get("published_log_path")
    if not isinstance(published_log_path, str) or not published_log_path.strip():
        raise ValueError(f"profile {profile!r} missing explicit published_log_path")
    published_log_resolved = resolve_config_path(published_log_path, profiles_path.parent)
    if not published_log_resolved.is_absolute():
        raise ValueError(f"profile {profile!r} published_log_path must resolve to an absolute path")
    ensure_within(published_log_resolved, article_workspace, "published_log_path")

    default_theme = profile_doc.get("default_theme")
    if default_theme != "sspai":
        raise ValueError(f"profile {profile!r} must explicitly set default_theme='sspai'")

    mcp_config_raw = publisher.get("mcp_config_file")
    if not isinstance(mcp_config_raw, str) or not mcp_config_raw.strip():
        raise ValueError(f"profile {profile!r} missing publisher.mcp_config_file")

    mcp_config_path = resolve_config_path(mcp_config_raw, profiles_path.parent)
    ensure_within(mcp_config_path, article_workspace, "publisher.mcp_config_file")
    if not mcp_config_path.exists() or not mcp_config_path.is_file():
        raise FileNotFoundError(f"mcp_config_file not found: {mcp_config_path}")
    if not os.access(mcp_config_path, os.R_OK):
        raise PermissionError(f"mcp_config_file not readable: {mcp_config_path}")

    mcp_doc = load_json(mcp_config_path)
    servers = mcp_doc.get("mcpServers")
    mcp_server = publisher.get("mcp_server") or "wenyan-mcp"
    if not isinstance(mcp_server, str) or not mcp_server.strip():
        raise ValueError(f"profile {profile!r} has invalid publisher.mcp_server")
    if not isinstance(servers, dict) or mcp_server not in servers:
        raise ValueError(f"mcp config missing {mcp_server}: {mcp_config_path}")

    result = {
        "profile": profile,
        "wechat_author": wechat_author,
        "published_log_path": str(published_log_resolved),
        "default_theme": default_theme,
        "publisher_mode": publisher.get("mode"),
        "mcp_server": mcp_server,
        "mcp_config_file": str(mcp_config_path),
        "checked_at": iso_now(),
        "wenyan_mcp_present": True,
    }
    return result, config, profiles_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate explicit publish profile and resolve wenyan MCP config")
    ap.add_argument("--config-path", help="Optional explicit config.json path; if omitted, infer from state-path/publish-md")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--state-path", help="Optional pipeline-state.json to persist/validate the effective profile/config path")
    ap.add_argument("--publish-md", help="Optional publish.md to validate frontmatter profile/author contract")
    return ap.parse_args()


def infer_config_path(args: argparse.Namespace) -> Path:
    candidates = []
    if args.config_path:
        candidates.append(Path(args.config_path).expanduser().resolve())
    if args.state_path:
        state_path = Path(args.state_path).expanduser().resolve()
        candidates.append(state_path.parent.parent / "config.json")
    if args.publish_md:
        publish_md = Path(args.publish_md).expanduser().resolve()
        candidates.append(publish_md.parent.parent / "config.json")

    seen = []
    for candidate in candidates:
        if candidate not in seen:
            seen.append(candidate)
    for candidate in seen:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError("unable to infer config.json from --config-path / --state-path / --publish-md; refusing implicit workspace fallback")


def main() -> int:
    args = parse_args()
    config_path = infer_config_path(args)

    try:
        result, _, _ = validate_profile(config_path, args.profile)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "profile": args.profile,
                    "config_path": str(config_path),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    frontmatter: Optional[Dict[str, Any]] = None
    if args.publish_md:
        try:
            frontmatter = validate_publish_frontmatter(Path(args.publish_md).expanduser().resolve(), result)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(exc),
                        "publish_md": str(Path(args.publish_md).expanduser().resolve()),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2

    if args.state_path:
        state_path = Path(args.state_path).expanduser().resolve()
        try:
            state = load_json(state_path) if state_path.exists() else {}
            existing_profile = state.get("profile")
            if existing_profile not in (None, "", result["profile"]):
                raise ValueError(
                    f"pipeline-state profile mismatch: state={existing_profile!r} expected={result['profile']!r}"
                )
            state["profile"] = result["profile"]
            state["published_log_path"] = result["published_log_path"]
            state["mcp_config_file"] = result["mcp_config_file"]
            state["mcp_server"] = result["mcp_server"]
            state["publisher_mode"] = result["publisher_mode"]
            state["wechat_author"] = result["wechat_author"]
            state["publish_profile_preflight"] = {
                "status": "ok",
                **result,
                "publish_md_checked": bool(frontmatter),
            }
            state["updated_at"] = iso_now()
            atomic_write_json(state_path, state)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"failed to write state: {exc}",
                        "state_path": str(state_path),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 1

    payload = {"ok": True, **result}
    if frontmatter is not None:
        payload["publish_frontmatter_checked"] = True
        payload["publish_frontmatter_profile"] = frontmatter.get("profile")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
