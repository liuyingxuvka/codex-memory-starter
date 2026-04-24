from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local_kb.i18n import DEFAULT_LANGUAGE, normalize_language


DEFAULT_DESKTOP_SETTINGS = {
    "language": DEFAULT_LANGUAGE,
}


def desktop_settings_path(repo_root: Path) -> Path:
    return repo_root / ".local" / "khaos_brain_desktop_settings.json"


def load_desktop_settings(repo_root: Path) -> dict[str, Any]:
    path = desktop_settings_path(repo_root)
    if not path.exists():
        return dict(DEFAULT_DESKTOP_SETTINGS)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_DESKTOP_SETTINGS)
    if not isinstance(payload, dict):
        return dict(DEFAULT_DESKTOP_SETTINGS)
    settings = dict(DEFAULT_DESKTOP_SETTINGS)
    settings["language"] = normalize_language(payload.get("language"))
    return settings


def save_desktop_settings(repo_root: Path, settings: dict[str, Any]) -> Path:
    payload = dict(DEFAULT_DESKTOP_SETTINGS)
    payload["language"] = normalize_language(settings.get("language"))
    path = desktop_settings_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
