from __future__ import annotations

import unittest
from pathlib import Path

from local_kb.desktop_app import _card_type_value, _detail_paragraphs
from local_kb.store import resolve_repo_root
from local_kb.ui_data import (
    build_card_detail_payload,
    build_overview_payload,
    build_route_view_payload,
    build_search_payload,
    navigation_card_count,
    navigation_children,
)


class KbDesktopUiDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = resolve_repo_root(Path(__file__).resolve().parents[1])

    def test_overview_counts_entries_and_taxonomy_gaps(self) -> None:
        payload = build_overview_payload(self.repo_root)

        self.assertGreater(payload["entry_count"], 0)
        self.assertIn("status_counts", payload)
        self.assertIn("scope_counts", payload)
        self.assertIn("taxonomy_gap_count", payload)

    def test_route_view_groups_primary_and_cross_route_cards(self) -> None:
        payload = build_route_view_payload(self.repo_root, route="system/knowledge-library/retrieval")

        primary_ids = [item["id"] for item in payload["cards"]["primary"]]
        cross_ids = [item["id"] for item in payload["cards"]["cross"]]

        self.assertIn("model-004", primary_ids)
        self.assertIn("cand-2026-04-20-codex-runtime-kb-postflight", cross_ids)
        self.assertEqual(payload["cards"]["primary"][0]["route_reason"], "primary")
        self.assertEqual(payload["cards"]["cross"][0]["route_reason"], "cross")

    def test_card_detail_payload_contains_model_sections_and_raw_data(self) -> None:
        payload = build_card_detail_payload(self.repo_root, "model-004")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["id"], "model-004")
        self.assertIn("if", payload)
        self.assertIn("action", payload)
        self.assertIn("predict", payload)
        self.assertIn("use", payload)
        self.assertIn("raw", payload)

    def test_search_payload_returns_results_for_desktop_deck(self) -> None:
        payload = build_search_payload(
            self.repo_root,
            query="release cleanup and version gaps",
            route_hint="repository/github-publishing/release-hygiene",
        )

        self.assertEqual(payload["route_hint"], ["repository", "github-publishing", "release-hygiene"])
        self.assertGreater(len(payload["results"]), 0)
        self.assertIn("id", payload["results"][0])
        self.assertIn("route_reason", payload["results"][0])

    def test_search_payload_filters_confidence_only_matches(self) -> None:
        payload = build_search_payload(self.repo_root, query="zzznomatchtoken", route_hint="")

        self.assertEqual(payload["results"], [])

    def test_navigation_children_merges_declared_and_observed_routes(self) -> None:
        payload = build_route_view_payload(self.repo_root, route="")
        children = navigation_children(payload)
        labels = [item["segment"] for item in children]

        self.assertIn("system", labels)
        self.assertEqual(labels, sorted(labels))

    def test_card_type_shortcuts_filter_models_and_preferences(self) -> None:
        payload = build_route_view_payload(self.repo_root, route="")
        models = [item for item in payload["deck"] if _card_type_value(item) == "model"]
        preferences = [item for item in payload["deck"] if _card_type_value(item) == "preference"]

        self.assertGreater(len(models), 0)
        self.assertGreater(len(preferences), 0)
        self.assertTrue(all(_card_type_value(item) == "model" for item in models))
        self.assertTrue(all(_card_type_value(item) == "preference" for item in preferences))
        self.assertFalse({item["id"] for item in models} & {item["id"] for item in preferences})

    def test_detail_paragraphs_hide_internal_schema_keys(self) -> None:
        paragraphs = _detail_paragraphs(
            {
                "expected_result": "The stronger path is easier to review.",
                "alternatives": [
                    {
                        "when": "The weaker path is repeated.",
                        "result": "The old mistake is likely to recur.",
                    }
                ],
            }
        )

        rendered = "\n".join(paragraphs)
        self.assertIn("The stronger path is easier to review.", rendered)
        self.assertIn("The weaker path is repeated.", rendered)
        self.assertNotIn("expected_result", rendered)
        self.assertNotIn("alternatives", rendered)
        self.assertNotIn("when ", rendered)
        self.assertNotIn("result ", rendered)

    def test_navigation_count_does_not_double_count_primary_cards(self) -> None:
        route = "automation/debugging/spec-drift"
        payload = build_route_view_payload(self.repo_root, route=route)
        parent_payload = build_route_view_payload(self.repo_root, route="automation/debugging")
        child = next(
            item
            for item in navigation_children(parent_payload)
            if item["segment"] == "spec-drift"
        )

        self.assertEqual(len(payload["deck"]), 1)
        self.assertEqual(child["primary_subtree_count"], 1)
        self.assertEqual(child["observed_subtree_count"], 1)
        self.assertEqual(navigation_card_count(child), len(payload["deck"]))


if __name__ == "__main__":
    unittest.main()
