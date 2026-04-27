from __future__ import annotations

from datetime import datetime, timezone
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from local_kb.store import load_yaml_file


ORG_KB_MANIFEST = "khaos_org_kb.yaml"
ORG_KB_KIND = "khaos-organization-kb"
SUPPORTED_SCHEMA_VERSION = 1
ORG_MAIN_ACTIVE_STATUSES = {"trusted", "candidate"}
ORG_TARGET_LAYOUT = "main-imports"
ORG_LEGACY_LAYOUT = "legacy-trusted-candidates"
ORG_RECOMMENDED_MAIN_PATH = "kb/main"
ORG_RECOMMENDED_IMPORTS_PATH = "kb/imports"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_relative_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return ""
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def _yaml_status_counts(path: Path) -> tuple[int, dict[str, int]]:
    if not path.exists():
        return 0, {}
    total = 0
    status_counts: dict[str, int] = {}
    for card_path in path.rglob("*.yaml"):
        total += 1
        try:
            card = load_yaml_file(card_path)
        except Exception:
            continue
        if not isinstance(card, dict):
            continue
        status = str(card.get("status") or "").strip().lower()
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
    return total, status_counts


def _git_executable() -> str:
    discovered = shutil.which("git") or shutil.which("git.cmd")
    if discovered:
        return discovered
    bundled = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin" / "git.cmd"
    if bundled.exists():
        return str(bundled)
    return "git"


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [_git_executable(), *args],
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(args=[_git_executable(), *args], returncode=127, stdout="", stderr=str(exc))


def current_git_commit(repo_path: Path) -> str:
    result = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def default_org_mirror_path(repo_root: Path, organization_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", organization_id.strip()).strip("-")
    if not safe_id:
        safe_id = "org"
    return repo_root / ".local" / "organization_sources" / safe_id


def guess_organization_source_id(repo_url: str) -> str:
    text = str(repo_url or "").strip().replace("\\", "/")
    if not text:
        return "org"
    text = text.rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    candidate = text.rsplit("/", 1)[-1].strip()
    if ":" in candidate:
        candidate = candidate.rsplit(":", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", candidate).strip("-") or "org"


def clone_or_fetch_organization_repo(repo_url: str, local_path: Path) -> dict[str, Any]:
    repo_url = str(repo_url or "").strip()
    if not repo_url:
        return {"ok": False, "action": "none", "errors": ["missing repository URL"], "commit": ""}

    local_path = Path(local_path)
    if (local_path / ".git").exists():
        result = _run_git(["fetch", "--prune"], cwd=local_path)
        if result.returncode != 0:
            return {
                "ok": False,
                "action": "fetch",
                "errors": [result.stderr.strip() or result.stdout.strip()],
                "commit": current_git_commit(local_path),
            }
        update = _run_git(["pull", "--ff-only"], cwd=local_path)
        return {
            "ok": update.returncode == 0,
            "action": "fetch",
            "errors": [] if update.returncode == 0 else [update.stderr.strip() or update.stdout.strip()],
            "commit": current_git_commit(local_path),
        }

    if local_path.exists() and any(local_path.iterdir()):
        return {
            "ok": False,
            "action": "none",
            "errors": [f"local mirror path is not an empty directory: {local_path}"],
            "commit": "",
        }

    local_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(["clone", repo_url, str(local_path)])
    return {
        "ok": result.returncode == 0,
        "action": "clone",
        "errors": [] if result.returncode == 0 else [result.stderr.strip() or result.stdout.strip()],
        "commit": current_git_commit(local_path) if result.returncode == 0 else "",
    }


def connect_organization_source(
    repo_root: Path,
    repo_url: str,
    *,
    local_mirror_path: str | Path | None = None,
) -> dict[str, Any]:
    repo_url = str(repo_url or "").strip()
    now = utc_timestamp()
    if local_mirror_path:
        mirror_path = Path(local_mirror_path)
    else:
        mirror_path = default_org_mirror_path(Path(repo_root), guess_organization_source_id(repo_url))

    if not repo_url:
        settings = {
            "repo_url": "",
            "local_mirror_path": str(mirror_path),
            "organization_id": "",
            "validated": False,
            "validation_status": "not_configured",
            "validation_message": "Organization repository URL is required.",
            "last_validated_at": now,
            "last_sync_commit": "",
            "last_sync_at": "",
        }
        return {"ok": False, "settings": settings, "clone": {}, "validation": {}}

    clone_result = clone_or_fetch_organization_repo(repo_url, mirror_path)
    if not clone_result.get("ok"):
        settings = {
            "repo_url": repo_url,
            "local_mirror_path": str(mirror_path),
            "organization_id": "",
            "validated": False,
            "validation_status": "invalid",
            "validation_message": "; ".join(clone_result.get("errors") or ["Failed to clone or fetch organization repository."]),
            "last_validated_at": now,
            "last_sync_commit": "",
            "last_sync_at": "",
        }
        return {"ok": False, "settings": settings, "clone": clone_result, "validation": {}}

    validation = validate_organization_repo(mirror_path)
    validation_ok = bool(validation.get("ok"))
    errors = validation.get("errors") or []
    commit = str(validation.get("commit") or clone_result.get("commit") or "")
    settings = {
        "repo_url": repo_url,
        "local_mirror_path": str(mirror_path),
        "organization_id": str(validation.get("organization_id") or ""),
        "validated": validation_ok,
        "validation_status": "valid" if validation_ok else "invalid",
        "validation_message": "Organization KB repository is valid." if validation_ok else "; ".join(errors),
        "last_validated_at": now,
        "last_sync_commit": commit if validation_ok else "",
        "last_sync_at": now if validation_ok else "",
    }
    return {"ok": validation_ok, "settings": settings, "clone": clone_result, "validation": validation}


def validate_organization_repo(repo_path: Path) -> dict[str, Any]:
    repo_path = Path(repo_path)
    errors: list[str] = []
    manifest_path = repo_path / ORG_KB_MANIFEST

    if not repo_path.exists() or not repo_path.is_dir():
        return {
            "ok": False,
            "errors": [f"repository path does not exist: {repo_path}"],
            "repo_path": str(repo_path),
        }

    if not manifest_path.exists():
        return {
            "ok": False,
            "errors": [f"missing organization KB manifest: {ORG_KB_MANIFEST}"],
            "repo_path": str(repo_path),
        }

    try:
        manifest = load_yaml_file(manifest_path)
    except Exception as exc:  # pragma: no cover - defensive around malformed YAML parser errors
        return {
            "ok": False,
            "errors": [f"failed to read organization KB manifest: {exc}"],
            "repo_path": str(repo_path),
        }

    if not isinstance(manifest, dict):
        manifest = {}
        errors.append("manifest must be a mapping")

    if manifest.get("kind") != ORG_KB_KIND:
        errors.append(f"manifest kind must be {ORG_KB_KIND}")

    if manifest.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SUPPORTED_SCHEMA_VERSION}")

    organization_id = str(manifest.get("organization_id") or "").strip()
    if not organization_id:
        errors.append("organization_id is required")

    kb = manifest.get("kb") if isinstance(manifest.get("kb"), dict) else {}
    skills = manifest.get("skills") if isinstance(manifest.get("skills"), dict) else {}

    main_path_text = _as_relative_path(kb.get("main_path") or "")
    trusted_path_text = _as_relative_path(kb.get("trusted_path") or "kb/trusted")
    candidates_path_text = _as_relative_path(kb.get("candidates_path") or "kb/candidates")
    imports_path_text = _as_relative_path(kb.get("imports_path") or "kb/imports")
    registry_path_text = _as_relative_path(skills.get("registry_path") or "skills/registry.yaml")
    skill_candidates_path_text = _as_relative_path(skills.get("candidates_path") or "skills/candidates")

    if not main_path_text and (repo_path / "kb" / "main").exists():
        main_path_text = "kb/main"

    required_dirs = {"main_path": main_path_text} if main_path_text else {
        "trusted_path": trusted_path_text,
        "candidates_path": candidates_path_text,
    }
    for label, relative in required_dirs.items():
        if not relative:
            errors.append(f"{label} must be a relative path")
            continue
        if not (repo_path / relative).is_dir():
            errors.append(f"{label} does not exist or is not a directory: {relative}")

    optional_dirs = {
        "imports_path": imports_path_text,
        "skill_candidates_path": skill_candidates_path_text,
    }
    for label, relative in optional_dirs.items():
        if relative and not (repo_path / relative).exists():
            errors.append(f"{label} does not exist: {relative}")

    registry_skills: list[Any] = []
    if registry_path_text:
        registry_path = repo_path / registry_path_text
        if registry_path.exists():
            registry_payload = load_yaml_file(registry_path)
            if isinstance(registry_payload, dict) and isinstance(registry_payload.get("skills"), list):
                registry_skills = registry_payload["skills"]
            else:
                errors.append("skills registry must contain a skills list")
        else:
            errors.append(f"skills registry does not exist: {registry_path_text}")

    layout = ORG_TARGET_LAYOUT if main_path_text else ORG_LEGACY_LAYOUT
    legacy_compatibility = layout == ORG_LEGACY_LAYOUT
    legacy_paths = [path for path in (trusted_path_text, candidates_path_text) if path]

    main_count = 0
    main_active_count = 0
    trusted_count = 0
    candidate_count = 0
    main_status_counts: dict[str, int] = {}
    imports_count = 0
    imports_status_counts: dict[str, int] = {}
    legacy_trusted_count = 0
    legacy_candidate_count = 0
    legacy_status_counts: dict[str, int] = {}

    if main_path_text and (repo_path / main_path_text).exists():
        main_count, main_status_counts = _yaml_status_counts(repo_path / main_path_text)
        main_active_count = sum(main_status_counts.get(status, 0) for status in ORG_MAIN_ACTIVE_STATUSES)
        trusted_count = main_status_counts.get("trusted", 0) + main_status_counts.get("approved", 0)
        candidate_count = main_status_counts.get("candidate", 0)
    else:
        legacy_trusted_count, trusted_status_counts = (
            _yaml_status_counts(repo_path / trusted_path_text) if trusted_path_text else (0, {})
        )
        legacy_candidate_count, candidate_status_counts = (
            _yaml_status_counts(repo_path / candidates_path_text) if candidates_path_text else (0, {})
        )
        trusted_count = legacy_trusted_count
        candidate_count = legacy_candidate_count
        main_active_count = trusted_count + candidate_count
        for status_counts in (trusted_status_counts, candidate_status_counts):
            for status, count in status_counts.items():
                legacy_status_counts[status] = legacy_status_counts.get(status, 0) + count

    if imports_path_text:
        imports_count, imports_status_counts = _yaml_status_counts(repo_path / imports_path_text)

    local_download_paths = [main_path_text] if main_path_text else legacy_paths
    layout_message = (
        "Organization repository uses the recommended kb/imports incoming lane and kb/main exchange surface."
        if not legacy_compatibility
        else (
            "Legacy kb/trusted and kb/candidates are accepted for compatibility only; "
            "the recommended organization layout is kb/imports for incoming proposals and kb/main for the exchange surface."
        )
    )

    return {
        "ok": not errors,
        "errors": errors,
        "repo_path": str(repo_path),
        "manifest_path": str(manifest_path),
        "organization_id": organization_id,
        "schema_version": manifest.get("schema_version"),
        "layout": layout,
        "target_layout": ORG_TARGET_LAYOUT,
        "legacy_compatibility": legacy_compatibility,
        "layout_message": layout_message,
        "incoming_lane_path": imports_path_text or ORG_RECOMMENDED_IMPORTS_PATH,
        "exchange_surface_path": main_path_text or ORG_RECOMMENDED_MAIN_PATH,
        "legacy_paths": legacy_paths,
        "local_download_primary_path": main_path_text or ORG_RECOMMENDED_MAIN_PATH,
        "local_download_paths": local_download_paths,
        "local_download_excluded_paths": [imports_path_text] if imports_path_text else [ORG_RECOMMENDED_IMPORTS_PATH],
        "main_path": main_path_text,
        "trusted_path": trusted_path_text,
        "candidates_path": candidates_path_text,
        "imports_path": imports_path_text,
        "skills_registry_path": registry_path_text,
        "skill_candidates_path": skill_candidates_path_text,
        "main_count": main_count,
        "main_active_count": main_active_count,
        "main_status_counts": main_status_counts,
        "imports_count": imports_count,
        "imports_status_counts": imports_status_counts,
        "legacy_trusted_count": legacy_trusted_count,
        "legacy_candidate_count": legacy_candidate_count,
        "legacy_status_counts": legacy_status_counts,
        "trusted_count": trusted_count,
        "candidate_count": candidate_count,
        "skill_count": len(registry_skills),
        "commit": current_git_commit(repo_path),
    }
