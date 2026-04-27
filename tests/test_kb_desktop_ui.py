from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from local_kb.desktop_app import (
    _card_type_value,
    _detail_paragraphs,
    _maintenance_display,
    _maintenance_from_display,
    _mode_display,
    _mode_from_display,
    _skill_badge_label,
    _source_line,
    _source_filter_label,
    _status_filter_label,
    _type_filter_label,
    _wheel_scroll_units,
)
from local_kb.settings import ORGANIZATION_MODE, PERSONAL_MODE
from local_kb.i18n import ZH_CN
from local_kb.store import write_yaml_file
from local_kb.ui_data import (
    build_card_detail_payload,
    build_overview_payload,
    build_route_view_payload,
    build_search_payload,
    navigation_card_count,
    navigation_children,
)
from tests.kb_fixtures import write_sample_kb_repo


class KbDesktopUiDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        write_sample_kb_repo(self.repo_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

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
        self.assertEqual(payload["source_info"]["label"], "local/public")
        self.assertEqual(payload["source_label"], "local/public")
        self.assertEqual(payload["author_label"], "local")
        self.assertFalse(payload["read_only"])
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
        self.assertIn("source_info", payload["results"][0])

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

    def test_card_summaries_expose_skill_dependency_badge_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_yaml_file(
                root / "kb" / "public" / "skill-backed.yaml",
                {
                    "id": "skill-backed",
                    "title": "Skill backed card",
                    "type": "model",
                    "scope": "public",
                    "status": "trusted",
                    "confidence": 0.9,
                    "domain_path": ["shared"],
                    "tags": ["skill"],
                    "trigger_keywords": ["skill"],
                    "required_skills": ["release-helper"],
                    "recommended_skills": ["review-helper"],
                    "if": {"notes": "A card uses Skills."},
                    "action": {"description": "Show a small Skill badge on the cover."},
                    "predict": {"expected_result": "The card is visibly Skill-backed."},
                    "use": {"guidance": "Open detail for the exact dependency list."},
                },
            )

            payload = build_route_view_payload(root, route="")
            card = payload["deck"][0]

        self.assertEqual(card["skill_dependency_count"], 2)
        self.assertEqual(_skill_badge_label(card), "2 Skills")
        self.assertEqual(_skill_badge_label(card, ZH_CN), "2 个技能")
        self.assertEqual(_skill_badge_label({"skill_dependency_count": 1}), "1 Skill")
        self.assertEqual(_skill_badge_label({"skill_dependency_count": 1}, ZH_CN), "1 个技能")

    def test_sidebar_filter_labels_cover_all_statuses_and_types(self) -> None:
        self.assertEqual(_status_filter_label("trusted"), "Trusted")
        self.assertEqual(_status_filter_label("candidate"), "Candidates")
        self.assertEqual(_status_filter_label("deprecated", ZH_CN), "已废弃")
        self.assertEqual(_type_filter_label("model"), "Models")
        self.assertEqual(_type_filter_label("preference"), "Preferences")
        self.assertEqual(_type_filter_label("heuristic", ZH_CN), "启发式")
        self.assertEqual(_type_filter_label("fact", ZH_CN), "事实")
        self.assertEqual(_source_filter_label("local"), "Local")
        self.assertEqual(_source_filter_label("organization", ZH_CN), "组织")

    def test_source_line_uses_localized_compact_display_labels(self) -> None:
        local_card = {
            "scope": "public",
            "source_label": "local/public",
            "author_label": "local",
            "source_info": {"kind": "local", "scope": "public"},
        }
        candidate_card = {
            "scope": "private",
            "source_label": "local/candidate",
            "author_label": "local",
            "source_info": {"kind": "local", "scope": "candidate"},
        }
        organization_card = {
            "scope": "public",
            "source_label": "org/sandbox/trusted",
            "author_label": "sandbox",
            "read_only": True,
            "source_info": {"kind": "organization", "scope": "trusted", "organization_id": "sandbox"},
        }

        self.assertEqual(_source_line(local_card), "Local · Public · Author: This device")
        self.assertEqual(_source_line(local_card, ZH_CN), "本地 · 公开 · 作者：本机")
        self.assertEqual(_source_line(candidate_card, ZH_CN), "本地 · 候选 · 作者：本机")
        self.assertEqual(_source_line(organization_card, ZH_CN), "组织 sandbox · 已信任 · 作者：未注明 · 只读")

    def test_settings_combobox_display_values_roundtrip(self) -> None:
        self.assertEqual(_mode_display(PERSONAL_MODE, ZH_CN), "个人")
        self.assertEqual(_mode_display(ORGANIZATION_MODE), "Organization")
        self.assertEqual(_mode_from_display("组织", ZH_CN), ORGANIZATION_MODE)
        self.assertEqual(_mode_from_display("Personal", ZH_CN), PERSONAL_MODE)
        self.assertEqual(_maintenance_display(True, ZH_CN), "参与组织维护")
        self.assertEqual(_maintenance_display(False), "Do not participate")
        self.assertTrue(_maintenance_from_display("Participate"))
        self.assertFalse(_maintenance_from_display("不参与组织维护", ZH_CN))

    def test_mousewheel_units_allow_faster_main_card_scrolling(self) -> None:
        self.assertEqual(_wheel_scroll_units(120), -1)
        self.assertEqual(_wheel_scroll_units(-120), 1)
        self.assertEqual(_wheel_scroll_units(120, multiplier=3), -3)
        self.assertEqual(_wheel_scroll_units(-240, multiplier=3), 6)
        self.assertEqual(_wheel_scroll_units(40, multiplier=3), -1)
        self.assertEqual(_wheel_scroll_units(0, multiplier=3), 0)

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

        self.assertGreaterEqual(len(payload["deck"]), 1)
        self.assertEqual(child["primary_subtree_count"], len(payload["deck"]))
        self.assertEqual(child["observed_subtree_count"], len(payload["deck"]))
        self.assertEqual(navigation_card_count(child), len(payload["deck"]))


if __name__ == "__main__":
    unittest.main()
