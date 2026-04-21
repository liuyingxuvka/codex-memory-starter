from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.dream import run_dream_maintenance


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def write_entry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


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
                                "observed_result": "The reusable lesson is more likely to be written back.",
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
                sleep_cooldown_minutes=0,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["selected_experiment_count"], 1)
            self.assertEqual(
                result["experiments"][0]["route_ref"],
                "engineering/agent-behavior/postflight",
            )

    def test_dream_run_creates_candidate_from_single_adjacent_observation(self) -> None:
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
                            "task_summary": "Need a reusable postflight lesson for this runtime",
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
                sleep_cooldown_minutes=0,
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
            experiments_path = repo_root / result["artifact_paths"]["experiments_path"]
            experiments_payload = json.loads(experiments_path.read_text(encoding="utf-8"))
            self.assertEqual(experiments_payload["experiments"][0]["classification"], "candidate-created")

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-2]["event_type"], "candidate-created")
            self.assertEqual(history_events[-2]["source"]["kind"], "dream-apply")
            self.assertEqual(history_events[-1]["event_type"], "observation")
            self.assertEqual(history_events[-1]["source"]["kind"], "dream-maintenance")

    def test_dream_run_skips_when_recent_sleep_run_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            sleep_run_dir = repo_root / "kb" / "history" / "consolidation" / "kb-sleep-recent"
            sleep_run_dir.mkdir(parents=True, exist_ok=True)
            (sleep_run_dir / "snapshot.json").write_text("{}", encoding="utf-8")
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            result = run_dream_maintenance(
                repo_root=repo_root,
                run_id="kb-dream-skip",
                sleep_cooldown_minutes=120,
            )

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "recent-sleep-run")
            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-1]["event_type"], "dream-skipped")

    def test_dream_run_records_history_only_for_taxonomy_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

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
                sleep_cooldown_minutes=0,
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
            self.assertEqual(history_events[-1]["event_type"], "observation")
            self.assertEqual(history_events[-1]["context"]["suggested_action"], "taxonomy-change")


if __name__ == "__main__":
    unittest.main()
