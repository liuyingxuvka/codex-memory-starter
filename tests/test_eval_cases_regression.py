from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from local_kb.search import render_search_payload, search_entries
from tests.kb_fixtures import write_sample_kb_repo


class EvalCasesRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo_root = Path(cls._tmp.name)
        write_sample_kb_repo(cls.repo_root)
        cls.eval_cases_path = project_root / "tests" / "eval_cases.yaml"
        cls.eval_cases = yaml.safe_load(cls.eval_cases_path.read_text(encoding="utf-8")) or []

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_eval_cases_top_result_matches_expected_ids(self) -> None:
        self.assertGreater(len(self.eval_cases), 0, "eval_cases.yaml should define at least one retrieval case")

        for case in self.eval_cases:
            query = str(case.get("query", "") or "").strip()
            path_hint = str(case.get("path_hint", "") or "").strip()
            expected_ids = [str(item).strip() for item in case.get("expected_ids", []) if str(item).strip()]

            with self.subTest(query=query, path_hint=path_hint):
                self.assertTrue(query, "Each eval case must provide a query")
                self.assertGreater(len(expected_ids), 0, "Each eval case must define expected_ids")

                payload = render_search_payload(
                    search_entries(
                        self.repo_root,
                        query=query,
                        path_hint=path_hint,
                        top_k=max(5, len(expected_ids)),
                    ),
                    self.repo_root,
                )

                self.assertTrue(
                    payload,
                    f"No results returned for query={query!r} path_hint={path_hint!r}",
                )
                self.assertIn(
                    payload[0]["id"],
                    expected_ids,
                    f"Top result {payload[0]['id']!r} did not match expected_ids={expected_ids!r}",
                )


if __name__ == "__main__":
    unittest.main()
