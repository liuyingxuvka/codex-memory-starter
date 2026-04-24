#!/usr/bin/env python3
"""Open the human-facing Khaos Brain desktop card browser."""

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


def _pythonw_executable() -> Path:
    executable = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return executable


def _exe_candidates(repo_root: Path) -> list[Path]:
    return [
        repo_root / "dist" / "KhaosBrain.exe",
        repo_root / "dist" / "KhaosBrain" / "KhaosBrain.exe",
        repo_root / "KhaosBrain.exe",
    ]


def _launch_command(repo_root: Path, *, prefer_python: bool, language: str) -> tuple[str, list[str]]:
    if not prefer_python:
        for exe_path in _exe_candidates(repo_root):
            if exe_path.exists():
                command = [str(exe_path), "--repo-root", str(repo_root)]
                if language:
                    command.extend(["--language", language])
                return "exe", command

    command = [
        str(_pythonw_executable()),
        str(repo_root / "scripts" / "kb_desktop.py"),
        "--repo-root",
        str(repo_root),
    ]
    if language:
        command.extend(["--language", language])
    return "python", command


def open_ui(repo_root: Path, *, prefer_python: bool = False, language: str = "") -> dict[str, Any]:
    mode, command = _launch_command(repo_root, prefer_python=prefer_python, language=language)
    process = subprocess.Popen(command, cwd=str(repo_root), close_fds=True)
    return {
        "ok": True,
        "mode": mode,
        "pid": process.pid,
        "command": command,
        "repo_root": str(repo_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Open Khaos Brain's desktop card browser.")
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--language", default="", choices=["", "en", "zh-CN"])
    parser.add_argument("--prefer-python", action="store_true", help="Ignore a built exe and open through Python.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root, cwd=SCRIPT_REPO_ROOT)
    payload = open_ui(repo_root, prefer_python=args.prefer_python, language=args.language)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Opened Khaos Brain desktop UI with {payload['mode']} launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
