from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_kb.config import install_state_path
from local_kb.install import (
    AUTOMATION_MODEL_ENV_VAR,
    AUTOMATION_REASONING_EFFORT_ENV_VAR,
    ORG_CONTRIBUTE_WINDOW,
    ORG_MAINTENANCE_WINDOW,
    REPO_AUTOMATION_SPECS,
    automation_rrule_for_spec,
    build_installation_check,
    global_agents_path,
    install_codex_integration,
    resolve_automation_runtime,
)


def write_cmd(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@echo off\r\n{body}\r\n", encoding="utf-8")


def rrule_local_minute(rrule: str) -> int:
    hour = re.search(r"BYHOUR=(\d+)", rrule)
    minute = re.search(r"BYMINUTE=(\d+)", rrule)
    if not hour or not minute:
        raise AssertionError(f"rrule does not contain BYHOUR/BYMINUTE: {rrule}")
    return int(hour.group(1)) * 60 + int(minute.group(1))


def toml_string_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)} = \"([^\"]*)\"$", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"toml text does not contain string value for {key}")
    return match.group(1)


class CodexInstallTests(unittest.TestCase):
    def test_sleep_maintenance_prompt_requires_self_preflight_and_postflight(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        prompt_text = (
            repo_root / ".agents" / "skills" / "local-kb-retrieve" / "MAINTENANCE_PROMPT.md"
        ).read_text(encoding="utf-8")

        self.assertIn("visible sleep execution plan", prompt_text)
        self.assertIn("checkpoint", prompt_text)
        self.assertIn("completed, skipped with reason, or blocked", prompt_text)
        self.assertIn("try the supported repair path", prompt_text)
        self.assertIn("sleep self-preflight", prompt_text)
        self.assertIn("system/knowledge-library/maintenance", prompt_text)
        self.assertIn("final sleep postflight check", prompt_text)
        self.assertIn("structured observation", prompt_text)
        self.assertIn("Do not rerun `kb_consolidate.py`", prompt_text)
        self.assertIn("final AI zh-CN display completion checkpoint", prompt_text)
        self.assertIn("route_segment_labels", prompt_text)
        self.assertIn("Do not run separate mid-run translation cleanup", prompt_text)

    def test_install_writes_global_skill_launcher_and_manifest(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            shell_bin_dir = Path(tmp_dir) / "shell-bin"
            git_real = Path(tmp_dir) / "tool-src" / "git-real.cmd"
            rg_source = Path(tmp_dir) / "tool-src" / "rg-source.exe"
            write_cmd(git_real, "echo git version test")
            rg_source.parent.mkdir(parents=True, exist_ok=True)
            rg_source.write_bytes(b"rg-binary")

            payload = install_codex_integration(
                repo_root=repo_root,
                codex_home=codex_home,
                shell_bin_dir=shell_bin_dir,
                git_executable=git_real,
                rg_source=rg_source,
                persist_user_shell_path=False,
            )
            automation_runtime = resolve_automation_runtime(codex_home)

            self.assertTrue((codex_home / "skills" / "predictive-kb-preflight" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "predictive-kb-preflight" / "kb_launch.py").exists())
            self.assertTrue((codex_home / "predictive-kb" / "install.json").exists())
            self.assertTrue((codex_home / "automations" / "kb-sleep" / "automation.toml").exists())
            self.assertTrue((codex_home / "automations" / "kb-dream" / "automation.toml").exists())
            self.assertTrue((codex_home / "automations" / "kb-architect" / "automation.toml").exists())
            self.assertTrue((codex_home / "automations" / "kb-org-contribute" / "automation.toml").exists())
            self.assertTrue((codex_home / "automations" / "kb-org-maintenance" / "automation.toml").exists())
            self.assertTrue((codex_home / "skills" / "kb-sleep-maintenance" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "kb-dream-pass" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "kb-architect-pass" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "kb-organization-contribute" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "kb-organization-maintenance" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "khaos-brain-update" / "SKILL.md").exists())
            self.assertTrue(global_agents_path(codex_home).exists())
            self.assertTrue((shell_bin_dir / "git.cmd").exists())
            self.assertTrue((shell_bin_dir / "rg.exe").exists())
            self.assertEqual(payload["repo_root"], str(repo_root))
            self.assertEqual(
                payload["maintenance_skill_names"],
                [
                    "kb-sleep-maintenance",
                    "kb-dream-pass",
                    "kb-architect-pass",
                    "kb-organization-contribute",
                    "kb-organization-maintenance",
                    "khaos-brain-update",
                ],
            )
            self.assertEqual(
                payload["automation_ids"],
                [
                    "kb-sleep",
                    "kb-dream",
                    "kb-architect",
                    "kb-org-contribute",
                    "kb-org-maintenance",
                ],
            )
            self.assertEqual(payload["automation_runtime"], automation_runtime)
            self.assertEqual(payload["shell_tools"]["shell_bin_dir"], str(shell_bin_dir))
            self.assertTrue(payload["shell_tools"]["git_shim_installed"])
            self.assertTrue(payload["shell_tools"]["rg_installed"])
            self.assertFalse(payload["shell_tools"]["issues"])

            skill_text = (codex_home / "skills" / "predictive-kb-preflight" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("--route-hint", skill_text)
            self.assertIn("search-style calls without the explicit `search` subcommand", skill_text)
            self.assertIn("Skill and plugin usage lessons count as reusable signals", skill_text)
            self.assertIn("Subagent and delegation usage lessons count as reusable signals", skill_text)
            self.assertIn("phase-change KB checkpoints", skill_text)
            self.assertIn("repeated same-type subtask", skill_text)

            openai_text = (
                codex_home / "skills" / "predictive-kb-preflight" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("allow_implicit_invocation: true", openai_text)
            self.assertIn("record a KB follow-up observation", openai_text)
            self.assertIn("required default preflight", openai_text)
            self.assertIn("skill/plugin usage lesson", openai_text)
            self.assertIn("subagent/delegation usage lesson", openai_text)
            self.assertIn("phase-change KB checkpoints", openai_text)

            global_agents_text = global_agents_path(codex_home).read_text(encoding="utf-8")
            self.assertIn("BEGIN MANAGED PREDICTIVE KB DEFAULTS", global_agents_text)
            self.assertIn("$predictive-kb-preflight", global_agents_text)
            self.assertIn("explicit KB postflight check", global_agents_text)
            self.assertIn("skill/plugin usage", global_agents_text)
            self.assertIn("subagent/delegation usage", global_agents_text)
            self.assertIn("phase-change KB checkpoints", global_agents_text)

            sleep_skill_text = (codex_home / "skills" / "kb-sleep-maintenance" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            sleep_skill_openai = (
                codex_home / "skills" / "kb-sleep-maintenance" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: kb-sleep-maintenance", sleep_skill_text)
            self.assertIn("docs/maintenance_agent_worldview.md", sleep_skill_text)
            self.assertIn("MAINTENANCE_PROMPT.md", sleep_skill_text)
            self.assertIn("mandatory similar-card merge checkpoint", sleep_skill_text)
            self.assertIn("mandatory overloaded-card split checkpoint", sleep_skill_text)
            self.assertIn("organization Skill bundle consolidation checkpoint", sleep_skill_text)
            self.assertIn("Do not skip the merge, split, or Skill bundle consolidation checkpoint itself", sleep_skill_text)
            self.assertIn("mechanical apply eligibility", sleep_skill_text)
            self.assertIn("final AI-authored zh-CN display completion checkpoint", sleep_skill_text)
            self.assertIn("route/path display labels", sleep_skill_text)
            self.assertIn("--status completed --run-id <run_id> --json", sleep_skill_text)
            self.assertIn("allow_implicit_invocation: false", sleep_skill_openai)
            self.assertIn("$kb-sleep-maintenance", sleep_skill_openai)

            dream_skill_text = (codex_home / "skills" / "kb-dream-pass" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            dream_skill_openai = (
                codex_home / "skills" / "kb-dream-pass" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: kb-dream-pass", dream_skill_text)
            self.assertIn("docs/maintenance_agent_worldview.md", dream_skill_text)
            self.assertIn("DREAM_PROMPT.md", dream_skill_text)
            self.assertIn("sandbox experiment artifacts", dream_skill_text)
            self.assertIn("allow_implicit_invocation: false", dream_skill_openai)
            self.assertIn("$kb-dream-pass", dream_skill_openai)

            architect_skill_text = (codex_home / "skills" / "kb-architect-pass" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            architect_skill_openai = (
                codex_home / "skills" / "kb-architect-pass" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: kb-architect-pass", architect_skill_text)
            self.assertIn("docs/maintenance_agent_worldview.md", architect_skill_text)
            self.assertIn("ARCHITECT_PROMPT.md", architect_skill_text)
            self.assertIn("sandbox_apply.sandbox_ready=true", architect_skill_text)
            self.assertIn("allow_implicit_invocation: false", architect_skill_openai)
            self.assertIn("$kb-architect-pass", architect_skill_openai)

            org_contribute_skill_text = (
                codex_home / "skills" / "kb-organization-contribute" / "SKILL.md"
            ).read_text(encoding="utf-8")
            org_contribute_skill_openai = (
                codex_home / "skills" / "kb-organization-contribute" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: kb-organization-contribute", org_contribute_skill_text)
            self.assertIn("scripts/kb_org_outbox.py", org_contribute_skill_text)
            self.assertIn("card-bound Skill bundle", org_contribute_skill_text)
            self.assertIn("local latest version for that bundle", org_contribute_skill_text)
            self.assertIn("allow_implicit_invocation: false", org_contribute_skill_openai)
            self.assertIn("$kb-organization-contribute", org_contribute_skill_openai)

            org_maintenance_skill_text = (
                codex_home / "skills" / "kb-organization-maintenance" / "SKILL.md"
            ).read_text(encoding="utf-8")
            org_maintenance_skill_openai = (
                codex_home / "skills" / "kb-organization-maintenance" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: kb-organization-maintenance", org_maintenance_skill_text)
            self.assertIn("scripts/kb_org_maintainer.py", org_maintenance_skill_text)
            self.assertIn("organization-level Sleep-like maintenance", org_maintenance_skill_text)
            self.assertIn("organization candidate intake checkpoint", org_maintenance_skill_text)
            self.assertIn("mandatory organization similar-card merge checkpoint", org_maintenance_skill_text)
            self.assertIn("mandatory organization overloaded-card split checkpoint", org_maintenance_skill_text)
            self.assertIn("Skill safety checkpoint", org_maintenance_skill_text)
            self.assertIn("Skill bundle version checkpoint", org_maintenance_skill_text)
            self.assertIn("latest approved version by `version_time`", org_maintenance_skill_text)
            self.assertIn("GitHub merge-readiness checkpoint", org_maintenance_skill_text)
            self.assertIn("organization-review", org_maintenance_skill_text)
            self.assertIn("allow_implicit_invocation: false", org_maintenance_skill_openai)
            self.assertIn("$kb-organization-maintenance", org_maintenance_skill_openai)

            update_skill_text = (codex_home / "skills" / "khaos-brain-update" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            update_skill_openai = (
                codex_home / "skills" / "khaos-brain-update" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("name: khaos-brain-update", update_skill_text)
            self.assertIn("scripts/install_codex_kb.py", update_skill_text)
            self.assertIn("Force-close Khaos Brain desktop UI processes", update_skill_text)
            self.assertIn("Do not require KB preflight", update_skill_text)
            self.assertIn("fast-forward", update_skill_text)
            self.assertIn("Do not run `git reset --hard`", update_skill_text)
            self.assertIn("allow_implicit_invocation: false", update_skill_openai)
            self.assertIn("$khaos-brain-update", update_skill_openai)

            sleep_toml = (codex_home / "automations" / "kb-sleep" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', sleep_toml)
            self.assertIn("$kb-sleep-maintenance", sleep_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=12;BYMINUTE=0"', sleep_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', sleep_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', sleep_toml)
            self.assertIn('model_policy = "strongest-available"', sleep_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', sleep_toml)
            self.assertIn("docs/maintenance_agent_worldview.md", sleep_toml)
            self.assertIn("shared maintenance-agent worldview", sleep_toml)
            self.assertIn("visible sleep execution plan", sleep_toml)
            self.assertIn("checkpoint statuses", sleep_toml)
            self.assertIn("every safe checkpoint", sleep_toml)
            self.assertIn("supported low-risk repairs", sleep_toml)
            self.assertIn("rerun the relevant validation", sleep_toml)
            self.assertIn("sleep self-preflight", sleep_toml)
            self.assertIn("system/knowledge-library/maintenance", sleep_toml)
            self.assertIn("mandatory similar-card merge checkpoint", sleep_toml)
            self.assertIn("mandatory overloaded-card split checkpoint", sleep_toml)
            self.assertIn("organization Skill bundle consolidation checkpoint", sleep_toml)
            self.assertIn("latest approved version by version_time", sleep_toml)
            self.assertIn("skip-with-reason decisions", sleep_toml)
            self.assertIn("mechanical apply eligibility", sleep_toml)
            self.assertIn("high-volume lanes proposal-only", sleep_toml)
            self.assertIn("sleep postflight check", sleep_toml)
            self.assertIn("structured maintenance observation", sleep_toml)
            self.assertIn("recursively consolidating", sleep_toml)
            self.assertIn("selected action keys", sleep_toml)
            self.assertIn("--action-key", sleep_toml)
            self.assertIn("final AI-authored zh-CN", sleep_toml)
            self.assertIn("route/path display labels", sleep_toml)
            self.assertIn("do not run separate mid-run translation cleanup", sleep_toml)
            self.assertIn("same run id", sleep_toml)
            self.assertIn("--status completed --run-id <run_id> --json", sleep_toml)
            self.assertIn(str(repo_root).replace("\\", "\\\\"), sleep_toml)

            dream_toml = (codex_home / "automations" / "kb-dream" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', dream_toml)
            self.assertIn("$kb-dream-pass", dream_toml)
            self.assertIn('kb_dream.py', dream_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=13;BYMINUTE=0"', dream_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', dream_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', dream_toml)
            self.assertIn('model_policy = "strongest-available"', dream_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', dream_toml)
            self.assertIn("docs/maintenance_agent_worldview.md", dream_toml)
            self.assertIn("shared maintenance-agent worldview", dream_toml)
            self.assertIn("generated preflight", dream_toml)
            self.assertIn("preflight entries retrieved", dream_toml)
            self.assertIn("bounded route-deduped batch", dream_toml)
            self.assertIn("experiments executed in order", dream_toml)
            self.assertIn("report a no-op", dream_toml)
            self.assertIn("execution-plan checkpoint status", dream_toml)
            self.assertIn("safety tier and rollback plan", dream_toml)
            self.assertIn("sandbox experiment artifacts", dream_toml)
            self.assertIn("retrieval-ab sandbox paths", dream_toml)
            self.assertIn("allowed writes", dream_toml)
            self.assertIn("evidence grades", dream_toml)
            self.assertIn("validation results", dream_toml)
            self.assertIn("prior Dream report", dream_toml)
            self.assertIn("external-system experiments proposal-only", dream_toml)
            self.assertIn("Sleep handoff", dream_toml)
            self.assertIn("Sleep/Architect handoff", dream_toml)

            architect_toml = (
                codex_home / "automations" / "kb-architect" / "automation.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', architect_toml)
            self.assertIn("$kb-architect-pass", architect_toml)
            self.assertIn('kb_architect.py', architect_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=14;BYMINUTE=0"', architect_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', architect_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', architect_toml)
            self.assertIn('model_policy = "strongest-available"', architect_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', architect_toml)
            self.assertIn("docs/maintenance_agent_worldview.md", architect_toml)
            self.assertIn("shared maintenance-agent worldview", architect_toml)
            self.assertIn("visible Architect execution plan", architect_toml)
            self.assertIn("checkpoint statuses", architect_toml)
            self.assertIn("Architect self-preflight", architect_toml)
            self.assertIn("system/knowledge-library/maintenance", architect_toml)
            self.assertIn("scripts/khaos_brain_update.py --architect-check --json", architect_toml)
            self.assertIn("$khaos-brain-update", architect_toml)
            self.assertIn("apply_ready=true", architect_toml)
            self.assertIn("software update gate result", architect_toml)
            self.assertIn("Evidence, Impact, and Safety", architect_toml)
            self.assertIn("human-review status", architect_toml)
            self.assertIn("long-observation items as watching", architect_toml)
            self.assertIn("KB operating mechanisms rather than card content", architect_toml)
            self.assertIn("do not rewrite trusted cards or promote candidates", architect_toml)
            self.assertIn("execution packet is agent-ready", architect_toml)
            self.assertIn("sandbox_apply.sandbox_ready=true", architect_toml)
            self.assertIn("planned sandbox path", architect_toml)
            self.assertIn("allowed/disallowed writes", architect_toml)
            self.assertIn("merge/block decision fields", architect_toml)
            self.assertIn("choose at most one", architect_toml)
            self.assertIn("instead of repeatedly reporting", architect_toml)
            self.assertIn("sandbox-ready packets", architect_toml)
            self.assertIn("blocked execution states", architect_toml)
            self.assertIn("validation bundle", architect_toml)
            self.assertIn("postflight observation status", architect_toml)
            self.assertIn("system-readable maintenance rollup", architect_toml)
            self.assertIn("content-boundary", architect_toml)
            self.assertIn("install-sync status", architect_toml)

            org_contribute_toml = (
                codex_home / "automations" / "kb-org-contribute" / "automation.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', org_contribute_toml)
            self.assertIn("$kb-organization-contribute", org_contribute_toml)
            self.assertIn("scripts/kb_org_outbox.py", org_contribute_toml)
            self.assertIn('schedule_policy = "stable-jitter"', org_contribute_toml)
            self.assertIn('schedule_window = "10:00-13:59"', org_contribute_toml)
            org_contribute_minute = rrule_local_minute(toml_string_value(org_contribute_toml, "rrule"))
            self.assertGreaterEqual(org_contribute_minute, ORG_CONTRIBUTE_WINDOW[0])
            self.assertLessEqual(org_contribute_minute, ORG_CONTRIBUTE_WINDOW[1])
            self.assertIn(f'model = "{automation_runtime["model"]}"', org_contribute_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', org_contribute_toml)
            self.assertIn("desktop settings", org_contribute_toml)
            self.assertIn("validated organization repository", org_contribute_toml)
            self.assertIn("successful no-op", org_contribute_toml)
            self.assertIn("sync the organization mirror first", org_contribute_toml)
            self.assertIn("KB preflight", org_contribute_toml)
            self.assertIn("content-hash-gated outbox", org_contribute_toml)
            self.assertIn("every exchanged hash", org_contribute_toml)
            self.assertIn("downloaded, used, absorbed, exported, uploaded", org_contribute_toml)
            self.assertIn("prepare an import branch", org_contribute_toml)
            self.assertIn("push eligible import proposals automatically", org_contribute_toml)
            self.assertIn("org-kb:auto-merge", org_contribute_toml)
            self.assertIn("card-bound Skill bundles", org_contribute_toml)
            self.assertIn("bundle_id", org_contribute_toml)
            self.assertIn("local latest version for that bundle", org_contribute_toml)
            self.assertIn("KB postflight", org_contribute_toml)

            org_maintenance_toml = (
                codex_home / "automations" / "kb-org-maintenance" / "automation.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', org_maintenance_toml)
            self.assertIn("$kb-organization-maintenance", org_maintenance_toml)
            self.assertIn("scripts/kb_org_maintainer.py", org_maintenance_toml)
            self.assertIn("organization-level Sleep-like maintenance", org_maintenance_toml)
            self.assertIn('schedule_policy = "stable-jitter"', org_maintenance_toml)
            self.assertIn('schedule_window = "14:00-16:00"', org_maintenance_toml)
            org_maintenance_minute = rrule_local_minute(toml_string_value(org_maintenance_toml, "rrule"))
            self.assertGreaterEqual(org_maintenance_minute, ORG_MAINTENANCE_WINDOW[0])
            self.assertLessEqual(org_maintenance_minute, ORG_MAINTENANCE_WINDOW[1])
            self.assertIn(f'model = "{automation_runtime["model"]}"', org_maintenance_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', org_maintenance_toml)
            self.assertIn("desktop settings", org_maintenance_toml)
            self.assertIn("organization maintenance participation", org_maintenance_toml)
            self.assertIn("shared exchange layer", org_maintenance_toml)
            self.assertIn("same editorial posture as local Sleep", org_maintenance_toml)
            self.assertIn("successful no-op", org_maintenance_toml)
            self.assertIn("KB preflight", org_maintenance_toml)
            self.assertIn("organization candidate intake checkpoint", org_maintenance_toml)
            self.assertIn("content-hash checkpoint", org_maintenance_toml)
            self.assertIn("mandatory organization similar-card merge checkpoint", org_maintenance_toml)
            self.assertIn("mandatory organization overloaded-card split checkpoint", org_maintenance_toml)
            self.assertIn("candidate decision checkpoint", org_maintenance_toml)
            self.assertIn("Skill safety checkpoint", org_maintenance_toml)
            self.assertIn("Skill bundle version checkpoint", org_maintenance_toml)
            self.assertIn("decision-apply checkpoint", org_maintenance_toml)
            self.assertIn("post-apply organization check", org_maintenance_toml)
            self.assertIn("GitHub merge-readiness checkpoint", org_maintenance_toml)
            self.assertIn("organization-review", org_maintenance_toml)
            self.assertIn("Skill registry", org_maintenance_toml)
            self.assertIn("duplicate content hashes", org_maintenance_toml)
            self.assertIn("duplicate entry ids", org_maintenance_toml)
            self.assertIn("bundle_id", org_maintenance_toml)
            self.assertIn("original-author updates", org_maintenance_toml)
            self.assertIn("latest approved version by version_time", org_maintenance_toml)
            self.assertIn("do not auto-install", org_maintenance_toml)
            self.assertIn("organization Sleep decision set", org_maintenance_toml)
            self.assertIn("organization-review as guidance rather than an apply gate", org_maintenance_toml)
            self.assertIn("exact selected action ids", org_maintenance_toml)
            self.assertIn("post-apply check result", org_maintenance_toml)
            self.assertIn("maintenance branch, PR, push, and auto-merge-label result", org_maintenance_toml)
            self.assertIn("KB postflight", org_maintenance_toml)

            check = build_installation_check(repo_root=repo_root, codex_home=codex_home)
            self.assertTrue(check["ok"], check["issues"])
            self.assertEqual(check["automation_runtime"], automation_runtime)
            self.assertEqual(
                check["maintenance_skill_names"],
                [
                    "kb-sleep-maintenance",
                    "kb-dream-pass",
                    "kb-architect-pass",
                    "kb-organization-contribute",
                    "kb-organization-maintenance",
                    "khaos-brain-update",
                ],
            )
            self.assertEqual(
                [item["name"] for item in check["maintenance_skill_checks"]],
                [
                    "kb-sleep-maintenance",
                    "kb-dream-pass",
                    "kb-architect-pass",
                    "kb-organization-contribute",
                    "kb-organization-maintenance",
                    "khaos-brain-update",
                ],
            )
            self.assertEqual(
                [item["id"] for item in check["automation_checks"]],
                [
                    "kb-sleep",
                    "kb-dream",
                    "kb-architect",
                    "kb-org-contribute",
                    "kb-org-maintenance",
                ],
            )
            checklist = {item["id"]: item for item in check["checklist"]}
            self.assertIn("codex_shell_tools", checklist)
            self.assertIn("strong_session_defaults", checklist)
            self.assertIn("repo_maintenance_skills", checklist)
            self.assertIn("kb_sleep_automation", checklist)
            self.assertIn("kb_architect_automation", checklist)
            self.assertIn("kb_org_contribute_automation", checklist)
            self.assertIn("kb_org_maintenance_automation", checklist)
            self.assertTrue(checklist["codex_shell_tools"]["ok"])
            self.assertTrue(checklist["repo_maintenance_skills"]["ok"])
            self.assertTrue(checklist["kb_sleep_automation"]["ok"])
            self.assertTrue(checklist["kb_architect_automation"]["ok"])
            self.assertTrue(checklist["kb_org_contribute_automation"]["ok"])
            self.assertTrue(checklist["kb_org_maintenance_automation"]["ok"])
            self.assertTrue(checklist["strong_session_defaults"]["ok"])
            self.assertTrue(checklist["global_agents_block"]["ok"])
            self.assertTrue(checklist["global_skill_postflight"]["ok"])
            self.assertTrue(checklist["global_skill_skill_usage"]["ok"])
            self.assertTrue(checklist["global_skill_subagent_usage"]["ok"])
            self.assertTrue(checklist["global_skill_phase_checkpoints"]["ok"])
            self.assertTrue(checklist["global_agents_skill_usage"]["ok"])
            self.assertTrue(checklist["global_agents_subagent_usage"]["ok"])
            self.assertTrue(checklist["global_agents_phase_checkpoints"]["ok"])

    def test_organization_automation_times_are_stable_and_windowed(self) -> None:
        specs = {str(spec["id"]): spec for spec in REPO_AUTOMATION_SPECS}
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir) / "repo"
            identity_path = repo_root / ".local" / "khaos_brain_installation.json"
            identity_path.parent.mkdir(parents=True, exist_ok=True)
            identity_path.write_text(
                json.dumps({"local_installation_id": "stable-installation-a"}),
                encoding="utf-8",
            )

            contribute_first = automation_rrule_for_spec(specs["kb-org-contribute"], repo_root)
            contribute_second = automation_rrule_for_spec(specs["kb-org-contribute"], repo_root)
            maintenance_first = automation_rrule_for_spec(specs["kb-org-maintenance"], repo_root)
            maintenance_second = automation_rrule_for_spec(specs["kb-org-maintenance"], repo_root)

            self.assertEqual(contribute_first, contribute_second)
            self.assertEqual(maintenance_first, maintenance_second)
            contribute_minute = rrule_local_minute(contribute_first)
            maintenance_minute = rrule_local_minute(maintenance_first)
            self.assertGreaterEqual(contribute_minute, ORG_CONTRIBUTE_WINDOW[0])
            self.assertLessEqual(contribute_minute, ORG_CONTRIBUTE_WINDOW[1])
            self.assertGreaterEqual(maintenance_minute, ORG_MAINTENANCE_WINDOW[0])
            self.assertLessEqual(maintenance_minute, ORG_MAINTENANCE_WINDOW[1])

        first_machine_rrule = contribute_first
        staggered = False
        for index in range(1, 8):
            with tempfile.TemporaryDirectory() as tmp_dir:
                repo_root = Path(tmp_dir) / "repo"
                identity_path = repo_root / ".local" / "khaos_brain_installation.json"
                identity_path.parent.mkdir(parents=True, exist_ok=True)
                identity_path.write_text(
                    json.dumps({"local_installation_id": f"stable-installation-b-{index}"}),
                    encoding="utf-8",
                )
                if automation_rrule_for_spec(specs["kb-org-contribute"], repo_root) != first_machine_rrule:
                    staggered = True
                    break

        self.assertTrue(staggered)

    def test_automation_runtime_prefers_newest_full_gpt_model_with_deepest_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            codex_home.mkdir(parents=True, exist_ok=True)
            (codex_home / "config.toml").write_text(
                'model = "gpt-5.4"\nmodel_reasoning_effort = "medium"\n',
                encoding="utf-8",
            )
            (codex_home / "models_cache.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "slug": "gpt-5.4",
                                "supported_reasoning_levels": [{"effort": "xhigh"}],
                            },
                            {
                                "slug": "gpt-6.1",
                                "supported_reasoning_levels": [
                                    {"effort": "high"},
                                    {"effort": "xhigh"},
                                ],
                            },
                            {
                                "slug": "codex-auto-review",
                                "supported_reasoning_levels": [{"effort": "xhigh"}],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {AUTOMATION_MODEL_ENV_VAR: "", AUTOMATION_REASONING_EFFORT_ENV_VAR: ""},
            ):
                runtime = resolve_automation_runtime(codex_home)

            self.assertEqual(runtime["model"], "gpt-6.1")
            self.assertEqual(runtime["reasoning_effort"], "xhigh")
            self.assertEqual(runtime["model_policy"], "strongest-available")
            self.assertEqual(runtime["reasoning_effort_policy"], "deepest")

    def test_automation_runtime_keeps_newest_model_when_xhigh_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            codex_home.mkdir(parents=True, exist_ok=True)
            (codex_home / "config.toml").write_text(
                'model = "gpt-5.5"\nmodel_reasoning_effort = "xhigh"\n',
                encoding="utf-8",
            )
            (codex_home / "models_cache.json").write_text(
                json.dumps(
                    {
                        "models": [
                            {
                                "slug": "gpt-5.5",
                                "supported_reasoning_levels": [{"effort": "xhigh"}],
                            },
                            {
                                "slug": "gpt-7",
                                "supported_reasoning_levels": [
                                    {"effort": "medium"},
                                    {"effort": "high"},
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {AUTOMATION_MODEL_ENV_VAR: "", AUTOMATION_REASONING_EFFORT_ENV_VAR: ""},
            ):
                runtime = resolve_automation_runtime(codex_home)

            self.assertEqual(runtime["model"], "gpt-7")
            self.assertEqual(runtime["reasoning_effort"], "high")

    def test_install_preserves_existing_global_agents_content(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            shell_bin_dir = Path(tmp_dir) / "shell-bin"
            git_real = Path(tmp_dir) / "tool-src" / "git-real.cmd"
            rg_source = Path(tmp_dir) / "tool-src" / "rg-source.exe"
            write_cmd(git_real, "echo git version test")
            rg_source.parent.mkdir(parents=True, exist_ok=True)
            rg_source.write_bytes(b"rg-binary")
            agents_path = global_agents_path(codex_home)
            agents_path.parent.mkdir(parents=True, exist_ok=True)
            agents_path.write_text("## User Custom Defaults\n\n- Keep this line.\n", encoding="utf-8")

            install_codex_integration(
                repo_root=repo_root,
                codex_home=codex_home,
                shell_bin_dir=shell_bin_dir,
                git_executable=git_real,
                rg_source=rg_source,
                persist_user_shell_path=False,
            )

            global_agents_text = agents_path.read_text(encoding="utf-8")
            self.assertIn("## User Custom Defaults", global_agents_text)
            self.assertIn("- Keep this line.", global_agents_text)
            self.assertIn("BEGIN MANAGED PREDICTIVE KB DEFAULTS", global_agents_text)
            self.assertEqual(global_agents_text.count("BEGIN MANAGED PREDICTIVE KB DEFAULTS"), 1)

    def test_check_fails_when_shell_tool_artifacts_are_missing(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            shell_bin_dir = Path(tmp_dir) / "shell-bin"
            git_real = Path(tmp_dir) / "tool-src" / "git-real.cmd"
            rg_source = Path(tmp_dir) / "tool-src" / "rg-source.exe"
            write_cmd(git_real, "echo git version test")
            rg_source.parent.mkdir(parents=True, exist_ok=True)
            rg_source.write_bytes(b"rg-binary")

            install_codex_integration(
                repo_root=repo_root,
                codex_home=codex_home,
                shell_bin_dir=shell_bin_dir,
                git_executable=git_real,
                rg_source=rg_source,
                persist_user_shell_path=False,
            )

            (shell_bin_dir / "rg.exe").unlink()

            check = build_installation_check(repo_root=repo_root, codex_home=codex_home)
            self.assertFalse(check["ok"])
            checklist = {item["id"]: item for item in check["checklist"]}
            self.assertFalse(checklist["codex_shell_tools"]["ok"])
            self.assertTrue(
                any("Codex shell rg binary is missing" in issue for issue in check["issues"]),
                check["issues"],
            )

    def test_check_skips_windows_shell_tools_for_non_windows_partial_install(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            shell_bin_dir = Path(tmp_dir) / "shell-bin"
            git_real = Path(tmp_dir) / "tool-src" / "git-real.cmd"
            rg_source = Path(tmp_dir) / "tool-src" / "rg-source.exe"
            write_cmd(git_real, "echo git version test")
            rg_source.parent.mkdir(parents=True, exist_ok=True)
            rg_source.write_bytes(b"rg-binary")

            install_codex_integration(
                repo_root=repo_root,
                codex_home=codex_home,
                shell_bin_dir=shell_bin_dir,
                git_executable=git_real,
                rg_source=rg_source,
                persist_user_shell_path=False,
            )

            (shell_bin_dir / "rg.exe").unlink()
            manifest_path = install_state_path(codex_home)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["shell_tools"]["rg_installed"] = False
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with mock.patch("local_kb.install.platform.system", return_value="Linux"):
                check = build_installation_check(repo_root=repo_root, codex_home=codex_home)

            checklist = {item["id"]: item for item in check["checklist"]}
            self.assertTrue(check["ok"], check["issues"])
            self.assertTrue(checklist["codex_shell_tools"]["ok"])
            self.assertTrue(
                any("shell git/rg shim check skipped" in warning for warning in check["warnings"]),
                check["warnings"],
            )

    def test_check_fails_when_managed_global_agents_block_is_missing(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            shell_bin_dir = Path(tmp_dir) / "shell-bin"
            git_real = Path(tmp_dir) / "tool-src" / "git-real.cmd"
            rg_source = Path(tmp_dir) / "tool-src" / "rg-source.exe"
            write_cmd(git_real, "echo git version test")
            rg_source.parent.mkdir(parents=True, exist_ok=True)
            rg_source.write_bytes(b"rg-binary")

            install_codex_integration(
                repo_root=repo_root,
                codex_home=codex_home,
                shell_bin_dir=shell_bin_dir,
                git_executable=git_real,
                rg_source=rg_source,
                persist_user_shell_path=False,
            )

            agents_path = global_agents_path(codex_home)
            agents_path.write_text("## User Custom Defaults\n\n- Keep this line only.\n", encoding="utf-8")

            check = build_installation_check(repo_root=repo_root, codex_home=codex_home)
            self.assertFalse(check["ok"])
            checklist = {item["id"]: item for item in check["checklist"]}
            self.assertFalse(checklist["global_agents_block"]["ok"])
            self.assertFalse(checklist["strong_session_defaults"]["ok"])


if __name__ == "__main__":
    unittest.main()
