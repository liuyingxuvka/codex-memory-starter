from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_kb.install import (
    AUTOMATION_MODEL_ENV_VAR,
    AUTOMATION_REASONING_EFFORT_ENV_VAR,
    build_installation_check,
    global_agents_path,
    install_codex_integration,
    resolve_automation_runtime,
)


def write_cmd(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@echo off\r\n{body}\r\n", encoding="utf-8")


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
            self.assertTrue(global_agents_path(codex_home).exists())
            self.assertTrue((shell_bin_dir / "git.cmd").exists())
            self.assertTrue((shell_bin_dir / "rg.exe").exists())
            self.assertEqual(payload["repo_root"], str(repo_root))
            self.assertEqual(payload["automation_ids"], ["kb-sleep", "kb-dream", "kb-architect"])
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

            openai_text = (
                codex_home / "skills" / "predictive-kb-preflight" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("allow_implicit_invocation: true", openai_text)
            self.assertIn("record a KB follow-up observation", openai_text)
            self.assertIn("required default preflight", openai_text)
            self.assertIn("skill/plugin usage lesson", openai_text)

            global_agents_text = global_agents_path(codex_home).read_text(encoding="utf-8")
            self.assertIn("BEGIN MANAGED PREDICTIVE KB DEFAULTS", global_agents_text)
            self.assertIn("$predictive-kb-preflight", global_agents_text)
            self.assertIn("explicit KB postflight check", global_agents_text)
            self.assertIn("skill/plugin usage", global_agents_text)

            sleep_toml = (codex_home / "automations" / "kb-sleep" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', sleep_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=12;BYMINUTE=0"', sleep_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', sleep_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', sleep_toml)
            self.assertIn('model_policy = "strongest-available"', sleep_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', sleep_toml)
            self.assertIn("visible sleep execution plan", sleep_toml)
            self.assertIn("checkpoint statuses", sleep_toml)
            self.assertIn("every safe checkpoint", sleep_toml)
            self.assertIn("supported low-risk repairs", sleep_toml)
            self.assertIn("rerun the relevant validation", sleep_toml)
            self.assertIn("sleep self-preflight", sleep_toml)
            self.assertIn("system/knowledge-library/maintenance", sleep_toml)
            self.assertIn("sleep postflight check", sleep_toml)
            self.assertIn("structured maintenance observation", sleep_toml)
            self.assertIn("recursively consolidating", sleep_toml)
            self.assertIn(str(repo_root).replace("\\", "\\\\"), sleep_toml)

            dream_toml = (codex_home / "automations" / "kb-dream" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', dream_toml)
            self.assertIn('kb_dream.py', dream_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=13;BYMINUTE=0"', dream_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', dream_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', dream_toml)
            self.assertIn('model_policy = "strongest-available"', dream_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', dream_toml)
            self.assertIn("generated preflight", dream_toml)
            self.assertIn("preflight entries retrieved", dream_toml)
            self.assertIn("exactly one executable experiment", dream_toml)
            self.assertIn("execution-plan checkpoint status", dream_toml)
            self.assertIn("safety tier and rollback plan", dream_toml)
            self.assertIn("external-system experiments proposal-only", dream_toml)
            self.assertIn("run-level Dream-process observation", dream_toml)

            architect_toml = (
                codex_home / "automations" / "kb-architect" / "automation.toml"
            ).read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', architect_toml)
            self.assertIn('kb_architect.py', architect_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=14;BYMINUTE=0"', architect_toml)
            self.assertIn(f'model = "{automation_runtime["model"]}"', architect_toml)
            self.assertIn(f'reasoning_effort = "{automation_runtime["reasoning_effort"]}"', architect_toml)
            self.assertIn('model_policy = "strongest-available"', architect_toml)
            self.assertIn('reasoning_effort_policy = "deepest"', architect_toml)
            self.assertIn("visible Architect execution plan", architect_toml)
            self.assertIn("checkpoint statuses", architect_toml)
            self.assertIn("Architect self-preflight", architect_toml)
            self.assertIn("system/knowledge-library/maintenance", architect_toml)
            self.assertIn("Evidence, Impact, and Safety", architect_toml)
            self.assertIn("human-review status", architect_toml)
            self.assertIn("long-observation items as watching", architect_toml)
            self.assertIn("KB operating mechanisms rather than card content", architect_toml)
            self.assertIn("do not rewrite trusted cards or promote candidates", architect_toml)
            self.assertIn("validation bundle", architect_toml)
            self.assertIn("postflight observation status", architect_toml)

            check = build_installation_check(repo_root=repo_root, codex_home=codex_home)
            self.assertTrue(check["ok"], check["issues"])
            self.assertEqual(check["automation_runtime"], automation_runtime)
            self.assertEqual(
                [item["id"] for item in check["automation_checks"]],
                ["kb-sleep", "kb-dream", "kb-architect"],
            )
            checklist = {item["id"]: item for item in check["checklist"]}
            self.assertIn("codex_shell_tools", checklist)
            self.assertIn("strong_session_defaults", checklist)
            self.assertIn("kb_architect_automation", checklist)
            self.assertTrue(checklist["codex_shell_tools"]["ok"])
            self.assertTrue(checklist["kb_architect_automation"]["ok"])
            self.assertTrue(checklist["strong_session_defaults"]["ok"])
            self.assertTrue(checklist["global_agents_block"]["ok"])
            self.assertTrue(checklist["global_skill_postflight"]["ok"])
            self.assertTrue(checklist["global_skill_skill_usage"]["ok"])
            self.assertTrue(checklist["global_agents_skill_usage"]["ok"])

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
