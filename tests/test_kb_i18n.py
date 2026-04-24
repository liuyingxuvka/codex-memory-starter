from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.consolidate import consolidate_history
from local_kb.desktop_app import _cover_title, _language_display, _language_from_display
from local_kb.i18n import localized_entry, localized_route_label, localized_route_segment, missing_i18n_fields
from local_kb.i18n_maintenance import build_i18n_actions, collect_route_segment_label_gaps
from local_kb.store import write_yaml_file
from local_kb.ui_data import build_route_view_payload


def _sample_entry() -> dict[str, object]:
    return {
        "id": "model-i18n",
        "title": "Scan local KB before repository tasks",
        "type": "model",
        "scope": "public",
        "domain_path": ["system", "knowledge-library", "retrieval"],
        "cross_index": [],
        "tags": ["kb"],
        "trigger_keywords": ["kb"],
        "if": {"notes": "When a repository task starts."},
        "action": {"description": "Run a lightweight local KB scan first."},
        "predict": {
            "expected_result": "Prior constraints are more likely to surface before edits.",
            "alternatives": [
                {
                    "when": "If the scan is skipped",
                    "result": "Prior constraints may be rediscovered late.",
                }
            ],
        },
        "use": {"guidance": "Use the result as bounded context."},
        "confidence": 0.8,
        "source": [{"origin": "test", "date": "2026-04-24"}],
        "status": "trusted",
        "updated_at": "2026-04-24",
    }


class KbI18nTests(unittest.TestCase):
    def test_localized_entry_falls_back_to_english_for_missing_fields(self) -> None:
        entry = _sample_entry()
        entry["i18n"] = {
            "zh-CN": {
                "title": "仓库任务前先扫描本地 KB",
                "predict": {"expected_result": "既有约束更可能在编辑前浮现。"},
            }
        }

        localized = localized_entry(entry, "zh-CN")

        self.assertEqual(localized["title"], "仓库任务前先扫描本地 KB")
        self.assertEqual(localized["predict"]["expected_result"], "既有约束更可能在编辑前浮现。")
        self.assertEqual(localized["action"]["description"], "Run a lightweight local KB scan first.")
        self.assertIn("action.description", missing_i18n_fields(entry, "zh-CN"))

    def test_i18n_apply_mode_uses_ai_plan_and_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry_path = repo_root / "kb" / "public" / "system" / "knowledge-library" / "retrieval" / "model-i18n.yaml"
            write_yaml_file(entry_path, _sample_entry())
            plan_path = repo_root / "kb" / "history" / "consolidation" / "i18n-test" / "i18n_zh-CN_plan.yaml"
            write_yaml_file(
                plan_path,
                {
                    "language": "zh-CN",
                    "translations": {
                        "model-i18n": {
                            "title": "仓库任务前先扫描本地 KB",
                            "if": {"notes": "当一个仓库任务开始时。"},
                            "action": {"description": "先运行一次轻量的本地 KB 扫描。"},
                            "predict": {
                                "expected_result": "既有约束更可能在编辑前浮现。",
                                "alternatives": [
                                    {
                                        "when": "如果跳过扫描",
                                        "result": "既有约束可能到后期才被重新发现。",
                                    }
                                ],
                            },
                            "use": {"guidance": "把结果作为有边界的上下文使用。"},
                        }
                    },
                },
            )

            result = consolidate_history(
                repo_root=repo_root,
                run_id="i18n-test",
                apply_mode="i18n-zh-CN",
                i18n_plan_path=plan_path,
            )

            self.assertEqual(result["apply_summary"]["updated_entry_count"], 1)
            updated_entry = yaml.safe_load(entry_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_entry["i18n"]["zh-CN"]["title"], "仓库任务前先扫描本地 KB")
            self.assertEqual(missing_i18n_fields(updated_entry, "zh-CN"), [])

            events_path = repo_root / "kb" / "history" / "events.jsonl"
            history_events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(history_events[-1]["event_type"], "i18n-updated")
            self.assertEqual(history_events[-1]["context"]["language"], "zh-CN")

    def test_route_payload_uses_chinese_display_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry = _sample_entry()
            entry["i18n"] = {"zh-CN": {"title": "仓库任务前先扫描本地 KB"}}
            entry_path = repo_root / "kb" / "public" / "system" / "knowledge-library" / "retrieval" / "model-i18n.yaml"
            write_yaml_file(entry_path, entry)

            payload = build_route_view_payload(
                repo_root,
                route="system/knowledge-library/retrieval",
                language="zh-CN",
            )

            self.assertEqual(payload["deck"][0]["title"], "仓库任务前先扫描本地 KB")
            self.assertEqual(payload["route_label"], "系统 / 知识库 / 检索")
            self.assertEqual(payload["deck"][0]["domain_path"], ["system", "knowledge-library", "retrieval"])
            self.assertEqual(payload["deck"][0]["domain_label"], "系统 / 知识库 / 检索")
            self.assertEqual(
                payload["deck"][0]["predicted_result"],
                "Prior constraints are more likely to surface before edits.",
            )

    def test_route_segment_translation_is_display_only(self) -> None:
        route = ["system", "knowledge-library", "retrieval"]

        self.assertEqual(localized_route_label(route, "zh-CN"), "系统 / 知识库 / 检索")
        self.assertEqual(localized_route_label(route, "en"), "system / knowledge-library / retrieval")
        self.assertEqual(localized_route_segment("unknown-segment", "zh-CN"), "unknown-segment")

    def test_sleep_i18n_reports_missing_route_segment_labels_without_renaming_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry = _sample_entry()
            entry["id"] = "model-route-i18n"
            entry["domain_path"] = ["system", "new-branch", "custom-leaf"]
            entry["cross_index"] = ["codex/workflow/unmapped-cross"]
            entry_path = repo_root / "kb" / "public" / "system" / "new-branch" / "custom-leaf" / "model-route-i18n.yaml"
            write_yaml_file(entry_path, entry)

            gaps = collect_route_segment_label_gaps(repo_root, "zh-CN")
            gap_segments = {item["segment"] for item in gaps}

            self.assertEqual(
                localized_route_label(["system", "new-branch", "custom-leaf"], "zh-CN"),
                "系统 / new-branch / custom-leaf",
            )
            self.assertIn("new-branch", gap_segments)
            self.assertIn("custom-leaf", gap_segments)
            self.assertIn("unmapped-cross", gap_segments)
            self.assertEqual(entry["domain_path"], ["system", "new-branch", "custom-leaf"])

    def test_i18n_actions_include_route_segment_display_label_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            entry = _sample_entry()
            entry["id"] = "model-route-i18n-action"
            entry["domain_path"] = ["system", "new-branch", "custom-leaf"]
            entry_path = repo_root / "kb" / "public" / "system" / "new-branch" / "custom-leaf" / "model-route-i18n-action.yaml"
            write_yaml_file(entry_path, entry)

            actions = build_i18n_actions(repo_root, "zh-CN")
            route_actions = [action for action in actions if action["action_type"] == "review-route-i18n"]

            self.assertEqual(len(route_actions), 1)
            action = route_actions[0]
            self.assertEqual(action["target"]["kind"], "route-segment-labels")
            self.assertIn("system/new-branch/custom-leaf", action["routes"])
            self.assertEqual(action["i18n_suggestion"]["apply_supported_mode"], "manual-code-change")
            self.assertIn(
                "Do not rename domain_path",
                action["i18n_suggestion"]["canonical_route_policy"],
            )

    def test_chinese_card_cover_uses_localized_title_not_english_alias(self) -> None:
        card = {"id": "runtime-card", "title": "Codex 运行时工具环境中的对照式路线经验"}

        self.assertEqual(_cover_title(card, "zh-CN"), "Codex 运行时工具环境中的对照式路线经验")
        self.assertEqual(_cover_title({"title": "Codex runtime behavior model"}, "en"), "Runtime Behavior")

    def test_language_selector_labels_are_bilingual_and_roundtrip(self) -> None:
        self.assertEqual(_language_display("en"), "English / 英文")
        self.assertEqual(_language_display("zh-CN"), "中文 / Chinese")
        self.assertEqual(_language_from_display("English / 英文"), "en")
        self.assertEqual(_language_from_display("中文 / Chinese"), "zh-CN")


if __name__ == "__main__":
    unittest.main()
