from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_kb.adoption import card_exchange_hash
from local_kb.org_automation import run_organization_contribution, run_organization_maintenance
from local_kb.org_sources import _run_git
from local_kb.settings import ORGANIZATION_MODE, save_desktop_settings
from local_kb.store import write_yaml_file
from tests.org_helpers import base_card, write_valid_org_repo


class OrganizationAutomationTests(unittest.TestCase):
    def _write_org_repo(self, root: Path) -> None:
        write_yaml_file(
            root / "khaos_org_kb.yaml",
            {
                "kind": "khaos-organization-kb",
                "schema_version": 1,
                "organization_id": "sandbox",
                "kb": {
                    "trusted_path": "kb/trusted",
                    "candidates_path": "kb/candidates",
                    "imports_path": "kb/imports",
                },
                "skills": {
                    "registry_path": "skills/registry.yaml",
                    "candidates_path": "skills/candidates",
                },
            },
        )
        write_yaml_file(root / "kb" / "trusted" / "trusted.yaml", {"id": "trusted", "status": "trusted"})
        write_yaml_file(root / "kb" / "candidates" / "candidate.yaml", {"id": "candidate", "status": "candidate"})
        (root / "kb" / "imports").mkdir(parents=True)
        write_yaml_file(root / "skills" / "registry.yaml", {"skills": [{"id": "org.demo", "status": "approved"}]})
        (root / "skills" / "candidates").mkdir(parents=True)

    def _write_local_card(self, root: Path, entry_id: str = "share-model") -> None:
        write_yaml_file(
            root / "kb" / "public" / f"{entry_id}.yaml",
            {
                "id": entry_id,
                "title": "Shareable model",
                "type": "model",
                "scope": "public",
                "status": "trusted",
                "confidence": 0.82,
                "domain_path": ["system", "knowledge-library", "organization"],
                "tags": ["organization", "sharing"],
                "trigger_keywords": ["organization", "outbox"],
                "if": {"notes": "A reusable organization KB contribution is useful."},
                "action": {"description": "Export it through the organization outbox."},
                "predict": {"expected_result": "Other machines can reuse the model."},
                "use": {"guidance": "Keep private details out of the shared proposal."},
            },
        )

    def _save_organization_settings(
        self,
        repo_root: Path,
        org_root: Path,
        *,
        maintenance_requested: bool = False,
    ) -> None:
        save_desktop_settings(
            repo_root,
            {
                "mode": ORGANIZATION_MODE,
                "organization": {
                    "repo_url": str(org_root),
                    "local_mirror_path": str(org_root),
                    "organization_id": "sandbox",
                    "validated": True,
                    "validation_status": "valid",
                    "organization_maintenance_requested": maintenance_requested,
                },
            },
        )

    def test_contribution_noops_without_valid_organization_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_organization_contribution(Path(tmp), record_postflight=False)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["skipped"], result)
        self.assertFalse(result["settings_gate"]["available"])
        self.assertEqual(result["preflight"], {})
        self.assertFalse(result["postflight_recorded"])

    def test_automation_scripts_noop_successfully_without_settings(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            local_root = Path(tmp)
            outbox = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "scripts" / "kb_org_outbox.py"),
                    "--repo-root",
                    str(local_root),
                    "--automation",
                    "--no-postflight",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            maintainer = subprocess.run(
                [
                    sys.executable,
                    str(repo_root / "scripts" / "kb_org_maintainer.py"),
                    "--repo-root",
                    str(local_root),
                    "--automation",
                    "--no-postflight",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(outbox.returncode, 0, outbox.stderr)
        self.assertEqual(maintainer.returncode, 0, maintainer.stderr)
        self.assertTrue(json.loads(outbox.stdout)["skipped"])
        self.assertTrue(json.loads(maintainer.stdout)["skipped"])

    def test_contribution_dry_run_uses_valid_settings_and_hash_gated_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            org = root / "org"
            repo = root / "repo"
            self._write_org_repo(org)
            self._write_local_card(repo)
            self._save_organization_settings(repo, org)

            result = run_organization_contribution(repo, dry_run=True, record_postflight=False)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["skipped"], result)
        self.assertTrue(result["settings_gate"]["available"])
        self.assertEqual(result["organization_id"], "sandbox")
        self.assertEqual(result["outbox"]["created_count"], 1)
        self.assertEqual(result["outbox"]["skipped_count"], 0)
        self.assertFalse((repo / "kb" / "outbox").exists())
        self.assertFalse(result["postflight_recorded"])

    def test_contribution_syncs_and_uploads_created_outbox_to_import_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            org = root / "org"
            repo = root / "repo"
            self.assertEqual(0, _run_git(["init", "--bare", str(remote)]).returncode)
            self._write_org_repo(org)
            self.assertEqual(0, _run_git(["init"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["remote", "add", "origin", str(remote)], cwd=org).returncode)
            self.assertEqual(0, _run_git(["add", "."], cwd=org).returncode)
            self.assertEqual(
                0,
                _run_git(
                    ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"],
                    cwd=org,
                ).returncode,
            )
            self.assertEqual(0, _run_git(["branch", "-M", "main"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["push", "-u", "origin", "main"], cwd=org).returncode)
            self._write_local_card(repo, "new-share-model")
            self._save_organization_settings(repo, org)

            result = run_organization_contribution(
                repo,
                branch_name="contrib/test/auto-upload",
                record_postflight=False,
            )
            second = run_organization_contribution(
                repo,
                branch_name="contrib/test/auto-upload-repeat",
                record_postflight=False,
            )
            branches = _run_git(["branch", "--list"], cwd=remote)
            current_branch = _run_git(["branch", "--show-current"], cwd=org).stdout.strip()
            outbox_exists_after_upload = (repo / "kb" / "outbox" / "organization" / "sandbox").exists()

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["sync"]["ok"], result)
        self.assertEqual(result["outbox"]["created_count"], 1)
        self.assertTrue(result["branch"]["attempted"], result)
        self.assertTrue(result["branch"]["push"]["pushed"], result)
        self.assertTrue(result["branch"]["restore_base"]["ok"], result)
        self.assertTrue(result["branch"]["clear_outbox"]["ok"], result)
        self.assertEqual(result["lane_policy"]["contribution_writes"], ["kb/imports"])
        self.assertEqual(result["lane_policy"]["maintenance_moves_reviewed_cards_to"], "kb/main")
        self.assertTrue(all(path.startswith("kb/imports/") for path in result["branch"]["created_files"]))
        self.assertEqual(current_branch, "main")
        self.assertIn("contrib/test/auto-upload", branches.stdout)
        self.assertFalse(outbox_exists_after_upload)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["outbox"]["created_count"], 0)
        self.assertFalse(second["branch"]["attempted"], second)
        self.assertNotIn("contrib/test/auto-upload-repeat", branches.stdout)

    def test_contribution_ignores_stale_outbox_when_hash_exists_in_organization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            org = root / "org"
            repo = root / "repo"
            self.assertEqual(0, _run_git(["init", "--bare", str(remote)]).returncode)
            self._write_org_repo(org)
            shared_card = base_card("already-shared", "Already shared", "This card is already in the organization.")
            write_yaml_file(org / "kb" / "trusted" / "already-shared.yaml", shared_card)
            stale_outbox = repo / "kb" / "outbox" / "organization" / "sandbox" / "already-shared.yaml"
            write_yaml_file(
                stale_outbox,
                {
                    **shared_card,
                    "status": "candidate",
                    "organization_proposal": {
                        "organization_id": "sandbox",
                        "source_path": "kb/public/already-shared.yaml",
                        "content_hash": card_exchange_hash(shared_card),
                    },
                },
            )
            self.assertEqual(0, _run_git(["init"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["remote", "add", "origin", str(remote)], cwd=org).returncode)
            self.assertEqual(0, _run_git(["add", "."], cwd=org).returncode)
            self.assertEqual(
                0,
                _run_git(
                    ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"],
                    cwd=org,
                ).returncode,
            )
            self.assertEqual(0, _run_git(["branch", "-M", "main"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["push", "-u", "origin", "main"], cwd=org).returncode)
            self._save_organization_settings(repo, org)

            result = run_organization_contribution(
                repo,
                branch_name="contrib/test/stale-outbox",
                record_postflight=False,
            )
            branches = _run_git(["branch", "--list"], cwd=remote)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["outbox"]["created_count"], 0)
        self.assertFalse(result["branch"]["attempted"], result)
        self.assertNotIn("contrib/test/stale-outbox", branches.stdout)

    def test_maintenance_applies_cleanup_and_pushes_maintenance_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            org = root / "org"
            repo = root / "repo"
            self.assertEqual(0, _run_git(["init", "--bare", str(remote)]).returncode)
            write_valid_org_repo(org, include_sandbox_cards=False)
            write_yaml_file(
                org / "kb" / "candidates" / "weak-card.yaml",
                base_card("weak-card", "Weak org card", "Weak shared candidate.", status="candidate", confidence=0.2),
            )
            write_yaml_file(
                org / "kb" / "candidates" / "strong-card.yaml",
                base_card("strong-card", "Strong org card", "Strong shared candidate.", status="candidate", confidence=0.9),
            )
            write_yaml_file(
                org / "kb" / "trusted" / "trusted-low.yaml",
                base_card("trusted-low", "Trusted low card", "Trusted but weak.", status="trusted", confidence=0.4),
            )
            self.assertEqual(0, _run_git(["init"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["remote", "add", "origin", str(remote)], cwd=org).returncode)
            self.assertEqual(0, _run_git(["add", "."], cwd=org).returncode)
            self.assertEqual(
                0,
                _run_git(
                    ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"],
                    cwd=org,
                ).returncode,
            )
            self.assertEqual(0, _run_git(["branch", "-M", "main"], cwd=org).returncode)
            self.assertEqual(0, _run_git(["push", "-u", "origin", "main"], cwd=org).returncode)
            self._save_organization_settings(repo, org, maintenance_requested=True)
            skill_dir = repo / ".agents" / "skills" / "organization-review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: organization-review\ndescription: Review organization KB proposals.\n---\n",
                encoding="utf-8",
            )

            result = run_organization_maintenance(repo, record_postflight=False)
            branches = _run_git(["branch", "--list", "maintenance/*"], cwd=remote)
            current_branch = _run_git(["branch", "--show-current"], cwd=org).stdout.strip()

        self.assertTrue(result["ok"], result)
        self.assertGreater(result["report"]["cleanup"]["apply"]["applied_count"], 0, result)
        self.assertTrue(result["maintenance_branch"]["attempted"], result)
        self.assertTrue(result["maintenance_branch"]["push"]["pushed"], result)
        self.assertTrue(result["maintenance_branch"]["restore_base"]["ok"], result)
        self.assertEqual(current_branch, "main")
        self.assertEqual(0, branches.returncode, branches.stderr)
        self.assertIn("maintenance/", branches.stdout)

    def test_maintenance_applies_cleanup_without_organization_review_skill_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            org = root / "org"
            repo = root / "repo"
            write_valid_org_repo(org, include_sandbox_cards=False)
            write_yaml_file(
                org / "kb" / "candidates" / "weak-card.yaml",
                base_card("weak-card", "Weak org card", "Weak shared candidate.", status="candidate", confidence=0.2),
            )
            self._save_organization_settings(repo, org, maintenance_requested=True)

            result = run_organization_maintenance(repo, record_postflight=False)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["report"]["cleanup"]["review"]["selected_count"], 1)
        self.assertGreater(result["report"]["cleanup"]["apply"]["applied_count"], 0, result)
        self.assertFalse(result["maintenance_branch"]["attempted"], result)
        self.assertEqual(result["maintenance_branch"]["reason"], "organization mirror is not a git checkout")

    def test_maintenance_noops_until_participation_is_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            org = root / "org"
            repo = root / "repo"
            self._write_org_repo(org)
            self._save_organization_settings(repo, org, maintenance_requested=False)

            result = run_organization_maintenance(repo, record_postflight=False)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["skipped"], result)
        self.assertFalse(result["settings_gate"]["available"])
        self.assertFalse(result["participation"]["available"])

    def test_maintenance_runs_when_participation_is_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            org = root / "org"
            repo = root / "repo"
            self._write_org_repo(org)
            self._save_organization_settings(repo, org, maintenance_requested=True)
            skill_dir = repo / ".agents" / "skills" / "organization-review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: organization-review\ndescription: Review organization KB proposals.\n---\n",
                encoding="utf-8",
            )

            result = run_organization_maintenance(repo, record_postflight=False)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["skipped"], result)
        self.assertTrue(result["settings_gate"]["available"])
        self.assertTrue(result["participation"]["available"])
        self.assertEqual(result["organization_id"], "sandbox")
        self.assertEqual(result["report"]["maintenance_model"]["role"], "organization-exchange-sleep")
        self.assertEqual(result["lane_policy"]["incoming_lane"], "kb/imports")
        self.assertEqual(result["lane_policy"]["exchange_surface"], "kb/main")
        self.assertEqual(result["report"]["layout_policy"]["local_download_excluded_paths"], ["kb/imports"])
        self.assertEqual(result["report"]["cleanup"]["exchange_surface_maintenance"], "in-scope-like-local-sleep")
        self.assertEqual(result["report"]["candidate_count"], 1)
        self.assertTrue(result["report"]["organization_review_skill"]["installed"])
        self.assertIn("migrate-legacy-compatible-layout-to-main-imports", result["report"]["recommendations"])
        self.assertIn("review-legacy-compatible-candidates", result["report"]["recommendations"])
        self.assertFalse(result["postflight_recorded"])


if __name__ == "__main__":
    unittest.main()
