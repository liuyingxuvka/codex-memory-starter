from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.store import resolve_repo_root
from local_kb.store import write_yaml_file
from local_kb.taxonomy import build_taxonomy_gap_report, build_taxonomy_view


class TemplateTaxonomyTests(unittest.TestCase):
    def test_template_repo_ships_one_safe_public_example_card(self) -> None:
        repo_root = resolve_repo_root(Path(__file__).resolve().parents[1])
        view = build_taxonomy_view(repo_root, route="system/knowledge-library/retrieval")

        self.assertTrue(view["declared"])
        self.assertEqual([card["id"] for card in view["direct_cards"]], ["model-004"])
        self.assertEqual(view["coverage"]["primary_direct_count"], 1)

    def test_empty_template_taxonomy_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            kb_root = repo_root / "kb"
            for segment in ("public", "private", "candidates", "history"):
                (kb_root / segment).mkdir(parents=True, exist_ok=True)
            write_yaml_file(
                kb_root / "taxonomy.yaml",
                {
                    "version": 1,
                    "kind": "official-taxonomy",
                    "updated_at": "template",
                    "nodes": [],
                },
            )

            view = build_taxonomy_view(repo_root)
            gaps = build_taxonomy_gap_report(repo_root)

            self.assertEqual(view["route"], [])
            self.assertEqual(view["declared_child_count"], 0)
            self.assertEqual(view["coverage"]["observed_subtree_count"], 0)
            self.assertEqual(gaps["route_count"], 0)

    def test_gap_report_surfaces_observed_route_not_declared_in_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            kb_root = repo_root / "kb"
            (kb_root / "public" / "writing" / "email").mkdir(parents=True, exist_ok=True)
            (kb_root / "private").mkdir(parents=True, exist_ok=True)
            (kb_root / "candidates").mkdir(parents=True, exist_ok=True)
            (kb_root / "history").mkdir(parents=True, exist_ok=True)
            write_yaml_file(
                kb_root / "taxonomy.yaml",
                {
                    "version": 1,
                    "kind": "official-taxonomy",
                    "updated_at": "template",
                    "nodes": [],
                },
            )
            write_yaml_file(
                kb_root / "public" / "writing" / "email" / "example-entry.yaml",
                {
                    "id": "example-001",
                    "title": "Example local rule",
                    "type": "heuristic",
                    "scope": "public",
                    "domain_path": ["writing", "email"],
                    "cross_index": [],
                    "tags": ["writing"],
                    "trigger_keywords": ["email"],
                    "if": {"notes": "Example only"},
                    "action": {"description": "Example action"},
                    "predict": {"expected_result": "Example result", "alternatives": []},
                    "use": {"guidance": "Example guidance"},
                    "confidence": 0.5,
                    "source": [{"origin": "template", "date": "2026-04-19"}],
                    "status": "candidate",
                    "updated_at": "2026-04-19",
                },
            )

            report = build_taxonomy_gap_report(repo_root)

            self.assertEqual(report["route_count"], 1)
            self.assertEqual(report["gaps"][0]["route_label"], "writing")


if __name__ == "__main__":
    unittest.main()
