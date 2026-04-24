from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.consolidate import consolidate_history
from local_kb.snapshots import build_rollback_manifest, restore_artifact
from local_kb.store import write_yaml_file


def write_history(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def sample_entry(entry_id: str, title: str = "Original") -> dict:
    return {
        "id": entry_id,
        "title": title,
        "type": "model",
        "scope": "private",
        "domain_path": ["system", "knowledge-library", "maintenance"],
        "cross_index": [],
        "tags": ["kb", "maintenance"],
        "trigger_keywords": ["kb"],
        "if": {"notes": "When maintaining the local KB."},
        "action": {"description": "Use the current card."},
        "predict": {"expected_result": "Maintenance remains grounded.", "alternatives": []},
        "use": {"guidance": "Keep the card as bounded context."},
        "confidence": 0.8,
        "source": [{"origin": "test", "date": "2026-04-24"}],
        "status": "trusted",
        "updated_at": "2026-04-24",
    }


def update_card_observation(entry_id: str, event_id: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": "observation",
        "created_at": "2026-04-24T08:00:00+00:00",
        "source": {"kind": "task", "agent": "tester"},
        "target": {
            "kind": "task-observation",
            "entry_ids": [entry_id],
            "route_hint": ["system", "knowledge-library", "maintenance"],
            "task_summary": f"Semantic review signal for {entry_id}",
        },
        "rationale": "AI should review this card semantically.",
        "context": {
            "suggested_action": "update-card",
            "hit_quality": "hit",
            "predictive_observation": {
                "scenario": "During KB maintenance.",
                "action_taken": f"Review {entry_id}.",
                "observed_result": "The card needs a sharper operational surface.",
                "operational_use": "Use semantic review to keep the card precise.",
                "reuse_judgment": "Reusable for semantic maintenance testing.",
            },
        },
    }


class SemanticReviewApplyTests(unittest.TestCase):
    def test_semantic_review_rewrites_at_most_three_trusted_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry_ids = ["model-a", "model-b", "model-c", "model-d"]
            for entry_id in entry_ids:
                write_yaml_file(
                    repo_root / "kb" / "private" / "system" / "knowledge-library" / "maintenance" / f"{entry_id}.yaml",
                    sample_entry(entry_id),
                )

            events = [update_card_observation(entry_id, f"obs-{entry_id[-1]}") for entry_id in entry_ids]
            write_history(repo_root / "kb" / "history" / "events.jsonl", events)

            plan_path = repo_root / "kb" / "history" / "consolidation" / "semantic-limit" / "semantic_review_plan.yaml"
            write_yaml_file(
                plan_path,
                {
                    "kind": "local-kb-semantic-review-plan",
                    "trusted_card_limit": 3,
                    "decisions": [
                        {
                            "action_key": f"review-entry-update::entry::{entry_id}",
                            "entry_id": entry_id,
                            "apply": True,
                            "decision": "rewrite",
                            "risk": "medium",
                            "utility_assessment": {
                                "judgment": "useful",
                                "reason": "The card remains useful but needs a narrower operational surface.",
                            },
                            "evidence_event_ids": [f"obs-{entry_id[-1]}"],
                            "rationale": "The cited evidence supports a narrower card surface.",
                            "expected_retrieval_effect": "Future retrieval should present sharper guidance.",
                            "rollback_note": "Restore the previous entry payload from apply.json if needed.",
                            "updated_fields": {
                                "use": {"guidance": f"Updated semantic guidance for {entry_id}."}
                            },
                        }
                        for entry_id in entry_ids
                    ],
                },
            )

            result = consolidate_history(
                repo_root=repo_root,
                run_id="semantic-limit",
                apply_mode="semantic-review",
                semantic_review_plan_path=plan_path,
            )

            self.assertEqual(result["apply_mode"], "semantic-review")
            self.assertEqual(result["apply_summary"]["trusted_card_limit"], 3)
            self.assertEqual(result["apply_summary"]["trusted_card_modified_count"], 3)
            self.assertEqual(result["apply_summary"]["updated_entry_count"], 3)
            self.assertTrue(result["apply_summary"]["i18n_followup"]["required"])
            self.assertTrue(
                any(
                    "Trusted-card semantic review budget exhausted" in item["reason"]
                    for item in result["apply_summary"]["skipped_actions"]
                )
            )

            updated_ids = {item["entry_id"] for item in result["apply_summary"]["updated_entries"]}
            self.assertEqual(len(updated_ids), 3)
            unchanged_ids = set(entry_ids) - updated_ids
            self.assertEqual(len(unchanged_ids), 1)
            for entry_id in updated_ids:
                payload = yaml.safe_load(
                    (
                        repo_root
                        / "kb"
                        / "private"
                        / "system"
                        / "knowledge-library"
                        / "maintenance"
                        / f"{entry_id}.yaml"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(payload["use"]["guidance"], f"Updated semantic guidance for {entry_id}.")

    def test_semantic_review_promotes_candidate_with_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            candidate = sample_entry("cand-semantic", title="Candidate semantic card")
            candidate["status"] = "candidate"
            write_yaml_file(repo_root / "kb" / "candidates" / "cand-semantic.yaml", candidate)
            write_history(
                repo_root / "kb" / "history" / "events.jsonl",
                [
                    {
                        "event_id": "candidate-created-1",
                        "event_type": "candidate-created",
                        "created_at": "2026-04-24T08:00:00+00:00",
                        "source": {"kind": "consolidation-apply", "agent": "kb-consolidate"},
                        "target": {
                            "kind": "candidate-entry",
                            "entry_id": "cand-semantic",
                            "domain_path": ["system", "knowledge-library", "maintenance"],
                            "task_summary": "Candidate needs promotion review",
                        },
                        "rationale": "Candidate was created by sleep maintenance.",
                        "context": {},
                    }
                ],
            )
            plan_path = repo_root / "kb" / "history" / "consolidation" / "semantic-promote" / "semantic_review_plan.yaml"
            write_yaml_file(
                plan_path,
                {
                    "kind": "local-kb-semantic-review-plan",
                    "trusted_card_limit": 3,
                    "decisions": [
                        {
                            "action_key": "review-candidate::entry::cand-semantic",
                            "entry_id": "cand-semantic",
                            "apply": True,
                            "decision": "promote",
                            "risk": "high",
                            "utility_assessment": {
                                "judgment": "useful",
                                "reason": "Reviewed evidence shows the candidate should guide future maintenance tasks.",
                            },
                            "target_scope": "private",
                            "evidence_event_ids": ["candidate-created-1"],
                            "rationale": "The candidate has enough reviewed evidence to enter trusted private scope.",
                            "expected_retrieval_effect": "Future retrieval should prefer this card over raw observations.",
                            "rollback_note": "Move the prior payload from apply.json back to kb/candidates if needed.",
                            "updated_fields": {
                                "title": "Promoted semantic card",
                                "confidence": 0.72,
                            },
                        }
                    ],
                },
            )

            result = consolidate_history(
                repo_root=repo_root,
                run_id="semantic-promote",
                apply_mode="semantic-review",
                semantic_review_plan_path=plan_path,
            )

            promoted_path = (
                repo_root
                / "kb"
                / "private"
                / "system"
                / "knowledge-library"
                / "maintenance"
                / "cand-semantic.yaml"
            )
            self.assertFalse((repo_root / "kb" / "candidates" / "cand-semantic.yaml").exists())
            self.assertTrue(promoted_path.exists())
            promoted = yaml.safe_load(promoted_path.read_text(encoding="utf-8"))
            self.assertEqual(promoted["status"], "trusted")
            self.assertEqual(promoted["scope"], "private")
            self.assertEqual(promoted["title"], "Promoted semantic card")
            self.assertEqual(promoted["confidence"], 0.72)
            self.assertEqual(result["apply_summary"]["updated_entry_count"], 1)

            history_events = [
                json.loads(line)
                for line in (repo_root / "kb" / "history" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-1]["event_type"], "semantic-reviewed")
            self.assertEqual(history_events[-1]["context"]["decision"], "promote")
            self.assertEqual(history_events[-1]["context"]["resolved_action_key"], "review-candidate::entry::cand-semantic")

            run_dir = repo_root / "kb" / "history" / "consolidation" / "semantic-promote"
            manifest = build_rollback_manifest(repo_root, run_dir)
            self.assertIn("semantic-review-entries", manifest["restorable_artifact_ids"])

            restore_result = restore_artifact(repo_root, manifest, "semantic-review-entries")
            self.assertTrue(restore_result["restored"])
            self.assertFalse(promoted_path.exists())
            restored_candidate_path = repo_root / "kb" / "candidates" / "cand-semantic.yaml"
            self.assertTrue(restored_candidate_path.exists())
            restored_candidate = yaml.safe_load(restored_candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(restored_candidate["status"], "candidate")

    def test_semantic_review_rejects_surface_change_without_useful_assessment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_yaml_file(
                repo_root / "kb" / "private" / "system" / "knowledge-library" / "maintenance" / "model-low-utility.yaml",
                sample_entry("model-low-utility"),
            )
            write_history(
                repo_root / "kb" / "history" / "events.jsonl",
                [update_card_observation("model-low-utility", "obs-low-utility")],
            )
            plan_path = repo_root / "kb" / "history" / "consolidation" / "semantic-low-utility" / "semantic_review_plan.yaml"
            write_yaml_file(
                plan_path,
                {
                    "kind": "local-kb-semantic-review-plan",
                    "trusted_card_limit": 3,
                    "decisions": [
                        {
                            "action_key": "review-entry-update::entry::model-low-utility",
                            "entry_id": "model-low-utility",
                            "apply": True,
                            "decision": "rewrite",
                            "risk": "medium",
                            "utility_assessment": {
                                "judgment": "low-utility",
                                "reason": "The review says this would not help future retrieval.",
                            },
                            "evidence_event_ids": ["obs-low-utility"],
                            "rationale": "The cited evidence is not enough to preserve the surface.",
                            "expected_retrieval_effect": "Future retrieval would be less noisy.",
                            "rollback_note": "Restore the previous entry payload from apply.json if needed.",
                            "updated_fields": {"use": {"guidance": "This should not be applied."}},
                        }
                    ],
                },
            )

            result = consolidate_history(
                repo_root=repo_root,
                run_id="semantic-low-utility",
                apply_mode="semantic-review",
                semantic_review_plan_path=plan_path,
            )

            self.assertEqual(result["apply_summary"]["updated_entry_count"], 0)
            self.assertIn(
                "Surface-retaining semantic review decisions require utility_assessment.judgment: useful",
                result["apply_summary"]["skipped_actions"][0]["reason"],
            )

    def test_semantic_review_deprecates_low_utility_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry_path = repo_root / "kb" / "private" / "system" / "knowledge-library" / "maintenance" / "model-deprecate.yaml"
            write_yaml_file(entry_path, sample_entry("model-deprecate"))
            write_history(
                repo_root / "kb" / "history" / "events.jsonl",
                [update_card_observation("model-deprecate", "obs-deprecate")],
            )
            plan_path = repo_root / "kb" / "history" / "consolidation" / "semantic-deprecate" / "semantic_review_plan.yaml"
            write_yaml_file(
                plan_path,
                {
                    "kind": "local-kb-semantic-review-plan",
                    "trusted_card_limit": 3,
                    "decisions": [
                        {
                            "action_key": "review-entry-update::entry::model-deprecate",
                            "entry_id": "model-deprecate",
                            "apply": True,
                            "decision": "deprecate",
                            "risk": "high",
                            "utility_assessment": {
                                "judgment": "low-utility",
                                "reason": "The card is noisy and no longer helps future action selection.",
                            },
                            "evidence_event_ids": ["obs-deprecate"],
                            "rationale": "The card should leave the active retrieval surface.",
                            "expected_retrieval_effect": "Future retrieval should avoid this low-utility rule.",
                            "rollback_note": "Restore the previous trusted entry payload from apply.json if needed.",
                            "updated_fields": {"confidence": 0.2},
                        }
                    ],
                },
            )

            result = consolidate_history(
                repo_root=repo_root,
                run_id="semantic-deprecate",
                apply_mode="semantic-review",
                semantic_review_plan_path=plan_path,
            )

            payload = yaml.safe_load(entry_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "deprecated")
            self.assertEqual(payload["confidence"], 0.2)
            self.assertEqual(result["apply_summary"]["updated_entry_count"], 1)
            history_events = [
                json.loads(line)
                for line in (repo_root / "kb" / "history" / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-1]["context"]["utility_assessment"]["judgment"], "low-utility")


if __name__ == "__main__":
    unittest.main()
