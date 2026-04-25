#!/usr/bin/env python3
"""Read or write local KB maintenance lane status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from local_kb.maintenance_lanes import build_lane_guard, read_lane_status, write_lane_status
from local_kb.store import resolve_repo_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--lane", required=True)
    parser.add_argument("--status", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--require-clear", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    guard = build_lane_guard(repo_root, args.lane) if args.require_clear else {}
    if args.require_clear and guard.get("blocked"):
        payload = {
            "lane": args.lane,
            "status": "blocked",
            "guard": guard,
        }
    elif args.status:
        payload = write_lane_status(
            repo_root,
            args.lane,
            args.status,
            run_id=args.run_id,
            note=args.note,
        )
        if guard:
            payload["guard"] = guard
    else:
        payload = read_lane_status(repo_root, args.lane)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"{args.lane}: {payload.get('status', 'missing')}")


if __name__ == "__main__":
    main()
