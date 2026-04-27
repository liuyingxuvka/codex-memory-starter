from __future__ import annotations

from pathlib import Path
from typing import Any

from local_kb.store import write_yaml_file


def _entry(
    entry_id: str,
    title: str,
    route: list[str],
    *,
    entry_type: str = "model",
    cross_index: list[str] | None = None,
    tags: list[str] | None = None,
    trigger_keywords: list[str] | None = None,
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "id": entry_id,
        "title": title,
        "type": entry_type,
        "scope": "public",
        "domain_path": route,
        "cross_index": cross_index or [],
        "tags": tags or [],
        "trigger_keywords": trigger_keywords or [],
        "if": {"notes": f"Fixture condition for {entry_id}."},
        "action": {"description": f"Use the fixture action for {entry_id}."},
        "predict": {"expected_result": f"The fixture result for {entry_id} is retrieved."},
        "use": {"guidance": f"Fixture guidance for {entry_id}."},
        "confidence": confidence,
        "status": "trusted",
        "updated_at": "2026-04-27",
    }


def write_sample_kb_repo(root: Path) -> None:
    write_yaml_file(
        root / "kb" / "taxonomy.yaml",
        {
            "version": 1,
            "kind": "official-taxonomy",
            "nodes": [
                {"segment": "codex", "children": [{"segment": "runtime-behavior", "children": [{"segment": "prompt-following"}]}]},
                {"segment": "communication", "children": [{"segment": "slides", "children": [{"segment": "executive-summary"}]}]},
                {"segment": "engineering", "children": [{"segment": "debugging", "children": [{"segment": "version-change"}]}]},
                {"segment": "repository", "children": [{"segment": "usage", "children": [{"segment": "local-kb-retrieve"}]}]},
                {"segment": "system", "children": [{"segment": "knowledge-library", "children": [{"segment": "retrieval"}]}]},
                {"segment": "troubleshooting", "children": [{"segment": "dependency", "children": [{"segment": "regression"}]}]},
                {"segment": "work", "children": [{"segment": "communication", "children": [{"segment": "email"}]}, {"segment": "reporting", "children": [{"segment": "ppt"}]}]},
                {"segment": "writing", "children": [{"segment": "business", "children": [{"segment": "email"}]}]},
            ],
        },
    )
    write_yaml_file(
        root / "kb" / "public" / "model-001.yaml",
        _entry(
            "model-001",
            "Dependency version changes can break integrations",
            ["engineering", "debugging", "version-change"],
            cross_index=["troubleshooting/dependency/regression", "engineering/integration/runtime-migration"],
            tags=["dependency", "upgrade", "sdk", "integration", "regression"],
            trigger_keywords=["dependency", "upgrade", "sdk", "version", "integration", "service", "broke", "behavior", "changed"],
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "model-002.yaml",
        _entry(
            "model-002",
            "Work emails should respect known language preferences",
            ["work", "communication", "email"],
            entry_type="preference",
            cross_index=["writing/business/email"],
            tags=["email", "work", "language", "preference", "client"],
            trigger_keywords=["reply", "email", "work", "language", "preferences", "client", "facing", "draft"],
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "model-004.yaml",
        _entry(
            "model-004",
            "Repository tasks surface more prior models when the local KB is scanned first",
            ["system", "knowledge-library", "retrieval"],
            cross_index=["codex/workflow/context-reuse", "repository/usage/local-kb-retrieve", "planning/prefetch/prior-lessons"],
            tags=["knowledge-base", "retrieval", "workflow", "repository"],
            trigger_keywords=["kb", "retrieve", "retrieval", "repository", "workflow", "lesson", "preflight"],
            confidence=0.96,
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "retrieval-cross.yaml",
        _entry(
            "cand-2026-04-20-codex-runtime-kb-postflight",
            "Postflight evidence should cross-link retrieval work",
            ["codex", "runtime-behavior", "prompt-following"],
            cross_index=["system/knowledge-library/retrieval"],
            tags=["postflight", "retrieval"],
            trigger_keywords=["postflight", "retrieval", "writeback"],
            confidence=0.7,
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "release-hygiene.yaml",
        _entry(
            "release-hygiene",
            "Release cleanup should keep version gaps reviewable",
            ["repository", "github-publishing", "release-hygiene"],
            tags=["release", "cleanup", "version", "github"],
            trigger_keywords=["release", "cleanup", "version", "gaps"],
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "language-gap.yaml",
        _entry(
            "language-gap",
            "Professional English language preference route",
            ["language", "professional", "english"],
            entry_type="preference",
            tags=["language", "english"],
            trigger_keywords=["language", "english"],
            confidence=0.7,
        ),
    )
    write_yaml_file(
        root / "kb" / "public" / "automation-spec-drift.yaml",
        _entry(
            "automation-spec-drift",
            "Automation spec drift needs a visible test fixture",
            ["automation", "debugging", "spec-drift"],
            tags=["automation", "debugging", "spec-drift"],
            trigger_keywords=["automation", "debugging", "spec", "drift"],
        ),
    )
