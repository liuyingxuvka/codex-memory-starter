from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.org_checks import check_organization_repository
from local_kb.org_cleanup import apply_organization_cleanup_proposal, build_organization_cleanup_proposal
from local_kb.store import load_yaml_file, write_yaml_file
from local_kb.ui_data import build_search_payload
from tests.org_helpers import base_card, write_valid_org_repo


class OrganizationCleanupTests(unittest.TestCase):
    def _write_cleanup_repo(self, root: Path) -> None:
        write_valid_org_repo(root, include_sandbox_cards=False)
        trusted_low = base_card(
            "trusted-low",
            "Old trusted route",
            "This trusted card has weak evidence and should be scored down.",
            status="trusted",
            confidence=0.4,
        )
        duplicate_a = base_card(
            "duplicate-a",
            "Duplicate candidate",
            "Keep only one copy of this organization candidate.",
            status="candidate",
            confidence=0.7,
        )
        duplicate_b = dict(duplicate_a)
        duplicate_b["id"] = "duplicate-b"
        weak = base_card(
            "weak-card",
            "Random weak candidate",
            "Random unreviewed text without durable organization value.",
            status="candidate",
            confidence=0.2,
        )
        strong = base_card(
            "strong-card",
            "Strong candidate",
            "Strong evidence should produce a promotion proposal, not direct low-risk apply.",
            status="candidate",
            confidence=0.9,
        )
        stale = base_card(
            "stale-rejected",
            "Stale rejected card",
            "Already rejected and low value.",
            status="rejected",
            confidence=0.1,
        )
        similar = base_card(
            "similar-card",
            "Duplicate candidate",
            "A similar but not identical candidate should trigger merge review.",
            status="candidate",
            confidence=0.72,
        )
        smoke = base_card(
            "auto-merge-smoke",
            "Organization auto-merge smoke test candidate",
            "This fixture checks organization auto-merge behavior.",
            status="candidate",
            confidence=0.55,
        )
        incoming = base_card(
            "incoming-card",
            "Incoming import candidate",
            "Imported candidate should be reviewed into main, not used directly from imports.",
            status="candidate",
            confidence=0.7,
        )
        smoke["tags"] = ["organization-kb", "auto-merge", "smoke-test"]
        write_yaml_file(root / "kb" / "trusted" / "trusted-low.yaml", trusted_low)
        write_yaml_file(root / "kb" / "candidates" / "duplicate-a.yaml", duplicate_a)
        write_yaml_file(root / "kb" / "candidates" / "duplicate-b.yaml", duplicate_b)
        write_yaml_file(root / "kb" / "candidates" / "weak-card.yaml", weak)
        write_yaml_file(root / "kb" / "candidates" / "strong-card.yaml", strong)
        write_yaml_file(root / "kb" / "candidates" / "stale-rejected.yaml", stale)
        write_yaml_file(root / "kb" / "candidates" / "similar-card.yaml", similar)
        write_yaml_file(root / "kb" / "candidates" / "auto-merge-smoke.yaml", smoke)
        write_yaml_file(root / "kb" / "imports" / "alice" / "incoming-card.yaml", incoming)

    def test_cleanup_proposal_includes_duplicates_weak_cards_score_adjustments_and_review_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_cleanup_repo(root)

            proposal = build_organization_cleanup_proposal(root)
            action_types = [item["action_type"] for item in proposal["actions"]]

        self.assertTrue(proposal["ok"], proposal)
        self.assertEqual(proposal["maintenance_model"]["role"], "organization-exchange-sleep")
        self.assertEqual(proposal["maintenance_model"]["incoming_lane"], "kb/imports")
        self.assertEqual(proposal["maintenance_model"]["exchange_surface"], "kb/main")
        self.assertEqual(proposal["maintenance_model"]["exchange_surface_content_maintenance"], "in-scope")
        self.assertEqual(proposal["maintenance_model"]["trusted_card_content_maintenance"], "in-scope")
        self.assertTrue(proposal["maintenance_model"]["local_final_adoption"])
        self.assertEqual(proposal["lane_policy"]["contribution_writes"], ["kb/imports"])
        self.assertEqual(proposal["lane_policy"]["maintenance_moves_reviewed_cards_to"], "kb/main")
        self.assertEqual(proposal["lane_policy"]["local_download_excluded_paths"], ["kb/imports"])
        self.assertIn("mark-duplicate", action_types)
        self.assertIn("status-adjust", action_types)
        self.assertIn("confidence-adjust", action_types)
        self.assertIn("delete-card", action_types)
        self.assertIn("merge-cards", action_types)
        self.assertIn("promote-card", action_types)
        self.assertIn("accept-import", action_types)
        promotion = next(item for item in proposal["actions"] if item.get("entry_id") == "strong-card")
        accepted_import = next(item for item in proposal["actions"] if item.get("entry_id") == "incoming-card")
        smoke = next(item for item in proposal["actions"] if item.get("entry_id") == "auto-merge-smoke")
        self.assertEqual(promotion["proposed_status"], "trusted")
        self.assertTrue(promotion["apply_supported"])
        self.assertTrue(promotion["proposed_path"].startswith("kb/main/"))
        self.assertEqual(accepted_import["action_type"], "accept-import")
        self.assertEqual(accepted_import["proposed_status"], "candidate")
        self.assertTrue(accepted_import["proposed_path"].startswith("kb/main/"))
        self.assertEqual(smoke["action_type"], "status-adjust")
        self.assertEqual(smoke["proposed_status"], "rejected")

    def test_cleanup_apply_updates_low_risk_actions_audits_and_keeps_checks_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_cleanup_repo(root)
            proposal = build_organization_cleanup_proposal(root)

            result = apply_organization_cleanup_proposal(
                root,
                proposal,
                allow_actions={"confidence-adjust", "status-adjust", "mark-duplicate", "delete-card"},
                allow_trusted=True,
                allow_delete=True,
            )
            weak = load_yaml_file(root / "kb" / "candidates" / "weak-card.yaml")
            duplicate_b = load_yaml_file(root / "kb" / "candidates" / "duplicate-b.yaml")
            trusted_low = load_yaml_file(root / "kb" / "trusted" / "trusted-low.yaml")
            strong = load_yaml_file(root / "kb" / "candidates" / "strong-card.yaml")
            smoke = load_yaml_file(root / "kb" / "candidates" / "auto-merge-smoke.yaml")
            stale_exists = (root / "kb" / "candidates" / "stale-rejected.yaml").exists()
            check = check_organization_repository(root)
            rejected_search = build_search_payload(root, "Random weak candidate", organization_sources=[{"path": str(root), "organization_id": "sandbox"}])
            rejected_result_ids = [item["id"] for item in rejected_search["results"]]
            audit_exists = (root / "maintenance" / "cleanup_audit.jsonl").exists()

        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["applied_count"], 4)
        self.assertEqual(weak["status"], "rejected")
        self.assertEqual(duplicate_b["status"], "rejected")
        self.assertEqual(duplicate_b["organization_cleanup"]["duplicate_of"], "kb/candidates/duplicate-a.yaml")
        self.assertLess(trusted_low["confidence"], 0.4)
        self.assertEqual(strong["status"], "candidate")
        self.assertEqual(smoke["status"], "rejected")
        self.assertFalse(stale_exists)
        self.assertTrue(check["ok"], check)
        self.assertNotIn("weak-card", rejected_result_ids)
        self.assertTrue(audit_exists)

    def test_cleanup_apply_promotes_reviewed_candidate_to_main_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_cleanup_repo(root)
            proposal = build_organization_cleanup_proposal(root)
            promotion = next(item for item in proposal["actions"] if item.get("entry_id") == "strong-card")

            result = apply_organization_cleanup_proposal(
                root,
                proposal,
                allow_actions={"promote-card"},
                allow_action_ids={promotion["action_id"]},
                allow_promote=True,
            )
            promoted_path = root / promotion["proposed_path"]
            promoted = load_yaml_file(promoted_path)
            original_exists = (root / "kb" / "candidates" / "strong-card.yaml").exists()
            check = check_organization_repository(root)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied_count"], 1)
        self.assertFalse(original_exists)
        self.assertEqual(promoted["status"], "trusted")
        self.assertEqual(promoted["organization_cleanup"]["promoted_from"], "kb/candidates/strong-card.yaml")
        self.assertTrue(check["ok"], check)

    def test_cleanup_apply_accepts_reviewed_import_to_main_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_cleanup_repo(root)
            proposal = build_organization_cleanup_proposal(root)
            incoming = next(item for item in proposal["actions"] if item.get("entry_id") == "incoming-card")

            result = apply_organization_cleanup_proposal(
                root,
                proposal,
                allow_actions={"accept-import"},
                allow_action_ids={incoming["action_id"]},
                allow_promote=True,
            )
            moved_path = root / incoming["proposed_path"]
            moved = load_yaml_file(moved_path)
            original_exists = (root / "kb" / "imports" / "alice" / "incoming-card.yaml").exists()
            check = check_organization_repository(root)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied_count"], 1)
        self.assertFalse(original_exists)
        self.assertEqual(moved["status"], "candidate")
        self.assertEqual(moved["organization_cleanup"]["moved_to_main_from"], "kb/imports/alice/incoming-card.yaml")
        self.assertTrue(check["ok"], check)


if __name__ == "__main__":
    unittest.main()
