from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.dream import run_dream_maintenance
from local_kb.maintenance_lanes import acquire_lane_lock, lane_lock_path


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def write_entry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_dream_process_entry(repo_root: Path) -> None:
    write_entry(
        repo_root / "kb" / "public" / "predictive-kb" / "agent-lifecycle" / "exploration" / "dream.yaml",
        {
            "id": "model-dream-process",
            "title": "Dream process stays bounded",
            "type": "model",
            "scope": "public",
            "domain_path": ["predictive-kb", "agent-lifecycle", "exploration"],
            "cross_index": ["kb/dream/verification"],
            "related_cards": [],
            "tags": ["dream", "exploration", "maintenance"],
            "trigger_keywords": ["dream", "bounded", "preflight", "observation"],
            "if": {"notes": "A Dream pass is about to select local KB experiments."},
            "action": {"description": "Recall prior Dream-process guidance before selecting routes."},
            "predict": {"expected_result": "The Dream run stays history-only or candidate-only.", "alternatives": []},
            "use": {"guidance": "Record a run-level Dream observation after experiments finish."},
            "confidence": 0.86,
            "source": [{"origin": "test", "date": "2026-04-24"}],
            "status": "trusted",
            "updated_at": "2026-04-24",
        },
    )


class DreamMaintenanceTests(unittest.TestCase):
    def test_dream_selector_prefers_dream_adjacent_over_sleep_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"

            sibling_entry_path = repo_root / "kb" / "public" / "engineering" / "agent-behavior" / "retrieval.yaml"
            write_entry(
                sibling_entry_path,
                {
                    "id": "model-agent-retrieval",
                    "title": "Agent retrieval sibling card",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["engineering", "agent-behavior", "retrieval"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["agent", "retrieval"],
                    "trigger_keywords": ["agent", "retrieval"],
                    "if": {"notes": "Sibling route for dream-adjacent selection."},
                    "action": {"description": "Use retrieval-first debugging."},
                    "predict": {"expected_result": "Agent debugging starts from the retrieval route.", "alternatives": []},
                    "use": {"guidance": "Keep route-specific cards bounded."},
                    "confidence": 0.88,
                    "source": [{"origin": "test", "date": "2026-04-21"}],
                    "status": "trusted",
                    "updated_at": "2026-04-21",
                },
            )

            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "dream-adjacent-1",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["engineering", "agent-behavior", "postflight"],
                            "task_summary": "Need a reusable postflight lesson for this runtime",
                        },
                        "rationale": "next=new-candidate",
                        "context": {
                            "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": "When a non-trivial repository task finishes in this runtime.",
                                "action_taken": "Make KB postflight explicit before finalization.",
                            },
                        },
                    },
                    {
                        "event_id": "sleep-eligible-1",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:10:00+00:00",
                        "source": {"kind": "task", "agent": "worker-2"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["work", "communication", "email"],
                            "task_summary": "Need reusable email preference guidance",
                        },
                        "rationale": "next=new-candidate",
                        "context": {"suggested_action": "new-candidate"},
                    },
                    {
                        "event_id": "sleep-eligible-2",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:11:00+00:00",
                        "source": {"kind": "task", "agent": "worker-2"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["work", "communication", "email"],
                            "task_summary": "Need default reply-language card for email work",
                        },
                        "rationale": "next=new-candidate",
                        "context": {"suggested_action": "new-candidate"},
                    },
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-priority",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 1)
            self.assertEqual(
                result["experiments"][0]["route_ref"],
                "engineering/agent-behavior/postflight",
            )
            self.assertTrue(result["experiments"][0]["is_executable"])

    def test_dream_selects_multiple_valuable_experiments_in_plan_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            write_dream_process_entry(repo_root)

            for path, payload in (
                (
                    repo_root / "kb" / "public" / "engineering" / "agent-behavior" / "retrieval.yaml",
                    {
                        "id": "model-agent-retrieval",
                        "title": "Agent retrieval sibling card",
                        "type": "model",
                        "scope": "public",
                        "domain_path": ["engineering", "agent-behavior", "retrieval"],
                        "cross_index": [],
                        "related_cards": [],
                        "tags": ["agent", "retrieval"],
                        "trigger_keywords": ["agent", "retrieval"],
                        "if": {"notes": "A sibling route exists under engineering / agent-behavior."},
                        "action": {"description": "Use retrieval-first debugging."},
                        "predict": {"expected_result": "Agent debugging starts from retrieval.", "alternatives": []},
                        "use": {"guidance": "Keep route-specific cards bounded."},
                        "confidence": 0.88,
                        "source": [{"origin": "test", "date": "2026-04-21"}],
                        "status": "trusted",
                        "updated_at": "2026-04-21",
                    },
                ),
                (
                    repo_root / "kb" / "public" / "work" / "communication" / "email.yaml",
                    {
                        "id": "model-email-communication",
                        "title": "Email communication sibling card",
                        "type": "model",
                        "scope": "public",
                        "domain_path": ["work", "communication", "email"],
                        "cross_index": [],
                        "related_cards": [],
                        "tags": ["email", "communication"],
                        "trigger_keywords": ["email", "communication"],
                        "if": {"notes": "A sibling route exists under work / communication."},
                        "action": {"description": "Prefer concise email replies."},
                        "predict": {"expected_result": "Email work stays concise.", "alternatives": []},
                        "use": {"guidance": "Keep communication cards actionable."},
                        "confidence": 0.9,
                        "source": [{"origin": "test", "date": "2026-04-21"}],
                        "status": "trusted",
                        "updated_at": "2026-04-21",
                    },
                ),
            ):
                write_entry(path, payload)

            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "dream-multi-1",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["engineering", "agent-behavior", "postflight"],
                        },
                        "rationale": "next=new-candidate",
                        "context": {
                            "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": "When a non-trivial repository task finishes.",
                                "action_taken": "Make KB postflight explicit before finalization.",
                                "observed_result": "The lesson is more likely to be written back.",
                                "operational_use": "Check postflight for non-trivial tasks.",
                            },
                        },
                    },
                    {
                        "event_id": "dream-multi-2",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:05:00+00:00",
                        "source": {"kind": "task", "agent": "worker-2"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["work", "communication", "triage"],
                        },
                        "rationale": "next=new-candidate",
                        "context": {
                            "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": "When inbox triage creates a reusable communication preference.",
                                "action_taken": "Capture the triage route as a bounded candidate.",
                                "observed_result": "Future email work can reuse the preference.",
                                "operational_use": "Route email triage lessons under work communication.",
                            },
                        },
                    },
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-multi",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 2)
            self.assertEqual(result["created_candidate_count"], 2)
            self.assertEqual([item["sequence_index"] for item in result["experiments"]], [1, 2])
            self.assertEqual(
                [item["route_ref"] for item in result["experiments"]],
                ["engineering/agent-behavior/postflight", "work/communication/triage"],
            )

            execution_plan_path = repo_root / result["artifact_paths"]["execution_plan_path"]
            execution_plan_payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(execution_plan_payload["selected_experiment_count"], 2)
            self.assertEqual(
                [item["sequence_index"] for item in execution_plan_payload["selected_experiments"]],
                [1, 2],
            )
            self.assertIn("Select a bounded batch", execution_plan_payload["policy"]["selection_rule"])
            self.assertEqual(execution_plan_payload["policy"]["max_selected_experiments"], 4)
            checkpoint_statuses = {item["id"]: item["status"] for item in execution_plan_payload["checkpoints"]}
            self.assertEqual(checkpoint_statuses["experiment-selection"], "completed")
            self.assertEqual(checkpoint_statuses["validation"], "completed")

    def test_dream_run_creates_candidate_from_single_adjacent_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            write_dream_process_entry(repo_root)

            sibling_entry_path = repo_root / "kb" / "public" / "engineering" / "agent-behavior" / "retrieval.yaml"
            write_entry(
                sibling_entry_path,
                {
                    "id": "model-agent-retrieval",
                    "title": "Agent retrieval sibling card",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["engineering", "agent-behavior", "retrieval"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["agent", "retrieval"],
                    "trigger_keywords": ["agent", "retrieval"],
                    "if": {"notes": "A sibling route already exists under engineering / agent-behavior."},
                    "action": {"description": "Use retrieval-first debugging."},
                    "predict": {"expected_result": "Agent debugging starts from the retrieval route.", "alternatives": []},
                    "use": {"guidance": "Keep route-specific cards bounded."},
                    "confidence": 0.88,
                    "source": [{"origin": "test", "date": "2026-04-21"}],
                    "status": "trusted",
                    "updated_at": "2026-04-21",
                },
            )

            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "dream-obs-1",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["engineering", "agent-behavior", "postflight"],
                        },
                        "rationale": "next=new-candidate",
                        "context": {
                            "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": "When a non-trivial repository task finishes in this runtime.",
                                "action_taken": "Make KB postflight explicit before finalization.",
                                "observed_result": "The reusable lesson is more likely to be written back.",
                                "operational_use": "Check KB postflight explicitly for non-trivial tasks.",
                                "reuse_judgment": "Likely reusable across more than one repository task.",
                            },
                        },
                    }
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-test",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["created_candidate_count"], 1)
            candidate_path = repo_root / result["created_candidates"][0]["entry_path"]
            self.assertTrue(candidate_path.exists())

            candidate_payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(
                candidate_payload["domain_path"],
                ["engineering", "agent-behavior", "postflight"],
            )
            self.assertIn("dream-generated", candidate_payload["tags"])
            self.assertIn("live-task confirmation", candidate_payload["use"]["guidance"])
            self.assertEqual(candidate_payload["source"][0]["origin"], "dream exploration")

            report_path = repo_root / result["artifact_paths"]["report_path"]
            self.assertTrue(report_path.exists())
            preflight_path = repo_root / result["artifact_paths"]["preflight_path"]
            self.assertTrue(preflight_path.exists())
            preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
            self.assertEqual(preflight_payload["kind"], "local-kb-dream-preflight")
            self.assertIn("model-dream-process", preflight_payload["matched_entry_ids"])
            self.assertIn("model-dream-process", result["preflight"]["matched_entry_ids"])
            self.assertTrue(result["run_observation_event_id"])

            plan_path = repo_root / result["artifact_paths"]["plan_path"]
            plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(plan_payload["preflight_matched_entry_count"], 1)
            self.assertIn("model-dream-process", plan_payload["preflight_matched_entry_ids"])

            experiments_path = repo_root / result["artifact_paths"]["experiments_path"]
            experiments_payload = json.loads(experiments_path.read_text(encoding="utf-8"))
            self.assertEqual(experiments_payload["experiments"][0]["classification"], "candidate-created")
            self.assertEqual(experiments_payload["experiments"][0]["sandbox_mode"], "retrieval-ab")
            self.assertEqual(experiments_payload["experiments"][0]["safety_tier"], "workspace-only")
            self.assertIn("validation_plan", experiments_payload["experiments"][0])

            execution_plan_path = repo_root / result["artifact_paths"]["execution_plan_path"]
            execution_plan_payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(execution_plan_payload["status"], "completed")
            self.assertIn("Select a bounded batch", execution_plan_payload["policy"]["selection_rule"])
            self.assertEqual(execution_plan_payload["selected_experiment_count"], 1)
            checkpoint_statuses = {item["id"]: item["status"] for item in execution_plan_payload["checkpoints"]}
            self.assertEqual(checkpoint_statuses["experiment-selection"], "completed")
            self.assertEqual(checkpoint_statuses["validation"], "completed")
            self.assertEqual(checkpoint_statuses["experiment-observation"], "completed")
            self.assertEqual(checkpoint_statuses["run-observation"], "completed")
            self.assertEqual(checkpoint_statuses["report"], "completed")

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-3]["event_type"], "candidate-created")
            self.assertEqual(history_events[-3]["source"]["kind"], "dream-apply")
            self.assertEqual(history_events[-2]["event_type"], "observation")
            self.assertEqual(history_events[-2]["source"]["kind"], "dream-maintenance")
            self.assertIn("Dream experiment", history_events[-2]["target"]["task_summary"])
            self.assertEqual(history_events[-1]["event_type"], "observation")
            self.assertEqual(history_events[-1]["source"]["kind"], "dream-maintenance")
            self.assertEqual(history_events[-1]["event_id"], result["run_observation_event_id"])
            self.assertEqual(
                history_events[-1]["target"]["route_hint"],
                ["predictive-kb", "agent-lifecycle", "exploration"],
            )

    def test_dream_selection_uses_bounded_route_deduped_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_dream_process_entry(repo_root)

            for index in range(6):
                write_entry(
                    repo_root / "kb" / "candidates" / f"cand-route-{index}.yaml",
                    {
                        "id": f"cand-route-{index}",
                        "title": f"Candidate route {index}",
                        "type": "model",
                        "scope": "public",
                        "domain_path": ["engineering", "validation", f"route-{index}"],
                        "cross_index": [],
                        "related_cards": [],
                        "tags": ["validation"],
                        "trigger_keywords": ["validation"],
                        "if": {"notes": f"Candidate {index} needs direct validation."},
                        "action": {"description": "Validate the candidate against local retrieval evidence."},
                        "predict": {
                            "expected_result": "Dream can inspect the card without trusted-memory mutation.",
                            "alternatives": [],
                        },
                        "use": {"guidance": "Keep validation read-only."},
                        "confidence": 0.4,
                        "source": [{"origin": "test", "date": "2026-04-24"}],
                        "status": "candidate",
                        "updated_at": "2026-04-24",
                    },
                )

            result = run_dream_maintenance(repo_root=repo_root, run_id="kb-dream-bounded-batch")

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 4)
            self.assertEqual(len({item["route_ref"] for item in result["experiments"]}), 4)
            execution_plan_path = repo_root / result["artifact_paths"]["execution_plan_path"]
            execution_plan_payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(execution_plan_payload["policy"]["max_selected_experiments"], 4)
            self.assertIn("At most one selected experiment", execution_plan_payload["policy"]["dedupe_rule"])

    def test_dream_prefers_existing_candidate_validation_over_adjacent_candidate_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            write_dream_process_entry(repo_root)

            write_entry(
                repo_root / "kb" / "candidates" / "cand-agent-retrieval.yaml",
                {
                    "id": "cand-agent-retrieval",
                    "title": "Agent retrieval sibling candidate",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["engineering", "agent-behavior", "retrieval"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["agent", "retrieval"],
                    "trigger_keywords": ["agent", "retrieval"],
                    "if": {"notes": "A sibling candidate route already exists under engineering / agent-behavior."},
                    "action": {"description": "Use retrieval-first debugging."},
                    "predict": {"expected_result": "Agent debugging starts from the retrieval route.", "alternatives": []},
                    "use": {"guidance": "Keep route-specific cards bounded."},
                    "confidence": 0.4,
                    "source": [{"origin": "test", "date": "2026-04-21"}],
                    "status": "candidate",
                    "updated_at": "2026-04-21",
                },
            )

            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "dream-adjacent-with-candidate-backlog",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["engineering", "agent-behavior", "postflight"],
                            "task_summary": "Need a reusable postflight lesson for this runtime",
                        },
                        "rationale": "next=new-candidate",
                        "context": {
                            "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": "When a non-trivial repository task finishes in this runtime.",
                                "action_taken": "Make KB postflight explicit before finalization.",
                                "observed_result": "The reusable lesson is more likely to be written back.",
                            },
                        },
                    }
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-candidate-backlog",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["created_candidate_count"], 0)
            self.assertEqual(result["selected_experiment_count"], 2)
            self.assertEqual(result["experiments"][0]["kind"], "entry-validation")
            self.assertEqual(result["experiments"][0]["permitted_write_back"], "history-only")
            self.assertEqual(result["experiments"][1]["classification"], "candidate-backlog")
            self.assertEqual(result["experiments"][1]["permitted_write_back"], "history-only")
            self.assertIn("Sleep to merge", result["experiments"][1]["comment"])

    def test_dream_run_can_validate_existing_candidate_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            write_entry(
                repo_root / "kb" / "candidates" / "cand-entry-validation.yaml",
                {
                    "id": "cand-entry-validation",
                    "title": "Candidate entry needs direct validation",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["engineering", "architecture", "refactor"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["architecture", "refactor"],
                    "trigger_keywords": ["architecture", "refactor"],
                    "if": {"notes": "A candidate card exists without enough confirmation."},
                    "action": {"description": "Validate the candidate against local retrieval evidence."},
                    "predict": {"expected_result": "Dream can inspect the card without mutating trusted memory.", "alternatives": []},
                    "use": {"guidance": "Keep validation read-only and write a history note."},
                    "confidence": 0.4,
                    "source": [{"origin": "test", "date": "2026-04-24"}],
                    "status": "candidate",
                    "updated_at": "2026-04-24",
                },
            )
            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "candidate-replay-source",
                        "event_type": "observation",
                        "created_at": "2026-04-24T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["engineering", "architecture", "refactor"],
                            "task_summary": "Need a safe refactor decision path for architecture work",
                        },
                        "rationale": "retrieval=weak",
                        "context": {
                            "hit_quality": "weak",
                            "suggested_action": "none",
                            "predictive_observation": {
                                "scenario": "When architecture work needs a refactor decision.",
                                "action_taken": "Look for candidate guidance before choosing a refactor path.",
                                "observed_result": "The candidate may clarify the task choice.",
                            },
                        },
                    }
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-entry-validation",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 1)
            self.assertEqual(result["experiments"][0]["kind"], "entry-validation")
            self.assertEqual(result["experiments"][0]["safety_tier"], "read-only")
            self.assertTrue(result["experiments"][0]["is_executable"])
            self.assertEqual(result["experiments"][0]["classification"], "validated")
            self.assertEqual(result["experiments"][0]["source_entry_id"], "cand-entry-validation")
            self.assertEqual(result["experiments"][0]["sandbox_mode"], "scenario-replay")
            self.assertEqual(result["experiments"][0]["evidence_grade"], "strong")
            self.assertEqual(result["experiments"][0]["validation_result"]["status"], "passed")
            self.assertIn("scenario_replay", result["experiments"][0])
            self.assertTrue(
                result["experiments"][0]["scenario_replay"]["decision_delta"]["candidate_improves_task_choice"]
            )
            self.assertTrue(result["experiments"][0]["sleep_handoff_detail"]["sleep_review_ready"])
            self.assertIn("sandbox_path", result["experiments"][0])
            self.assertIn("allowed_writes", result["experiments"][0])
            self.assertIn("scenario-replay", result["experiments"][0]["sleep_handoff"])
            self.assertIn("Architect", result["experiments"][0]["architect_handoff"])
            self.assertEqual(result["created_candidate_count"], 0)

            sandbox_path = repo_root / result["experiments"][0]["sandbox_path"]
            self.assertTrue(sandbox_path.exists())
            self.assertEqual(
                result["experiments"][0]["allowed_writes"],
                ["kb/history/dream/kb-dream-entry-validation/sandbox/"],
            )
            sandbox_payload = json.loads(sandbox_path.read_text(encoding="utf-8"))
            self.assertEqual(sandbox_payload["kind"], "local-kb-dream-sandbox-experiment")
            self.assertEqual(sandbox_payload["sandbox_mode"], "scenario-replay")
            self.assertFalse(sandbox_payload["trusted_card_mutation"])
            self.assertEqual(sandbox_payload["source_entry_id"], "cand-entry-validation")
            self.assertEqual(sandbox_payload["evidence_grade"], "strong")
            self.assertEqual(sandbox_payload["validation_result"]["status"], "passed")
            self.assertEqual(sandbox_payload["allowed_writes"], result["experiments"][0]["allowed_writes"])
            self.assertEqual(sandbox_payload["sandbox_path"], result["experiments"][0]["sandbox_path"])
            self.assertEqual([item["name"] for item in sandbox_payload["variants"]], ["without-tested-card", "with-tested-card"])
            scenario_replay = sandbox_payload["scenario_replay"]
            self.assertEqual(scenario_replay["candidate_card"]["entry_id"], "cand-entry-validation")
            self.assertEqual(scenario_replay["decision_delta"]["candidate_rank"], 1)
            self.assertTrue(scenario_replay["decision_delta"]["candidate_improves_task_choice"])
            self.assertEqual(scenario_replay["decision_delta"]["baseline_exact_route_hit_count"], 0)
            self.assertEqual(sandbox_payload["sleep_handoff_detail"]["candidate_entry_id"], "cand-entry-validation")

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            experiment_event = history_events[-2]
            self.assertEqual(experiment_event["source"]["kind"], "dream-maintenance")
            self.assertEqual(experiment_event["context"]["suggested_action"], "update-card")
            self.assertEqual(experiment_event["target"]["entry_ids"], ["cand-entry-validation"])
            dream_validation = experiment_event["context"]["dream_validation"]
            self.assertEqual(dream_validation["classification"], "validated")
            self.assertEqual(dream_validation["evidence_grade"], "strong")
            self.assertEqual(dream_validation["validation_status"], "passed")
            self.assertEqual(dream_validation["entry_status"], "candidate")
            self.assertEqual(dream_validation["entry_confidence"], 0.4)
            self.assertFalse(dream_validation["trusted_card_mutation"])
            self.assertEqual(dream_validation["handoff_action"], "update-card")
            self.assertIn("scenario-replay", dream_validation["sleep_handoff"])
            self.assertTrue(dream_validation["sleep_handoff_detail"]["sleep_review_ready"])
            self.assertEqual(dream_validation["scenario_replay"]["decision_delta"]["candidate_rank"], 1)
            contrastive = experiment_event["context"]["predictive_observation"]["contrastive_evidence"]
            self.assertIn("without the tested card", contrastive["previous_action"])
            self.assertIn("with the tested card", contrastive["revised_action"])

            execution_plan_path = repo_root / result["artifact_paths"]["execution_plan_path"]
            execution_plan_payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(execution_plan_payload["selected_experiment"]["kind"], "entry-validation")
            self.assertEqual(execution_plan_payload["selected_experiment"]["safety_tier"], "read-only")
            self.assertEqual(execution_plan_payload["selected_experiment"]["sandbox_mode"], "scenario-replay")
            self.assertIn("scenario-replay", execution_plan_payload["policy"]["sandbox_experiment_modes"])
            self.assertIn("retrieval-ab", execution_plan_payload["policy"]["sandbox_experiment_modes"])
            self.assertEqual(
                execution_plan_payload["policy"]["sandbox_allowed_writes"],
                ["kb/history/dream/kb-dream-entry-validation/sandbox/"],
            )
            self.assertEqual(
                execution_plan_payload["artifact_paths"]["sandbox_dir"],
                "kb/history/dream/kb-dream-entry-validation/sandbox",
            )

    def test_dream_run_skips_prior_passed_sandbox_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            write_entry(
                repo_root / "kb" / "candidates" / "cand-entry-validation.yaml",
                {
                    "id": "cand-entry-validation",
                    "title": "Candidate entry needs one validation",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["engineering", "architecture", "refactor"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["architecture", "refactor"],
                    "trigger_keywords": ["architecture", "refactor"],
                    "if": {"notes": "A candidate card exists without enough confirmation."},
                    "action": {"description": "Validate the candidate against local retrieval evidence."},
                    "predict": {
                        "expected_result": "Dream can inspect the card without mutating trusted memory.",
                        "alternatives": [],
                    },
                    "use": {"guidance": "Keep validation read-only and write a history note."},
                    "confidence": 0.4,
                    "source": [{"origin": "test", "date": "2026-04-24"}],
                    "status": "candidate",
                    "updated_at": "2026-04-24",
                },
            )

            first = run_dream_maintenance(repo_root=repo_root, run_id="kb-dream-entry-validation-a")
            second = run_dream_maintenance(repo_root=repo_root, run_id="kb-dream-entry-validation-b")

            self.assertEqual(first["selected_experiment_count"], 1)
            self.assertEqual(first["experiments"][0]["validation_result"]["status"], "passed")
            self.assertEqual(second["selected_experiment_count"], 0)
            self.assertGreaterEqual(second["skipped_prior_sandbox_success_count"], 1)

            opportunities_path = repo_root / second["artifact_paths"]["opportunities_path"]
            opportunities_payload = json.loads(opportunities_path.read_text(encoding="utf-8"))
            skipped = [
                item
                for item in opportunities_payload["opportunities"]
                if item.get("selection_status") == "skipped-prior-sandbox-success"
            ]
            self.assertGreaterEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["prior_sandbox_success"]["run_id"], "kb-dream-entry-validation-a")

    def test_dream_run_noops_when_no_opportunity_clears_value_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"

            write_jsonl(
                history_path,
                [
                    {
                        "event_id": "dream-noop-1",
                        "event_type": "observation",
                        "created_at": "2026-04-21T09:00:00+00:00",
                        "source": {"kind": "task", "agent": "worker-1"},
                        "target": {
                            "kind": "task-observation",
                            "route_hint": ["isolated", "signal", "gap"],
                            "task_summary": "One isolated route has no adjacent evidence",
                        },
                        "rationale": "next=new-candidate",
                        "context": {"suggested_action": "new-candidate"},
                    }
                ],
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-noop",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 0)
            self.assertEqual(result["valuable_opportunity_count"], 0)
            self.assertEqual(result["created_candidate_count"], 0)
            self.assertEqual(result["experiments"], [])

            execution_plan_path = repo_root / result["artifact_paths"]["execution_plan_path"]
            execution_plan_payload = json.loads(execution_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(execution_plan_payload["selected_experiments"], [])
            checkpoint_statuses = {item["id"]: item["status"] for item in execution_plan_payload["checkpoints"]}
            self.assertEqual(checkpoint_statuses["experiment-selection"], "completed")
            self.assertEqual(checkpoint_statuses["validation"], "skipped")
            self.assertEqual(checkpoint_statuses["experiment-observation"], "skipped")

    def test_dream_run_recovers_stale_lane_lock_instead_of_skipping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            acquire_lane_lock(repo_root, "kb-sleep", run_id="kb-sleep-running", poll_seconds=0)
            lock_path = lane_lock_path(repo_root, "local-maintenance")
            lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
            lock_payload["heartbeat_epoch"] = 0
            lock_path.write_text(json.dumps(lock_payload), encoding="utf-8")
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-stale-lock",
            )

            self.assertEqual(result["status"], "completed")
            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertFalse(any(event.get("event_type") == "dream-skipped" for event in history_events))

    def test_dream_run_records_history_only_for_taxonomy_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            write_entry(
                repo_root / "kb" / "taxonomy.yaml",
                {
                    "version": 1,
                    "kind": "official-taxonomy",
                    "nodes": [
                        {
                            "segment": "system",
                            "children": [
                                {
                                    "segment": "agent-lifecycle",
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
            )

            gap_entry_path = repo_root / "kb" / "public" / "system" / "agent-lifecycle" / "sleep.yaml"
            write_entry(
                gap_entry_path,
                {
                    "id": "model-sleep-maintenance",
                    "title": "Sleep maintenance card",
                    "type": "model",
                    "scope": "public",
                    "domain_path": ["system", "agent-lifecycle", "sleep"],
                    "cross_index": [],
                    "related_cards": [],
                    "tags": ["sleep"],
                    "trigger_keywords": ["sleep"],
                    "if": {"notes": "Sleep route exists but taxonomy is undeclared in this temp repo."},
                    "action": {"description": "Run sleep maintenance."},
                    "predict": {"expected_result": "Memory stays consolidated.", "alternatives": []},
                    "use": {"guidance": "Keep sleep separate from other maintenance lanes."},
                    "confidence": 0.9,
                    "source": [{"origin": "test", "date": "2026-04-21"}],
                    "status": "trusted",
                    "updated_at": "2026-04-21",
                },
            )

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-gap",
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["created_candidate_count"], 0)
            self.assertEqual(result["selected_experiment_count"], 1)
            self.assertEqual(result["experiments"][0]["kind"], "taxonomy-gap")
            self.assertEqual(result["experiments"][0]["classification"], "history-only")

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-2]["event_type"], "observation")
            self.assertEqual(history_events[-2]["context"]["suggested_action"], "taxonomy-change")
            self.assertEqual(history_events[-1]["event_type"], "observation")
            self.assertEqual(history_events[-1]["event_id"], result["run_observation_event_id"])


if __name__ == "__main__":
    unittest.main()
