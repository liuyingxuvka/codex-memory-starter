#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


KB_ROOT_ENV_VAR = "CODEX_PREDICTIVE_KB_ROOT"
INSTALL_STATE_SUBPATH = Path("predictive-kb") / "install.json"
REPO_MARKERS = (
    Path("AGENTS.md"),
    Path("PROJECT_SPEC.md"),
    Path("kb") / "taxonomy.yaml",
    Path(".agents") / "skills" / "local-kb-retrieve" / "SKILL.md",
)
SCRIPT_MAP = {
    "search": "kb_search.py",
    "taxonomy": "kb_taxonomy.py",
    "nav": "kb_nav.py",
    "feedback": "kb_feedback.py",
    "capture-candidate": "kb_capture_candidate.py",
    "consolidate": "kb_consolidate.py",
    "proposals": "kb_proposals.py",
    "rollback": "kb_rollback.py",
    "maintenance": "kb_maintenance.py",
}
SEARCH_FLAG_MARKERS = {"--query", "--path-hint", "--route-hint", "--top-k"}
SEARCH_ARG_ALIASES = {"--route-hint": "--path-hint"}


def codex_home() -> Path:
    return Path(__file__).resolve().parents[2]


def install_state_path() -> Path:
    return codex_home() / INSTALL_STATE_SUBPATH


def load_install_state() -> dict[str, Any]:
    path = install_state_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def is_repo_root(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return all((resolved / marker).exists() for marker in REPO_MARKERS)


def env_repo_root() -> Path | None:
    env_value = os.environ.get(KB_ROOT_ENV_VAR, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser().resolve()
        if is_repo_root(candidate):
            return candidate
    return None


def manifest_repo_root() -> Path | None:
    manifest = load_install_state()
    manifest_root = str(manifest.get("repo_root", "") or "").strip()
    if manifest_root:
        candidate = Path(manifest_root).expanduser().resolve()
        if is_repo_root(candidate):
            return candidate
    return None


def configured_repo_root() -> Path | None:
    return env_repo_root() or manifest_repo_root()


def discover_repo_root() -> Path | None:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if is_repo_root(candidate):
            return candidate
    return None


def resolve_repo_root() -> Path:
    for candidate in (env_repo_root(), discover_repo_root(), manifest_repo_root()):
        if candidate is not None:
            return candidate
    raise SystemExit(
        "Unable to resolve the predictive KB repo root. "
        "Run `python scripts/install_codex_kb.py --json` from a predictive KB clone "
        "or set CODEX_PREDICTIVE_KB_ROOT."
    )


def build_check_payload() -> dict[str, Any]:
    manifest = load_install_state()
    env_value = os.environ.get(KB_ROOT_ENV_VAR, "").strip()
    configured = configured_repo_root()
    discovered = discover_repo_root()
    launcher_path = Path(__file__).resolve()
    issues: list[str] = []

    if configured is None:
        issues.append("No valid configured KB root was found in CODEX_PREDICTIVE_KB_ROOT or the install manifest.")

    return {
        "ok": not issues,
        "launcher_path": str(launcher_path),
        "codex_home": str(codex_home()),
        "install_state_path": str(install_state_path()),
        "env_var_name": KB_ROOT_ENV_VAR,
        "env_var_value": env_value,
        "manifest_repo_root": str(manifest.get("repo_root", "") or ""),
        "resolved_repo_root": str(configured or ""),
        "discovered_workspace_repo_root": str(discovered or ""),
        "issues": issues,
    }


def normalize_launcher_args(argv: list[str]) -> list[str]:
    if not argv:
        return []
    if argv[0] in SCRIPT_MAP or argv[0] == "check":
        return list(argv)
    if any(token in SEARCH_FLAG_MARKERS for token in argv):
        return ["search", *argv]
    return list(argv)


def normalize_forwarded_args(command: str, args: list[str]) -> list[str]:
    if command != "search":
        return list(args)
    return [SEARCH_ARG_ALIASES.get(token, token) for token in args]


def main() -> int:
    argv = normalize_launcher_args(sys.argv[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=[*SCRIPT_MAP.keys(), "check"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)

    if parsed.command == "check":
        payload = build_check_payload()
        if "--json" in parsed.args:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for key in [
                "ok",
                "launcher_path",
                "codex_home",
                "install_state_path",
                "env_var_name",
                "env_var_value",
                "manifest_repo_root",
                "resolved_repo_root",
                "discovered_workspace_repo_root",
            ]:
                print(f"{key}: {payload[key]}")
            if payload["issues"]:
                print("issues:")
                for item in payload["issues"]:
                    print(f"- {item}")
        return 0 if payload["ok"] else 1

    repo_root = resolve_repo_root()
    script_path = repo_root / ".agents" / "skills" / "local-kb-retrieve" / "scripts" / SCRIPT_MAP[parsed.command]
    forwarded = [sys.executable, str(script_path)]
    normalized_args = normalize_forwarded_args(parsed.command, list(parsed.args))
    if "--repo-root" not in normalized_args:
        forwarded.extend(["--repo-root", str(repo_root)])
    forwarded.extend(normalized_args)
    completed = subprocess.run(forwarded)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
