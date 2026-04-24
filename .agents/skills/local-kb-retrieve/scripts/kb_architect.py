#!/usr/bin/env python3
"""Run one KB Architect mechanism-maintenance pass."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from local_kb.architect import run_architect_maintenance
from local_kb.store import resolve_repo_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--sleep-cooldown-minutes", type=int, default=60)
    parser.add_argument("--dream-cooldown-minutes", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    result = run_architect_maintenance(
        repo_root=repo_root,
        run_id=args.run_id or None,
        max_events=args.max_events or None,
        sleep_cooldown_minutes=max(0, args.sleep_cooldown_minutes),
        dream_cooldown_minutes=max(0, args.dream_cooldown_minutes),
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return

    print(
        f"Architect run {result['run_id']} finished with status={result['status']} "
        f"and {result.get('proposal_count', 0)} mechanism proposals."
    )
    if result["status"] == "skipped":
        print(f"Reason: {result['reason']}")
    print(f"Run dir: {result['artifact_paths']['run_dir']}")
    if result.get("history_event_ids"):
        print(f"History events: {', '.join(result['history_event_ids'])}")


if __name__ == "__main__":
    main()
