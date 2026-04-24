from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.architect import run_architect_maintenance
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
                sleep_cooldown_minutes=0,
                dream_cooldown_minutes=0,
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
        self.assertIn("postflight observation", prompt_text)


if __name__ == "__main__":
    unittest.main()
