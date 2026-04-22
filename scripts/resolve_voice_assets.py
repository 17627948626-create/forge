#!/usr/bin/env python3
"""Resolve OpenClaw voice assets with source-aware fallback rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def load_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def existing_file(path: Optional[Path]) -> Optional[Path]:
    if path and path.exists() and path.is_file():
        return path.resolve()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve voice-pack / voice-profile assets for an OpenClaw workspace.")
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--workspace-path", help="Workspace writer directory. Defaults to config parent.")
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()

    config_path = Path(args.config_path).expanduser().resolve()
    workspace_path = Path(args.workspace_path).expanduser().resolve() if args.workspace_path else config_path.parent
    repo_root = Path(__file__).resolve().parent.parent

    config = load_json(config_path)
    profiles_path = Path(str(config.get("profiles_path", workspace_path / "profiles.json"))).expanduser().resolve()
    profiles = load_json(profiles_path).get("profiles", {})
    profile = profiles.get(args.profile, {}) if isinstance(profiles, dict) else {}
    if not isinstance(profile, dict):
        profile = {}

    warnings: List[str] = []

    configured_pack = existing_file(Path(str(profile.get("voice_pack_path"))).expanduser()) if profile.get("voice_pack_path") else None
    configured_profile = existing_file(Path(str(profile.get("voice_profile_path"))).expanduser()) if profile.get("voice_profile_path") else None

    if profile.get("voice_pack_path") and not configured_pack:
        warnings.append("configured voice_pack_path missing; falling back")
    if profile.get("voice_profile_path") and not configured_profile:
        warnings.append("configured voice_profile_path missing; falling back")

    candidates: List[Tuple[str, str, Optional[Path]]] = [
        ("voice-pack", "profile", configured_pack),
        ("voice-profile", "profile", configured_profile),
        ("voice-pack", "workspace", existing_file(workspace_path / "voice-pack.json")),
        ("voice-profile", "workspace", existing_file(workspace_path / "voice-profile.json")),
        ("voice-pack", "default", existing_file(repo_root / "references" / "default-voice-pack.json")),
        ("voice-profile", "default", existing_file(repo_root / "references" / "default-voice-profile.json")),
    ]

    preferred_asset = None
    preferred_source = None
    preferred_path = None
    resolved_pack = None
    resolved_profile = None

    for asset, source, path in candidates:
        if path is None:
            continue
        if asset == "voice-pack" and resolved_pack is None:
            resolved_pack = str(path)
        if asset == "voice-profile" and resolved_profile is None:
            resolved_profile = str(path)
        if preferred_path is None:
            preferred_asset = asset
            preferred_source = source
            preferred_path = str(path)

    result = {
        "ok": preferred_path is not None,
        "profile": args.profile,
        "workspace_path": str(workspace_path),
        "preferred_asset": preferred_asset,
        "preferred_source": preferred_source,
        "preferred_path": preferred_path,
        "voice_pack_path": resolved_pack,
        "voice_profile_path": resolved_profile,
        "resolution_order": [
            "profile.voice_pack_path",
            "profile.voice_profile_path",
            "workspace/voice-pack.json",
            "workspace/voice-profile.json",
            "skill/references/default-voice-pack.json",
            "skill/references/default-voice-profile.json",
        ],
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if preferred_path else 1


if __name__ == "__main__":
    raise SystemExit(main())
