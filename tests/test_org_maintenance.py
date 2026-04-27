from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.org_maintenance import build_organization_maintenance_report
from local_kb.store import write_yaml_file
from tests.org_helpers import base_card, write_valid_org_repo


class OrganizationMaintenanceTests(unittest.TestCase):
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
        write_yaml_file(root / "kb" / "trusted" / "model.yaml", {"id": "shared-card", "status": "trusted"})
        write_yaml_file(root / "kb" / "candidates" / "dupe.yaml", {"id": "shared-card", "status": "candidate"})
        (root / "kb" / "imports").mkdir(parents=True)
        write_yaml_file(root / "skills" / "registry.yaml", {"skills": [{"id": "demo-skill", "status": "approved"}]})
        (root / "skills" / "candidates").mkdir(parents=True)

    def test_maintenance_report_ignores_duplicate_ids_and_detects_candidates_skills_and_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            org = root / "org"
            self._write_org_repo(org)
            write_yaml_file(repo_root / "kb" / "outbox" / "organization" / "sandbox" / "proposal.yaml", {"id": "proposal"})

            report = build_organization_maintenance_report(org, repo_root=repo_root)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["organization_id"], "sandbox")
        self.assertTrue(report["legacy_compatibility"])
        self.assertIn("compatibility inputs only", report["legacy_notice"])
        self.assertEqual(report["layout_policy"]["incoming_lane_path"], "kb/imports")
        self.assertEqual(report["layout_policy"]["exchange_surface_path"], "kb/main")
        self.assertEqual(report["layout_policy"]["local_download_excluded_paths"], ["kb/imports"])
        self.assertEqual(report["outbox_count"], 1)
        self.assertIn("migrate-legacy-compatible-layout-to-main-imports", report["recommendations"])
        self.assertIn("review-legacy-compatible-candidates", report["recommendations"])
        self.assertNotIn("review-duplicate-entry-ids", report["recommendations"])
        self.assertIn("review-local-outbox-proposals", report["recommendations"])
        self.assertIn("review-skill-registry", report["recommendations"])
        self.assertFalse(report["organization_review_skill"]["installed"])

    def test_maintenance_report_detects_installed_organization_review_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            org = root / "org"
            self._write_org_repo(org)
            skill_dir = repo_root / ".agents" / "skills" / "organization-review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: organization-review\ndescription: Review organization KB proposals.\n---\n",
                encoding="utf-8",
            )

            report = build_organization_maintenance_report(org, repo_root=repo_root)

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["organization_review_skill"]["installed"])

    def test_maintenance_report_surfaces_duplicate_hash_cleanup_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            org = root / "org"
            self._write_org_repo(org)
            duplicate_card = {
                "id": "duplicate-a",
                "title": "Duplicate organization card",
                "type": "model",
                "scope": "public",
                "status": "candidate",
                "confidence": 0.7,
                "domain_path": ["shared"],
                "tags": ["duplicate"],
                "trigger_keywords": ["duplicate"],
                "if": {"notes": "Same reusable condition."},
                "action": {"description": "Use the same action."},
                "predict": {"expected_result": "Duplicate hash should be detected."},
                "use": {"guidance": "Keep only one canonical version."},
            }
            second_duplicate = dict(duplicate_card)
            second_duplicate["id"] = "duplicate-b"
            write_yaml_file(org / "kb" / "imports" / "alice" / "duplicate-a.yaml", duplicate_card)
            write_yaml_file(org / "kb" / "imports" / "bob" / "duplicate-b.yaml", second_duplicate)

            report = build_organization_maintenance_report(org, repo_root=repo_root)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["imports_count"], 2)
        self.assertIn("review-organization-imports", report["recommendations"])
        self.assertEqual(report["cleanup"]["duplicate_content_hash_count"], 1)
        self.assertIn("review-duplicate-card-content-hashes", report["recommendations"])
        self.assertIn("duplicate card content hashes require organization maintenance", report["organization_check"]["auto_merge_blockers"])
        self.assertEqual(report["cleanup"]["similar_card_merge_apply"], "planned")
        self.assertEqual(report["cleanup"]["weak_card_rejection_apply"], "planned")
        self.assertEqual(report["cleanup"]["skill_bundle_cleanup_apply"], "partial")

    def test_maintenance_report_can_review_and_apply_supported_cleanup_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            org = root / "org"
            write_valid_org_repo(org, include_sandbox_cards=False)
            weak = base_card("weak-card", "Weak org card", "Weak shared candidate.", status="candidate", confidence=0.2)
            strong = base_card("strong-card", "Strong org card", "Strong shared candidate.", status="candidate", confidence=0.9)
            trusted_low = base_card("trusted-low", "Trusted low card", "Trusted but weak.", status="trusted", confidence=0.4)
            write_yaml_file(org / "kb" / "candidates" / "weak-card.yaml", weak)
            write_yaml_file(org / "kb" / "candidates" / "strong-card.yaml", strong)
            write_yaml_file(org / "kb" / "trusted" / "trusted-low.yaml", trusted_low)

            report = build_organization_maintenance_report(
                org,
                repo_root=repo_root,
                apply_reviewed_cleanup=True,
            )
            promoted = next(item for item in report["cleanup"]["apply"]["applied"] if item["action_type"] == "promote-card")
            promoted_exists = (org / promoted["updated_path"]).exists()
            post_apply_validation = report["cleanup"]["post_apply_validation"]

        self.assertTrue(report["ok"], report)
        review = report["cleanup"]["review"]
        apply = report["cleanup"]["apply"]
        self.assertGreaterEqual(review["approved_count"], 3)
        self.assertEqual(review["selected_count"], review["approved_count"])
        self.assertTrue(apply["attempted"])
        self.assertGreaterEqual(apply["applied_count"], 3)
        self.assertEqual(report["cleanup"]["exchange_surface_maintenance"], "in-scope-like-local-sleep")
        self.assertTrue(report["cleanup"]["post_apply_check"]["ok"], report)
        self.assertTrue(report["cleanup"]["post_apply_check"]["validation_ok"], report)
        self.assertTrue(post_apply_validation["ok"], report)
        self.assertGreaterEqual(post_apply_validation["main_count"], report["main_count"])
        self.assertTrue(promoted_exists)

    def test_maintenance_report_uses_main_imports_target_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            org = root / "org"
            write_yaml_file(
                org / "khaos_org_kb.yaml",
                {
                    "kind": "khaos-organization-kb",
                    "schema_version": 1,
                    "organization_id": "sandbox",
                    "kb": {
                        "main_path": "kb/main",
                        "imports_path": "kb/imports",
                    },
                    "skills": {
                        "registry_path": "skills/registry.yaml",
                        "candidates_path": "skills/candidates",
                    },
                },
            )
            write_yaml_file(org / "kb" / "main" / "trusted.yaml", base_card("trusted", "Trusted main", "Main trusted.", status="trusted"))
            write_yaml_file(org / "kb" / "main" / "candidate.yaml", base_card("candidate", "Candidate main", "Main candidate.", status="candidate"))
            write_yaml_file(org / "kb" / "imports" / "alice" / "incoming.yaml", base_card("incoming", "Incoming import", "Incoming lane.", status="candidate"))
            write_yaml_file(org / "skills" / "registry.yaml", {"skills": []})
            (org / "skills" / "candidates").mkdir(parents=True)

            report = build_organization_maintenance_report(org, repo_root=repo_root)
            applied_report = build_organization_maintenance_report(
                org,
                repo_root=repo_root,
                apply_reviewed_cleanup=True,
            )

        self.assertTrue(report["ok"], report)
        self.assertFalse(report["legacy_compatibility"])
        self.assertEqual(report["main_count"], 2)
        self.assertEqual(report["main_active_count"], 2)
        self.assertEqual(report["imports_count"], 1)
        self.assertEqual(report["layout_policy"]["local_download_paths"], ["kb/main"])
        self.assertIn("review-main-exchange-surface", report["recommendations"])
        self.assertIn("review-organization-imports", report["recommendations"])
        self.assertTrue(applied_report["cleanup"]["apply"]["attempted"], applied_report)
        self.assertEqual(applied_report["cleanup"]["apply"]["applied_count"], 1)
        self.assertEqual(applied_report["cleanup"]["post_apply_validation"]["main_count"], 3)
        self.assertEqual(applied_report["cleanup"]["post_apply_validation"]["imports_count"], 0)


if __name__ == "__main__":
    unittest.main()
