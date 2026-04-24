from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from local_kb.common import (
    normalize_string_list,
    normalize_text,
    parse_route_segments,
    safe_float,
    tokenize,
)
from local_kb.models import Entry
from local_kb.store import load_entries


def longest_common_prefix(left: list[str], right: list[str]) -> int:
    count = 0
    for left_item, right_item in zip(left, right):
        if left_item != right_item:
            break
        count += 1
    return count


def unique_overlap(left: Iterable[str], right: Iterable[str]) -> int:
    return len(set(left) & set(right))


def get_guidance(data: dict[str, Any]) -> str:
    return (
        normalize_text(data.get("use", {}).get("guidance"))
        or normalize_text(data.get("then", {}).get("guidance"))
    )


def get_predicted_result(data: dict[str, Any]) -> str:
    return normalize_text(data.get("predict", {}).get("expected_result"))


def get_body_text(data: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            normalize_text(data.get("if")),
            normalize_text(data.get("action")),
            normalize_text(data.get("predict")),
            normalize_text(data.get("use")),
            normalize_text(data.get("source")),
            normalize_text(data.get("i18n")),
        ]
        if part
    )


def score_entry(entry: Entry, query_tokens: list[str], path_hint_segments: list[str]) -> float:
    data = entry.data
    title_tokens = tokenize(normalize_text(data.get("title", "")))
    tag_tokens = tokenize(normalize_text(data.get("tags", [])))
    trigger_tokens = tokenize(normalize_text(data.get("trigger_keywords", [])))
    body_tokens = tokenize(get_body_text(data))
    confidence = safe_float(data.get("confidence", 0.5) or 0.5, default=0.5)
    status = str(data.get("status", "candidate")).lower()

    domain_path = parse_route_segments(data.get("domain_path", []))
    cross_index_segments = parse_route_segments(data.get("cross_index", []))

    relevance_score = 0.0
    if path_hint_segments:
        relevance_score += longest_common_prefix(path_hint_segments, domain_path) * 8.0
        relevance_score += unique_overlap(path_hint_segments, domain_path) * 5.0
        relevance_score += unique_overlap(path_hint_segments, cross_index_segments) * 4.0

    relevance_score += unique_overlap(query_tokens, title_tokens) * 3.0
    relevance_score += unique_overlap(query_tokens, tag_tokens) * 5.0
    relevance_score += unique_overlap(query_tokens, trigger_tokens) * 4.0
    relevance_score += unique_overlap(query_tokens, body_tokens) * 1.0

    if relevance_score <= 0:
        return 0.0

    score = relevance_score + confidence * 2.0
    if status == "trusted":
        score += 4.0
    if status == "deprecated":
        score -= 5.0
    return score


def search_entries(repo_root: Path, query: str, path_hint: str = "", top_k: int = 5) -> list[Entry]:
    query_tokens = tokenize(query)
    path_hint_segments = parse_route_segments(path_hint)
    entries = load_entries(repo_root)
    for entry in entries:
        entry.score = score_entry(entry, query_tokens, path_hint_segments)
    ranked = [entry for entry in sorted(entries, key=lambda item: item.score, reverse=True) if entry.score > 0]
    return ranked[:top_k]


def render_entry(entry: Entry, repo_root: Path) -> dict[str, Any]:
    data = entry.data
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "type": data.get("type"),
        "scope": data.get("scope"),
        "status": data.get("status"),
        "confidence": data.get("confidence"),
        "domain_path": parse_route_segments(data.get("domain_path", [])),
        "cross_index": normalize_string_list(data.get("cross_index", [])),
        "related_cards": normalize_string_list(data.get("related_cards", [])),
        "tags": data.get("tags", []),
        "trigger_keywords": data.get("trigger_keywords", []),
        "predicted_result": get_predicted_result(data),
        "guidance": get_guidance(data),
        "path": os.path.relpath(entry.path, repo_root),
        "score": round(entry.score, 3),
    }


def render_search_payload(entries: list[Entry], repo_root: Path) -> list[dict[str, Any]]:
    return [render_entry(entry, repo_root) for entry in entries]


def format_search_output(payload: list[dict[str, Any]], path_hint: str = "") -> str:
    lines: list[str] = []
    path_hint_segments = parse_route_segments(path_hint)
    if not payload:
        return "No relevant local predictive KB entries found."

    if path_hint_segments:
        lines.append(f"Path hint: {' / '.join(path_hint_segments)}")
        lines.append("")

    lines.append("Top local predictive KB entries:")
    lines.append("")
    for index, item in enumerate(payload, start=1):
        lines.append(f"{index}. [{item['id']}] {item['title']}")
        lines.append(
            "   "
            f"type={item['type']} scope={item['scope']} status={item['status']} score={item['score']}"
        )
        lines.append(
            "   "
            f"domain_path={' / '.join(item['domain_path']) if item['domain_path'] else '-'}"
        )
        lines.append(
            "   "
            f"cross_index={'; '.join(item['cross_index']) if item['cross_index'] else '-'}"
        )
        lines.append(
            "   "
            f"related_cards={'; '.join(item['related_cards']) if item['related_cards'] else '-'}"
        )
        lines.append(f"   predicted_result={item['predicted_result']}")
        lines.append(f"   guidance={item['guidance']}")
        lines.append(f"   tags={', '.join(item['tags'])}")
        lines.append(f"   trigger_keywords={', '.join(item['trigger_keywords'])}")
        lines.append(f"   path={item['path']}")
        lines.append("")
    return "\n".join(lines).rstrip()
