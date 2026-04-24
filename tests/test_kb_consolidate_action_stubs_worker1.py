from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_kb.consolidate import consolidate_history


class ConsolidateActionStubTests(unittest.TestCase):
    def test_emit_files_writes_one_action_stub_per_grouped_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-update-1",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:05:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "entry_ids": ["model-release-notes-first"],
                        "route_hint": ["engineering", "debugging", "version-change"],
                        "task_summary": "Release notes card missed a known remediation step",
                    },
                    "rationale": "retrieval=miss, next=update-card",
                    "context": {"suggested_action": "update-card", "hit_quality": "miss"},
                },
                {
                    "event_id": "obs-update-2",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:06:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "entry_ids": ["model-release-notes-first"],
                        "route_hint": ["troubleshooting", "dependency", "regression"],
                        "task_summary": "Release notes card now overlaps with dependency regression routing",
                    },
                    "rationale": "retrieval=weak, next=update-card",
                    "context": {
                        "suggested_action": "update-card",
                        "hit_quality": "weak",
                        "predictive_observation": {
                            "scenario": "When regression triage reaches the same release-notes card from a different route.",
                            "action_taken": "Use the existing card as the first step.",
                            "observed_result": "The card appears broad enough to warrant split review.",
                            "operational_use": "Review whether the card should split by route-specific case.",
                            "reuse_judgment": "Potentially reusable because the same entry is now serving multiple routes.",
                        },
                    },
                },
                {
                    "event_id": "obs-new-cand-1",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:09:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["work", "communication", "email"],
                        "task_summary": "Need a reusable email preference card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {"suggested_action": "new-candidate"},
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="stub-run",
                emit_files=True,
            )

            self.assertEqual(result["candidate_action_count"], 6)
            self.assertEqual(result["action_stub_count"], 6)
            self.assertEqual(
                result["action_stub_dir"],
                "kb/history/consolidation/stub-run/actions",
            )
            self.assertEqual(
                result["artifact_paths"]["action_stub_dir"],
                "kb/history/consolidation/stub-run/actions",
            )
            self.assertEqual(result["artifact_paths"]["action_stub_count"], 6)

            stub_dir = repo_root / result["action_stub_dir"]
            stub_paths = sorted(stub_dir.glob("*.json"))
            self.assertEqual(len(stub_paths), 6)

            stub_payload = json.loads(stub_paths[0].read_text(encoding="utf-8"))
            self.assertEqual(stub_payload["schema_version"], 1)
            self.assertEqual(stub_payload["kind"], "local-kb-consolidation-action-stub")
            self.assertEqual(stub_payload["run_id"], "stub-run")
            self.assertIn(
                stub_payload["action_type"],
                {
                    "review-entry-update",
                    "review-confidence",
                    "review-cross-index",
                    "consider-new-candidate",
                    "review-observation-evidence",
                },
            )
            self.assertIn("priority_score", stub_payload)
            self.assertIn("event_ids", stub_payload)
            self.assertIn("routes", stub_payload)
            self.assertIn("task_summaries", stub_payload)
            self.assertIn("signals", stub_payload)
            self.assertIn("suggested_artifact_kind", stub_payload)
            self.assertIn("apply_eligibility", stub_payload)
            self.assertIn("recommended_next_step", stub_payload)
            self.assertTrue(stub_payload["ai_decision_required"])
            self.assertIn("provenance", stub_payload)
            self.assertIn("predictive_evidence_summary", stub_payload)

            entry_update_stub = next(
                json.loads(path.read_text(encoding="utf-8"))
                for path in stub_paths
                if json.loads(path.read_text(encoding="utf-8"))["action_type"] == "review-entry-update"
            )
            self.assertEqual(
                entry_update_stub["split_review_suggestion"]["recommendation"],
                "consider-split-review",
            )

    def test_apply_mode_also_emits_action_stub_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-new-cand-1",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:09:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["work", "reporting", "ppt"],
                        "task_summary": "Need a reusable reporting deck card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {"suggested_action": "new-candidate"},
                },
                {
                    "event_id": "obs-new-cand-2",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:12:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["work", "reporting", "ppt"],
                        "task_summary": "Need a route-specific slide structure card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {"suggested_action": "new-candidate"},
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-stub-run",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["apply_mode"], "new-candidates")
            self.assertEqual(result["action_stub_count"], 2)
            self.assertIn("apply_path", result["artifact_paths"])

            stub_paths = result["artifact_paths"]["action_stub_paths"]
            self.assertEqual(len(stub_paths), 2)
            stub_payloads = [json.loads((repo_root / stub_path).read_text(encoding="utf-8")) for stub_path in stub_paths]
            candidate_stub = next(item for item in stub_payloads if item["action_type"] == "consider-new-candidate")
            evidence_stub = next(item for item in stub_payloads if item["action_type"] == "review-observation-evidence")
            self.assertEqual(candidate_stub["target"]["ref"], "work/reporting/ppt")
            self.assertFalse(candidate_stub["apply_eligibility"]["eligible"])
            self.assertIn("future utility", candidate_stub["apply_eligibility"]["reason"])
            self.assertEqual(candidate_stub["suggested_artifact_kind"], "candidate-entry-proposal")
            self.assertEqual(evidence_stub["disposition_suggestion"]["recommendation"], "rewrite-or-split-observations")

    def test_action_stub_surfaces_contrastive_candidate_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-contrastive-1",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:09:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "agent-behavior", "postflight"],
                        "task_summary": "Need a reusable postflight branching card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "When Codex closes a non-trivial repository task in this runtime.",
                            "action_taken": "Treat KB postflight as an explicit done check.",
                            "observed_result": "Write-back happens more consistently before finalization.",
                            "contrastive_evidence": {
                                "previous_action": "Leave KB postflight implicit and move straight to the final answer.",
                                "previous_result": "The reusable lesson is often never recorded.",
                                "revised_action": "Make KB postflight part of done and check for a meaningful signal before ending.",
                                "revised_result": "The lesson is more likely to be captured before finalization.",
                            },
                            "operational_use": "Default to an explicit postflight check whenever the task was non-trivial.",
                        },
                    },
                },
                {
                    "event_id": "obs-contrastive-2",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:12:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "agent-behavior", "postflight"],
                        "task_summary": "Need the bad branch to stay visible too",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "When a repository task finishes and the runtime is tempted to stop at the main deliverable.",
                            "action_taken": "Record both the weaker path and the corrected path in the observation.",
                            "observed_result": "Maintenance can synthesize a card with a direct alternative branch.",
                            "contrastive_evidence": {
                                "previous_action": "Only summarize the final success path.",
                                "previous_result": "Maintenance has to guess the bad branch later.",
                                "revised_action": "Record both the weaker path and the corrected path in the observation.",
                                "revised_result": "The candidate scaffold keeps an explicit alternative branch.",
                            },
                            "operational_use": "Keep mistake-versus-correction evidence visible during maintenance.",
                        },
                    },
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="contrastive-stub-run",
                emit_files=True,
            )

            candidate_stub = next(
                action
                for action in result["actions"]
                if action["action_type"] == "consider-new-candidate"
            )
            self.assertEqual(candidate_stub["predictive_evidence_summary"]["contrastive_event_count"], 2)
            self.assertEqual(candidate_stub["predictive_evidence_summary"]["contrastive_example_count"], 2)
            self.assertIn("candidate_scaffold_preview", candidate_stub)
            self.assertEqual(
                candidate_stub["candidate_scaffold_preview"]["title"],
                "Contrastive route lesson in engineering / agent-behavior / postflight",
            )
            self.assertEqual(
                len(candidate_stub["candidate_scaffold_preview"]["predict"]["alternatives"]),
                2,
            )
            self.assertIn(
                "earlier weaker path",
                candidate_stub["candidate_scaffold_preview"]["predict"]["alternatives"][0]["when"],
            )
            self.assertIn(
                "single success summary",
                candidate_stub["candidate_scaffold_preview"]["use"]["guidance"],
            )

    def test_action_stub_surfaces_same_project_timeline_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-timeline-1",
                    "event_type": "observation",
                    "created_at": "2026-04-20T09:00:00+00:00",
                    "source": {
                        "kind": "task",
                        "agent": "worker-1",
                        "thread_ref": "thread-1",
                        "project_ref": "repo-a",
                        "workspace_root": "C:/repos/repo-a",
                    },
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "debugging", "build-failure"],
                        "task_summary": "First attempt patched the wrong script",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "When a build failure is still being localized.",
                            "action_taken": "Patch the first script that looks suspicious.",
                            "observed_result": "The build still fails because the real root cause is elsewhere.",
                            "operational_use": "Avoid treating the first visible script as the root cause.",
                            "reuse_judgment": "Reusable because local-first debugging keeps tempting the same shortcut.",
                        },
                    },
                },
                {
                    "event_id": "obs-timeline-2",
                    "event_type": "observation",
                    "created_at": "2026-04-20T09:08:00+00:00",
                    "source": {
                        "kind": "task",
                        "agent": "worker-1",
                        "thread_ref": "thread-1",
                        "project_ref": "repo-a",
                        "workspace_root": "C:/repos/repo-a",
                    },
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "debugging", "build-failure"],
                        "task_summary": "Second attempt followed the failing dependency chain",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "When the same build failure is inspected through the actual dependency chain.",
                            "action_taken": "Trace the failing dependency chain before patching.",
                            "observed_result": "The real broken dependency is identified and the fix lands in the right file.",
                            "operational_use": "Prefer dependency-chain tracing before editing suspicious leaf files.",
                            "reuse_judgment": "Reusable because the same correction pattern repeats across debugging tasks.",
                        },
                    },
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="timeline-stub-run",
                emit_files=True,
            )

            candidate_action = next(
                action
                for action in result["actions"]
                if action["action_type"] == "consider-new-candidate"
            )
            timeline_summary = candidate_action["timeline_summary"]
            self.assertEqual(timeline_summary["episode_count"], 1)
            self.assertEqual(timeline_summary["episodes"][0]["project_ref"], "repo-a")
            self.assertEqual(
                [step["event_id"] for step in timeline_summary["episodes"][0]["steps"]],
                ["obs-timeline-1", "obs-timeline-2"],
            )
            self.assertIn("project repo-a", timeline_summary["sequence_examples"][0])
            self.assertIn("Observed chronology:", candidate_action["candidate_scaffold_preview"]["if"]["notes"])


if __name__ == "__main__":
    unittest.main()
