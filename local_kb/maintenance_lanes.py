from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local_kb.common import utc_now_iso


LANE_STATUS_DIR = Path("kb") / "history" / "lane-status"
CORE_MAINTENANCE_LANES = ("kb-sleep", "kb-dream", "kb-architect")


def lane_status_path(repo_root: Path, lane: str) -> Path:
    safe_lane = lane.strip().lower().replace("/", "-").replace("\\", "-")
    return repo_root / LANE_STATUS_DIR / f"{safe_lane}.json"


def read_lane_status(repo_root: Path, lane: str) -> dict[str, Any]:
    path = lane_status_path(repo_root, lane)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"lane": lane, "status": "unknown", "path": str(path)}
    return payload if isinstance(payload, dict) else {}


def write_lane_status(
    repo_root: Path,
    lane: str,
    status: str,
    *,
    run_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    path = lane_status_path(repo_root, lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "lane": lane,
        "status": status,
        "run_id": run_id,
        "note": note,
        "updated_at": utc_now_iso(),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    payload["path"] = str(path)
    return payload


def lane_is_running(repo_root: Path, lane: str) -> bool:
    status = str(read_lane_status(repo_root, lane).get("status", "") or "").lower()
    return status == "running"


def build_lane_guard(
    repo_root: Path,
    lane: str,
    *,
    lanes: tuple[str, ...] = CORE_MAINTENANCE_LANES,
) -> dict[str, Any]:
    statuses: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for other_lane in lanes:
        if other_lane == lane:
            continue
        payload = read_lane_status(repo_root, other_lane)
        statuses[other_lane] = payload
        if str(payload.get("status", "") or "").lower() == "running":
            blockers.append(other_lane)
    return {
        "lane": lane,
        "blocked": bool(blockers),
        "blocking_lanes": blockers,
        "statuses": statuses,
    }
