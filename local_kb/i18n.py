from __future__ import annotations

import copy
from typing import Any

from local_kb.common import parse_route_segments


DEFAULT_LANGUAGE = "en"
ZH_CN = "zh-CN"
SUPPORTED_LANGUAGES = (DEFAULT_LANGUAGE, ZH_CN)

LOCALIZABLE_SECTION_FIELDS = {
    "if": ("notes",),
    "action": ("description",),
    "predict": ("expected_result",),
    "use": ("guidance",),
}

ROUTE_SEGMENT_LABELS_ZH_CN = {
    "agent-behavior": "智能体行为",
    "agent-lifecycle": "智能体生命周期",
    "architecture": "架构",
    "automation": "自动化",
    "automation-bootstrap": "自动化引导",
    "bilingual": "双语",
    "breaking-change": "破坏性变更",
    "business": "商务",
    "cleanup-cooldown": "清理冷却",
    "cleanup-review": "清理审查",
    "codex": "Codex",
    "communication": "沟通",
    "companies": "公司",
    "companies and search": "公司与搜索",
    "companies timeout ownership": "公司超时归属",
    "company-discovery": "公司发现",
    "company-fit": "公司匹配",
    "company scheduling": "公司调度",
    "context-reuse": "上下文复用",
    "cooldown": "冷却",
    "debugging": "调试",
    "dependency": "依赖",
    "design": "设计",
    "desktop-app": "桌面应用",
    "desktop-rendering": "桌面渲染",
    "desktop_app": "桌面应用",
    "demo seed": "演示种子",
    "discovery-state": "发现状态",
    "done-condition": "完成条件",
    "dream": "梦境整理",
    "email": "邮件",
    "engineering": "工程",
    "english": "英文",
    "exploration": "探索",
    "field-retirement": "字段退役",
    "github-publishing": "GitHub 发布",
    "human-ui": "人类界面",
    "install": "安装",
    "integration": "集成",
    "job-hunter": "求职助手",
    "kb": "知识库",
    "knowledge-browser": "知识浏览器",
    "knowledge-library": "知识库",
    "language": "语言",
    "local-kb-retrieve": "本地 KB 检索",
    "localization": "本地化",
    "maintenance": "维护",
    "migration": "迁移",
    "orchestration": "编排",
    "orchestration + bootstrap": "编排与启动",
    "persistence": "持久化",
    "planning": "规划",
    "postflight": "事后记录",
    "predictive-kb": "预测 KB",
    "prefetch": "预取",
    "prior-lessons": "既有经验",
    "professional": "专业",
    "prompt-following": "提示遵循",
    "prompt-refresh-control": "提示刷新控制",
    "prompting": "提示词",
    "python": "Python",
    "python desktop app": "Python 桌面应用",
    "qt embedding": "Qt 嵌入",
    "readme": "README",
    "readme-presentation": "README 展示",
    "recovery-state": "恢复状态",
    "refactor": "重构",
    "regression": "回归",
    "release-hygiene": "发布卫生",
    "repository": "仓库",
    "repository-cleanup": "仓库清理",
    "repository-workflows": "仓库工作流",
    "resume-queue": "恢复队列",
    "retrieval": "检索",
    "runtime-behavior": "运行时行为",
    "runtime-migration": "运行时迁移",
    "runtime-state": "运行时状态",
    "search": "搜索",
    "search-core": "搜索核心",
    "search orchestration": "搜索编排",
    "search-orchestration": "搜索编排",
    "search-runtime": "搜索运行时",
    "search-selection": "搜索选择",
    "session lifecycle": "会话生命周期",
    "session-stop-logic": "会话停止逻辑",
    "software": "软件",
    "software-engineering": "软件工程",
    "spec-drift": "规格漂移",
    "state": "状态",
    "state-boundary": "状态边界",
    "stages and search": "阶段与搜索",
    "system": "系统",
    "tagging": "标签",
    "template": "模板",
    "testing": "测试",
    "testing-and-smoke": "测试与冒烟",
    "timeouts": "超时",
    "tool-environment": "工具环境",
    "troubleshooting": "排障",
    "ui": "界面",
    "ui-state": "界面状态",
    "unittest": "单元测试",
    "usage": "使用",
    "user-entry": "用户入口",
    "verification": "验证",
    "version-change": "版本变更",
    "versioning": "版本管理",
    "work": "工作",
    "workflow": "工作流",
    "writing": "写作",
}


def normalize_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"zh", "zh-cn", "zh_cn", "chinese", "中文", "简体中文"}:
        return ZH_CN
    return DEFAULT_LANGUAGE


def language_label(language: str) -> str:
    return "中文" if normalize_language(language) == ZH_CN else "English"


def localized_route_segment(segment: Any, language: str) -> str:
    text = str(segment or "").strip()
    if not text:
        return ""
    if normalize_language(language) != ZH_CN:
        return text
    return ROUTE_SEGMENT_LABELS_ZH_CN.get(text.lower(), text)


def has_route_segment_label(segment: Any, language: str = ZH_CN) -> bool:
    text = str(segment or "").strip()
    if not text:
        return True
    if normalize_language(language) != ZH_CN:
        return True
    return text.lower() in ROUTE_SEGMENT_LABELS_ZH_CN


def localized_route_label(route: Any, language: str, *, empty_label: str = "root") -> str:
    segments = parse_route_segments(route)
    if not segments:
        return empty_label
    return " / ".join(localized_route_segment(segment, language) for segment in segments)


def localized_route_title(route: Any, language: str, *, empty_label: str = "root") -> str:
    segments = parse_route_segments(route)
    if not segments:
        return empty_label
    if normalize_language(language) == ZH_CN:
        return " / ".join(localized_route_segment(segment, language) for segment in segments)
    return " / ".join(segment.replace("-", " ").title() for segment in segments)


def _localized_root(data: dict[str, Any], language: str) -> dict[str, Any]:
    if normalize_language(language) == DEFAULT_LANGUAGE:
        return {}
    i18n = data.get("i18n", {})
    if not isinstance(i18n, dict):
        return {}
    localized = i18n.get(ZH_CN, {})
    return localized if isinstance(localized, dict) else {}


def _localized_text(localized: dict[str, Any], section: str, field: str) -> str:
    section_payload = localized.get(section, {})
    if not isinstance(section_payload, dict):
        return ""
    value = section_payload.get(field)
    return str(value).strip() if isinstance(value, str) else ""


def localized_title(data: dict[str, Any], language: str) -> str:
    localized = _localized_root(data, language)
    value = localized.get("title")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return str(data.get("title") or "").strip()


def localized_section(data: dict[str, Any], section: str, language: str) -> dict[str, Any]:
    source = data.get(section, {})
    if not isinstance(source, dict):
        return {}
    if normalize_language(language) == DEFAULT_LANGUAGE:
        return copy.deepcopy(source)

    result = copy.deepcopy(source)
    localized = _localized_root(data, language)
    for field in LOCALIZABLE_SECTION_FIELDS.get(section, ()):
        value = _localized_text(localized, section, field)
        if value:
            result[field] = value

    if section == "predict":
        result["alternatives"] = localized_alternatives(data, language)
    return result


def localized_alternatives(data: dict[str, Any], language: str) -> list[dict[str, Any]]:
    predict = data.get("predict", {})
    if not isinstance(predict, dict):
        return []
    alternatives = predict.get("alternatives", [])
    if not isinstance(alternatives, list):
        return []

    source_items = [copy.deepcopy(item) for item in alternatives if isinstance(item, dict)]
    if normalize_language(language) == DEFAULT_LANGUAGE:
        return source_items

    localized_predict = _localized_root(data, language).get("predict", {})
    localized_items = []
    if isinstance(localized_predict, dict) and isinstance(localized_predict.get("alternatives"), list):
        localized_items = [item for item in localized_predict["alternatives"] if isinstance(item, dict)]

    result: list[dict[str, Any]] = []
    for index, source in enumerate(source_items):
        item = dict(source)
        localized = localized_items[index] if index < len(localized_items) else {}
        for field in ("when", "result"):
            value = localized.get(field)
            if isinstance(value, str) and value.strip():
                item[field] = value.strip()
        result.append(item)
    return result


def localized_entry(data: dict[str, Any], language: str) -> dict[str, Any]:
    if normalize_language(language) == DEFAULT_LANGUAGE:
        return copy.deepcopy(data)

    result = copy.deepcopy(data)
    title = localized_title(data, language)
    if title:
        result["title"] = title
    for section in LOCALIZABLE_SECTION_FIELDS:
        if section in data:
            result[section] = localized_section(data, section, language)
    return result


def _has_canonical_text(data: dict[str, Any], section: str, field: str) -> bool:
    section_payload = data.get(section, {})
    return isinstance(section_payload, dict) and bool(str(section_payload.get(field) or "").strip())


def missing_i18n_fields(data: dict[str, Any], language: str = ZH_CN) -> list[str]:
    if normalize_language(language) == DEFAULT_LANGUAGE:
        return []
    missing: list[str] = []
    localized = _localized_root(data, language)

    if str(data.get("title") or "").strip() and not str(localized.get("title") or "").strip():
        missing.append("title")

    for section, fields in LOCALIZABLE_SECTION_FIELDS.items():
        localized_section_payload = localized.get(section, {})
        if not isinstance(localized_section_payload, dict):
            localized_section_payload = {}
        for field in fields:
            if _has_canonical_text(data, section, field) and not str(localized_section_payload.get(field) or "").strip():
                missing.append(f"{section}.{field}")

    predict = data.get("predict", {})
    canonical_alternatives = predict.get("alternatives", []) if isinstance(predict, dict) else []
    localized_predict = localized.get("predict", {})
    localized_alternative_items = (
        localized_predict.get("alternatives", [])
        if isinstance(localized_predict, dict) and isinstance(localized_predict.get("alternatives"), list)
        else []
    )
    if isinstance(canonical_alternatives, list):
        for index, item in enumerate(canonical_alternatives):
            if not isinstance(item, dict):
                continue
            localized_item = localized_alternative_items[index] if index < len(localized_alternative_items) else {}
            if not isinstance(localized_item, dict):
                localized_item = {}
            for field in ("when", "result"):
                if str(item.get(field) or "").strip() and not str(localized_item.get(field) or "").strip():
                    missing.append(f"predict.alternatives[{index}].{field}")

    return missing


def has_language(data: dict[str, Any], language: str = ZH_CN) -> bool:
    return not missing_i18n_fields(data, language=language)


def merge_i18n_payload(data: dict[str, Any], language: str, localized_payload: dict[str, Any]) -> dict[str, Any]:
    normalized_language = normalize_language(language)
    if normalized_language == DEFAULT_LANGUAGE:
        raise ValueError("English is the canonical source and is not stored under i18n.")
    result = copy.deepcopy(data)
    i18n = result.get("i18n", {})
    if not isinstance(i18n, dict):
        i18n = {}
    current_language_payload = i18n.get(normalized_language, {})
    if not isinstance(current_language_payload, dict):
        current_language_payload = {}
    merged = _deep_merge_dict(current_language_payload, localized_payload)
    i18n[normalized_language] = merged
    result["i18n"] = i18n
    return result


def _deep_merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
