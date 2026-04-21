#!/usr/bin/env python3
"""Search the local predictive knowledge base."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from local_kb.search import format_search_output, render_search_payload, search_entries
from local_kb.store import resolve_repo_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--query", required=True)
    parser.add_argument("--path-hint", "--route-hint", dest="path_hint", default="")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    entries = search_entries(repo_root, query=args.query, path_hint=args.path_hint, top_k=args.top_k)
    payload = render_search_payload(entries, repo_root)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(format_search_output(payload, path_hint=args.path_hint))


if __name__ == "__main__":
    main()
