from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_kb.install import install_codex_integration


class KbPreflightEntryCompatibilityTests(unittest.TestCase):
    def test_installed_launcher_accepts_search_like_call_without_explicit_subcommand(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex_home = Path(tmp_dir) / ".codex"
            install_codex_integration(repo_root=repo_root, codex_home=codex_home)
            launcher_path = codex_home / "skills" / "predictive-kb-preflight" / "kb_launch.py"
            env = os.environ.copy()
            env["CODEX_PREDICTIVE_KB_ROOT"] = str(repo_root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(launcher_path),
                    "--route-hint",
                    "system/knowledge-library/retrieval",
                    "--query",
                    "knowledge library retrieval",
                    "--json",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload[0]["id"], "model-004")

    def test_local_search_accepts_route_hint_alias(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / ".agents" / "skills" / "local-kb-retrieve" / "scripts" / "kb_search.py"
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(repo_root),
                "--route-hint",
                "system/knowledge-library/retrieval",
                "--query",
                "knowledge library retrieval",
                "--json",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload[0]["id"], "model-004")


if __name__ == "__main__":
    unittest.main()
