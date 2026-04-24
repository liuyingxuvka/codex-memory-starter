from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.consolidate import consolidate_history
from local_kb.consolidate_apply import apply_new_candidate_actions


class ConsolidateApplyModeTests(unittest.TestCase):
    def test_new_candidate_apply_skips_actions_from_other_apply_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-related-1",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:09:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["codex", "runtime-behavior", "tool-environment"],
                        "task_summary": "Need related-card update only",
                    },
                    "rationale": "next=update-card",
                    "context": {"suggested_action": "update-card"},
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            summary = apply_new_candidate_actions(
                repo_root=repo_root,
                actions=[
                    {
                        "action_key": "review-related-cards::entry::model-runtime",
                        "action_type": "review-related-cards",
                        "target": {"kind": "entry", "ref": "model-runtime"},
                        "event_count": 1,
                        "event_ids": ["obs-related-1"],
                        "apply_eligibility": {
                            "supported_mode": "related-cards",
                            "eligible": True,
                            "reason": "Repeated co-use suggests a stable direct related-card link set.",
                        },
                    }
                ],
                events=events,
                run_id="wrong-mode",
                generated_at="2026-04-19T08:30:00+00:00",
            )

            self.assertEqual(summary["created_candidate_count"], 0)
            self.assertEqual(summary["skipped_action_count"], 1)
            self.assertIn("related-cards apply mode", summary["skipped_actions"][0]["reason"])
            self.assertFalse((repo_root / "kb" / "candidates").exists())

    def test_apply_mode_creates_candidate_for_grouped_route_actions_only(self) -> None:
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
                        "route_hint": ["work", "communication", "email"],
                        "task_summary": "Need reusable email preference guidance",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "Email workflow tasks repeatedly need route-specific preference guidance.",
                            "action_taken": "Record a new-candidate observation for the communication email route.",
                            "observed_result": "Maintenance can synthesize a candidate instead of losing the repeated route gap.",
                            "operational_use": "Prefer a route-specific email preference card when similar email tasks recur.",
                        },
                    },
                },
                {
                    "event_id": "obs-new-cand-2",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:12:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["work", "communication", "email"],
                        "task_summary": "Need default reply-language card for email work",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "Email reply-language tasks keep exposing missing reusable guidance.",
                            "action_taken": "Group the observation under the communication email route.",
                            "observed_result": "The route has enough reusable evidence for a candidate scaffold.",
                            "operational_use": "Use the email route card to choose default reply-language behavior later.",
                        },
                    },
                },
                {
                    "event_id": "obs-update-1",
                    "event_type": "observation",
                    "created_at": "2026-04-19T08:15:00+00:00",
                    "source": {"kind": "task", "agent": "worker-1"},
                    "target": {
                        "kind": "task-observation",
                        "entry_ids": ["model-release-notes-first"],
                        "route_hint": ["engineering", "debugging", "version-change"],
                        "task_summary": "Release notes card needs a confidence update",
                    },
                    "rationale": "next=update-card",
                    "context": {"suggested_action": "update-card", "hit_quality": "miss"},
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-20260419",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["candidate_action_count"], 5)
            self.assertEqual(result["apply_mode"], "new-candidates")
            self.assertEqual(result["apply_summary"]["created_candidate_count"], 1)
            self.assertEqual(result["apply_summary"]["skipped_action_count"], 4)
            self.assertTrue(result["apply_summary"]["i18n_followup"]["required"])
            self.assertEqual(result["apply_summary"]["i18n_followup"]["missing_entry_count"], 1)
            self.assertIn("snapshot_path", result["artifact_paths"])
            self.assertIn("proposal_path", result["artifact_paths"])
            self.assertIn("apply_path", result["artifact_paths"])

            created_candidate = result["apply_summary"]["created_candidates"][0]
            candidate_path = repo_root / created_candidate["entry_path"]
            self.assertTrue(candidate_path.exists())

            candidate_payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate_payload["status"], "candidate")
            self.assertEqual(candidate_payload["scope"], "private")
            self.assertEqual(candidate_payload["domain_path"], ["work", "communication", "email"])
            self.assertEqual(candidate_payload["source"][0]["run_id"], "apply-20260419")
            self.assertIn("auto-created scaffold", candidate_payload["use"]["guidance"])

            apply_payload = json.loads(
                (repo_root / result["artifact_paths"]["apply_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(apply_payload["created_candidate_count"], 1)
            self.assertEqual(
                sorted(item["action_type"] for item in apply_payload["skipped_actions"]),
                [
                    "review-confidence",
                    "review-cross-index",
                    "review-entry-update",
                    "review-observation-evidence",
                ],
            )

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(history_events), 4)
            self.assertEqual(history_events[-1]["event_type"], "candidate-created")
            self.assertEqual(history_events[-1]["source"]["kind"], "consolidation-apply")
            self.assertEqual(
                history_events[-1]["context"]["action_key"],
                created_candidate["action_key"],
            )

    def test_apply_mode_creates_low_confidence_seed_candidate_from_complete_single_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "event_id": "obs-new-cand-1",
                "event_type": "observation",
                "created_at": "2026-04-19T08:09:00+00:00",
                "source": {"kind": "task", "agent": "worker-1"},
                "target": {
                    "kind": "task-observation",
                    "route_hint": ["work", "reporting", "ppt"],
                    "task_summary": "Need a reusable slide-outline card",
                },
                "rationale": "next=new-candidate",
                "context": {
                    "suggested_action": "new-candidate",
                    "predictive_observation": {
                        "scenario": "Slide-outline tasks repeatedly need a reusable starting structure.",
                        "action_taken": "Create a route-specific seed candidate from the complete observation.",
                        "observed_result": "The lesson becomes retrievable for later maintenance without being trusted yet.",
                        "operational_use": "Use the seed only as provisional scaffolding until more evidence arrives.",
                    },
                },
            }
            history_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-single",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["candidate_action_count"], 1)
            self.assertEqual(result["apply_summary"]["created_candidate_count"], 1)
            self.assertEqual(result["apply_summary"]["skipped_action_count"], 0)
            candidate_action = next(action for action in result["actions"] if action["action_type"] == "consider-new-candidate")
            self.assertTrue(candidate_action["apply_eligibility"]["eligible"])
            self.assertEqual(candidate_action["apply_eligibility"]["candidate_creation_mode"], "seed")

            created_candidate = result["apply_summary"]["created_candidates"][0]
            candidate_path = repo_root / created_candidate["entry_path"]
            candidate_payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate_payload["confidence"], 0.4)
            self.assertIn("seed-candidate", candidate_payload["tags"])
            self.assertEqual(candidate_payload["source"][0]["candidate_creation_mode"], "seed")
            self.assertIn("retrieval seed", candidate_payload["use"]["guidance"])
            self.assertEqual(
                result["apply_summary"]["i18n_followup"]["entries"][0]["entry_id"],
                candidate_payload["id"],
            )
            self.assertIn(
                "title",
                result["apply_summary"]["i18n_followup"]["entries"][0]["missing_i18n_fields"],
            )

            history_events = [
                json.loads(line)
                for line in history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(history_events), 2)
            self.assertEqual(history_events[-1]["event_type"], "candidate-created")

    def test_apply_mode_skips_incomplete_single_observation_route_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "event_id": "obs-new-cand-1",
                "event_type": "observation",
                "created_at": "2026-04-19T08:09:00+00:00",
                "source": {"kind": "task", "agent": "worker-1"},
                "target": {
                    "kind": "task-observation",
                    "route_hint": ["work", "reporting", "ppt"],
                    "task_summary": "Need a reusable slide-outline card",
                },
                "rationale": "next=new-candidate",
                "context": {"suggested_action": "new-candidate"},
            }
            history_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-single-incomplete",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["candidate_action_count"], 2)
            self.assertEqual(result["apply_summary"]["created_candidate_count"], 0)
            self.assertEqual(result["apply_summary"]["skipped_action_count"], 2)
            self.assertFalse((repo_root / "kb" / "candidates").exists())
            candidate_action = next(action for action in result["actions"] if action["action_type"] == "consider-new-candidate")
            self.assertFalse(candidate_action["apply_eligibility"]["eligible"])
            self.assertIn("complete predictive evidence", candidate_action["apply_eligibility"]["reason"])
            self.assertIn("review-observation-evidence", [item["action_type"] for item in result["apply_summary"]["skipped_actions"]])

    def test_apply_mode_skips_low_utility_single_observation_route_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            event = {
                "event_id": "obs-low-utility-1",
                "event_type": "observation",
                "created_at": "2026-04-19T08:09:00+00:00",
                "source": {"kind": "task", "agent": "worker-1"},
                "target": {
                    "kind": "task-observation",
                    "route_hint": ["work", "reporting", "ppt"],
                    "task_summary": "Complete but useless observation should not become a card",
                },
                "rationale": "next=new-candidate",
                "context": {
                    "suggested_action": "new-candidate",
                    "predictive_observation": {
                        "scenario": "A one-time reporting task happened.",
                        "action_taken": "Record the observation without reusable action guidance.",
                        "observed_result": "There is no future retrieval value.",
                    },
                },
            }
            history_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-single-low-utility",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["apply_summary"]["created_candidate_count"], 0)
            candidate_action = next(action for action in result["actions"] if action["action_type"] == "consider-new-candidate")
            self.assertFalse(candidate_action["apply_eligibility"]["eligible"])
            self.assertIn("future utility", candidate_action["apply_eligibility"]["reason"])
            evidence_action = next(action for action in result["actions"] if action["action_type"] == "review-observation-evidence")
            self.assertEqual(evidence_action["reasons"], ["predictive-utility:missing-operational-use"])
            self.assertFalse((repo_root / "kb" / "candidates").exists())

    def test_apply_mode_skips_broad_routes_even_when_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            events = [
                {
                    "event_id": "obs-broad-1",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:09:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering"],
                        "task_summary": "Need a general engineering refactor card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "A broad engineering task suggests reusable guidance but lacks a specific route.",
                            "action_taken": "Keep the broad route in proposal-only review.",
                            "observed_result": "Maintenance should not create a broad scaffold even with utility.",
                            "operational_use": "Review broad engineering observations for a narrower route before card creation.",
                        },
                    },
                },
                {
                    "event_id": "obs-broad-2",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:10:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering"],
                        "task_summary": "Need another engineering workflow card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "A second broad engineering task still lacks a precise maintenance route.",
                            "action_taken": "Keep the route-depth gate active for the broad group.",
                            "observed_result": "The broad route remains ineligible for automatic candidate creation.",
                            "operational_use": "Prefer narrowing broad engineering lessons before creating cards.",
                        },
                    },
                },
                {
                    "event_id": "obs-specific-1",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:11:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "ui-state", "desktop-app"],
                        "task_summary": "Need a desktop UI-state recovery card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "Desktop UI-state tasks need reusable recovery guidance.",
                            "action_taken": "Group this observation under the desktop app UI-state route.",
                            "observed_result": "The specific route can produce a candidate while broad routes stay manual.",
                            "operational_use": "Prefer the desktop UI-state card for future recovery tasks.",
                        },
                    },
                },
                {
                    "event_id": "obs-specific-2",
                    "event_type": "observation",
                    "created_at": "2026-04-20T08:12:00+00:00",
                    "source": {"kind": "task", "agent": "worker-2"},
                    "target": {
                        "kind": "task-observation",
                        "route_hint": ["engineering", "ui-state", "desktop-app"],
                        "task_summary": "Need a second desktop UI-state recovery card",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "A second desktop UI-state task repeats the same route gap.",
                            "action_taken": "Group the second observation under the same desktop app route.",
                            "observed_result": "The repeated specific route remains eligible for candidate creation.",
                            "operational_use": "Use the desktop UI-state candidate when future app recovery tasks recur.",
                        },
                    },
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-broad-route",
                apply_mode="new-candidates",
            )

            broad_action = next(
                action
                for action in result["actions"]
                if action["action_type"] == "consider-new-candidate"
                and action["target"]["ref"] == "engineering"
            )
            specific_action = next(
                action
                for action in result["actions"]
                if action["action_type"] == "consider-new-candidate"
                and action["target"]["ref"] == "engineering/ui-state/desktop-app"
            )

            self.assertFalse(broad_action["apply_eligibility"]["eligible"])
            self.assertIn("at least 3 segments", broad_action["apply_eligibility"]["reason"])
            self.assertTrue(specific_action["apply_eligibility"]["eligible"])
            self.assertEqual(result["apply_summary"]["created_candidate_count"], 1)
            self.assertEqual(
                result["apply_summary"]["created_candidates"][0]["action_key"],
                specific_action["action_key"],
            )

    def test_apply_mode_requires_route_depth_three_for_auto_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            history_path = repo_root / "kb" / "history" / "events.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)

            route_groups = [
                (
                    "broad-1",
                    ["engineering"],
                    [
                        "Need a reusable engineering guidance card",
                        "Engineering tasks keep surfacing the same missing heuristic",
                    ],
                ),
                (
                    "broad-2",
                    ["engineering", "agent-behavior"],
                    [
                        "Need a reusable agent-behavior guidance card",
                        "Agent behavior work still lacks a shared predictive model",
                    ],
                ),
                (
                    "specific",
                    ["engineering", "agent-behavior", "unittest"],
                    [
                        "Need a reusable unittest strategy card",
                        "Unittest planning work keeps exposing the same missing guidance",
                    ],
                ),
            ]

            events: list[dict[str, object]] = []
            for group_index, (group_name, route_hint, summaries) in enumerate(route_groups, start=1):
                for observation_index, task_summary in enumerate(summaries, start=1):
                    minute = (group_index - 1) * 2 + observation_index
                    events.append(
                        {
                            "event_id": f"{group_name}-{observation_index}",
                            "event_type": "observation",
                            "created_at": f"2026-04-19T08:{minute:02d}:00+00:00",
                            "source": {"kind": "task", "agent": "worker-1"},
                            "target": {
                                "kind": "task-observation",
                                "route_hint": route_hint,
                                "task_summary": task_summary,
                            },
                            "rationale": "next=new-candidate",
                            "context": {
                                "suggested_action": "new-candidate",
                            "predictive_observation": {
                                "scenario": f"Repeated tasks keep routing through {' / '.join(route_hint)}.",
                                "action_taken": "Record another new-candidate observation for the same route.",
                                "observed_result": "The route still lacks a reusable predictive card.",
                                "operational_use": f"Prefer route-specific guidance for future {' / '.join(route_hint)} tasks.",
                            },
                        },
                        }
                    )

            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-depth",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["candidate_action_count"], 3)
            self.assertEqual(result["apply_summary"]["created_candidate_count"], 1)
            self.assertEqual(result["apply_summary"]["skipped_action_count"], 2)

            actions_by_target = {
                action["target"]["ref"]: action
                for action in result["actions"]
                if action["action_type"] == "consider-new-candidate"
            }
            self.assertFalse(actions_by_target["engineering"]["apply_eligibility"]["eligible"])
            self.assertIn(
                "at least 3 segments",
                actions_by_target["engineering"]["apply_eligibility"]["reason"],
            )
            self.assertFalse(actions_by_target["engineering/agent-behavior"]["apply_eligibility"]["eligible"])
            self.assertIn(
                "at least 3 segments",
                actions_by_target["engineering/agent-behavior"]["apply_eligibility"]["reason"],
            )
            self.assertTrue(actions_by_target["engineering/agent-behavior/unittest"]["apply_eligibility"]["eligible"])

            skipped_targets = {
                item["target"]["ref"]
                for item in result["apply_summary"]["skipped_actions"]
                if item["action_type"] == "consider-new-candidate"
            }
            self.assertEqual(
                skipped_targets,
                {"engineering", "engineering/agent-behavior"},
            )

            created_candidate = result["apply_summary"]["created_candidates"][0]
            candidate_path = repo_root / created_candidate["entry_path"]
            self.assertTrue(candidate_path.exists())

            candidate_payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual(
                candidate_payload["domain_path"],
                ["engineering", "agent-behavior", "unittest"],
            )
            self.assertEqual(len(list((repo_root / "kb" / "candidates").glob("*.yaml"))), 1)

    def test_apply_mode_writes_contrastive_candidate_branches_from_observations(self) -> None:
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
                                "previous_result": "The task outcome may ship, but the reusable lesson is often never recorded.",
                                "revised_action": "Make KB postflight part of done and check for a meaningful signal before ending.",
                                "revised_result": "The lesson is more likely to be captured as a reusable observation or candidate.",
                            },
                            "operational_use": "Default to an explicit postflight check whenever the task was non-trivial.",
                            "reuse_judgment": "This is reusable because the same runtime keeps dropping the memory write-back when it stays implicit.",
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
                        "task_summary": "Need the card to preserve the weaker branch too",
                    },
                    "rationale": "next=new-candidate",
                    "context": {
                        "suggested_action": "new-candidate",
                        "predictive_observation": {
                            "scenario": "When a repository task finishes and the runtime is tempted to stop at the main deliverable.",
                            "action_taken": "Explicitly ask whether there was a KB miss, route gap, or reusable lesson.",
                            "observed_result": "Observation quality improves because the mistake-and-fix branch is still visible.",
                            "contrastive_evidence": {
                                "previous_action": "Only summarize the final success path.",
                                "previous_result": "Maintenance later has to guess the bad branch instead of reading it directly.",
                                "revised_action": "Record both the weaker path and the corrected path in the observation.",
                                "revised_result": "Maintenance can synthesize a card with a direct alternative branch.",
                            },
                            "operational_use": "Keep mistake-versus-correction evidence visible so candidate synthesis can stay model-like.",
                            "reuse_judgment": "This should recur whenever the same runtime learns from correction episodes.",
                        },
                    },
                },
            ]
            with history_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(json.dumps(event) + "\n")

            result = consolidate_history(
                repo_root=repo_root,
                run_id="apply-contrastive",
                apply_mode="new-candidates",
            )

            self.assertEqual(result["apply_summary"]["created_candidate_count"], 1)
            created_candidate = result["apply_summary"]["created_candidates"][0]
            candidate_path = repo_root / created_candidate["entry_path"]
            candidate_payload = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))

            self.assertEqual(candidate_payload["title"], "Contrastive route lesson in engineering / agent-behavior / postflight")
            self.assertIn(
                "weaker earlier path and a stronger revised path",
                candidate_payload["if"]["notes"],
            )
            self.assertIn(
                "stronger revised path",
                candidate_payload["action"]["description"],
            )
            self.assertIn(
                "reusable observation or candidate",
                candidate_payload["predict"]["expected_result"],
            )
            self.assertEqual(len(candidate_payload["predict"]["alternatives"]), 2)
            self.assertIn(
                "earlier weaker path",
                candidate_payload["predict"]["alternatives"][0]["when"],
            )
            self.assertIn(
                "single success summary",
                candidate_payload["use"]["guidance"],
            )
            self.assertIn("contrastive-evidence", candidate_payload["tags"])


if __name__ == "__main__":
    unittest.main()
