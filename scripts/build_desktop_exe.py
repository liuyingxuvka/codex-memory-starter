#!/usr/bin/env python3
"""Build the Windows desktop card viewer executable."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_REPO_ROOT))

from local_kb.config import resolve_repo_root  # noqa: E402


APP_NAME = "KhaosBrain"
ICON_SOURCE = Path("assets") / "khaos-brain-icon.png"
ICON_TARGET = Path("assets") / "khaos-brain.ico"


def _ensure_windows_icon(repo_root: Path) -> Path:
    source = repo_root / ICON_SOURCE
    target = repo_root / ICON_TARGET
    if not source.exists():
        raise FileNotFoundError(f"Missing icon source: {source}")

    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised by local environment.
        raise SystemExit("Missing dependency: Pillow is required to generate the Windows .ico file.") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGBA").save(
            target,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return target


def _pyinstaller_main() -> Any:
    try:
        import PyInstaller.__main__ as pyinstaller_main
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: PyInstaller. Install it with `python -m pip install --user pyinstaller`."
        ) from exc
    return pyinstaller_main


def build_exe(repo_root: Path) -> dict[str, Any]:
    icon_path = _ensure_windows_icon(repo_root)
    dist_dir = repo_root / "dist"
    work_dir = repo_root / "build" / "pyinstaller"
    spec_dir = work_dir / "spec"
    script_path = repo_root / "scripts" / "kb_desktop.py"
    asset_data = f"{repo_root / 'assets'}{os.pathsep}assets"

    pyinstaller_main = _pyinstaller_main()
    pyinstaller_main.run(
        [
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onefile",
            "--name",
            APP_NAME,
            "--icon",
            str(icon_path),
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(spec_dir),
            "--add-data",
            asset_data,
            str(script_path),
        ]
    )

    exe_path = dist_dir / f"{APP_NAME}.exe"
    return {
        "ok": exe_path.exists(),
        "app_name": APP_NAME,
        "exe_path": str(exe_path),
        "icon_path": str(icon_path),
        "dist_dir": str(dist_dir),
        "bundled_data": ["assets"],
        "kb_data_policy": "The executable bundles code and public UI assets only. It reads KB cards from --repo-root at runtime.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/KhaosBrain.exe for the desktop card viewer.")
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo_root = resolve_repo_root(args.repo_root, cwd=SCRIPT_REPO_ROOT)
    payload = build_exe(repo_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Built Khaos Brain desktop executable: {payload['exe_path']}")
        print(payload["kb_data_policy"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
