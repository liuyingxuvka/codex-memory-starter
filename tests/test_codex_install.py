from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.install import build_installation_check, install_codex_integration


class CodexInstallTests(unittest.TestCase):
    def test_install_writes_global_skill_launcher_and_manifest(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            payload = install_codex_integration(repo_root=repo_root, codex_home=codex_home)

            self.assertTrue((codex_home / "skills" / "predictive-kb-preflight" / "SKILL.md").exists())
            self.assertTrue((codex_home / "skills" / "predictive-kb-preflight" / "kb_launch.py").exists())
            self.assertTrue((codex_home / "predictive-kb" / "install.json").exists())
            self.assertTrue((codex_home / "automations" / "kb-sleep" / "automation.toml").exists())
            self.assertTrue((codex_home / "automations" / "kb-dream" / "automation.toml").exists())
            self.assertEqual(payload["repo_root"], str(repo_root))
            self.assertEqual(payload["automation_ids"], ["kb-sleep", "kb-dream"])

            openai_text = (
                codex_home / "skills" / "predictive-kb-preflight" / "agents" / "openai.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("allow_implicit_invocation: true", openai_text)
            self.assertIn("record a KB follow-up observation", openai_text)

            sleep_toml = (codex_home / "automations" / "kb-sleep" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', sleep_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=12;BYMINUTE=0"', sleep_toml)
            self.assertIn(str(repo_root).replace("\\", "\\\\"), sleep_toml)

            dream_toml = (codex_home / "automations" / "kb-dream" / "automation.toml").read_text(encoding="utf-8")
            self.assertIn('kind = "cron"', dream_toml)
            self.assertIn('kb_dream.py', dream_toml)
            self.assertIn('rrule = "FREQ=WEEKLY;BYDAY=SU,MO,TU,WE,TH,FR,SA;BYHOUR=13;BYMINUTE=0"', dream_toml)

            check = build_installation_check(repo_root=repo_root, codex_home=codex_home)
            self.assertTrue(check["ok"], check["issues"])
            self.assertEqual([item["id"] for item in check["automation_checks"]], ["kb-sleep", "kb-dream"])


if __name__ == "__main__":
    unittest.main()
