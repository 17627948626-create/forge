#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description='Minimal hard gate before final WeChat publish click')
    ap.add_argument('--article-title', required=True)
    ap.add_argument('--creative-source', required=True, choices=['ai_generated'])
    ap.add_argument('--original-state', required=True, choices=['text_original', 'original_timeout_continue'])
    ap.add_argument('--group-notify', required=True, choices=['on', 'off'])
    ap.add_argument('--scheduled', required=True, choices=['on', 'off'])
    ap.add_argument('--require-group-notify', choices=['on', 'off'])
    args = ap.parse_args()

    if args.require_group_notify and args.group_notify != args.require_group_notify:
        print(json.dumps({
            'ok': False,
            'error': f'group_notify mismatch: observed={args.group_notify} required={args.require_group_notify}',
        }, ensure_ascii=False), file=sys.stderr)
        return 2

    if not args.article_title.strip():
        print(json.dumps({'ok': False, 'error': 'article title is empty'}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({
        'ok': True,
        'article_title': args.article_title,
        'creative_source': args.creative_source,
        'original_state': args.original_state,
        'group_notify': args.group_notify,
        'scheduled': args.scheduled,
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
