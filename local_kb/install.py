from __future__ import annotations

import json
import os
import time
import tomllib
from pathlib import Path
from typing import Any

from local_kb.common import utc_now_iso
from local_kb.config import (
    KB_ROOT_ENV_VAR,
    default_codex_home,
    install_state_path,
    is_repo_root,
    load_install_state,
    save_install_state,
)


GLOBAL_SKILL_NAME = "predictive-kb-preflight"
GLOBAL_SKILL_ROOT = Path("skills") / GLOBAL_SKILL_NAME
TEMPLATE_ROOT = Path("templates") / GLOBAL_SKILL_NAME
AUTOMATIONS_ROOT = Path("automations")

SLEEP_AUTOMATION_PROMPT = (
    "Run the repository's local KB sleep-maintenance pass for this workspace. Use PROJECT_SPEC.md, "
    "docs/maintenance_runbook.md, and .agents/skills/local-kb-retrieve/MAINTENANCE_PROMPT.md as the "
    "authoritative guides. Start in proposal mode, inspect taxonomy and route gaps, allow only the current "
    "low-risk new-candidate, related-card, and cross-index apply paths when clearly eligible, keep trusted-card "
    "or taxonomy rewrites proposal-only unless current tooling cleanly supports them, inspect rollback artifacts "
    "when needed, and report the run id, reviewed observation counts, candidates created, maintenance decisions, "
    "undeclared taxonomy gaps, hub-vs-overloaded card reviews, and the next proposal-only targets."
)

DREAM_AUTOMATION_PROMPT = (
    "Run one bounded local KB dream-mode pass for this workspace. Use PROJECT_SPEC.md, docs/dream_runbook.md, "
    "and .agents/skills/local-kb-retrieve/DREAM_PROMPT.md as the authoritative guides. Run "
    "`python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json --max-experiments 1 "
    "--sleep-cooldown-minutes 45`, inspect the generated plan, opportunity, experiment, and report artifacts, "
    "keep write-back history-only or candidate-only, avoid trusted-card or taxonomy rewrites, and report the "
    "run id, selected experiment, created candidates if any, history events written, and anything still needing "
    "live-task confirmation."
)

REPO_AUTOMATION_SPECS = (
    {
        "id": "kb-sleep",
        "name": "KB Sleep",
        "kind": "cron",
        "prompt": SLEEP_AUTOMATION_PROMPT,
        "status": "ACTIVE",
        "rrule": "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=12;BYMINUTE=0",
        "model": "gpt-5.2",
        "reasoning_effort": "medium",
        "execution_environment": "local",
    },
    {
        "id": "kb-dream",
        "name": "KB Dream",
        "kind": "cron",
        "prompt": DREAM_AUTOMATION_PROMPT,
        "status": "ACTIVE",
        "rrule": "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=13;BYMINUTE=0",
        "model": "gpt-5.2",
        "reasoning_effort": "medium",
        "execution_environment": "local",
    },
)


def global_skill_dir(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / GLOBAL_SKILL_ROOT


def automation_dir(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / AUTOMATIONS_ROOT


def automation_toml_path(automation_id: str, codex_home: Path | None = None) -> Path:
    return automation_dir(codex_home) / automation_id / "automation.toml"


def _render_template(text: str, replacements: dict[str, str]) -> str:
    rendered = text
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _read_template(repo_root: Path, relative_path: str | Path) -> str:
    path = repo_root / TEMPLATE_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def _automation_spec_payload(spec: dict[str, str], repo_root: Path) -> dict[str, Any]:
    return {
        "version": 1,
        "id": spec["id"],
        "kind": spec["kind"],
        "name": spec["name"],
        "prompt": spec["prompt"],
        "status": spec["status"],
        "rrule": spec["rrule"],
        "model": spec["model"],
        "reasoning_effort": spec["reasoning_effort"],
        "execution_environment": spec["execution_environment"],
        "cwds": [str(repo_root)],
    }


def _load_automation_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_automation_toml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"version = {int(payload['version'])}",
        f"id = {json.dumps(payload['id'], ensure_ascii=False)}",
        f"kind = {json.dumps(payload['kind'], ensure_ascii=False)}",
        f"name = {json.dumps(payload['name'], ensure_ascii=False)}",
        f"prompt = {json.dumps(payload['prompt'], ensure_ascii=False)}",
        f"status = {json.dumps(payload['status'], ensure_ascii=False)}",
        f"rrule = {json.dumps(payload['rrule'], ensure_ascii=False)}",
        f"model = {json.dumps(payload['model'], ensure_ascii=False)}",
        f"reasoning_effort = {json.dumps(payload['reasoning_effort'], ensure_ascii=False)}",
        f"execution_environment = {json.dumps(payload['execution_environment'], ensure_ascii=False)}",
        f"cwds = {json.dumps(list(payload['cwds']), ensure_ascii=False)}",
        f"created_at = {int(payload['created_at'])}",
        f"updated_at = {int(payload['updated_at'])}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_repo_automations(repo_root: Path, codex_home: Path | None = None) -> list[dict[str, Any]]:
    home = codex_home or default_codex_home()
    automation_root = automation_dir(home)
    automation_root.mkdir(parents=True, exist_ok=True)

    now_ms = int(time.time() * 1000)
    installed: list[dict[str, Any]] = []
    for spec in REPO_AUTOMATION_SPECS:
        path = automation_toml_path(spec["id"], home)
        existing = _load_automation_toml(path)
        payload = _automation_spec_payload(spec, repo_root)
        payload["created_at"] = int(existing.get("created_at") or now_ms)
        payload["updated_at"] = now_ms
        _write_automation_toml(path, payload)
        installed.append(
            {
                "id": spec["id"],
                "kind": payload["kind"],
                "name": payload["name"],
                "path": str(path),
                "rrule": payload["rrule"],
                "execution_environment": payload["execution_environment"],
                "cwds": list(payload["cwds"]),
            }
        )
    return installed


def install_codex_integration(repo_root: Path, codex_home: Path | None = None) -> dict[str, Any]:
    home = codex_home or default_codex_home()
    skill_dir = global_skill_dir(home)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)

    launcher_path = skill_dir / "kb_launch.py"
    skill_path = skill_dir / "SKILL.md"
    openai_path = skill_dir / "agents" / "openai.yaml"

    replacements = {
        "KB_ROOT": str(repo_root),
        "LAUNCHER_PATH": str(launcher_path),
        "ENV_VAR_NAME": KB_ROOT_ENV_VAR,
    }

    skill_path.write_text(
        _render_template(_read_template(repo_root, "SKILL.md.template"), replacements),
        encoding="utf-8",
    )
    launcher_path.write_text(_read_template(repo_root, "kb_launch.py"), encoding="utf-8")
    openai_path.write_text(_read_template(repo_root, Path("agents") / "openai.yaml"), encoding="utf-8")
    automations = install_repo_automations(repo_root=repo_root, codex_home=home)

    manifest = {
        "repo_root": str(repo_root),
        "codex_home": str(home),
        "skill_name": GLOBAL_SKILL_NAME,
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_path),
        "launcher_path": str(launcher_path),
        "openai_path": str(openai_path),
        "env_var_name": KB_ROOT_ENV_VAR,
        "automation_ids": [item["id"] for item in automations],
        "automations": automations,
        "installed_at": utc_now_iso(),
    }
    manifest_path = save_install_state(manifest, home)
    manifest["install_state_path"] = str(manifest_path)
    return manifest


def build_installation_check(
    repo_root: Path | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    home = codex_home or default_codex_home()
    skill_dir = global_skill_dir(home)
    skill_path = skill_dir / "SKILL.md"
    launcher_path = skill_dir / "kb_launch.py"
    openai_path = skill_dir / "agents" / "openai.yaml"
    manifest = load_install_state(home)
    manifest_root_raw = str(manifest.get("repo_root", "") or "").strip()
    env_value = os.environ.get(KB_ROOT_ENV_VAR, "").strip()
    managed_automations = manifest.get("automations", [])

    issues: list[str] = []
    warnings: list[str] = []

    resolved_manifest_root = ""
    if manifest_root_raw:
        manifest_path = Path(manifest_root_raw).expanduser().resolve()
        resolved_manifest_root = str(manifest_path)
        if not is_repo_root(manifest_path):
            issues.append(f"Manifest repo root is missing or invalid: {manifest_path}")
    else:
        issues.append("Install manifest does not define repo_root.")

    requested_repo_root = ""
    if repo_root is not None:
        requested_repo_root = str(repo_root)
        if not is_repo_root(repo_root):
            issues.append(f"Requested repo root is missing required KB markers: {repo_root}")
        elif resolved_manifest_root and resolved_manifest_root != requested_repo_root:
            warnings.append(
                "Requested repo root differs from the installed manifest path. "
                "Run the installer again if this clone should become the active KB root."
            )

    if not skill_path.exists():
        issues.append(f"Global skill file is missing: {skill_path}")
    if not launcher_path.exists():
        issues.append(f"Launcher file is missing: {launcher_path}")
    if not openai_path.exists():
        issues.append(f"Global skill openai.yaml is missing: {openai_path}")
        openai_text = ""
    else:
        try:
            openai_text = openai_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"Global skill openai.yaml could not be read: {exc}")
            openai_text = ""

    if openai_text and "allow_implicit_invocation: true" not in openai_text:
        issues.append(
            "Global skill openai.yaml does not enable implicit invocation. "
            "Re-run the installer so the installed global preflight skill can trigger automatically."
        )
    if openai_text and "record a KB follow-up observation" not in openai_text:
        warnings.append(
            "Global skill default_prompt does not contain the expected KB postflight reminder. "
            "Re-run the installer to refresh the installed prompt."
        )

    automation_checks: list[dict[str, Any]] = []
    expected_repo_root = repo_root or (Path(manifest_root_raw) if manifest_root_raw else Path("."))
    for spec in REPO_AUTOMATION_SPECS:
        expected = _automation_spec_payload(spec, expected_repo_root)
        path = automation_toml_path(spec["id"], home)
        payload = _load_automation_toml(path)
        issues_for_automation: list[str] = []
        if not path.exists():
            issues_for_automation.append(f"Automation file is missing: {path}")
        elif not payload:
            issues_for_automation.append(f"Automation file could not be parsed: {path}")
        else:
            if str(payload.get("id", "") or "") != expected["id"]:
                issues_for_automation.append(f"Automation id mismatch for {path}: expected {expected['id']}")
            if str(payload.get("kind", "") or "") != expected["kind"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should be kind={expected['kind']}."
                )
            if str(payload.get("name", "") or "") != expected["name"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should be named {expected['name']}."
                )
            if str(payload.get("status", "") or "") != expected["status"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should be status={expected['status']}."
                )
            if str(payload.get("rrule", "") or "") != expected["rrule"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use rrule {expected['rrule']}."
                )
            if str(payload.get("model", "") or "") != expected["model"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use model={expected['model']}."
                )
            if str(payload.get("reasoning_effort", "") or "") != expected["reasoning_effort"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use reasoning_effort={expected['reasoning_effort']}."
                )
            if str(payload.get("execution_environment", "") or "") != expected["execution_environment"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use execution_environment={expected['execution_environment']}."
                )
            payload_cwds = [str(item) for item in payload.get("cwds", [])] if isinstance(payload.get("cwds"), list) else []
            if payload_cwds != expected["cwds"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should target cwds={expected['cwds']}."
                )
            prompt_text = str(payload.get("prompt", "") or "")
            required_prompt_markers = (
                ".agents/skills/local-kb-retrieve",
                "PROJECT_SPEC.md",
            )
            for marker in required_prompt_markers:
                if marker not in prompt_text:
                    issues_for_automation.append(
                        f"Automation {expected['id']} prompt is missing required marker: {marker}"
                    )
            if expected["id"] == "kb-dream" and "kb_dream.py" not in prompt_text:
                issues_for_automation.append("Automation kb-dream prompt must reference kb_dream.py.")
            if expected["id"] == "kb-sleep" and "MAINTENANCE_PROMPT.md" not in prompt_text:
                issues_for_automation.append(
                    "Automation kb-sleep prompt must reference MAINTENANCE_PROMPT.md."
                )
        if issues_for_automation:
            issues.extend(issues_for_automation)
        automation_checks.append(
            {
                "id": spec["id"],
                "path": str(path),
                "exists": path.exists(),
                "issues": issues_for_automation,
            }
        )

    if not managed_automations:
        warnings.append(
            "Install manifest does not record the repository-managed sleep/dream automations. "
            "Re-run the installer to refresh automation setup."
        )

    return {
        "ok": not issues,
        "repo_root": requested_repo_root,
        "manifest_repo_root": resolved_manifest_root,
        "codex_home": str(home),
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_path),
        "launcher_path": str(launcher_path),
        "openai_path": str(openai_path),
        "install_state_path": str(install_state_path(home)),
        "env_var_name": KB_ROOT_ENV_VAR,
        "env_var_value": env_value,
        "automation_checks": automation_checks,
        "issues": issues,
        "warnings": warnings,
    }
