from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import time
import tomllib
from pathlib import Path
from typing import Any

from local_kb.card_ids import load_or_create_installation_id
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
GLOBAL_SKILLS_ROOT = Path("skills")
REPO_SKILLS_ROOT = Path(".agents") / "skills"
TEMPLATE_ROOT = Path("templates") / GLOBAL_SKILL_NAME
AUTOMATIONS_ROOT = Path("automations")
GLOBAL_AGENTS_FILENAME = "AGENTS.md"
GLOBAL_AGENTS_BEGIN = "<!-- BEGIN MANAGED PREDICTIVE KB DEFAULTS -->"
GLOBAL_AGENTS_END = "<!-- END MANAGED PREDICTIVE KB DEFAULTS -->"
CODEX_SHELL_BIN_RELATIVE = Path("OpenAI") / "Codex" / "bin"
AUTOMATION_MODEL_POLICY = "strongest-available"
AUTOMATION_REASONING_EFFORT_POLICY = "deepest"
AUTOMATION_MODEL_ENV_VAR = "CODEX_KB_AUTOMATION_MODEL"
AUTOMATION_REASONING_EFFORT_ENV_VAR = "CODEX_KB_AUTOMATION_REASONING_EFFORT"
AUTOMATION_FALLBACK_MODEL = "gpt-5.5"
AUTOMATION_FALLBACK_REASONING_EFFORT = "xhigh"
REASONING_EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh")
AUTOMATION_DAILY_BYDAY = "SU,MO,TU,WE,TH,FR,SA"
ORG_CONTRIBUTE_WINDOW = (10 * 60, 13 * 60 + 59)
ORG_MAINTENANCE_WINDOW = (14 * 60, 16 * 60)
MAINTENANCE_SKILL_SPECS = (
    {
        "name": "kb-sleep-maintenance",
        "automation_id": "kb-sleep",
        "prompt_marker": "MAINTENANCE_PROMPT.md",
    },
    {
        "name": "kb-dream-pass",
        "automation_id": "kb-dream",
        "prompt_marker": "DREAM_PROMPT.md",
    },
    {
        "name": "kb-architect-pass",
        "automation_id": "kb-architect",
        "prompt_marker": "ARCHITECT_PROMPT.md",
    },
    {
        "name": "kb-organization-contribute",
        "automation_id": "kb-org-contribute",
        "prompt_marker": "scripts/kb_org_outbox.py",
    },
    {
        "name": "kb-organization-maintenance",
        "automation_id": "kb-org-maintenance",
        "prompt_marker": "scripts/kb_org_maintainer.py",
    },
    {
        "name": "khaos-brain-update",
        "automation_id": "manual-update",
        "prompt_marker": "scripts/install_codex_kb.py",
    },
)
MAINTENANCE_SKILL_NAMES = tuple(item["name"] for item in MAINTENANCE_SKILL_SPECS)

SLEEP_AUTOMATION_PROMPT = (
    "Use $kb-sleep-maintenance to run the repository's local KB sleep-maintenance pass for this workspace. "
    "Use PROJECT_SPEC.md, "
    "docs/maintenance_agent_worldview.md, docs/maintenance_runbook.md, and .agents/skills/local-kb-retrieve/MAINTENANCE_PROMPT.md as the "
    "authoritative guides. Before the first stateful command, run "
    "`python .agents/skills/local-kb-retrieve/scripts/kb_lane_status.py --lane kb-sleep --status running "
    "--wait-clear --poll-seconds 300 --json`; if another core maintenance lane is running, wait and recheck "
    "every 5 minutes instead of skipping. "
    "First read the shared maintenance-agent worldview, write a visible sleep execution plan with checkpoint statuses, start with a "
    "sleep self-preflight search against system/knowledge-library/maintenance, then run proposal mode, inspect "
    "taxonomy and route gaps, treat high-volume proposal output and candidate backlog as editorial triage inputs "
    "rather than an apply agenda, track the current maintenance run id from the consolidation output or chosen "
    "`--run-id` and reuse that same run id for final lane completion, run a mandatory similar-card merge checkpoint, run a mandatory overloaded-card "
    "split checkpoint, run an organization Skill bundle consolidation checkpoint that groups imported read-only "
    "Skills by bundle_id and keeps only the latest approved version by version_time, record skip-with-reason "
    "decisions when merge, split, or Skill replacement is not safe, review "
    "candidate route quality by preferring functional "
    "domain paths over project-name roots, do not create new candidates merely because the tooling can, "
    "treat mechanical apply eligibility as capability rather than approval and keep high-volume lanes proposal-only "
    "unless a compact reviewed action-key set is explicitly selected, "
    "inspect `dream_validation_summary` on review-candidate or review-entry-update actions as Dream sandbox evidence for Sleep judgment "
    "rather than automatic promotion, "
    "allow the current low-risk new-candidate, related-card, cross-index, "
    "AI-authored semantic-review, and AI-authored i18n apply paths when clearly eligible, "
    "use selected action keys with `--action-key` when only part of an apply lane is approved, "
    "require future utility before auto-creating candidate cards, require semantic-review utility assessments, "
    "limit semantic-review to at most 3 trusted-card modifications per run, run exactly one final AI-authored zh-CN "
    "display completion checkpoint after candidate/card creation, semantic card text changes, and route review are done, "
    "cover card display fields and route/path display labels in that single checkpoint through one i18n plan, do not "
    "run separate mid-run translation cleanup, keep taxonomy rewrites proposal-only unless current "
    "tooling cleanly supports them, inspect rollback artifacts including history-events, related-card-entries, "
    "cross-index-entries, and semantic-review-entries when present, continue "
    "through every safe checkpoint instead of stopping after a short proposal, attempt supported low-risk repairs "
    "and rerun the relevant validation when a command exposes a fixable issue, run a final sleep postflight check, "
    "append one structured maintenance observation when the pass exposed a reusable lesson or process hazard, stop "
    "after that final observation instead of recursively consolidating it, then run "
    "`python .agents/skills/local-kb-retrieve/scripts/kb_lane_status.py --lane kb-sleep --status completed --run-id <run_id> --json`, "
    "and report the run id, execution plan "
    "status, self-preflight entries, what became more accurate or clearer, reviewed observation counts, "
    "candidates created or deliberately not created, weak/noisy material rejected or kept history-only, route adjustments or concerns, "
    "semantic-review decisions applied or skipped, final zh-CN display completion status for cards and routes, translations updated or still missing, validations run, "
    "repaired or proposal-only issues, maintenance decisions, "
    "final postflight observation status, undeclared taxonomy gaps, hub-vs-overloaded card reviews, and the next "
    "proposal-only targets."
)

DREAM_AUTOMATION_PROMPT = (
    "Use $kb-dream-pass to run one bounded local KB dream-mode pass for this workspace. "
    "Use PROJECT_SPEC.md, docs/maintenance_agent_worldview.md, docs/dream_runbook.md, "
    "and .agents/skills/local-kb-retrieve/DREAM_PROMPT.md as the authoritative guides. First read the "
    "shared maintenance-agent worldview; the runner must wait on the shared local maintenance lock instead of skipping when Sleep or Architect is active, then run "
    "`python .agents/skills/local-kb-retrieve/scripts/kb_dream.py --json`, "
    "inspect the generated preflight, plan, opportunity, experiment, execution-plan, "
    "and report artifacts, select a bounded route-deduped batch of grounded evidence gaps only when each one "
    "clarifies future retrieval, routing, card use, or Sleep consolidation, report a no-op when no valuable gap exists, require experiment "
    "design, validation plan, safety tier, rollback plan, and explicit success/failure/inconclusive criteria before "
    "execution, write sandbox experiment artifacts only under kb/history/dream/<run-id>/sandbox/ and record "
    "retrieval-ab sandbox paths, allowed writes, evidence grades, validation results, Sleep handoff, and Architect handoff, "
    "skip route-and-mode experiments already passed with strong or moderate sandbox evidence in a prior Dream report, "
    "when a strong or moderate passed sandbox result validates an existing candidate or low-confidence card, record "
    "the source entry id and structured Sleep handoff with suggested_action update-card, "
    "keep write-back history-only by default, create candidates only when history-only is insufficient, "
    "keep external-system experiments proposal-only, avoid trusted-card or taxonomy rewrites, avoid repeating known "
    "route-gap observations without new decision value, and report the run id, preflight entries retrieved, selected "
    "evidence gaps or no-op reason, future retrieval/use decisions clarified, experiments executed in order, "
    "execution-plan checkpoint status, safety tier and rollback plan, result classifications, candidates created if any with why history-only was insufficient, "
    "history events written, sandbox paths, evidence grades, validation results, Sleep/Architect handoff, and anything still needing live-task confirmation."
)

ARCHITECT_AUTOMATION_PROMPT = (
    "Use $kb-architect-pass to run one KB Architect mechanism-maintenance pass for this workspace. "
    "Use PROJECT_SPEC.md, "
    "docs/maintenance_agent_worldview.md, docs/architecture_runbook.md, and .agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md as the "
    "authoritative guides. First read the shared maintenance-agent worldview. The runner must wait on the shared local maintenance lock instead of skipping when Sleep or Dream is active. Before the first stateful command, write a visible Architect execution plan with "
    "checkpoint statuses and include every required checkpoint; do not skip any checkpoint silently. Start with "
    "Architect self-preflight against system/knowledge-library/maintenance, then run "
    "`python scripts/khaos_brain_update.py --architect-check --json`; if it reports apply_ready=true, use "
    "$khaos-brain-update to apply the authorized update while the UI is closed, report the update result, and "
    "stop this old-version Architect pass so the next run uses the updated code. If the update is available but "
    "not prepared, or prepared while the UI is running, leave the state for the UI and continue normal Architect "
    "maintenance. Then run "
    "`python .agents/skills/local-kb-retrieve/scripts/kb_architect.py --json`, "
    "inspect the generated plan, preflight, signals, proposals, decisions, "
    "execution-plan, report, and proposal_queue artifacts as incoming evidence, inspect the maintained queue and the "
    "system-readable maintenance rollup at kb/history/architecture/maintenance_rollup.json before "
    "acting on new signals, start with queue hygiene by merging duplicates, closing resolved or obsolete items, and "
    "avoiding reopened terminal items unless there is a real regression, use only Evidence, Impact, and Safety for proposal "
    "review, keep statuses limited to new, watching, ready-for-patch, ready-for-apply, applied, rejected, and "
    "superseded, do not use a human-review status, keep long-observation items as watching, keep the scope to "
    "KB operating mechanisms rather than card content, do not rewrite trusted cards or promote candidates, apply "
    "only narrow, reversible, high-value mechanism changes whose execution packet is agent-ready inside prompt, "
    "runbook, validation, or proposal-queue maintenance with an immediate validation bundle, sandbox-apply only "
    "when sandbox_apply.sandbox_ready=true and the packet lists planned sandbox path, allowed/disallowed writes, "
    "expected effect, validation commands, manual checks, and merge/block decision fields, choose at most one "
    "sandbox-ready packet to trial before ending the full Architect pass instead of repeatedly reporting the same "
    "ready packet, inspect selected_sandbox_trial, write <planned_sandbox_path>/trial_result.json after the trial, "
    "record it with --record-trial-result, generate patch plans "
    "for medium-safety mechanism changes, mark successful packets applied and unsafe or failed packets blocked, "
    "create a new proposal only when the signal is not already represented by an active or terminal queue item, confirm the "
    "runner's KB postflight observation or append one structured Architect observation if a new mechanism lesson "
    "was exposed, confirm the rollup contains Sleep, Dream, Architect, FlowGuard, organization, content-boundary, and install-sync status, and report the run id, checkpoint status for every plan item, preflight entries retrieved, "
    "software update gate result, "
    "proposal counts by status before and after queue hygiene, duplicate clusters merged or superseded, resolved or "
    "already-applied items closed, ready-for-apply and ready-for-patch items, sandbox-ready packets with planned sandbox path and write boundaries, execution packets by mode, changes "
    "applied, validation bundle run, blocked execution states, postflight observation status, system-readable maintenance rollup status, watching items left "
    "for long observation, and the system evolution route."
)

ORG_CONTRIBUTE_AUTOMATION_PROMPT = (
    "Use $kb-organization-contribute to run one settings-gated organization KB contribution pass for this "
    "workspace. Use PROJECT_SPEC.md, docs/organization_mode_plan.md, and .agents/skills/local-kb-retrieve/SKILL.md "
    "as the authoritative guides. Start by reading .local/khaos_brain_desktop_settings.json through "
    "scripts/kb_org_outbox.py --automation; if the desktop settings are personal mode, missing, unvalidated, or not "
    "connected to a validated organization repository, return a successful no-op. When organization mode is valid, "
    "sync the organization mirror first, run KB preflight against system/knowledge-library/organization, then export only shareable public model and "
    "heuristic cards through the content-hash-gated outbox. Respect every exchanged hash including downloaded, used, absorbed, exported, uploaded, "
    "current local card hashes, current organization main-card hashes, and current import hashes; do not export "
    "private cards, personal preferences, credentials, raw local paths, or raw machine identifiers. When cards "
    "depend on local Skills, upload card-bound Skill bundles with bundle_id, content_hash, version_time, "
    "original_author, readonly_when_imported, and update_policy=original_author_only; if several local cards point "
    "at the same bundle_id, upload the local latest version for that bundle rather than an older card-carried copy. Use "
    "`python scripts/kb_org_outbox.py --automation` for the scheduled pass; it should prepare an import branch under kb/imports, push eligible import proposals automatically, open a GitHub PR when available, and apply org-kb:auto-merge only when checks allow it "
    "while leaving movement into organization main, trust upgrades, and final merge to organization maintenance and GitHub checks. Run KB postflight after "
    "any non-skipped pass, record a "
    "structured observation, and report the settings gate, sync result, preflight entries, created and skipped proposal counts, "
    "outbox path, import branch status, push or pull request URL, postflight path, and "
    "errors."
)

ORG_MAINTENANCE_AUTOMATION_PROMPT = (
    "Use $kb-organization-maintenance to run one settings-gated organization-level Sleep-like maintenance pass "
    "for this workspace. Treat the organization KB as a shared exchange layer rather than a central truth layer: "
    "organization maintenance may maintain organization main cards and imported card content with the same editorial "
    "posture as local Sleep, while local machines keep final adoption authority. Use PROJECT_SPEC.md, "
    "docs/maintenance_agent_worldview.md, docs/organization_mode_plan.md, "
    ".agents/skills/local-kb-retrieve/SKILL.md, and organization-review guidance when available. Start by "
    "reading .local/khaos_brain_desktop_settings.json through scripts/kb_org_maintainer.py --automation; if the "
    "desktop settings are personal mode, missing, unvalidated, or organization maintenance participation is not "
    "requested, return a successful no-op. When participation is available for a validated organization "
    "repository, run KB preflight against system/knowledge-library/organization, validate the organization "
    "manifest, expected paths, imports entry lane, main exchange lane, Skill registry, and current Git state, "
    "then run the organization card-surface map checkpoint, organization candidate intake checkpoint, content-hash checkpoint, mandatory organization "
    "similar-card merge checkpoint, mandatory organization overloaded-card split checkpoint, candidate decision "
    "checkpoint, Skill safety checkpoint, Skill bundle version checkpoint, decision-apply checkpoint, post-apply organization check, and GitHub merge-readiness checkpoint. Inspect organization trusted cards, candidates, "
    "main cards, imports, Skill registry entries, card-and-Skill bundles, privacy boundaries, and GitHub auto-merge readiness "
    "using the organization maintenance worldview and organization-review guidance when available. Treat duplicate content hashes as maintenance signals and duplicate entry ids as "
    "non-blocking handles. Trusted/shared card content maintenance is allowed when the evidence supports a "
    "Sleep-style keep, reject, watch, merge, split, rewrite, promote, demote, deprecate, or cross-link decision. "
    "For card-bound Skill bundles, group by bundle_id, approve only original-author updates "
    "on the same bundle, require sha256 content_hash and version_time, treat non-author changes as forks, and select "
    "the latest approved version by version_time for organization distribution. Use candidate, approved, and rejected "
    "as the first-pass Skill states; do not auto-install candidate, rejected, unknown, unpinned, or non-hash-verified "
    "Skills. Build an organization Sleep decision set over cleanup proposals, select-for-apply or watch each action with a reason, treat organization-review as guidance rather than an apply gate, and apply only exact selected action ids. "
    "Keep privacy and executable Skill boundaries stricter than ordinary card content. It is acceptable to skip applying a change when evidence, "
    "safety, tooling, permissions, or scope is insufficient, but the inspection and recorded decision must still "
    "happen. Run KB postflight after any non-skipped pass, record a structured observation, and report the settings "
    "gate, participation status, preflight entries, manifest status, main status counts and import counts, content-hash "
    "duplicate decisions, organization merge checkpoint decisions, organization split checkpoint decisions, "
    "candidate approval or rejection decisions, Sleep decision counts, selected action ids, apply result, post-apply check result, maintenance branch, PR, push, and auto-merge-label result, Skill dependency decisions, Skill bundle version decisions, GitHub "
    "merge-readiness result, organization-review guidance availability, recommendations, postflight path, and errors."
)

REPO_AUTOMATION_SPECS = (
    {
        "id": "kb-sleep",
        "name": "KB Sleep",
        "kind": "cron",
        "prompt": SLEEP_AUTOMATION_PROMPT,
        "skill_name": "kb-sleep-maintenance",
        "status": "ACTIVE",
        "rrule": "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=12;BYMINUTE=0",
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "execution_environment": "local",
    },
    {
        "id": "kb-dream",
        "name": "KB Dream",
        "kind": "cron",
        "prompt": DREAM_AUTOMATION_PROMPT,
        "skill_name": "kb-dream-pass",
        "status": "ACTIVE",
        "rrule": "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=13;BYMINUTE=0",
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "execution_environment": "local",
    },
    {
        "id": "kb-architect",
        "name": "KB Architect",
        "kind": "cron",
        "prompt": ARCHITECT_AUTOMATION_PROMPT,
        "skill_name": "kb-architect-pass",
        "status": "ACTIVE",
        "rrule": "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=14;BYMINUTE=0",
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "execution_environment": "local",
    },
    {
        "id": "kb-org-contribute",
        "name": "KB Organization Contribute",
        "kind": "cron",
        "prompt": ORG_CONTRIBUTE_AUTOMATION_PROMPT,
        "skill_name": "kb-organization-contribute",
        "status": "ACTIVE",
        "jitter_window": ORG_CONTRIBUTE_WINDOW,
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "execution_environment": "local",
    },
    {
        "id": "kb-org-maintenance",
        "name": "KB Organization Maintenance",
        "kind": "cron",
        "prompt": ORG_MAINTENANCE_AUTOMATION_PROMPT,
        "skill_name": "kb-organization-maintenance",
        "status": "ACTIVE",
        "jitter_window": ORG_MAINTENANCE_WINDOW,
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "execution_environment": "local",
    },
)


def default_local_appdata() -> Path:
    raw = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / "AppData" / "Local").resolve()


def global_skill_dir(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / GLOBAL_SKILL_ROOT


def maintenance_skill_source_dir(repo_root: Path, skill_name: str) -> Path:
    return repo_root / REPO_SKILLS_ROOT / skill_name


def maintenance_skill_install_dir(skill_name: str, codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / GLOBAL_SKILLS_ROOT / skill_name


def codex_shell_bin_dir(path_env: str | None = None, local_appdata: Path | None = None) -> Path:
    active_path = str(path_env if path_env is not None else os.environ.get("PATH", "") or "")
    for raw_entry in active_path.split(os.pathsep):
        entry_text = raw_entry.strip().strip('"')
        if not entry_text:
            continue
        entry = Path(entry_text).expanduser()
        parts = [part.lower() for part in entry.parts]
        if len(parts) >= 3 and parts[-3:] == ["openai", "codex", "bin"]:
            return entry.resolve()
    base = local_appdata or default_local_appdata()
    return (base / CODEX_SHELL_BIN_RELATIVE).resolve()


def automation_dir(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / AUTOMATIONS_ROOT


def automation_toml_path(automation_id: str, codex_home: Path | None = None) -> Path:
    return automation_dir(codex_home) / automation_id / "automation.toml"


def _rrule_for_local_minute(total_minutes: int) -> str:
    hour = max(0, min(23, int(total_minutes) // 60))
    minute = max(0, min(59, int(total_minutes) % 60))
    return f"FREQ=WEEKLY;BYDAY={AUTOMATION_DAILY_BYDAY};BYHOUR={hour};BYMINUTE={minute}"


def _stable_window_minute(repo_root: Path, automation_id: str, window: tuple[int, int]) -> int:
    start, end = int(window[0]), int(window[1])
    if end < start:
        raise ValueError(f"Invalid automation jitter window: {window}")
    installation_id = load_or_create_installation_id(repo_root)
    digest = hashlib.sha256(f"{installation_id}:{automation_id}".encode("utf-8")).digest()
    offset = int.from_bytes(digest[:8], "big") % (end - start + 1)
    return start + offset


def automation_rrule_for_spec(spec: dict[str, Any], repo_root: Path) -> str:
    window = spec.get("jitter_window")
    if isinstance(window, tuple) and len(window) == 2:
        return _rrule_for_local_minute(_stable_window_minute(repo_root, str(spec["id"]), window))
    return str(spec["rrule"])


def automation_time_window_label(spec: dict[str, Any]) -> str:
    window = spec.get("jitter_window")
    if not isinstance(window, tuple) or len(window) != 2:
        return ""
    start, end = int(window[0]), int(window[1])
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def global_agents_path(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / GLOBAL_AGENTS_FILENAME


def codex_config_path(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / "config.toml"


def models_cache_path(codex_home: Path | None = None) -> Path:
    home = codex_home or default_codex_home()
    return home / "models_cache.json"


def _load_toml_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_models_cache(codex_home: Path | None = None) -> list[dict[str, Any]]:
    path = models_cache_path(codex_home)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return [item for item in models if isinstance(item, dict)]


def _supported_reasoning_efforts(model: dict[str, Any]) -> list[str]:
    raw_levels = model.get("supported_reasoning_levels", [])
    efforts: list[str] = []
    if isinstance(raw_levels, list):
        for item in raw_levels:
            if isinstance(item, dict):
                effort = str(item.get("effort", "") or "").strip()
            else:
                effort = str(item or "").strip()
            if effort:
                efforts.append(effort)
    return efforts


def _general_model_version_key(slug: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"gpt-(\d+(?:\.\d+)*)", slug.strip().lower())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _config_model(codex_home: Path | None = None) -> str:
    payload = _load_toml_object(codex_config_path(codex_home))
    return str(payload.get("model", "") or "").strip()


def _config_reasoning_effort(codex_home: Path | None = None) -> str:
    payload = _load_toml_object(codex_config_path(codex_home))
    return str(payload.get("model_reasoning_effort", "") or "").strip()


def resolve_automation_model(codex_home: Path | None = None) -> str:
    env_value = str(os.environ.get(AUTOMATION_MODEL_ENV_VAR, "") or "").strip()
    if env_value:
        return env_value

    models = _load_models_cache(codex_home)
    candidates: list[tuple[tuple[int, ...], str]] = []
    for model in models:
        slug = str(model.get("slug", "") or "").strip()
        version_key = _general_model_version_key(slug)
        if version_key is None:
            continue
        candidates.append((version_key, slug))
    if candidates:
        return sorted(candidates, key=lambda item: item[0])[-1][1]

    configured_model = _config_model(codex_home)
    if configured_model:
        return configured_model
    return AUTOMATION_FALLBACK_MODEL


def resolve_automation_reasoning_effort(
    codex_home: Path | None = None,
    *,
    model: str | None = None,
) -> str:
    env_value = str(os.environ.get(AUTOMATION_REASONING_EFFORT_ENV_VAR, "") or "").strip()
    if env_value:
        return env_value

    selected_model = str(model or resolve_automation_model(codex_home)).strip()
    models = _load_models_cache(codex_home)
    for model_payload in models:
        if str(model_payload.get("slug", "") or "").strip() != selected_model:
            continue
        supported = _supported_reasoning_efforts(model_payload)
        if AUTOMATION_FALLBACK_REASONING_EFFORT in supported:
            return AUTOMATION_FALLBACK_REASONING_EFFORT
        ranked = [item for item in REASONING_EFFORT_ORDER if item in supported]
        if ranked:
            return ranked[-1]

    configured_effort = _config_reasoning_effort(codex_home)
    if configured_effort:
        return configured_effort
    return AUTOMATION_FALLBACK_REASONING_EFFORT


def resolve_automation_runtime(codex_home: Path | None = None) -> dict[str, str]:
    model = resolve_automation_model(codex_home)
    reasoning_effort = resolve_automation_reasoning_effort(codex_home, model=model)
    return {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "model_policy": AUTOMATION_MODEL_POLICY,
        "reasoning_effort_policy": AUTOMATION_REASONING_EFFORT_POLICY,
        "model_env_var": AUTOMATION_MODEL_ENV_VAR,
        "reasoning_effort_env_var": AUTOMATION_REASONING_EFFORT_ENV_VAR,
    }


def _render_template(text: str, replacements: dict[str, str]) -> str:
    rendered = text
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _read_template(repo_root: Path, relative_path: str | Path) -> str:
    path = repo_root / TEMPLATE_ROOT / relative_path
    return path.read_text(encoding="utf-8")


def _render_managed_global_agents_block(repo_root: Path) -> str:
    body = _read_template(repo_root, "AGENTS.md.template").strip()
    return f"{GLOBAL_AGENTS_BEGIN}\n{body}\n{GLOBAL_AGENTS_END}\n"


def _upsert_managed_global_agents(existing_text: str, managed_block: str) -> str:
    if GLOBAL_AGENTS_BEGIN in existing_text and GLOBAL_AGENTS_END in existing_text:
        start = existing_text.index(GLOBAL_AGENTS_BEGIN)
        end = existing_text.index(GLOBAL_AGENTS_END) + len(GLOBAL_AGENTS_END)
        prefix = existing_text[:start].rstrip()
        suffix = existing_text[end:].lstrip()
        parts = [part for part in [prefix, managed_block.strip(), suffix] if part]
        return "\n\n".join(parts).rstrip() + "\n"
    if not existing_text.strip():
        return managed_block
    return existing_text.rstrip() + "\n\n" + managed_block


def install_global_agents_defaults(repo_root: Path, codex_home: Path | None = None) -> str:
    path = global_agents_path(codex_home)
    try:
        existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        existing_text = ""
    rendered = _upsert_managed_global_agents(existing_text, _render_managed_global_agents_block(repo_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return str(path)


def _checklist_item(
    item_id: str,
    label: str,
    ok: bool,
    details: str,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "label": label,
        "ok": ok,
        "required": required,
        "details": details,
    }


def _candidate_paths(*raw_paths: str | Path | None) -> list[Path]:
    seen: set[str] = set()
    candidates: list[Path] = []
    for raw_path in raw_paths:
        if raw_path is None:
            continue
        text = str(raw_path).strip().strip('"')
        if not text:
            continue
        path = Path(text).expanduser()
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    return candidates


def _path_entries(path_env: str | None = None) -> list[Path]:
    active_path = str(path_env if path_env is not None else os.environ.get("PATH", "") or "")
    return _candidate_paths(*active_path.split(os.pathsep))


def resolve_git_executable(
    *,
    shell_bin_dir: Path | None = None,
    explicit_path: str | Path | None = None,
    path_env: str | None = None,
) -> Path | None:
    if explicit_path is not None:
        path = Path(explicit_path).expanduser()
        return path.resolve() if path.exists() else None

    shell_bin = (shell_bin_dir or codex_shell_bin_dir(path_env=path_env)).resolve()
    local_appdata = default_local_appdata()
    program_files = Path(str(os.environ.get("ProgramFiles", "") or "")).expanduser()
    program_files_x86 = Path(str(os.environ.get("ProgramFiles(x86)", "") or "")).expanduser()

    candidates = _candidate_paths(
        program_files / "Git" / "cmd" / "git.exe" if str(program_files) else None,
        program_files / "Git" / "bin" / "git.exe" if str(program_files) else None,
        program_files_x86 / "Git" / "cmd" / "git.exe" if str(program_files_x86) else None,
        program_files_x86 / "Git" / "bin" / "git.exe" if str(program_files_x86) else None,
        local_appdata / "Programs" / "Git" / "cmd" / "git.exe",
        local_appdata / "Programs" / "Git" / "bin" / "git.exe",
    )
    candidates.extend(_candidate_paths(*(entry / "git.exe" for entry in _path_entries(path_env))))

    github_desktop_root = local_appdata / "GitHubDesktop"
    if github_desktop_root.exists():
        try:
            candidates.extend(
                _candidate_paths(
                    *github_desktop_root.glob("app-*\\resources\\app\\git\\cmd\\git.exe")
                )
            )
        except OSError:
            pass

    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.resolve().parent == shell_bin:
            continue
        return candidate.resolve()
    return None


def resolve_rg_source(
    *,
    shell_bin_dir: Path | None = None,
    explicit_path: str | Path | None = None,
    path_env: str | None = None,
) -> Path | None:
    if explicit_path is not None:
        path = Path(explicit_path).expanduser()
        return path.resolve() if path.exists() else None

    shell_bin = (shell_bin_dir or codex_shell_bin_dir(path_env=path_env)).resolve()
    existing_dest = shell_bin / "rg.exe"
    if existing_dest.exists():
        return existing_dest.resolve()

    local_appdata = default_local_appdata()
    program_files = Path(str(os.environ.get("ProgramFiles", "") or "")).expanduser()

    candidates = _candidate_paths(*(entry / "rg.exe" for entry in _path_entries(path_env)))
    candidates.extend(
        _candidate_paths(
            local_appdata / "Programs" / "Microsoft VS Code" / "resources" / "app" / "node_modules.asar.unpacked" / "@vscode" / "ripgrep" / "bin" / "rg.exe",
            local_appdata / "Programs" / "cursor" / "resources" / "app" / "node_modules.asar.unpacked" / "@vscode" / "ripgrep" / "bin" / "rg.exe",
            program_files / "Microsoft VS Code" / "resources" / "app" / "node_modules.asar.unpacked" / "@vscode" / "ripgrep" / "bin" / "rg.exe" if str(program_files) else None,
            program_files / "VSCodium" / "resources" / "app" / "node_modules.asar.unpacked" / "@vscode" / "ripgrep" / "bin" / "rg.exe" if str(program_files) else None,
        )
    )

    windows_apps = program_files / "WindowsApps" if str(program_files) else None
    if windows_apps and windows_apps.exists():
        try:
            candidates.extend(
                _candidate_paths(
                    *windows_apps.glob("OpenAI.Codex_*\\app\\resources\\rg.exe")
                )
            )
        except OSError:
            pass

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _prepend_process_path(path: Path) -> bool:
    resolved = str(path.resolve())
    current_path = str(os.environ.get("PATH", "") or "")
    entries = [entry.strip().strip('"') for entry in current_path.split(os.pathsep) if entry.strip()]
    if resolved in entries:
        return False
    os.environ["PATH"] = resolved if not current_path else f"{resolved}{os.pathsep}{current_path}"
    return True


def _persist_user_path(path: Path) -> bool:
    try:
        import winreg  # type: ignore
    except ImportError:
        return False

    resolved = str(path.resolve())
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
            current_value, _ = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        current_value = ""
    current_text = str(current_value or "")
    entries = [entry.strip().strip('"') for entry in current_text.split(os.pathsep) if entry.strip()]
    if resolved in entries:
        return False
    updated_text = resolved if not entries else os.pathsep.join([resolved, *entries])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated_text)
    return True


def install_codex_shell_tools(
    *,
    shell_bin_dir: Path | None = None,
    git_executable: str | Path | None = None,
    rg_source: str | Path | None = None,
    path_env: str | None = None,
    persist_user_path: bool = True,
) -> dict[str, Any]:
    bin_dir = (shell_bin_dir or codex_shell_bin_dir(path_env=path_env)).resolve()
    bin_dir.mkdir(parents=True, exist_ok=True)

    resolved_git = resolve_git_executable(
        shell_bin_dir=bin_dir,
        explicit_path=git_executable,
        path_env=path_env,
    )
    resolved_rg = resolve_rg_source(
        shell_bin_dir=bin_dir,
        explicit_path=rg_source,
        path_env=path_env,
    )

    issues: list[str] = []
    git_shim_path = bin_dir / "git.cmd"
    rg_path = bin_dir / "rg.exe"

    if resolved_git is None:
        issues.append("Unable to locate a Git executable for the Codex shell shim.")
    else:
        shim_command = (
            f'call "{resolved_git}" %*'
            if resolved_git.suffix.lower() in {".cmd", ".bat"}
            else f'"{resolved_git}" %*'
        )
        git_shim_path.write_text(f"@echo off\r\n{shim_command}\r\n", encoding="ascii")

    if resolved_rg is None:
        issues.append("Unable to locate an rg.exe source for the Codex shell shim.")
    elif resolved_rg.resolve() != rg_path.resolve():
        shutil.copy2(resolved_rg, rg_path)

    process_path_updated = _prepend_process_path(bin_dir)
    user_path_updated = _persist_user_path(bin_dir) if persist_user_path else False

    return {
        "shell_bin_dir": str(bin_dir),
        "git_executable": str(resolved_git) if resolved_git else "",
        "git_shim_path": str(git_shim_path),
        "git_shim_installed": git_shim_path.exists(),
        "rg_source": str(resolved_rg) if resolved_rg else "",
        "rg_path": str(rg_path),
        "rg_installed": rg_path.exists(),
        "process_path_updated": process_path_updated,
        "user_path_updated": user_path_updated,
        "issues": issues,
    }


def _automation_spec_payload(
    spec: dict[str, Any],
    repo_root: Path,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    runtime = resolve_automation_runtime(codex_home)
    schedule_window = automation_time_window_label(spec)
    return {
        "version": 1,
        "id": spec["id"],
        "kind": spec["kind"],
        "name": spec["name"],
        "prompt": spec["prompt"],
        "status": spec["status"],
        "rrule": automation_rrule_for_spec(spec, repo_root),
        "schedule_policy": "stable-jitter" if schedule_window else "fixed",
        "schedule_window": schedule_window,
        "model": runtime["model"],
        "reasoning_effort": runtime["reasoning_effort"],
        "model_policy": spec.get("model_policy", runtime["model_policy"]),
        "reasoning_effort_policy": spec.get(
            "reasoning_effort_policy",
            runtime["reasoning_effort_policy"],
        ),
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
        f"schedule_policy = {json.dumps(payload.get('schedule_policy', 'fixed'), ensure_ascii=False)}",
        f"schedule_window = {json.dumps(payload.get('schedule_window', ''), ensure_ascii=False)}",
        f"model = {json.dumps(payload['model'], ensure_ascii=False)}",
        f"reasoning_effort = {json.dumps(payload['reasoning_effort'], ensure_ascii=False)}",
        f"model_policy = {json.dumps(payload['model_policy'], ensure_ascii=False)}",
        f"reasoning_effort_policy = {json.dumps(payload['reasoning_effort_policy'], ensure_ascii=False)}",
        f"execution_environment = {json.dumps(payload['execution_environment'], ensure_ascii=False)}",
        f"cwds = {json.dumps(list(payload['cwds']), ensure_ascii=False)}",
        f"created_at = {int(payload['created_at'])}",
        f"updated_at = {int(payload['updated_at'])}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_repo_maintenance_skills(repo_root: Path, codex_home: Path | None = None) -> list[dict[str, Any]]:
    home = codex_home or default_codex_home()
    installed: list[dict[str, Any]] = []
    for spec in MAINTENANCE_SKILL_SPECS:
        skill_name = spec["name"]
        source = maintenance_skill_source_dir(repo_root, skill_name)
        destination = maintenance_skill_install_dir(skill_name, home)
        skill_path = source / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Repository-managed maintenance skill is missing: {skill_path}")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        installed.append(
            {
                "name": skill_name,
                "source_path": str(source),
                "install_path": str(destination),
                "skill_path": str(destination / "SKILL.md"),
                "openai_path": str(destination / "agents" / "openai.yaml"),
                "automation_id": spec["automation_id"],
            }
        )
    return installed


def install_repo_automations(repo_root: Path, codex_home: Path | None = None) -> list[dict[str, Any]]:
    home = codex_home or default_codex_home()
    automation_root = automation_dir(home)
    automation_root.mkdir(parents=True, exist_ok=True)

    now_ms = int(time.time() * 1000)
    installed: list[dict[str, Any]] = []
    for spec in REPO_AUTOMATION_SPECS:
        path = automation_toml_path(spec["id"], home)
        existing = _load_automation_toml(path)
        payload = _automation_spec_payload(spec, repo_root, codex_home=home)
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
                "schedule_policy": payload["schedule_policy"],
                "schedule_window": payload["schedule_window"],
                "model": payload["model"],
                "reasoning_effort": payload["reasoning_effort"],
                "model_policy": payload["model_policy"],
                "reasoning_effort_policy": payload["reasoning_effort_policy"],
                "execution_environment": payload["execution_environment"],
                "cwds": list(payload["cwds"]),
            }
        )
    return installed


def install_codex_integration(
    repo_root: Path,
    codex_home: Path | None = None,
    *,
    shell_bin_dir: Path | None = None,
    git_executable: str | Path | None = None,
    rg_source: str | Path | None = None,
    persist_user_shell_path: bool = True,
) -> dict[str, Any]:
    home = codex_home or default_codex_home()
    skill_dir = global_skill_dir(home)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)

    launcher_path = skill_dir / "kb_launch.py"
    skill_path = skill_dir / "SKILL.md"
    openai_path = skill_dir / "agents" / "openai.yaml"
    global_agents = install_global_agents_defaults(repo_root=repo_root, codex_home=home)

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
    maintenance_skills = install_repo_maintenance_skills(repo_root=repo_root, codex_home=home)
    shell_tools = install_codex_shell_tools(
        shell_bin_dir=shell_bin_dir,
        git_executable=git_executable,
        rg_source=rg_source,
        persist_user_path=persist_user_shell_path,
    )
    automation_runtime = resolve_automation_runtime(home)
    automations = install_repo_automations(repo_root=repo_root, codex_home=home)

    manifest = {
        "repo_root": str(repo_root),
        "codex_home": str(home),
        "skill_name": GLOBAL_SKILL_NAME,
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_path),
        "launcher_path": str(launcher_path),
        "openai_path": str(openai_path),
        "global_agents_path": global_agents,
        "env_var_name": KB_ROOT_ENV_VAR,
        "maintenance_skill_names": list(MAINTENANCE_SKILL_NAMES),
        "maintenance_skills": maintenance_skills,
        "shell_tools": shell_tools,
        "automation_runtime": automation_runtime,
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
    global_agents = global_agents_path(home)
    manifest = load_install_state(home)
    manifest_root_raw = str(manifest.get("repo_root", "") or "").strip()
    env_value = os.environ.get(KB_ROOT_ENV_VAR, "").strip()
    managed_automations = manifest.get("automations", [])
    managed_maintenance_skills = manifest.get("maintenance_skills", [])
    shell_tools_manifest = manifest.get("shell_tools", {}) if isinstance(manifest.get("shell_tools"), dict) else {}

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
        issues.append(
            "Global skill default_prompt does not contain the expected KB postflight reminder. "
            "Re-run the installer to refresh the installed prompt."
        )
    if openai_text and "skill/plugin usage lesson" not in openai_text:
        issues.append(
            "Global skill default_prompt does not mention skill/plugin usage lessons as KB signals. "
            "Re-run the installer to refresh the installed prompt."
        )
    if openai_text and "subagent/delegation usage lesson" not in openai_text:
        issues.append(
            "Global skill default_prompt does not mention subagent/delegation usage lessons as KB signals. "
            "Re-run the installer to refresh the installed prompt."
        )
    if openai_text and "phase-change KB checkpoints" not in openai_text:
        issues.append(
            "Global skill default_prompt does not mention phase-change KB checkpoints for long mixed tasks. "
            "Re-run the installer to refresh the installed prompt."
        )
    if not global_agents.exists():
        issues.append(
            f"Global AGENTS defaults file is missing: {global_agents}. "
            "Re-run the installer so every session inherits the predictive KB defaults."
        )
        global_agents_text = ""
    else:
        try:
            global_agents_text = global_agents.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(f"Global AGENTS defaults file could not be read: {exc}")
            global_agents_text = ""

    if global_agents_text and GLOBAL_AGENTS_BEGIN not in global_agents_text:
        issues.append(
            "Global AGENTS file is present but missing the managed predictive KB defaults block. "
            "Re-run the installer to restore the session-wide KB instructions."
        )
    if global_agents_text and "$predictive-kb-preflight" not in global_agents_text:
        issues.append(
            "Global AGENTS defaults do not mention $predictive-kb-preflight. "
            "Re-run the installer to restore the required KB preflight reminder."
        )
    if global_agents_text and "explicit KB postflight check" not in global_agents_text:
        issues.append(
            "Global AGENTS defaults do not contain the expected explicit KB postflight check wording. "
            "Re-run the installer to refresh the session-wide defaults."
        )
    if global_agents_text and "skill/plugin usage" not in global_agents_text:
        issues.append(
            "Global AGENTS defaults do not mention skill/plugin usage lessons as KB signals. "
            "Re-run the installer to refresh the session-wide defaults."
        )
    if global_agents_text and "subagent/delegation usage" not in global_agents_text:
        issues.append(
            "Global AGENTS defaults do not mention subagent/delegation usage lessons as KB signals. "
            "Re-run the installer to refresh the session-wide defaults."
        )
    if global_agents_text and "phase-change KB checkpoints" not in global_agents_text:
        issues.append(
            "Global AGENTS defaults do not mention phase-change KB checkpoints for long mixed tasks. "
            "Re-run the installer to refresh the session-wide defaults."
        )

    shell_bin = Path(
        str(shell_tools_manifest.get("shell_bin_dir", "") or codex_shell_bin_dir())
    ).expanduser()
    git_shim_path = Path(
        str(shell_tools_manifest.get("git_shim_path", "") or (shell_bin / "git.cmd"))
    ).expanduser()
    rg_path = Path(
        str(shell_tools_manifest.get("rg_path", "") or (shell_bin / "rg.exe"))
    ).expanduser()
    shell_tools_required = (
        platform.system().lower() == "windows"
        or (
            bool(shell_tools_manifest.get("git_shim_installed"))
            and bool(shell_tools_manifest.get("rg_installed"))
        )
    )
    if shell_tools_required:
        if not git_shim_path.exists():
            issues.append(
                f"Codex shell Git shim is missing: {git_shim_path}. "
                "Re-run the installer to restore stable Git command resolution."
            )
        if not rg_path.exists():
            issues.append(
                f"Codex shell rg binary is missing: {rg_path}. "
                "Re-run the installer to restore stable ripgrep command resolution."
            )
    else:
        warnings.append(
            "Codex shell git/rg shim check skipped because this non-Windows install "
            "did not create Windows shell shim files."
        )

    expected_repo_root = repo_root or (Path(manifest_root_raw) if manifest_root_raw else Path("."))
    maintenance_skill_checks: list[dict[str, Any]] = []
    for spec in MAINTENANCE_SKILL_SPECS:
        skill_name = spec["name"]
        source_dir = maintenance_skill_source_dir(expected_repo_root, skill_name)
        install_dir = maintenance_skill_install_dir(skill_name, home)
        source_skill_path = source_dir / "SKILL.md"
        install_skill_path = install_dir / "SKILL.md"
        install_openai_path = install_dir / "agents" / "openai.yaml"
        issues_for_skill: list[str] = []
        if not source_skill_path.exists():
            issues_for_skill.append(f"Repository maintenance skill source is missing: {source_skill_path}")
            source_skill_text = ""
        else:
            try:
                source_skill_text = source_skill_path.read_text(encoding="utf-8")
            except OSError as exc:
                issues_for_skill.append(f"Repository maintenance skill source could not be read: {exc}")
                source_skill_text = ""
        if not install_skill_path.exists():
            issues_for_skill.append(f"Installed maintenance skill file is missing: {install_skill_path}")
            skill_text = ""
        else:
            try:
                skill_text = install_skill_path.read_text(encoding="utf-8")
            except OSError as exc:
                issues_for_skill.append(f"Installed maintenance skill could not be read: {exc}")
                skill_text = ""
        if not install_openai_path.exists():
            issues_for_skill.append(f"Installed maintenance skill openai.yaml is missing: {install_openai_path}")
            skill_openai_text = ""
        else:
            try:
                skill_openai_text = install_openai_path.read_text(encoding="utf-8")
            except OSError as exc:
                issues_for_skill.append(f"Installed maintenance skill openai.yaml could not be read: {exc}")
                skill_openai_text = ""
        if skill_text:
            if f"name: {skill_name}" not in skill_text:
                issues_for_skill.append(f"Installed maintenance skill {skill_name} has the wrong frontmatter name.")
            if "[TODO" in skill_text:
                issues_for_skill.append(f"Installed maintenance skill {skill_name} still contains TODO scaffolding.")
            if str(spec["prompt_marker"]) not in skill_text:
                issues_for_skill.append(
                    f"Installed maintenance skill {skill_name} is missing prompt marker {spec['prompt_marker']}."
                )
            if source_skill_text and skill_text != source_skill_text:
                issues_for_skill.append(
                    f"Installed maintenance skill {skill_name} differs from repository source. "
                    "Re-run the installer to refresh it."
                )
        if skill_openai_text:
            if "allow_implicit_invocation: false" not in skill_openai_text:
                issues_for_skill.append(
                    f"Installed maintenance skill {skill_name} should disable implicit invocation."
                )
            if f"${skill_name}" not in skill_openai_text:
                issues_for_skill.append(
                    f"Installed maintenance skill {skill_name} default prompt should mention ${skill_name}."
                )
        if issues_for_skill:
            issues.extend(issues_for_skill)
        maintenance_skill_checks.append(
            {
                "name": skill_name,
                "source_path": str(source_dir),
                "install_path": str(install_dir),
                "exists": install_skill_path.exists(),
                "openai_exists": install_openai_path.exists(),
                "automation_id": spec["automation_id"],
                "issues": issues_for_skill,
            }
        )

    automation_checks: list[dict[str, Any]] = []
    automation_runtime = resolve_automation_runtime(home)
    for spec in REPO_AUTOMATION_SPECS:
        expected = _automation_spec_payload(spec, expected_repo_root, codex_home=home)
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
            if str(payload.get("schedule_policy", "") or "") != expected["schedule_policy"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should record schedule_policy={expected['schedule_policy']}."
                )
            if str(payload.get("schedule_window", "") or "") != expected["schedule_window"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should record schedule_window={expected['schedule_window']}."
                )
            if str(payload.get("model", "") or "") != expected["model"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use model={expected['model']} from policy={expected['model_policy']}."
                )
            if str(payload.get("reasoning_effort", "") or "") != expected["reasoning_effort"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should use reasoning_effort={expected['reasoning_effort']} from policy={expected['reasoning_effort_policy']}."
                )
            if str(payload.get("model_policy", "") or "") != expected["model_policy"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} should record model_policy={expected['model_policy']}."
                )
            if str(payload.get("reasoning_effort_policy", "") or "") != expected["reasoning_effort_policy"]:
                issues_for_automation.append(
                    "Automation "
                    f"{expected['id']} should record reasoning_effort_policy={expected['reasoning_effort_policy']}."
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
            if prompt_text != expected["prompt"]:
                issues_for_automation.append(
                    f"Automation {expected['id']} prompt differs from the repository spec."
                )
            expected_skill_name = str(spec.get("skill_name", "") or "")
            if expected_skill_name and f"${expected_skill_name}" not in prompt_text:
                issues_for_automation.append(
                    f"Automation {expected['id']} prompt must explicitly invoke ${expected_skill_name}."
                )
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
            if expected["id"] == "kb-dream":
                for marker in (
                    "docs/maintenance_agent_worldview.md",
                    "shared maintenance-agent worldview",
                    "generated preflight",
                    "preflight entries retrieved",
                    "bounded route-deduped batch",
                    "experiments executed in order",
                    "report a no-op",
                    "execution-plan checkpoint status",
                    "safety tier and rollback plan",
                    "sandbox experiment artifacts",
                    "retrieval-ab sandbox paths",
                    "allowed writes",
                    "evidence grades",
                    "validation results",
                    "prior Dream report",
                    "structured Sleep handoff",
                    "suggested_action update-card",
                    "external-system experiments proposal-only",
                    "Sleep handoff",
                    "Sleep/Architect handoff",
                ):
                    if marker not in prompt_text:
                        issues_for_automation.append(
                            f"Automation kb-dream prompt is missing dream lifecycle marker: {marker}"
                        )
            if expected["id"] == "kb-sleep" and "MAINTENANCE_PROMPT.md" not in prompt_text:
                issues_for_automation.append(
                    "Automation kb-sleep prompt must reference MAINTENANCE_PROMPT.md."
                )
            if expected["id"] == "kb-sleep":
                for marker in (
                    "visible sleep execution plan",
                    "shared maintenance-agent worldview",
                    "checkpoint statuses",
                    "kb_lane_status.py",
                    "--wait-clear",
                    "wait and recheck",
                    "sleep self-preflight",
                    "system/knowledge-library/maintenance",
                    "mandatory similar-card merge checkpoint",
                    "mandatory overloaded-card split checkpoint",
                    "organization Skill bundle consolidation checkpoint",
                    "latest approved version by version_time",
                    "skip-with-reason decisions",
                    "mechanical apply eligibility",
                    "high-volume lanes proposal-only",
                    "dream_validation_summary",
                    "every safe checkpoint",
                    "supported low-risk repairs",
                    "rerun the relevant validation",
                    "sleep postflight check",
                    "structured maintenance observation",
                    "selected action keys",
                    "--action-key",
                    "final AI-authored zh-CN",
                    "route/path display labels",
                    "do not run separate mid-run translation cleanup",
                    "--run-id <run_id>",
                    "same run id",
                    "status completed",
                    "recursively consolidating",
                ):
                    if marker not in prompt_text:
                        issues_for_automation.append(
                            f"Automation kb-sleep prompt is missing sleep lifecycle marker: {marker}"
                        )
            if expected["id"] == "kb-architect" and "kb_architect.py" not in prompt_text:
                issues_for_automation.append("Automation kb-architect prompt must reference kb_architect.py.")
            if expected["id"] == "kb-architect":
                for marker in (
                    "docs/maintenance_agent_worldview.md",
                    "shared maintenance-agent worldview",
                    "visible Architect execution plan",
                    "checkpoint statuses",
                    "Architect self-preflight",
                    "system/knowledge-library/maintenance",
                    "scripts/khaos_brain_update.py --architect-check --json",
                    "$khaos-brain-update",
                    "software update gate result",
                    "Evidence, Impact, and Safety",
                    "human-review status",
                    "long-observation items as watching",
                    "KB operating mechanisms rather than card content",
                    "do not rewrite trusted cards or promote candidates",
                    "execution packet is agent-ready",
                    "sandbox_apply.sandbox_ready=true",
                    "planned sandbox path",
                    "allowed/disallowed writes",
                    "merge/block decision fields",
                    "choose at most one",
                    "instead of repeatedly reporting",
                    "selected_sandbox_trial",
                    "trial_result.json",
                    "--record-trial-result",
                    "sandbox-ready packets",
                    "blocked execution states",
                    "validation bundle",
                    "postflight observation status",
                    "system-readable maintenance rollup",
                    "content-boundary",
                    "install-sync status",
                ):
                    if marker not in prompt_text:
                        issues_for_automation.append(
                            f"Automation kb-architect prompt is missing architect lifecycle marker: {marker}"
                        )
            if expected["id"] == "kb-org-contribute":
                for marker in (
                    "scripts/kb_org_outbox.py",
                    "desktop settings",
                    "organization mode",
                    "validated organization repository",
                    "successful no-op",
                    "sync the organization mirror first",
                    "KB preflight",
                    "content-hash-gated outbox",
                    "every exchanged hash",
                    "downloaded, used, absorbed, exported, uploaded",
                    "prepare an import branch",
                    "push eligible import proposals automatically",
                    "org-kb:auto-merge",
                    "KB postflight",
                ):
                    if marker not in prompt_text:
                        issues_for_automation.append(
                            f"Automation kb-org-contribute prompt is missing organization contribution marker: {marker}"
                        )
            if expected["id"] == "kb-org-maintenance":
                for marker in (
                    "scripts/kb_org_maintainer.py",
                    "organization-level Sleep-like maintenance",
                    "desktop settings",
                    "organization maintenance participation",
                    "successful no-op",
                    "KB preflight",
                    "organization candidate intake checkpoint",
                    "content-hash checkpoint",
                    "mandatory organization similar-card merge checkpoint",
                    "mandatory organization overloaded-card split checkpoint",
                    "candidate decision checkpoint",
                    "Skill safety checkpoint",
                    "Skill bundle version checkpoint",
                    "decision-apply checkpoint",
                    "post-apply organization check",
                    "GitHub merge-readiness checkpoint",
                    "organization-review",
                    "Skill registry",
                    "duplicate content hashes",
                    "duplicate entry ids",
                    "bundle_id",
                    "original-author updates",
                    "latest approved version by version_time",
                    "do not auto-install",
                    "organization Sleep decision set",
                    "organization-review as guidance rather than an apply gate",
                    "exact selected action ids",
                    "post-apply check result",
                    "maintenance branch, PR, push, and auto-merge-label result",
                    "KB postflight",
                ):
                    if marker not in prompt_text:
                        issues_for_automation.append(
                            f"Automation kb-org-maintenance prompt is missing organization maintenance marker: {marker}"
                        )
        if issues_for_automation:
            issues.extend(issues_for_automation)
        automation_checks.append(
            {
                "id": spec["id"],
                "path": str(path),
                "exists": path.exists(),
                "rrule": expected["rrule"],
                "schedule_policy": expected["schedule_policy"],
                "schedule_window": expected["schedule_window"],
                "issues": issues_for_automation,
            }
        )

    if not managed_automations:
        warnings.append(
            "Install manifest does not record the repository-managed KB automations. "
            "Re-run the installer to refresh automation setup."
        )
    if not managed_maintenance_skills:
        warnings.append(
            "Install manifest does not record the repository-managed KB skills. "
            "Re-run the installer to refresh skill setup."
        )

    automation_issue_map = {item["id"]: item["issues"] for item in automation_checks}
    maintenance_skill_ok = all(not item["issues"] for item in maintenance_skill_checks)
    global_skill_present = skill_path.exists() and launcher_path.exists() and openai_path.exists()
    global_skill_implicit = bool(openai_text and "allow_implicit_invocation: true" in openai_text)
    global_skill_postflight = bool(
        openai_text
        and "record a KB follow-up observation" in openai_text
        and "required default preflight" in openai_text
    )
    global_skill_skill_usage = bool(openai_text and "skill/plugin usage lesson" in openai_text)
    global_skill_subagent_usage = bool(openai_text and "subagent/delegation usage lesson" in openai_text)
    global_skill_phase_checkpoints = bool(openai_text and "phase-change KB checkpoints" in openai_text)
    global_agents_present = global_agents.exists()
    global_agents_managed = bool(
        global_agents_text
        and GLOBAL_AGENTS_BEGIN in global_agents_text
        and GLOBAL_AGENTS_END in global_agents_text
    )
    global_agents_preflight = bool(global_agents_text and "$predictive-kb-preflight" in global_agents_text)
    global_agents_postflight = bool(global_agents_text and "explicit KB postflight check" in global_agents_text)
    global_agents_skill_usage = bool(global_agents_text and "skill/plugin usage" in global_agents_text)
    global_agents_subagent_usage = bool(global_agents_text and "subagent/delegation usage" in global_agents_text)
    global_agents_phase_checkpoints = bool(global_agents_text and "phase-change KB checkpoints" in global_agents_text)
    kb_sleep_ok = not automation_issue_map.get("kb-sleep")
    kb_dream_ok = not automation_issue_map.get("kb-dream")
    kb_architect_ok = not automation_issue_map.get("kb-architect")
    kb_org_contribute_ok = not automation_issue_map.get("kb-org-contribute")
    kb_org_maintenance_ok = not automation_issue_map.get("kb-org-maintenance")
    automation_check_map = {item["id"]: item for item in automation_checks}
    codex_shell_tools_ok = not shell_tools_required or (git_shim_path.exists() and rg_path.exists())
    strong_defaults_ok = (
        global_skill_implicit
        and global_skill_postflight
        and global_agents_managed
        and global_agents_preflight
        and global_agents_postflight
        and global_skill_skill_usage
        and global_agents_skill_usage
        and global_skill_subagent_usage
        and global_agents_subagent_usage
        and global_skill_phase_checkpoints
        and global_agents_phase_checkpoints
        and maintenance_skill_ok
    )
    checklist = [
        _checklist_item(
            "global_skill_files",
            "Global predictive KB skill and launcher are installed",
            global_skill_present,
            f"skill_path={skill_path}; launcher_path={launcher_path}; openai_path={openai_path}",
        ),
        _checklist_item(
            "global_skill_implicit",
            "Global predictive KB skill enables implicit invocation",
            global_skill_implicit,
            f"openai_path={openai_path}",
        ),
        _checklist_item(
            "global_skill_postflight",
            "Global predictive KB prompt requires KB preflight and postflight reminders",
            global_skill_postflight,
            f"openai_path={openai_path}",
        ),
        _checklist_item(
            "global_skill_skill_usage",
            "Global predictive KB prompt treats skill/plugin lessons as recordable KB signals",
            global_skill_skill_usage,
            f"openai_path={openai_path}",
        ),
        _checklist_item(
            "global_skill_subagent_usage",
            "Global predictive KB prompt treats subagent/delegation lessons as recordable KB signals",
            global_skill_subagent_usage,
            f"openai_path={openai_path}",
        ),
        _checklist_item(
            "global_skill_phase_checkpoints",
            "Global predictive KB prompt requires phase-change KB checkpoints for long mixed tasks",
            global_skill_phase_checkpoints,
            f"openai_path={openai_path}",
        ),
        _checklist_item(
            "global_agents_file",
            "Global AGENTS defaults file exists",
            global_agents_present,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_block",
            "Global AGENTS contains the managed predictive KB defaults block",
            global_agents_managed,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_preflight",
            "Global AGENTS defaults mention $predictive-kb-preflight",
            global_agents_preflight,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_postflight",
            "Global AGENTS defaults require an explicit KB postflight check",
            global_agents_postflight,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_skill_usage",
            "Global AGENTS defaults treat skill/plugin lessons as recordable KB signals",
            global_agents_skill_usage,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_subagent_usage",
            "Global AGENTS defaults treat subagent/delegation lessons as recordable KB signals",
            global_agents_subagent_usage,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "global_agents_phase_checkpoints",
            "Global AGENTS defaults require phase-change KB checkpoints for long mixed tasks",
            global_agents_phase_checkpoints,
            f"global_agents_path={global_agents}",
        ),
        _checklist_item(
            "repo_maintenance_skills",
            "Repository-managed KB maintenance, organization, and update skills are installed",
            maintenance_skill_ok,
            "; ".join(f"{item['name']}={item['install_path']}" for item in maintenance_skill_checks),
        ),
        _checklist_item(
            "kb_sleep_automation",
            "KB Sleep automation is installed and matches the repository spec",
            kb_sleep_ok,
            f"path={automation_toml_path('kb-sleep', home)}",
        ),
        _checklist_item(
            "kb_dream_automation",
            "KB Dream automation is installed and matches the repository spec",
            kb_dream_ok,
            f"path={automation_toml_path('kb-dream', home)}",
        ),
        _checklist_item(
            "kb_architect_automation",
            "KB Architect automation is installed and matches the repository spec",
            kb_architect_ok,
            f"path={automation_toml_path('kb-architect', home)}",
        ),
        _checklist_item(
            "kb_org_contribute_automation",
            "KB Organization Contribute automation is installed and matches the repository spec",
            kb_org_contribute_ok,
            (
                f"path={automation_toml_path('kb-org-contribute', home)}; "
                f"rrule={automation_check_map.get('kb-org-contribute', {}).get('rrule', '')}; "
                f"window={automation_check_map.get('kb-org-contribute', {}).get('schedule_window', '')}"
            ),
        ),
        _checklist_item(
            "kb_org_maintenance_automation",
            "KB Organization Maintenance automation is installed and matches the repository spec",
            kb_org_maintenance_ok,
            (
                f"path={automation_toml_path('kb-org-maintenance', home)}; "
                f"rrule={automation_check_map.get('kb-org-maintenance', {}).get('rrule', '')}; "
                f"window={automation_check_map.get('kb-org-maintenance', {}).get('schedule_window', '')}"
            ),
        ),
        _checklist_item(
            "codex_shell_tools",
            "Codex shell git/rg tools are installed in a stable user-level bin",
            codex_shell_tools_ok,
            (
                f"shell_bin={shell_bin}; git_shim={git_shim_path}; rg_path={rg_path}; "
                f"required={shell_tools_required}"
            ),
        ),
        _checklist_item(
            "strong_session_defaults",
            "The strongest available session-wide KB defaults layer is installed",
            strong_defaults_ok,
            f"global_agents_path={global_agents}; openai_path={openai_path}",
        ),
    ]

    return {
        "ok": not issues,
        "repo_root": requested_repo_root,
        "manifest_repo_root": resolved_manifest_root,
        "codex_home": str(home),
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_path),
        "launcher_path": str(launcher_path),
        "openai_path": str(openai_path),
        "global_agents_path": str(global_agents),
        "install_state_path": str(install_state_path(home)),
        "env_var_name": KB_ROOT_ENV_VAR,
        "env_var_value": env_value,
        "maintenance_skill_names": list(MAINTENANCE_SKILL_NAMES),
        "shell_tools": {
            "shell_bin_dir": str(shell_bin),
            "git_shim_path": str(git_shim_path),
            "rg_path": str(rg_path),
            "required": shell_tools_required,
        },
        "automation_runtime": automation_runtime,
        "checklist": checklist,
        "maintenance_skill_checks": maintenance_skill_checks,
        "automation_checks": automation_checks,
        "issues": issues,
        "warnings": warnings,
    }
