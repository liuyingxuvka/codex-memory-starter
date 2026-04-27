from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_kb.proposals import build_proposal_report, load_proposal_stubs


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "local-kb-retrieve"
    / "scripts"
    / "kb_proposals.py"
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class KbProposalInspectionTests(unittest.TestCase):
    def test_loads_and_summarizes_action_stubs_from_temp_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            run_id = "daily-maintenance"
            actions_dir = repo_root / "kb" / "history" / "consolidation" / run_id / "actions"

            write_json(
                actions_dir / "candidate-1.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-19T20:00:00+00:00",
                    "action_key": "candidate-route-work-reporting-ppt",
                    "action_type": "consider-new-candidate",
                    "target": {"kind": "route", "ref": "work/reporting/ppt"},
                    "priority_score": 3.5,
                    "event_count": 2,
                    "event_ids": ["obs-1", "obs-2"],
                    "routes": ["work/reporting/ppt"],
                    "task_summaries": ["Management deck feedback kept missing a route card"],
                    "signals": {"miss_count": 2},
                    "suggested_artifact_kind": "candidate-card",
                    "apply_eligibility": {
                        "eligible": True,
                        "supported_mode": "new-candidates",
                        "reason": "repeated route group",
                    },
                    "recommended_next_step": "Draft a candidate card for this route.",
                    "ai_decision_required": False,
                },
            )
            write_json(
                actions_dir / "taxonomy-1.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-19T20:00:01+00:00",
                    "action_key": "taxonomy-design-presentation",
                    "action_type": "review-taxonomy",
                    "target": {"kind": "route", "ref": "design/presentation"},
                    "priority_score": 4.0,
                    "event_count": 3,
                    "event_ids": ["obs-3", "obs-4", "obs-5"],
                    "routes": ["design/presentation/message-ordering"],
                    "task_summaries": ["Observed undeclared design presentation route"],
                    "signals": {"gap_count": 3},
                    "suggested_artifact_kind": "taxonomy-branch",
                    "apply_eligibility": {
                        "eligible": False,
                        "supported_mode": "manual-taxonomy",
                        "reason": "proposal only",
                    },
                    "recommended_next_step": "Review whether a new taxonomy branch should be declared.",
                    "ai_decision_required": True,
                },
            )
            write_json(
                actions_dir / "entry-update-1.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-19T20:00:02+00:00",
                    "action_key": "update-model-004",
                    "action_type": "review-entry-update",
                    "target": {"kind": "entry", "entry_id": "model-004"},
                    "priority_score": 2.0,
                    "event_count": 1,
                    "event_ids": ["obs-6"],
                    "routes": ["system/knowledge-library/retrieval"],
                    "task_summaries": ["Retriever preflight card needs narrower wording"],
                    "suggested_artifact_kind": "entry-update",
                    "apply_eligibility": {
                        "eligible": False,
                        "supported_mode": "semantic-review",
                        "reason": "AI should inspect",
                    },
                    "recommended_next_step": "Inspect the current model card and tighten its scope.",
                    "ai_decision_required": True,
                    "split_review_suggestion": {
                        "recommendation": "consider-split-review",
                        "distinct_route_count": 2,
                        "reason": "The same card is now carrying route-specific subcases.",
                    },
                },
            )

            stubs = load_proposal_stubs(repo_root, run_id=run_id)
            report = build_proposal_report(repo_root, run_id=run_id)

            self.assertEqual(len(stubs), 3)
            self.assertEqual(report["stub_count"], 3)
            self.assertEqual(report["valid_stub_count"], 2)
            self.assertEqual(report["invalid_stub_count"], 1)
            self.assertEqual(report["ai_decision_required_count"], 2)
            editorial_summary = report["editorial_summary"]
            self.assertEqual(editorial_summary["total_actions"], 3)
            self.assertEqual(editorial_summary["eligible_actions"], 1)
            self.assertEqual(editorial_summary["non_eligible_actions"], 2)
            self.assertEqual(
                {item["action_type"]: item["count"] for item in editorial_summary["action_type_counts"]},
                {
                    "consider-new-candidate": 1,
                    "review-entry-update": 1,
                    "review-taxonomy": 1,
                },
            )
            supported_modes = {
                item["supported_mode"]: item
                for item in editorial_summary["eligibility_supported_mode_counts"]
            }
            self.assertEqual(supported_modes["new-candidates"]["action_count"], 1)
            self.assertEqual(supported_modes["new-candidates"]["eligible_action_count"], 1)
            self.assertEqual(supported_modes["semantic-review"]["non_eligible_action_count"], 1)
            self.assertEqual(
                editorial_summary["eligible_action_briefs"][0]["action_key"],
                "candidate-route-work-reporting-ppt",
            )
            self.assertEqual(
                {item["reason"]: item["count"] for item in editorial_summary["non_eligible_reason_counts"]},
                {"AI should inspect": 1, "proposal only": 1},
            )
            candidate_action_summary = next(
                item for item in report["action_type_summary"] if item["action_type"] == "consider-new-candidate"
            )
            candidate_artifact_summary = next(
                item
                for item in report["suggested_artifact_kind_summary"]
                if item["suggested_artifact_kind"] == "candidate-card"
            )
            self.assertEqual(candidate_action_summary["stub_count"], 1)
            self.assertEqual(candidate_artifact_summary["stub_count"], 1)

            invalid_stub = next(item for item in stubs if item["action_key"] == "update-model-004")
            self.assertEqual(invalid_stub["missing_fields"], ["signals"])
            self.assertFalse(invalid_stub["valid"])
            self.assertEqual(
                invalid_stub["split_review_suggestion"]["recommendation"],
                "consider-split-review",
            )

    def test_loads_timeline_summary_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            run_id = "timeline-check"
            actions_dir = repo_root / "kb" / "history" / "consolidation" / run_id / "actions"
            write_json(
                actions_dir / "timeline.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-23T09:00:00+00:00",
                    "action_key": "candidate-engineering-debugging-build-failure",
                    "action_type": "consider-new-candidate",
                    "target": {"kind": "route", "ref": "engineering/debugging/build-failure"},
                    "priority_score": 4.0,
                    "event_count": 2,
                    "event_ids": ["obs-1", "obs-2"],
                    "routes": ["engineering/debugging/build-failure"],
                    "task_summaries": ["Repeated debugging correction sequence"],
                    "signals": {"suggested_actions": {"new-candidate": 2}},
                    "suggested_artifact_kind": "candidate-entry-proposal",
                    "apply_eligibility": {"eligible": True, "reason": "repeated route group"},
                    "recommended_next_step": "Draft a candidate card from the repeated episode.",
                    "ai_decision_required": True,
                    "timeline_summary": {
                        "episode_count": 1,
                        "sequence_examples": ["In project repo-a, the work moved from 'guess' to 'trace'."],
                    },
                },
            )

            stubs = load_proposal_stubs(repo_root, run_id=run_id)

            self.assertEqual(stubs[0]["timeline_summary"]["episode_count"], 1)
            self.assertIn("project repo-a", stubs[0]["timeline_summary"]["sequence_examples"][0])

    def test_cli_json_supports_run_id_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            run_id = "nightly-pass"
            actions_dir = repo_root / "kb" / "history" / "consolidation" / run_id / "actions"
            write_json(
                actions_dir / "candidate.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-19T21:00:00+00:00",
                    "action_key": "candidate-work-email",
                    "action_type": "consider-new-candidate",
                    "target": {"kind": "route", "ref": "work/communication/email"},
                    "priority_score": 3,
                    "event_count": 2,
                    "event_ids": ["obs-1", "obs-2"],
                    "routes": ["work/communication/email"],
                    "task_summaries": ["Email card gap"],
                    "signals": {"miss_count": 2},
                    "suggested_artifact_kind": "candidate-card",
                    "apply_eligibility": {"eligible": True, "reason": "repeated"},
                    "recommended_next_step": "Create a candidate card.",
                    "ai_decision_required": False,
                },
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--run-id",
                    run_id,
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(payload["kind"], "local-kb-proposal-inspection")
            self.assertEqual(payload["run_id"], run_id)
            self.assertEqual(payload["stub_count"], 1)
            self.assertEqual(payload["action_type_summary"][0]["action_type"], "consider-new-candidate")

    def test_cli_human_output_supports_run_dir_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            run_dir = repo_root / "kb" / "history" / "consolidation" / "manual-check"
            actions_dir = run_dir / "actions"
            write_json(
                actions_dir / "taxonomy.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": "manual-check",
                    "generated_at": "2026-04-19T21:30:00+00:00",
                    "action_key": "taxonomy-gap-design",
                    "action_type": "review-taxonomy",
                    "target": {"kind": "route", "ref": "design"},
                    "priority_score": 4.5,
                    "event_count": 4,
                    "event_ids": ["obs-1", "obs-2", "obs-3", "obs-4"],
                    "routes": ["design/presentation/message-ordering"],
                    "task_summaries": ["Design route is still undeclared"],
                    "signals": {"gap_count": 4},
                    "suggested_artifact_kind": "taxonomy-branch",
                    "apply_eligibility": {
                        "eligible": False,
                        "supported_mode": "manual-taxonomy",
                        "reason": "AI maintenance only",
                    },
                    "recommended_next_step": "Review the taxonomy gap during maintenance.",
                    "ai_decision_required": True,
                },
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--run-dir",
                    str(run_dir),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertIn("Run manual-check has 1 proposal stubs", result.stdout)
            self.assertIn("Editorial summary:", result.stdout)
            self.assertIn("total_actions=1", result.stdout)
            self.assertIn("eligible_actions=0", result.stdout)
            self.assertIn("eligibility_supported_modes: manual-taxonomy=1", result.stdout)
            self.assertIn("non_eligible_reasons: AI maintenance only=1", result.stdout)
            self.assertIn("By action type:", result.stdout)
            self.assertIn("review-taxonomy", result.stdout)
            self.assertIn("taxonomy-gap-design", result.stdout)

    def test_human_output_shows_split_review_hint_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            run_id = "split-check"
            actions_dir = repo_root / "kb" / "history" / "consolidation" / run_id / "actions"
            write_json(
                actions_dir / "entry-update.json",
                {
                    "schema_version": 1,
                    "kind": "local-kb-proposal-stub",
                    "run_id": run_id,
                    "generated_at": "2026-04-19T22:00:00+00:00",
                    "action_key": "update-model-004",
                    "action_type": "review-entry-update",
                    "target": {"kind": "entry", "entry_id": "model-004"},
                    "priority_score": 4.2,
                    "event_count": 2,
                    "event_ids": ["obs-1", "obs-2"],
                    "routes": ["system/knowledge-library/retrieval", "repository/usage/local-kb-retrieve"],
                    "task_summaries": ["Repeated KB workflow card hit"],
                    "signals": {"suggested_actions": {"update-card": 2}},
                    "suggested_artifact_kind": "entry-update-proposal",
                    "apply_eligibility": {"eligible": False, "reason": "AI should inspect"},
                    "recommended_next_step": "Inspect whether the card should split.",
                    "ai_decision_required": True,
                    "split_review_suggestion": {
                        "recommendation": "consider-split-review",
                        "reason": "The entry now appears across multiple route-specific scenarios.",
                    },
                },
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--repo-root",
                    str(repo_root),
                    "--run-id",
                    run_id,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertIn("split_review=consider-split-review", result.stdout)


if __name__ == "__main__":
    unittest.main()
