from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_kb.architect import record_architect_sandbox_trial_result, run_architect_maintenance
from local_kb.feedback import build_observation, record_observation


class KBArchitectTests(unittest.TestCase):
    def test_architect_runner_maintains_mechanism_queue_with_three_axes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Architect automation should enforce postflight validation signal {index}",
                    route_hint="system/knowledge-library/maintenance",
                    hit_quality="hit",
                    outcome="Repeated mechanism signal found.",
                    comment="Architect should review automation postflight and validation mechanics.",
                    suggested_action="code-change",
                    scenario="Scheduled KB mechanism maintenance exposes repeated postflight validation issues.",
                    action_taken="Record the signal as a mechanism proposal, not a card-content edit.",
                    observed_result="The proposal queue has repeated evidence for a mechanism patch.",
                    operational_use="Architect should classify the signal with Evidence, Impact, and Safety.",
                    reuse_judgment="Reusable for the Architect proposal lifecycle.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"test-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            result = run_architect_maintenance(
                repo_root,
                run_id="architect-test",
            )

            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["proposal_count"], 1)
            self.assertGreaterEqual(result["ready_for_patch_count"], 1)
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            self.assertTrue(queue_path.exists())

            proposals = result["status_counts"]
            self.assertIn("ready-for-patch", proposals)

            run_dir = repo_root / "kb" / "history" / "architecture" / "runs" / "architect-test"
            self.assertTrue((run_dir / "execution_plan.json").exists())
            self.assertTrue((run_dir / "preflight.json").exists())
            self.assertTrue((run_dir / "decisions.json").exists())
            self.assertTrue(result["history_event_ids"])
            self.assertGreaterEqual(result["patch_plan_count"], 1)

    def test_skill_maintenance_signal_enters_architect_queue_as_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Skill prompt should absorb repeated fallback evidence {index}",
                    route_hint="codex/workflow/skills",
                    hit_quality="hit",
                    outcome="Repeated skill-use evidence found.",
                    comment="Sleep should keep the card lesson path while Architect reviews the Skill workflow patch.",
                    suggested_action="new-candidate",
                    scenario="A local Skill repeatedly needs the same fallback instruction to avoid rework.",
                    action_taken="Record the card-level evidence and surface a proposal-only Skill maintenance signal.",
                    observed_result="Architect can review a Skill workflow patch without Sleep rewriting the Skill directly.",
                    operational_use="Review the Codex Skill prompt when repeated skill-use evidence shows the workflow instruction should change.",
                    reuse_judgment="Reusable for Skill maintenance proposals.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"skill-test-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            result = run_architect_maintenance(
                repo_root,
                run_id="architect-skill-test",
            )

            self.assertEqual(result["status"], "completed")
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            skill_proposal = next(
                item
                for item in queue["proposals"]
                if item["category"] == "skill-maintenance"
                and item["target"]["ref"] == "codex/workflow/skills"
            )
            self.assertEqual(skill_proposal["status"], "ready-for-patch")
            self.assertEqual(skill_proposal["safety"]["level"], "medium")
            self.assertEqual(skill_proposal["evidence"]["signal_count"], 3)
            self.assertEqual(skill_proposal["source_actions"][0]["action_type"], "review-code-change")
            self.assertEqual(skill_proposal["execution_packet"]["execution_mode"], "patch-plan")
            self.assertFalse(skill_proposal["execution_packet"]["runner_direct_write_allowed"])
            self.assertTrue(skill_proposal["execution_packet"]["requires_patch_or_human"])
            self.assertIn(".agents/skills/**", skill_proposal["execution_packet"]["allowed_paths"])

    def test_ready_for_apply_prompt_proposal_gets_execution_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Architect prompt should carry execution packet closure guidance {index}",
                    route_hint="system/knowledge-library/maintenance",
                    hit_quality="hit",
                    outcome="Repeated prompt mechanism signal found.",
                    comment="Architect prompt should distinguish ready-for-apply work from patch-only work with a validation bundle.",
                    suggested_action="code-change",
                    scenario="The mechanism prompt needs clearer execution packet and validation-loop wording.",
                    action_taken="Record a prompt-scoped mechanism signal for Architect.",
                    observed_result="Architect can classify a narrow prompt proposal as safe for a follow-on agent.",
                    operational_use="Use prompt execution packets to apply only narrow prompt/runbook/validation/proposal-queue changes.",
                    reuse_judgment="Reusable for Architect proposal execution closure.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"prompt-test-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            result = run_architect_maintenance(repo_root, run_id="architect-ready-apply-test")

            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["agent_ready_count"], 1)
            self.assertGreaterEqual(result["sandbox_ready_count"], 1)
            self.assertIn("selected_sandbox_trial", result)
            self.assertTrue(result["selected_sandbox_trial"]["proposal_id"])
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(queue["sandbox_ready_packets"]), 1)
            self.assertEqual(queue["selected_sandbox_trial"]["proposal_id"], result["selected_sandbox_trial"]["proposal_id"])
            prompt_proposal = next(
                item
                for item in queue["proposals"]
                if item["category"] == "prompt"
            )
            self.assertEqual(prompt_proposal["status"], "ready-for-apply")
            self.assertEqual(prompt_proposal["execution_state"]["state"], "ready-for-agent")
            packet = prompt_proposal["execution_packet"]
            self.assertEqual(packet["execution_mode"], "agent-ready-apply")
            self.assertFalse(packet["runner_direct_write_allowed"])
            self.assertTrue(packet["architect_agent_direct_apply_allowed"])
            self.assertFalse(packet["requires_patch_or_human"])
            self.assertIn(".agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md", packet["allowed_paths"])
            self.assertIn("python -m unittest tests.test_kb_architect", packet["validation_plan"]["commands"])
            self.assertEqual(packet["closure_contract"]["applied_update"]["proposal.status"], "applied")
            self.assertEqual(packet["closure_contract"]["blocked_update"]["proposal.execution_state.state"], "blocked")
            sandbox_apply = packet["sandbox_apply"]
            self.assertTrue(sandbox_apply["sandbox_ready"])
            self.assertEqual(sandbox_apply["strategy"], "sandbox-trial")
            self.assertEqual(sandbox_apply["sandbox_path"], "")
            self.assertTrue(sandbox_apply["planned_sandbox_path"].endswith(packet["packet_id"]))
            self.assertIn(".agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md", sandbox_apply["allowed_writes"])
            self.assertIn("kb/public/**", sandbox_apply["disallowed_writes"])
            self.assertIn("Trial a narrow mechanism update", sandbox_apply["expected_effect"])
            self.assertIn("python -m unittest tests.test_kb_architect", sandbox_apply["validation_commands"])
            self.assertIn("Confirm the diff stays inside the execution packet allowed_paths.", sandbox_apply["manual_checks"])
            self.assertEqual(sandbox_apply["merge_decision"]["record_fields"]["proposal.status"], "applied")
            self.assertEqual(sandbox_apply["block_decision"]["record_fields"]["proposal.execution_state.state"], "blocked")
            report_packet = next(
                item
                for item in result["sandbox_ready_packets"]
                if item["proposal_id"] == prompt_proposal["proposal_id"]
            )
            self.assertEqual(report_packet["planned_sandbox_path"], sandbox_apply["planned_sandbox_path"])
            self.assertEqual(report_packet["merge_decision_fields"]["proposal.status"], "applied")
            self.assertEqual(report_packet["block_decision_fields"]["proposal.execution_state.state"], "blocked")
            first_ready_since = prompt_proposal["execution_state"]["ready_since_at"]
            self.assertTrue(first_ready_since)

            second = run_architect_maintenance(repo_root, run_id="architect-ready-apply-test-second")
            second_queue = json.loads(queue_path.read_text(encoding="utf-8"))
            second_prompt_proposal = next(
                item
                for item in second_queue["proposals"]
                if item["proposal_id"] == prompt_proposal["proposal_id"]
            )
            self.assertEqual(second_prompt_proposal["execution_state"]["state"], "ready-for-agent")
            self.assertEqual(second_prompt_proposal["execution_state"]["ready_since_at"], first_ready_since)
            second_packet = next(
                item
                for item in second["sandbox_ready_packets"]
                if item["proposal_id"] == prompt_proposal["proposal_id"]
            )
            self.assertEqual(second_packet["ready_since_at"], first_ready_since)

    def test_sandbox_trial_result_marks_ready_packet_applied_and_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Architect prompt can close a sandbox trial {index}",
                    route_hint="system/knowledge-library/maintenance",
                    hit_quality="hit",
                    outcome="Repeated prompt mechanism signal found.",
                    comment="Architect prompt closure should record applied sandbox trials.",
                    suggested_action="code-change",
                    scenario="A narrow prompt proposal is ready for one sandbox trial.",
                    action_taken="Record a prompt-scoped mechanism signal for Architect.",
                    observed_result="Architect can select and close one prompt packet.",
                    operational_use="Record applied Architect trial results with validation evidence.",
                    reuse_judgment="Reusable for Architect execution closure.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"trial-applied-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            first = run_architect_maintenance(repo_root, run_id="architect-trial-applied")
            selected = first["selected_sandbox_trial"]
            record = record_architect_sandbox_trial_result(
                repo_root,
                {
                    "run_id": "architect-trial-applied",
                    "proposal_id": selected["proposal_id"],
                    "packet_id": selected["packet_id"],
                    "decision": "applied",
                    "sandbox_path": selected["planned_sandbox_path"],
                    "touched_paths": [".agents/skills/local-kb-retrieve/ARCHITECT_PROMPT.md"],
                    "diff_within_allowed": True,
                    "validation_results": [
                        {"command": "python -m unittest tests.test_kb_architect", "status": "passed"}
                    ],
                    "manual_check_results": [
                        {"check": selected["manual_checks"][0], "status": "passed"},
                        {"check": selected["manual_checks"][1], "status": "passed"},
                    ],
                    "reason": "Prompt trial stayed inside the packet allowlist and validation passed.",
                },
                generated_at="2026-04-26T12:00:00+00:00",
            )

            self.assertEqual(record["decision"], "applied")
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            proposal = next(item for item in queue["proposals"] if item["proposal_id"] == selected["proposal_id"])
            self.assertEqual(proposal["status"], "applied")
            self.assertEqual(proposal["execution_state"]["state"], "applied")
            self.assertEqual(proposal["execution_packet"]["execution_mode"], "closed-applied")
            self.assertEqual(queue["execution_summary"]["applied_count"], 1)
            self.assertEqual(queue["selected_sandbox_trial"], {})
            self.assertTrue(record["run_report_update"]["updated"])
            self.assertTrue(record["run_report_update"]["report_updated"])
            final_state_path = repo_root / record["run_report_update"]["final_state_path"]
            final_state = json.loads(final_state_path.read_text(encoding="utf-8"))
            self.assertEqual(final_state["decision"], "applied")
            self.assertEqual(final_state["final_status"], "applied")
            self.assertEqual(final_state["final_execution_summary"]["applied_count"], 1)
            report_path = repo_root / "kb" / "history" / "architecture" / "runs" / "architect-trial-applied" / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["selected_sandbox_trial"]["proposal_id"], selected["proposal_id"])
            self.assertEqual(report["trial_result_summary"]["decision"], "applied")
            self.assertEqual(report["trial_result_summary"]["final_status"], "applied")
            self.assertEqual(report["final_execution_summary"]["applied_count"], 1)
            self.assertEqual(
                report["artifact_paths"]["trial_final_state_path"],
                record["run_report_update"]["final_state_path"],
            )

            second = run_architect_maintenance(repo_root, run_id="architect-trial-applied-second")
            second_queue = json.loads(queue_path.read_text(encoding="utf-8"))
            second_proposal = next(item for item in second_queue["proposals"] if item["proposal_id"] == selected["proposal_id"])
            self.assertEqual(second_proposal["status"], "applied")
            self.assertEqual(second_proposal["execution_packet"]["execution_mode"], "closed-applied")
            self.assertEqual(second["applied_execution_count"], 1)

    def test_sandbox_trial_result_blocks_failed_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Architect runbook packet may block after trial {index}",
                    route_hint="system/knowledge-library/maintenance",
                    hit_quality="hit",
                    outcome="Repeated runbook mechanism signal found.",
                    comment="Architect runbook closure should record blocked sandbox trials.",
                    suggested_action="code-change",
                    scenario="A narrow runbook proposal is ready but fails validation.",
                    action_taken="Record a runbook-scoped mechanism signal for Architect.",
                    observed_result="Architect should block the packet with a concrete reason.",
                    operational_use="Record blocked Architect trial results instead of repeating the same ready packet.",
                    reuse_judgment="Reusable for Architect execution closure.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"trial-blocked-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            first = run_architect_maintenance(repo_root, run_id="architect-trial-blocked")
            selected = first["selected_sandbox_trial"]
            record = record_architect_sandbox_trial_result(
                repo_root,
                {
                    "run_id": "architect-trial-blocked",
                    "proposal_id": selected["proposal_id"],
                    "packet_id": selected["packet_id"],
                    "decision": "blocked",
                    "sandbox_path": selected["planned_sandbox_path"],
                    "touched_paths": ["kb/public/not-allowed.yaml"],
                    "diff_within_allowed": False,
                    "validation_results": [
                        {"command": "python -m unittest tests.test_kb_architect", "status": "failed"}
                    ],
                    "manual_check_results": [
                        {"check": "Confirm the diff stays inside the execution packet allowed_paths.", "status": "failed"}
                    ],
                    "reason": "Trial touched a disallowed path and validation failed.",
                },
                generated_at="2026-04-26T12:05:00+00:00",
            )

            self.assertEqual(record["decision"], "blocked")
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            proposal = next(item for item in queue["proposals"] if item["proposal_id"] == selected["proposal_id"])
            self.assertEqual(proposal["status"], "watching")
            self.assertEqual(proposal["execution_state"]["state"], "blocked")
            self.assertIn("disallowed path", proposal["execution_state"]["blocker"])
            self.assertEqual(proposal["execution_packet"]["execution_mode"], "blocked")
            self.assertEqual(queue["execution_summary"]["blocked_count"], 1)
            self.assertEqual(queue["selected_sandbox_trial"], {})
            self.assertTrue(record["run_report_update"]["updated"])
            report_path = repo_root / "kb" / "history" / "architecture" / "runs" / "architect-trial-blocked" / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["trial_result_summary"]["decision"], "blocked")
            self.assertEqual(report["trial_result_summary"]["final_execution_state"]["state"], "blocked")
            self.assertEqual(report["final_execution_summary"]["blocked_count"], 1)

    def test_sandbox_trial_result_rejects_non_ready_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            for index in range(3):
                event = build_observation(
                    task_summary=f"Architect Skill mechanism needs patch pass {index}",
                    route_hint="codex/workflow/skills",
                    hit_quality="hit",
                    outcome="Repeated Skill mechanism signal found.",
                    comment="Skill mechanism changes should stay patch-only.",
                    suggested_action="code-change",
                    scenario="Skill maintenance proposal needs a patch plan.",
                    action_taken="Record a Skill-scoped mechanism signal for Architect.",
                    observed_result="Architect should classify the item as ready-for-patch.",
                    operational_use="Do not sandbox-apply patch-only Skill maintenance items.",
                    reuse_judgment="Reusable for Architect safety boundaries.",
                    source_kind="test",
                    agent_name="test",
                    thread_ref=f"trial-reject-{index}",
                    project_ref="test-kb",
                    workspace_root=str(repo_root),
                )
                record_observation(repo_root, event)

            run_architect_maintenance(repo_root, run_id="architect-trial-reject")
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            proposal = next(item for item in queue["proposals"] if item["category"] == "skill-maintenance")
            packet = proposal["execution_packet"]
            with self.assertRaises(ValueError):
                record_architect_sandbox_trial_result(
                    repo_root,
                    {
                        "proposal_id": proposal["proposal_id"],
                        "packet_id": packet["packet_id"],
                        "decision": "applied",
                        "sandbox_path": ".local/architect/sandbox/not-ready",
                        "touched_paths": [".agents/skills/kb-dream-pass/SKILL.md"],
                        "diff_within_allowed": True,
                        "validation_results": [{"command": "python -m unittest tests.test_kb_architect", "status": "passed"}],
                        "manual_check_results": [{"check": "manual", "status": "passed"}],
                    },
                )

    def test_execution_state_closes_or_blocks_carried_queue_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "local-kb-architect-proposal-queue",
                        "proposal_count": 2,
                        "proposals": [
                            {
                                "proposal_id": "arch-prop-applied",
                                "title": "Applied prompt execution packet",
                                "category": "prompt",
                                "status": "ready-for-apply",
                                "target": {"kind": "route", "ref": "system/knowledge-library/maintenance"},
                                "evidence": {"level": "high", "signal_count": 3, "source_action_count": 1, "supporting_run_count": 1},
                                "impact": {"level": "medium", "rationale": "test"},
                                "safety": {"level": "high", "rationale": "test"},
                                "source_actions": [],
                                "supporting_run_ids": ["old-a"],
                                "execution_state": {
                                    "state": "applied",
                                    "reason": "Prompt edit validated with tests/test_kb_architect.py.",
                                },
                            },
                            {
                                "proposal_id": "arch-prop-blocked",
                                "title": "Blocked runbook execution packet",
                                "category": "runbook",
                                "status": "ready-for-apply",
                                "target": {"kind": "path", "ref": "docs/architecture_runbook.md"},
                                "evidence": {"level": "high", "signal_count": 3, "source_action_count": 1, "supporting_run_count": 1},
                                "impact": {"level": "medium", "rationale": "test"},
                                "safety": {"level": "high", "rationale": "test"},
                                "source_actions": [],
                                "supporting_run_ids": ["old-b"],
                                "execution_state": {
                                    "state": "blocked",
                                    "reason": "The needed change exceeded the prompt/runbook allowlist.",
                                },
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = run_architect_maintenance(repo_root, run_id="architect-closure-test")

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["applied_execution_count"], 1)
            self.assertEqual(result["blocked_execution_count"], 1)
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            applied = next(item for item in queue["proposals"] if item["proposal_id"] == "arch-prop-applied")
            blocked = next(item for item in queue["proposals"] if item["proposal_id"] == "arch-prop-blocked")
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(applied["execution_packet"]["execution_mode"], "closed-applied")
            self.assertEqual(blocked["status"], "watching")
            self.assertEqual(blocked["execution_state"]["state"], "blocked")
            self.assertEqual(blocked["execution_packet"]["execution_mode"], "blocked")

    def test_architect_queue_hygiene_supersedes_duplicate_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            queue_path = repo_root / "kb" / "history" / "architecture" / "proposal_queue.json"
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            queue_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "local-kb-architect-proposal-queue",
                        "proposal_count": 2,
                        "proposals": [
                            {
                                "proposal_id": "arch-prop-primary",
                                "title": "Primary retrieval prompt proposal",
                                "category": "prompt",
                                "status": "watching",
                                "target": {"kind": "route", "ref": "system/knowledge-library/retrieval"},
                                "evidence": {"level": "medium", "signal_count": 2, "source_action_count": 1, "supporting_run_count": 3},
                                "impact": {"level": "medium", "rationale": "test"},
                                "safety": {"level": "high", "rationale": "test"},
                                "source_actions": [{"action_key": "review-code-change::route::system/knowledge-library/retrieval"}],
                                "supporting_run_ids": ["old-a", "old-b", "old-c"],
                            },
                            {
                                "proposal_id": "arch-prop-duplicate",
                                "title": "Duplicate retrieval prompt proposal",
                                "category": "prompt",
                                "status": "ready-for-apply",
                                "target": {"kind": "route", "ref": "system/knowledge-library/retrieval"},
                                "evidence": {"level": "medium", "signal_count": 1, "source_action_count": 1, "supporting_run_count": 1},
                                "impact": {"level": "medium", "rationale": "test"},
                                "safety": {"level": "high", "rationale": "test"},
                                "source_actions": [{"action_key": "review-observation-evidence::route::system/knowledge-library/retrieval"}],
                                "supporting_run_ids": ["old-d"],
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = run_architect_maintenance(repo_root, run_id="architect-duplicate-test")

            self.assertEqual(result["status"], "completed")
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            duplicate = next(item for item in queue["proposals"] if item["proposal_id"] == "arch-prop-duplicate")
            primary = next(item for item in queue["proposals"] if item["proposal_id"] == "arch-prop-primary")
            self.assertEqual(duplicate["status"], "superseded")
            self.assertEqual(duplicate["superseded_by"], "arch-prop-primary")
            self.assertEqual(primary["evidence"]["source_action_count"], 2)

    def test_architect_prompt_declares_scope_and_status_rules(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        prompt_text = (
            repo_root / ".agents" / "skills" / "local-kb-retrieve" / "ARCHITECT_PROMPT.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Evidence", prompt_text)
        self.assertIn("Impact", prompt_text)
        self.assertIn("Safety", prompt_text)
        self.assertIn("Do not use a human-review status", prompt_text)
        self.assertIn("Do not rewrite trusted cards", prompt_text)
        self.assertIn("Do not promote candidates", prompt_text)
        self.assertIn("validation bundle", prompt_text)
        self.assertIn("execution packet", prompt_text)
        self.assertIn("runner_direct_write_allowed", prompt_text)
        self.assertIn("execution_state.state", prompt_text)
        self.assertIn("blocked", prompt_text)
        self.assertIn("selected_sandbox_trial", prompt_text)
        self.assertIn("trial_result.json", prompt_text)
        self.assertIn("--record-trial-result", prompt_text)
        self.assertIn("postflight observation", prompt_text)
        self.assertIn("scripts/khaos_brain_update.py --architect-check --json", prompt_text)
        self.assertIn("$khaos-brain-update", prompt_text)
        self.assertIn("software update gate result", prompt_text)


if __name__ == "__main__":
    unittest.main()
