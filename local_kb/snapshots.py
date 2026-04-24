from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local_kb.consolidate import consolidation_run_dir, sanitize_run_id
from local_kb.store import history_events_path, write_yaml_file


SCHEMA_VERSION = 1
SNAPSHOT_FILENAME = "snapshot.json"
PROPOSAL_FILENAME = "proposal.json"
APPLY_FILENAME = "apply.json"
MANIFEST_FILENAME = "rollback_manifest.json"
ROLLBACK_MANIFEST_KIND = "local-kb-rollback-manifest"
SUPPORTED_RESTORE_ARTIFACTS = ("history-events", "semantic-review-entries")


def relative_repo_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_run_dir(
    repo_root: Path,
    *,
    run_id: str | None = None,
    run_dir: str | Path | None = None,
) -> Path:
    if bool(run_id) == bool(run_dir):
        raise ValueError("Provide exactly one of run_id or run_dir.")
    if run_id:
        return consolidation_run_dir(repo_root, sanitize_run_id(run_id))
    path = Path(run_dir) if run_dir is not None else repo_root
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _build_snapshot_artifact(
    repo_root: Path,
    run_dir: Path,
    snapshot_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot_path = run_dir / SNAPSHOT_FILENAME
    event_count = 0
    if snapshot_payload and isinstance(snapshot_payload.get("events"), list):
        event_count = len(snapshot_payload["events"])
    return {
        "artifact_id": "snapshot",
        "kind": "consolidation-snapshot",
        "path": relative_repo_path(repo_root, snapshot_path),
        "exists": snapshot_path.exists(),
        "low_risk": True,
        "restorable": False,
        "details": {
            "event_count": event_count,
            "history_path": str(snapshot_payload.get("history_path", "") or "") if snapshot_payload else "",
        },
    }


def _build_proposal_artifact(
    repo_root: Path,
    run_dir: Path,
    proposal_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    proposal_path = run_dir / PROPOSAL_FILENAME
    candidate_action_count = 0
    if proposal_payload:
        candidate_action_count = int(proposal_payload.get("candidate_action_count", 0) or 0)
    return {
        "artifact_id": "proposal",
        "kind": "consolidation-proposal",
        "path": relative_repo_path(repo_root, proposal_path),
        "exists": proposal_path.exists(),
        "low_risk": True,
        "restorable": False,
        "details": {
            "candidate_action_count": candidate_action_count,
        },
    }


def _build_history_events_artifact(
    repo_root: Path,
    run_dir: Path,
    snapshot_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot_path = run_dir / SNAPSHOT_FILENAME
    default_history_path = relative_repo_path(repo_root, history_events_path(repo_root))
    history_path_value = default_history_path
    event_count = 0
    restorable = False
    if snapshot_payload:
        history_path_value = str(snapshot_payload.get("history_path", "") or default_history_path)
        raw_events = snapshot_payload.get("events")
        if isinstance(raw_events, list):
            event_count = len(raw_events)
            restorable = True

    target_path = resolve_repo_path(repo_root, history_path_value)
    return {
        "artifact_id": "history-events",
        "kind": "jsonl-history",
        "path": history_path_value,
        "exists": target_path.exists(),
        "low_risk": True,
        "restorable": restorable,
        "restore_strategy": "rewrite-jsonl-from-snapshot-events" if restorable else "",
        "source_path": relative_repo_path(repo_root, snapshot_path),
        "details": {
            "event_count": event_count,
        },
    }


def _semantic_review_restore_entries(apply_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not apply_payload or apply_payload.get("apply_mode") != "semantic-review":
        return []
    entries: list[dict[str, Any]] = []
    for item in apply_payload.get("updated_entries", []):
        if not isinstance(item, dict):
            continue
        previous_entry = item.get("previous_entry")
        previous_entry_path = str(item.get("previous_entry_path", "") or "").strip()
        updated_entry_path = str(item.get("entry_path", "") or "").strip()
        if isinstance(previous_entry, dict) and previous_entry_path:
            entries.append(
                {
                    "entry_id": str(item.get("entry_id", "") or "").strip(),
                    "previous_entry_path": previous_entry_path,
                    "updated_entry_path": updated_entry_path,
                    "previous_entry": previous_entry,
                }
            )
    return entries


def _build_semantic_review_entries_artifact(
    repo_root: Path,
    run_dir: Path,
    apply_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    entries = _semantic_review_restore_entries(apply_payload)
    if not apply_payload and not (run_dir / APPLY_FILENAME).exists():
        return None
    if not entries:
        return None
    return {
        "artifact_id": "semantic-review-entries",
        "kind": "semantic-review-entry-files",
        "path": "<multiple-entry-files>",
        "exists": True,
        "low_risk": False,
        "restorable": True,
        "restore_strategy": "rewrite-entry-files-from-apply-previous-entry-payloads",
        "source_path": relative_repo_path(repo_root, run_dir / APPLY_FILENAME),
        "details": {
            "entry_count": len(entries),
            "entry_ids": [entry["entry_id"] for entry in entries if entry.get("entry_id")],
        },
    }


def build_rollback_manifest(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    snapshot_payload = load_json_object(run_dir / SNAPSHOT_FILENAME)
    proposal_payload = load_json_object(run_dir / PROPOSAL_FILENAME)
    apply_payload = load_json_object(run_dir / APPLY_FILENAME)
    run_id = str(
        (snapshot_payload or {}).get("run_id")
        or (proposal_payload or {}).get("run_id")
        or run_dir.name
    )
    generated_at = str(
        (proposal_payload or {}).get("generated_at")
        or (snapshot_payload or {}).get("generated_at")
        or ""
    )

    artifacts = [
        _build_snapshot_artifact(repo_root, run_dir, snapshot_payload),
        _build_proposal_artifact(repo_root, run_dir, proposal_payload),
        _build_history_events_artifact(repo_root, run_dir, snapshot_payload),
    ]
    semantic_review_artifact = _build_semantic_review_entries_artifact(repo_root, run_dir, apply_payload)
    if semantic_review_artifact:
        artifacts.append(semantic_review_artifact)
    restorable_ids = [artifact["artifact_id"] for artifact in artifacts if artifact["restorable"]]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ROLLBACK_MANIFEST_KIND,
        "run_id": run_id,
        "generated_at": generated_at,
        "run_dir": relative_repo_path(repo_root, run_dir),
        "artifact_count": len(artifacts),
        "restorable_artifact_count": len(restorable_ids),
        "restorable_artifact_ids": restorable_ids,
        "artifacts": artifacts,
    }


def manifest_path(run_dir: Path) -> Path:
    return run_dir / MANIFEST_FILENAME


def write_rollback_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    path = manifest_path(run_dir)
    write_json_object(path, manifest)
    return path


def find_artifact(manifest: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_id") == artifact_id:
            return artifact
    raise ValueError(f"Unknown artifact_id: {artifact_id}")


def restore_artifact(
    repo_root: Path,
    manifest: dict[str, Any],
    artifact_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if artifact_id not in SUPPORTED_RESTORE_ARTIFACTS:
        raise ValueError(f"Unsupported artifact_id: {artifact_id}")

    artifact = find_artifact(manifest, artifact_id)
    if not artifact.get("restorable"):
        raise ValueError(f"Artifact {artifact_id} is not restorable for this run.")

    if artifact_id == "semantic-review-entries":
        return restore_semantic_review_entries(repo_root, manifest, artifact, dry_run=dry_run)

    source_path = resolve_repo_path(repo_root, str(artifact.get("source_path", "") or ""))
    snapshot_payload = load_json_object(source_path)
    if not snapshot_payload:
        raise ValueError(f"Missing snapshot payload for {artifact_id} restore: {source_path}")

    events = snapshot_payload.get("events")
    if not isinstance(events, list):
        raise ValueError(f"Snapshot payload does not contain an events list: {source_path}")

    target_path = resolve_repo_path(repo_root, str(artifact.get("path", "") or ""))
    result = {
        "run_id": str(manifest.get("run_id", "") or ""),
        "artifact_id": artifact_id,
        "target_path": relative_repo_path(repo_root, target_path),
        "source_path": relative_repo_path(repo_root, source_path),
        "event_count": len(events),
        "dry_run": dry_run,
        "restored": False,
    }

    if dry_run:
        return result

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    result["restored"] = True
    return result


def _path_within_repo(repo_root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
        return True
    except ValueError:
        return False


def restore_semantic_review_entries(
    repo_root: Path,
    manifest: dict[str, Any],
    artifact: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    source_path = resolve_repo_path(repo_root, str(artifact.get("source_path", "") or ""))
    apply_payload = load_json_object(source_path)
    if not apply_payload:
        raise ValueError(f"Missing apply payload for semantic-review restore: {source_path}")
    entries = _semantic_review_restore_entries(apply_payload)
    if not entries:
        raise ValueError(f"Apply payload does not contain semantic-review previous entry payloads: {source_path}")

    restored_entries: list[dict[str, Any]] = []
    for entry in entries:
        previous_entry_path = resolve_repo_path(repo_root, str(entry["previous_entry_path"]))
        updated_entry_path = resolve_repo_path(repo_root, str(entry.get("updated_entry_path", "") or entry["previous_entry_path"]))
        if not _path_within_repo(repo_root, previous_entry_path):
            raise ValueError(f"Refusing to restore outside repository: {previous_entry_path}")
        if not _path_within_repo(repo_root, updated_entry_path):
            raise ValueError(f"Refusing to remove outside repository: {updated_entry_path}")
        restored_entries.append(
            {
                "entry_id": str(entry.get("entry_id", "") or ""),
                "previous_entry_path": relative_repo_path(repo_root, previous_entry_path),
                "updated_entry_path": relative_repo_path(repo_root, updated_entry_path),
            }
        )
        if dry_run:
            continue
        write_yaml_file(previous_entry_path, entry["previous_entry"])
        if updated_entry_path != previous_entry_path and updated_entry_path.exists():
            updated_entry_path.unlink()

    return {
        "run_id": str(manifest.get("run_id", "") or ""),
        "artifact_id": "semantic-review-entries",
        "source_path": relative_repo_path(repo_root, source_path),
        "entry_count": len(entries),
        "restored_entries": restored_entries,
        "dry_run": dry_run,
        "restored": not dry_run,
    }
