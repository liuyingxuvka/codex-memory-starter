from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from local_kb.store import resolve_repo_root
from local_kb.taxonomy import (
    build_taxonomy_gap_report,
    build_taxonomy_view,
    derive_route_counts,
    load_taxonomy,
)


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "local-kb-retrieve"
    / "scripts"
    / "kb_taxonomy.py"
)


class KbTaxonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = resolve_repo_root(Path(__file__).resolve().parents[1])

    def test_loads_minimal_explicit_taxonomy_covering_current_sample_routes(self) -> None:
        taxonomy = load_taxonomy(self.repo_root)
        root_segments = [node["segment"] for node in taxonomy["nodes"]]
        self.assertIn("work", root_segments)
        self.assertIn("engineering", root_segments)
        self.assertIn("system", root_segments)
        self.assertIn("communication", root_segments)
        self.assertIn("repository", root_segments)

    def test_root_view_combines_declared_children_with_observed_coverage_signal(self) -> None:
        view = build_taxonomy_view(self.repo_root)
        child_segments = [item["segment"] for item in view["children"]]
        self.assertIn("work", child_segments)
        self.assertIn("engineering", child_segments)
        self.assertGreaterEqual(view["coverage"]["primary_subtree_count"], 4)
        undeclared_segments = [item["segment"] for item in view["coverage"]["undeclared_children"]]
        self.assertIn("language", undeclared_segments)
        self.assertIn("planning", undeclared_segments)

    def test_nested_route_view_reports_direct_cards_and_undeclared_child_signal(self) -> None:
        work_view = build_taxonomy_view(self.repo_root, route="work")
        self.assertTrue(work_view["declared"])
        self.assertEqual(
            [item["segment"] for item in work_view["children"]],
            ["communication", "reporting"],
        )

        engineering_view = build_taxonomy_view(self.repo_root, route="engineering")
        undeclared_segments = [item["segment"] for item in engineering_view["coverage"]["undeclared_children"]]
        self.assertIn("integration", undeclared_segments)

        ppt_view = build_taxonomy_view(self.repo_root, route="work/reporting/ppt")
        self.assertTrue(ppt_view["declared"])
        self.assertEqual([card["id"] for card in ppt_view["direct_cards"]], [])
        self.assertEqual(ppt_view["coverage"]["primary_direct_count"], 0)

        retrieval_view = build_taxonomy_view(self.repo_root, route="system/knowledge-library/retrieval")
        retrieval_direct_ids = [card["id"] for card in retrieval_view["direct_cards"]]
        self.assertIn("model-004", retrieval_direct_ids)
        self.assertGreaterEqual(retrieval_view["coverage"]["primary_direct_count"], 1)

    def test_route_counts_include_declared_and_cross_index_routes(self) -> None:
        from local_kb.store import load_entries

        counts = derive_route_counts(load_entries(self.repo_root))
        self.assertIn("model-004", counts[("system", "knowledge-library", "retrieval")]["primary_direct_ids"])
        self.assertEqual(
            len(counts[("writing", "business", "email")]["observed_direct_ids"]),
            1,
        )

    def test_gap_report_surfaces_smallest_missing_taxonomy_routes(self) -> None:
        report = build_taxonomy_gap_report(self.repo_root)
        gap_labels = [item["route_label"] for item in report["gaps"]]
        self.assertIn("language", gap_labels)
        self.assertIn("engineering / integration", gap_labels)
        language_gap = next(item for item in report["gaps"] if item["route_label"] == "language")
        self.assertEqual(language_gap["recommended_action"], "review-taxonomy-add")
        self.assertIn("language / professional / english", language_gap["example_observed_routes"])

    def test_cli_json_smoke(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--route",
                "work",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["route"], ["work"])
        self.assertEqual(payload["declared_child_count"], 2)

    def test_gap_cli_json_smoke(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--repo-root",
                str(self.repo_root),
                "--gaps-only",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "local-kb-taxonomy-gap-report")
        self.assertTrue(payload["route_count"] >= 1)


if __name__ == "__main__":
    unittest.main()
