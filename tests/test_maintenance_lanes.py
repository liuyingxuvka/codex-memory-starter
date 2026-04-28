from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_kb.maintenance_lanes import (
    acquire_lane_lock,
    build_lane_guard,
    lane_lock_group,
    read_lane_lock,
    read_lane_status,
    release_lane_lock,
)


class MaintenanceLaneLockTests(unittest.TestCase):
    def test_local_maintenance_lanes_share_one_waiting_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            first = acquire_lane_lock(repo_root, "kb-sleep", run_id="sleep-1", poll_seconds=0)
            second = acquire_lane_lock(repo_root, "kb-dream", run_id="dream-1", wait=False, poll_seconds=0)

            self.assertTrue(first["acquired"])
            self.assertFalse(second["acquired"])
            self.assertEqual(second["blocked_by"]["lane"], "kb-sleep")
            self.assertEqual(build_lane_guard(repo_root, "kb-dream")["blocking_lanes"], ["kb-sleep"])

            released = release_lane_lock(repo_root, "kb-sleep", run_id="sleep-1")
            self.assertTrue(released["released"])
            self.assertEqual(read_lane_lock(repo_root, "local-maintenance"), {})

    def test_organization_lanes_share_a_separate_waiting_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            org = acquire_lane_lock(repo_root, "kb-org-contribute", run_id="contrib-1", poll_seconds=0)
            local = acquire_lane_lock(repo_root, "kb-dream", run_id="dream-1", wait=False, poll_seconds=0)
            blocked_org = acquire_lane_lock(
                repo_root,
                "kb-org-maintenance",
                run_id="maint-1",
                wait=False,
                poll_seconds=0,
            )

            self.assertEqual(lane_lock_group("kb-org-maintenance"), "organization-maintenance")
            self.assertTrue(org["acquired"])
            self.assertTrue(local["acquired"])
            self.assertFalse(blocked_org["acquired"])
            self.assertEqual(blocked_org["blocked_by"]["lane"], "kb-org-contribute")

    def test_stale_lane_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            acquire_lane_lock(repo_root, "kb-sleep", run_id="sleep-1", poll_seconds=0)
            recovered = acquire_lane_lock(
                repo_root,
                "kb-dream",
                run_id="dream-1",
                poll_seconds=0,
                stale_after_seconds=0,
            )

            self.assertTrue(recovered["acquired"])
            self.assertEqual(recovered["lane"], "kb-dream")

    def test_dream_releases_lock_and_marks_failed_on_exception(self) -> None:
        from local_kb.dream import run_dream_maintenance

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            with patch("local_kb.dream.build_dream_guard", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    run_dream_maintenance(repo_root, run_id="dream-fail")

            self.assertEqual(read_lane_lock(repo_root, "local-maintenance"), {})
            self.assertEqual(read_lane_status(repo_root, "kb-dream")["status"], "failed")

    def test_architect_releases_lock_and_marks_failed_on_exception(self) -> None:
        from local_kb.architect import run_architect_maintenance

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            with patch("local_kb.architect.build_initial_execution_plan", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    run_architect_maintenance(repo_root, run_id="architect-fail")

            self.assertEqual(read_lane_lock(repo_root, "local-maintenance"), {})
            self.assertEqual(read_lane_status(repo_root, "kb-architect")["status"], "failed")

    def test_organization_contribute_releases_lock_and_marks_failed_on_exception(self) -> None:
        from local_kb.org_automation import run_organization_contribution

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source = {"path": str(repo_root / "org"), "organization_id": "sandbox", "repo_url": ""}
            settings = {"mode": "organization", "organization": {"validated": True}}

            with (
                patch("local_kb.org_automation._first_organization_source", return_value=(source, [source], settings)),
                patch("local_kb.org_automation._sync_first_organization_source", side_effect=RuntimeError("boom")),
            ):
                with self.assertRaises(RuntimeError):
                    run_organization_contribution(repo_root)

            self.assertEqual(read_lane_lock(repo_root, "organization-maintenance"), {})
            self.assertEqual(read_lane_status(repo_root, "kb-org-contribute")["status"], "failed")

    def test_organization_maintenance_releases_lock_and_marks_failed_on_exception(self) -> None:
        from local_kb.org_automation import run_organization_maintenance

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source = {"path": str(repo_root / "org"), "organization_id": "sandbox", "repo_url": ""}

            with (
                patch("local_kb.org_automation.load_desktop_settings", return_value={"mode": "organization"}),
                patch(
                    "local_kb.org_automation.maintenance_participation_status_from_settings",
                    return_value={"available": True, "requested": True},
                ),
                patch("local_kb.org_automation.organization_sources_from_settings", return_value=[source]),
                patch("local_kb.org_automation._sync_first_organization_source", side_effect=RuntimeError("boom")),
            ):
                with self.assertRaises(RuntimeError):
                    run_organization_maintenance(repo_root)

            self.assertEqual(read_lane_lock(repo_root, "organization-maintenance"), {})
            self.assertEqual(read_lane_status(repo_root, "kb-org-maintenance")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
