#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Dict, List, Optional

REGISTRY_DEFAULT = str(pathlib.Path(__file__).resolve().parent.parent / 'references' / 'browser-use-agent-profiles.json')


def ps_lines() -> List[str]:
    out = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,args='], text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def load_registry(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def parse_daemons(lines: List[str]) -> Dict[int, dict]:
    daemons = {}
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, args = int(parts[0]), int(parts[1]), parts[2]
        m = re.search(r'browser_use\.skill_cli\.daemon --session ([^ ]+)', args)
        if m:
            daemons[pid] = {'pid': pid, 'ppid': ppid, 'session': m.group(1), 'args': args}
    return daemons


def build_parent_map(lines: List[str]) -> Dict[int, int]:
    parent_map = {}
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        pid, ppid = int(parts[0]), int(parts[1])
        parent_map[pid] = ppid
    return parent_map


def find_owner_session(pid: int, parent_map: Dict[int, int], daemons: Dict[int, dict]) -> Optional[str]:
    seen = set()
    cur = pid
    while cur and cur not in seen:
        seen.add(cur)
        if cur in daemons:
            return daemons[cur]['session']
        cur = parent_map.get(cur)
    return None


def extract_user_data_dir(args: str) -> Optional[str]:
    m = re.search(r'--user-data-dir=([^ ]+)', args)
    return m.group(1) if m else None


def parse_browsers(lines: List[str], daemons: Dict[int, dict], parent_map: Dict[int, int]) -> List[dict]:
    browsers = []
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, args = int(parts[0]), int(parts[1]), parts[2]
        if 'chrome-linux64/chrome' not in args and 'chromium' not in args:
            continue
        user_data_dir = extract_user_data_dir(args)
        owner_session = find_owner_session(pid, parent_map, daemons)
        browsers.append({
            'pid': pid,
            'ppid': ppid,
            'owner_session': owner_session,
            'user_data_dir': user_data_dir,
            'args': args,
        })
    return browsers


def session_sockets() -> List[dict]:
    root = pathlib.Path('/root/.browser-use')
    rows = []
    if not root.exists():
        return rows
    for pid_file in root.glob('*.pid'):
        try:
            pid = int(pid_file.read_text().strip())
        except Exception:
            pid = None
        rows.append({'session': pid_file.stem, 'pid': pid, 'pid_file': str(pid_file)})
    return rows


def singleton_info(target_dir: str) -> dict:
    p = pathlib.Path(target_dir)
    info = {}
    for name in ['SingletonLock', 'SingletonSocket', 'SingletonCookie', 'DevToolsActivePort']:
        fp = p / name
        info[name] = {'exists': fp.exists(), 'path': str(fp)}
        if fp.exists() and fp.is_symlink():
            try:
                info[name]['target'] = os.readlink(fp)
            except OSError:
                pass
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description='Fail-closed guard for agent-bound browser-use profiles.')
    ap.add_argument('--agent', required=True)
    ap.add_argument('--registry', default=REGISTRY_DEFAULT)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    reg = load_registry(args.registry)
    entry = (reg.get('agents') or {}).get(args.agent)
    if not entry:
        print(json.dumps({'ok': False, 'error': f'agent {args.agent!r} not found in registry'}))
        return 2

    expected_session = entry['session']
    target_dir = entry['user_data_dir']
    lines = ps_lines()
    daemons = parse_daemons(lines)
    parent_map = build_parent_map(lines)
    browsers = parse_browsers(lines, daemons, parent_map)
    sockets = session_sockets()
    singleton = singleton_info(target_dir)

    target_dir_holders = [b for b in browsers if b['user_data_dir'] == target_dir]
    conflicting_sessions = sorted({b['owner_session'] for b in target_dir_holders if b['owner_session'] and b['owner_session'] != expected_session})
    orphan_holders = [b for b in target_dir_holders if not b['owner_session']]
    expected_session_holders = [b for b in browsers if b['owner_session'] == expected_session]
    session_dir_mismatch = [b for b in expected_session_holders if b['user_data_dir'] and b['user_data_dir'] != target_dir]
    ok = not conflicting_sessions and not orphan_holders and not session_dir_mismatch

    report = {
        'ok': ok,
        'agent': args.agent,
        'expected_session': expected_session,
        'user_data_dir': target_dir,
        'conflicting_sessions': conflicting_sessions,
        'orphan_holders': orphan_holders,
        'target_dir_holders': target_dir_holders,
        'expected_session_holders': expected_session_holders,
        'session_dir_mismatch': session_dir_mismatch,
        'browsers': browsers,
        'daemons': list(daemons.values()),
        'sockets': sockets,
        'singleton': singleton,
        'hint': None if ok else 'Profile/session mismatch detected. Stop conflicting browser-use daemons or restart the session through the agent wrapper before continuing.'
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
