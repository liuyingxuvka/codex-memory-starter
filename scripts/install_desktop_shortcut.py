#!/usr/bin/env python3
"""Create or refresh a Windows desktop shortcut for Khaos Brain."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from local_kb.config import resolve_repo_root  # noqa: E402
from scripts.open_khaos_brain_ui import _exe_candidates, _pythonw_executable  # noqa: E402


DEFAULT_SHORTCUT_NAME = "Khaos Brain.lnk"


def _desktop_dir() -> Path:
    return Path.home() / "Desktop"


def _target_and_arguments(repo_root: Path, *, prefer_python: bool, language: str) -> tuple[Path, str]:
    if not prefer_python:
        for exe_path in _exe_candidates(repo_root):
            if exe_path.exists():
                args = [f'--repo-root "{repo_root}"']
                if language:
                    args.append(f'--language "{language}"')
                return exe_path, " ".join(args)

    args = [f'"{repo_root / "scripts" / "kb_desktop.py"}"', f'--repo-root "{repo_root}"']
    if language:
        args.append(f'--language "{language}"')
    return _pythonw_executable(), " ".join(args)


def create_shortcut(
    repo_root: Path,
    *,
    shortcut_name: str = DEFAULT_SHORTCUT_NAME,
    prefer_python: bool = False,
    language: str = "",
) -> dict[str, Any]:
    if sys.platform != "win32":
        raise SystemExit("Desktop shortcut installation is only supported on Windows.")

    shortcut_path = _desktop_dir() / shortcut_name
    target_path, arguments = _target_and_arguments(repo_root, prefer_python=prefer_python, language=language)
    icon_path = repo_root / "assets" / "khaos-brain.ico"
    icon_location = str(icon_path if icon_path.exists() else target_path)

    payload = {
        "shortcut_path": str(shortcut_path),
        "target_path": str(target_path),
        "arguments": arguments,
        "working_directory": str(repo_root),
        "icon_location": icon_location,
    }
    ps_payload = json.dumps(payload, ensure_ascii=False)
    script = f"""
$payload = @'
{ps_payload}
'@ | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($payload.shortcut_path)
$shortcut.TargetPath = $payload.target_path
$shortcut.Arguments = $payload.arguments
$shortcut.WorkingDirectory = $payload.working_directory
$shortcut.IconLocation = $payload.icon_location
$shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
    )
    payload["ok"] = shortcut_path.exists()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Windows desktop shortcut for Khaos Brain.")
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--name", default=DEFAULT_SHORTCUT_NAME)
    parser.add_argument("--language", default="", choices=["", "en", "zh-CN"])
    parser.add_argument("--prefer-python", action="store_true", help="Create a Python fallback shortcut even when exe exists.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root, cwd=SCRIPT_REPO_ROOT)
    payload = create_shortcut(repo_root, shortcut_name=args.name, prefer_python=args.prefer_python, language=args.language)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Created shortcut: {payload['shortcut_path']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
