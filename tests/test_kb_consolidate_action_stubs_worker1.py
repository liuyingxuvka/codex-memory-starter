from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_kb.consolidate import consolidate_history
from local_kb.consolidate_apply import action_stub_filename
from local_kb.store import write_yaml_file


class ConsolidateActionStubTests(unittest.TestCase):
    def test_action_stub_filename_stays_windows_path_friendly(self) -> None:
        long_action_key = (
            "review-cross-index::entry::"
            "cand-2026-04-20-codex-runtime-kb-postflight-with-extra-route-detail"
        )

        filename = action_stub_filename(long_action_key, 2)

        self.assertLessEqual(len(filename), 50)
        self.assertRegex(filename, r"^003-[a-z0-9-]+-[a-f0-9]{8}\.json$")

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

    def test_dream_validation_handoff_surfaces_on_candidate_review_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "event_id": "dream-validated-1",
                "event_type": "observation",
                "created_at": "2026-04-24T08:00:00+00:00",
                "source": {"kind": "dream-maintenance", "agent": "kb-dreamer", "thread_ref": "dream-run::a"},
                "target": {
                    "kind": "task-observation",
                    "entry_ids": ["cand-entry-validation"],
                    "route_hint": ["engineering", "architecture", "refactor"],
                    "task_summary": "Dream experiment for engineering / architecture / refactor",
                },
                "rationale": "Dream mode treated this as read-only evidence for later sleep review.",
                "context": {
                    "suggested_action": "update-card",
                    "hit_quality": "hit",
                    "predictive_observation": {
                        "scenario": "A candidate card exists without enough confirmation.",
                        "action_taken": "Ran a bounded Dream retrieval A/B validation.",
                        "observed_result": "Validated the existing card with exact route-local retrieval evidence.",
                        "operational_use": "Sleep should review whether the card should be strengthened or kept watched.",
                    },
                    "dream_validation": {
                        "run_id": "dream-run-a",
                        "opportunity_kind": "entry-validation",
                        "classification": "validated",
                        "evidence_grade": "strong",
                        "validation_status": "passed",
                        "sandbox_mode": "retrieval-ab",
                        "sandbox_path": "kb/history/dream/dream-run-a/sandbox/experiment-001-retrieval-ab.json",
                        "source_entry_id": "cand-entry-validation",
                        "entry_status": "candidate",
                        "entry_confidence": 0.4,
                        "entry_ids": ["cand-entry-validation"],
                        "trusted_card_mutation": False,
                        "sleep_handoff": (
                            "Sleep should use this strong sandbox evidence when deciding whether the existing "
                            "candidate should stay watched or be strengthened."
                        ),
                        "architect_handoff": "No Architect action from this sandbox result.",
                        "handoff_action": "update-card",
                    },
                },
            }
            with history_path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")

            result = consolidate_history(repo_root=repo_root, run_id="dream-handoff", emit_files=True)

            action = next(action for action in result["actions"] if action["action_type"] == "review-candidate")
            self.assertEqual(action["target"]["ref"], "cand-entry-validation")
            self.assertIn("dream_validation_summary", action)
            self.assertEqual(action["dream_validation_summary"]["evidence_event_count"], 1)
            self.assertEqual(action["dream_validation_summary"]["strongest_evidence_grade"], "strong")
            self.assertEqual(action["dream_validation_summary"]["validation_statuses"], {"passed": 1})
            self.assertEqual(action["dream_validation_summary"]["entry_statuses"], ["candidate"])
            self.assertIn("Dream sandbox validation", action["recommended_next_step"])
            self.assertFalse(action["apply_eligibility"]["eligible"])
            self.assertEqual(action["apply_eligibility"]["supported_mode"], "semantic-review")
            self.assertNotIn("review-entry-update", [action["action_type"] for action in result["actions"]])

            stub_path = next(
                Path(repo_root / path)
                for path in result["artifact_paths"]["action_stub_paths"]
                if json.loads((repo_root / path).read_text(encoding="utf-8"))["action_type"] == "review-candidate"
            )
            stub_payload = json.loads(stub_path.read_text(encoding="utf-8"))
            self.assertEqual(stub_payload["dream_validation_summary"]["sandbox_paths"], [event["context"]["dream_validation"]["sandbox_path"]])

    def test_dream_validation_handoff_ignores_weak_or_unsafe_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            base_event = {
                "event_type": "observation",
                "created_at": "2026-04-24T08:00:00+00:00",
                "source": {"kind": "dream-maintenance", "agent": "kb-dreamer"},
                "target": {
                    "kind": "task-observation",
                    "entry_ids": ["cand-entry-validation"],
                    "route_hint": ["engineering", "architecture", "refactor"],
                    "task_summary": "Dream experiment for engineering / architecture / refactor",
                },
                "rationale": "Dream sandbox result is not strong enough for candidate review.",
                "context": {
                    "suggested_action": "none",
                    "hit_quality": "hit",
                    "dream_validation": {
                        "run_id": "dream-run-a",
                        "opportunity_kind": "entry-validation",
                        "classification": "validated",
                        "evidence_grade": "weak",
                        "validation_status": "passed",
                        "sandbox_mode": "retrieval-ab",
                        "sandbox_path": "kb/history/dream/dream-run-a/sandbox/experiment-001-retrieval-ab.json",
                        "source_entry_id": "cand-entry-validation",
                        "entry_status": "candidate",
                        "entry_confidence": 0.4,
                        "entry_ids": ["cand-entry-validation"],
                        "trusted_card_mutation": False,
                        "sleep_handoff": "Sleep should not strengthen this from weak evidence.",
                        "handoff_action": "none",
                    },
                },
            }
            unsafe_event = json.loads(json.dumps(base_event))
            unsafe_event["event_id"] = "dream-unsafe-1"
            unsafe_event["context"]["dream_validation"]["evidence_grade"] = "strong"
            unsafe_event["context"]["dream_validation"]["trusted_card_mutation"] = True
            weak_event = json.loads(json.dumps(base_event))
            weak_event["event_id"] = "dream-weak-1"
            with history_path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(weak_event) + "\n")
                handle.write(json.dumps(unsafe_event) + "\n")

            result = consolidate_history(repo_root=repo_root, run_id="dream-handoff-negative")

            self.assertNotIn("review-candidate", [action["action_type"] for action in result["actions"]])
            self.assertNotIn("review-entry-update", [action["action_type"] for action in result["actions"]])

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
            self.assertEqual(candidate_action["scope_assessment"]["scope"], "single-project-generalizable")
            self.assertEqual(
                candidate_action["candidate_scaffold_preview"]["scope_assessment"]["scope"],
                "single-project-generalizable",
            )
            self.assertIn(
                "source project in provenance",
                candidate_action["candidate_scaffold_preview"]["use"]["guidance"],
            )

    def test_skill_specific_candidate_keeps_skill_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "event_id": "obs-skill-1",
                "event_type": "observation",
                "created_at": "2026-05-15T08:00:00+00:00",
                "source": {
                    "kind": "task",
                    "agent": "tester",
                    "project_ref": "khaos-brain",
                    "thread_ref": "thread-skill",
                },
                "target": {
                    "kind": "task-observation",
                    "route_hint": ["codex", "workflow", "skills"],
                    "task_summary": "The presentations Skill needs a bounded usage rule",
                },
                "rationale": "next=new-candidate",
                "context": {
                    "suggested_action": "new-candidate",
                    "predictive_observation": {
                        "scenario": "When a task asks to create or edit a slide deck.",
                        "action_taken": "Use the presentations Skill before writing deck code.",
                        "observed_result": "The deck workflow keeps render-and-verify expectations visible.",
                        "operational_use": "Invoke the presentations Skill for deck tasks and keep its validation boundary.",
                        "reuse_judgment": "Reusable only when the presentations Skill or equivalent deck workflow is relevant.",
                    },
                },
            }
            history_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

            result = consolidate_history(repo_root=repo_root, run_id="skill-scope-run", emit_files=True)

            candidate_action = next(action for action in result["actions"] if action["action_type"] == "consider-new-candidate")
            self.assertEqual(candidate_action["scope_assessment"]["scope"], "skill-specific")
            self.assertEqual(candidate_action["candidate_scaffold_preview"]["scope_assessment"]["scope"], "skill-specific")
            self.assertIn("Skill-specific lesson", candidate_action["candidate_scaffold_preview"]["title"])
            self.assertIn("Skill, plugin, connector", candidate_action["candidate_scaffold_preview"]["use"]["guidance"])

    def test_existing_project_shaped_card_gets_generalization_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_yaml_file(
                repo_root / "kb" / "private" / "engineering" / "release" / "model-khaos-release.yaml",
                {
                    "id": "model-khaos-release",
                    "title": "Khaos Brain release checks",
                    "type": "model",
                    "scope": "private",
                    "domain_path": ["engineering", "release"],
                    "cross_index": [],
                    "tags": ["khaos-brain", "release"],
                    "trigger_keywords": ["khaos brain release"],
                    "if": {"notes": "When publishing Khaos Brain."},
                    "action": {"description": "Check tag and release state."},
                    "predict": {"expected_result": "Release drift is avoided.", "alternatives": []},
                    "use": {"guidance": "Check Khaos Brain releases before publishing."},
                    "confidence": 0.7,
                    "source": [{"origin": "test", "date": "2026-05-15"}],
                    "status": "trusted",
                    "updated_at": "2026-05-15",
                },
            )
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            event = {
                "event_id": "obs-release-general",
                "event_type": "observation",
                "created_at": "2026-05-15T09:00:00+00:00",
                "source": {"kind": "task", "agent": "tester", "project_ref": "Khaos Brain"},
                "target": {
                    "kind": "task-observation",
                    "entry_ids": ["model-khaos-release"],
                    "route_hint": ["engineering", "release", "versioning"],
                    "task_summary": "Repository release needed state audit before version bump",
                },
                "rationale": "next=update-card",
                "context": {
                    "suggested_action": "update-card",
                    "hit_quality": "hit",
                    "predictive_observation": {
                        "scenario": "When a repository has version, tag, and GitHub Release surfaces.",
                        "action_taken": "Audit current release state before deciding whether to bump version.",
                        "observed_result": "The release path avoids creating unnecessary versions for the same source state.",
                        "operational_use": "Use release-state audit before publishing repositories with version/tag/release surfaces.",
                    },
                },
            }
            history_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

            result = consolidate_history(repo_root=repo_root, run_id="generalize-old-card-run", emit_files=True)

            update_action = next(action for action in result["actions"] if action["action_type"] == "review-entry-update")
            self.assertEqual(update_action["scope_assessment"]["scope"], "single-project-generalizable")
            self.assertEqual(
                update_action["generalization_review_suggestion"]["recommendation"],
                "rewrite-as-general-rule",
            )


if __name__ == "__main__":
    unittest.main()
