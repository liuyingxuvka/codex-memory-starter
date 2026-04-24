from __future__ import annotations

import ctypes
import math
import sys
import textwrap
from pathlib import Path
from typing import Any


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError, ValueError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError, ValueError):
            pass


_enable_windows_dpi_awareness()

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from local_kb.common import normalize_text
from local_kb.i18n import (
    DEFAULT_LANGUAGE,
    ZH_CN,
    localized_route_label,
    localized_route_segment,
    localized_route_title,
    normalize_language,
)
from local_kb.settings import load_desktop_settings, save_desktop_settings
from local_kb.store import resolve_repo_root
from local_kb.ui_data import (
    build_card_detail_payload,
    build_route_view_payload,
    build_search_payload,
    navigation_card_count,
    navigation_children,
)


BG = "#ffffff"
SIDEBAR = "#fbfbfc"
SIDEBAR_ACTIVE = "#f0eeee"
TEXT = "#171717"
MUTED = "#7c7c82"
LINE = "#e6e6eb"
LINE_SOFT = "#f2f2f5"
ACCENT = "#ff2d55"
UI_FONT = "Segoe UI"
CJK_UI_FONT = "Microsoft YaHei UI"
DEFAULT_WINDOW_SIZE = (1440, 900)
MIN_WINDOW_SIZE = (1080, 720)
SIDEBAR_WIDTH = 344
MAIN_MARGIN_X = 36
MAIN_MAX_COLUMNS = 5
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
APP_ICON_PATH = ASSET_DIR / "khaos-brain-icon.png"
BRAND_ICON_PATH = ASSET_DIR / "khaos-brain-icon-sidebar.png"
PROJECT_GITHUB_URL = "https://github.com/liuyingxuvka/Khaos-Brain"
SUPPORT_PAYPAL = "liu.yingxu.vka@gmail.com"

LANGUAGE_DISPLAY_OPTIONS = {
    DEFAULT_LANGUAGE: "English / 英文",
    ZH_CN: "中文 / Chinese",
}


def _language_display(language: str) -> str:
    return LANGUAGE_DISPLAY_OPTIONS.get(normalize_language(language), LANGUAGE_DISPLAY_OPTIONS[DEFAULT_LANGUAGE])


def _language_from_display(value: str) -> str:
    for language, label in LANGUAGE_DISPLAY_OPTIONS.items():
        if value == label:
            return language
    return normalize_language(value)

UI_TEXT = {
    DEFAULT_LANGUAGE: {
        "all_cards": "All Cards",
        "predictive_memory_cards": "Predictive memory cards",
        "cards_suffix": "cards",
        "library": "Library",
        "trusted": "Trusted",
        "candidates": "Candidates",
        "models": "Models",
        "preferences": "Preferences",
        "routes": "Routes",
        "settings": "Settings / 设置",
        "about": "About / 关于",
        "search": "Search",
        "no_cards": "No cards in this view.",
        "confidence": "confidence",
        "close": "Close",
        "save": "Save / 保存",
        "cancel": "Cancel / 取消",
        "language": "Language / 语言",
        "display_language": "Language / 语言",
        "language_hint": "Choose the display language. Card source text stays canonical in English.",
        "english_canonical": "English remains the canonical card source. Chinese is a display layer maintained during sleep.",
        "settings_title": "Settings / 设置",
        "about_title": "About Khaos Brain",
        "if": "If",
        "action": "Action",
        "predict": "Predict",
        "use": "Use",
        "routes_section": "Routes",
        "primary": "Primary",
        "also": "Also",
        "related": "Related",
        "recent_history": "Recent history",
        "search_title": "Search",
        "about_body": (
            "A local predictive memory library for Codex.\n\n"
            "Latest version:\n{github_url}\n\n"
            "If Khaos Brain helps your work, you can buy the developer a coffee via PayPal:\n"
            "{paypal}\n\n"
            "Cards are stored as auditable files. Routes can surface the same card through multiple paths."
        ),
    },
    ZH_CN: {
        "all_cards": "全部卡片",
        "predictive_memory_cards": "预测记忆卡片",
        "cards_suffix": "张卡片",
        "library": "资料库",
        "trusted": "已信任",
        "candidates": "候选",
        "models": "模型",
        "preferences": "偏好",
        "routes": "路线",
        "settings": "设置 / Settings",
        "about": "关于 / About",
        "search": "搜索",
        "no_cards": "当前视图没有卡片。",
        "confidence": "置信度",
        "close": "关闭",
        "save": "保存 / Save",
        "cancel": "取消 / Cancel",
        "language": "语言 / Language",
        "display_language": "语言 / Language",
        "language_hint": "选择界面显示语言。卡片源文本仍以英文为规范源。",
        "english_canonical": "英文仍是卡片的规范源；中文是睡眠维护补齐的显示层。",
        "settings_title": "设置 / Settings",
        "about_title": "关于 Khaos Brain",
        "if": "适用场景",
        "action": "动作/条件",
        "predict": "预测结果",
        "use": "使用方式",
        "routes_section": "路线",
        "primary": "主路径",
        "also": "也可从",
        "related": "相关卡片",
        "recent_history": "最近历史",
        "search_title": "搜索",
        "about_body": (
            "一个给 Codex 使用的本地预测记忆库。\n\n"
            "最新版本：\n{github_url}\n\n"
            "如果 Khaos Brain 对你的工作有帮助，可以通过 PayPal 请开发者喝咖啡：\n"
            "{paypal}\n\n"
            "卡片以可审查文件保存；不同路线可以找到同一张卡片。"
        ),
    },
}

CARD_PALETTES = [
    {
        "name": "rose",
        "fill": "#f84f8f",
        "deep": "#ffffff",
        "soft": "#ff8eb8",
        "line": "#ffbfd3",
        "muted": "#ffe6ef",
        "pill": "#ffffff",
        "pill_text": "#c91558",
        "outline": "#f4c0d2",
    },
    {
        "name": "sunset",
        "fill": "#ff7a1a",
        "deep": "#ffffff",
        "soft": "#ffb24c",
        "line": "#ffd173",
        "muted": "#fff0d2",
        "pill": "#fff3df",
        "pill_text": "#bd4a00",
        "outline": "#f4c891",
    },
    {
        "name": "solar",
        "fill": "#ffd166",
        "deep": "#4b3300",
        "soft": "#ffe199",
        "line": "#fff0b7",
        "muted": "#7d5c12",
        "pill": "#fff4cc",
        "pill_text": "#684500",
        "outline": "#f0c66d",
    },
    {
        "name": "violet",
        "fill": "#6d4cff",
        "deep": "#ffffff",
        "soft": "#9c7cff",
        "line": "#c1b0ff",
        "muted": "#eee9ff",
        "pill": "#efeaff",
        "pill_text": "#4d2fd6",
        "outline": "#c9bfff",
    },
    {
        "name": "bluewave",
        "fill": "#1677ff",
        "deep": "#ffffff",
        "soft": "#55a4ff",
        "line": "#9fd0ff",
        "muted": "#e2f1ff",
        "pill": "#e9f4ff",
        "pill_text": "#0759c7",
        "outline": "#a9d0ff",
    },
    {
        "name": "cyan",
        "fill": "#00a6d6",
        "deep": "#ffffff",
        "soft": "#4cc6e8",
        "line": "#a5e8f7",
        "muted": "#e5faff",
        "pill": "#e7fbff",
        "pill_text": "#006987",
        "outline": "#a8e8f4",
    },
    {
        "name": "emerald",
        "fill": "#2fb344",
        "deep": "#ffffff",
        "soft": "#63cf72",
        "line": "#b5ecbd",
        "muted": "#e7f8e9",
        "pill": "#e8faeb",
        "pill_text": "#18752a",
        "outline": "#abe4b4",
    },
    {
        "name": "lime",
        "fill": "#a3d82f",
        "deep": "#263600",
        "soft": "#c7ec6a",
        "line": "#e4f7a5",
        "muted": "#456000",
        "pill": "#f1ffd1",
        "pill_text": "#365000",
        "outline": "#d4ee8a",
    },
    {
        "name": "magenta",
        "fill": "#c026d3",
        "deep": "#ffffff",
        "soft": "#e879f9",
        "line": "#f0abfc",
        "muted": "#fde7ff",
        "pill": "#fde9ff",
        "pill_text": "#9412a5",
        "outline": "#efb5f6",
    },
    {
        "name": "cranberry",
        "fill": "#c2413d",
        "deep": "#ffffff",
        "soft": "#e06b67",
        "line": "#f2aaa7",
        "muted": "#ffe8e7",
        "pill": "#fff0ef",
        "pill_text": "#92201d",
        "outline": "#e7aca9",
    },
    {
        "name": "steel",
        "fill": "#6f7f96",
        "deep": "#ffffff",
        "soft": "#94a3b8",
        "line": "#cbd5e1",
        "muted": "#eef2f7",
        "pill": "#edf2f7",
        "pill_text": "#475569",
        "outline": "#c8d1dc",
    },
    {
        "name": "grape",
        "fill": "#7055b8",
        "deep": "#ffffff",
        "soft": "#9b87d8",
        "line": "#c8bbef",
        "muted": "#f0ebff",
        "pill": "#f0ebff",
        "pill_text": "#5b3ca1",
        "outline": "#cabeee",
    },
    {
        "name": "cream",
        "fill": "#fff4e8",
        "deep": "#70482d",
        "soft": "#ffe8d0",
        "line": "#efd2b4",
        "muted": "#9c7a63",
        "pill": "#f8ddc1",
        "pill_text": "#70482d",
        "outline": "#eadfd9",
    },
    {
        "name": "sky",
        "fill": "#67b7dc",
        "deep": "#ffffff",
        "soft": "#91cdec",
        "line": "#b8e2f4",
        "muted": "#effaff",
        "pill": "#e8f8ff",
        "pill_text": "#247699",
        "outline": "#b3dff2",
    },
    {
        "name": "mint",
        "fill": "#72c6a4",
        "deep": "#0d3f30",
        "soft": "#9ee0c4",
        "line": "#c7f2df",
        "muted": "#174f3f",
        "pill": "#dff8ee",
        "pill_text": "#166044",
        "outline": "#bcead7",
    },
    {
        "name": "lavender",
        "fill": "#a99bdd",
        "deep": "#ffffff",
        "soft": "#c6b8ee",
        "line": "#d7cdf2",
        "muted": "#f0ecff",
        "pill": "#f2eeff",
        "pill_text": "#6c58bc",
        "outline": "#d4c9ef",
    },
]


def _route_to_string(route: Any) -> str:
    if not route:
        return ""
    if isinstance(route, str):
        return route.strip("/")
    return "/".join(str(item).strip("/") for item in route if str(item).strip("/"))


def _ui_text(language: str, key: str) -> str:
    normalized = normalize_language(language)
    return UI_TEXT.get(normalized, UI_TEXT[DEFAULT_LANGUAGE]).get(key, UI_TEXT[DEFAULT_LANGUAGE].get(key, key))


def _route_label(route: Any, language: str = DEFAULT_LANGUAGE) -> str:
    return localized_route_label(route, language, empty_label=_ui_text(language, "all_cards"))


def _route_title(route: Any, language: str = DEFAULT_LANGUAGE) -> str:
    return localized_route_title(route, language, empty_label=_ui_text(language, "all_cards"))


def _short_text(value: Any, limit: int = 150) -> str:
    text = normalize_text(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _short_id(value: Any, limit: int = 16) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _blend_hex(start: str, end: str, amount: float) -> str:
    ratio = max(0.0, min(1.0, amount))
    sr, sg, sb = _hex_to_rgb(start)
    er, eg, eb = _hex_to_rgb(end)
    return f"#{round(sr + (er - sr) * ratio):02x}{round(sg + (eg - sg) * ratio):02x}{round(sb + (eb - sb) * ratio):02x}"


def _palette(card: dict[str, Any] | None) -> dict[str, str]:
    if not card:
        return CARD_PALETTES[0]
    card_id = str(card.get("id") or card.get("title") or "")
    return CARD_PALETTES[sum(ord(char) for char in card_id) % len(CARD_PALETTES)]


def _card_type_label(card: dict[str, Any], language: str = DEFAULT_LANGUAGE) -> str:
    value = str(card.get("type") or "model").replace("_", " ").strip()
    if normalize_language(language) == ZH_CN:
        return {"model": "模型", "preference": "偏好", "heuristic": "启发式", "fact": "事实"}.get(value.lower(), value)
    return value.upper() if value else "MODEL"


def _card_type_value(card: dict[str, Any]) -> str:
    return str(card.get("type") or "model").replace("_", "-").strip().lower()


def _status_label(card: dict[str, Any], language: str = DEFAULT_LANGUAGE) -> str:
    value = str(card.get("status") or "card").strip()
    if normalize_language(language) == ZH_CN:
        return {"trusted": "已信任", "candidate": "候选", "deprecated": "已废弃"}.get(value.lower(), value)
    return value


def _confidence_label(card: dict[str, Any]) -> str:
    value = card.get("confidence")
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _cover_title(card: dict[str, Any], language: str = DEFAULT_LANGUAGE) -> str:
    raw_title = normalize_text(card.get("title")).strip()
    if normalize_language(language) == ZH_CN:
        return raw_title or str(card.get("id") or "卡片")

    title = raw_title.lower()
    if "local kb" in title and "scanned first" in title:
        return "Scan KB First"
    if "release" in title:
        return "Release Hygiene"
    if "postflight" in title:
        return "Postflight Memory"
    if "route" in title:
        return "Route Discovery"
    if "preference" in title or "user" in title:
        return "User Preference"
    if "runtime" in title or "codex" in title:
        return "Runtime Behavior"
    words = raw_title.split()
    return " ".join(words[:4]) if words else str(card.get("id") or "Card")


def _text_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return [""]
    if all(ord(char) <= 127 for char in clean):
        wrapped = textwrap.wrap(clean, width=max_chars, break_long_words=False, break_on_hyphens=False) or [""]
        if len(wrapped) <= max_lines:
            return wrapped
        last = wrapped[max_lines - 1]
        return [*wrapped[: max_lines - 1], f"{last[: max(0, len(last) - 3)].rstrip()}..."]
    lines: list[str] = []
    current = ""
    current_units = 0
    for char in clean:
        units = 2 if ord(char) > 127 else 1
        if char.isspace() and not current:
            continue
        if current and current_units + units > max_chars:
            lines.append(current.rstrip())
            if len(lines) >= max_lines:
                last = lines[-1]
                lines[-1] = f"{last[: max(0, len(last) - 3)].rstrip()}..."
                return lines
            current = ""
            current_units = 0
            if char.isspace():
                continue
        current += char
        current_units += units
    if current or not lines:
        lines.append(current.rstrip())
    return lines[:max_lines]


def _detail_paragraphs(value: Any, language: str = DEFAULT_LANGUAGE) -> list[str]:
    paragraphs: list[str] = []

    def append_text(item: Any) -> None:
        text = normalize_text(item).strip()
        if text:
            paragraphs.append(text)

    def append_value(item: Any) -> None:
        if item in (None, ""):
            return
        if isinstance(item, dict):
            preferred_keys = (
                "notes",
                "description",
                "expected_result",
                "guidance",
                "summary",
                "scenario",
                "action_taken",
                "observed_result",
                "previous_action",
                "previous_result",
                "revised_action",
                "revised_result",
                "operational_use",
            )
            for key in preferred_keys:
                if key in item:
                    append_value(item.get(key))
            alternatives = item.get("alternatives")
            if isinstance(alternatives, list):
                is_zh = normalize_language(language) == ZH_CN
                label = "对照路径" if is_zh else "Alternative"
                colon = "：" if is_zh else ": "
                for alternative in alternatives:
                    if isinstance(alternative, dict):
                        when = normalize_text(alternative.get("when")).strip()
                        result = normalize_text(alternative.get("result")).strip()
                        if when and result:
                            separator = f"；对应结果：" if is_zh else " -> "
                            paragraphs.append(f"{label}{colon}{when}{separator}{result}")
                        elif when or result:
                            paragraphs.append(f"{label}{colon}{when or result}")
                    else:
                        append_text(alternative)
            for key, nested in item.items():
                if key in (*preferred_keys, "alternatives"):
                    continue
                if isinstance(nested, (str, int, float, bool)):
                    append_value(nested)
            return
        if isinstance(item, list):
            for nested in item:
                append_value(nested)
            return
        append_text(item)

    append_value(value)
    return paragraphs or ["-"]


class KbDesktopApp(tk.Tk):
    def __init__(self, repo_root: str | Path, *, language: str | None = None) -> None:
        super().__init__()
        self._unit_scale = self._detect_unit_scale()
        self._font_scale = self._detect_font_scale()
        self.repo_root = resolve_repo_root(repo_root)
        self.settings = load_desktop_settings(self.repo_root)
        selected_language = language if language is not None else self.settings.get("language")
        self.language = normalize_language(selected_language)
        self.settings["language"] = self.language
        self.route = ""
        self.deck: list[dict[str, Any]] = []
        self.selected_index = -1
        self.children_by_route: dict[str, list[dict[str, Any]]] = {}
        self.expanded_routes: set[str] = {""}
        self.nav_hitboxes: list[tuple[int, int, int, int, str, str]] = []
        self.footer_hitboxes: list[tuple[int, int, int, int, str]] = []
        self.card_hitboxes: list[tuple[int, int, int, int, int]] = []
        self._main_width = 0
        self._main_height = 0
        self._card_selected_by_user = False
        self.hovered_index = -1
        self._search_after_id: str | None = None

        self.title("Khaos Brain")
        self.geometry(f"{self._u(DEFAULT_WINDOW_SIZE[0])}x{self._u(DEFAULT_WINDOW_SIZE[1])}")
        self.minsize(self._u(MIN_WINDOW_SIZE[0]), self._u(MIN_WINDOW_SIZE[1]))
        self.configure(bg=BG)
        self._app_icon_photo: tk.PhotoImage | None = None
        self._brand_icon_photo: tk.PhotoImage | None = None
        self._card_surface_photos: list[Any] = []
        self._card_surface_cache: dict[tuple[Any, ...], Any] = {}
        self._load_image_assets()

        self._build_layout()
        self.load_route("")
        self.after_idle(self._maximize_initial_window)
        self.after(160, self._maximize_initial_window)

    def _load_image_assets(self) -> None:
        if APP_ICON_PATH.exists():
            try:
                self._app_icon_photo = tk.PhotoImage(file=str(APP_ICON_PATH))
                self.iconphoto(True, self._app_icon_photo)
            except tk.TclError:
                self._app_icon_photo = None
        if BRAND_ICON_PATH.exists():
            try:
                icon_size = self._u(52)
                with Image.open(BRAND_ICON_PATH) as image:
                    self._brand_icon_photo = ImageTk.PhotoImage(
                        image.convert("RGBA").resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    )
            except (OSError, tk.TclError):
                self._brand_icon_photo = None

    def _maximize_initial_window(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry(f"{self._u(1440)}x{self._u(900)}")

    def _detect_unit_scale(self) -> float:
        try:
            dpi = float(self.winfo_fpixels("1i"))
        except tk.TclError:
            dpi = 96.0
        return max(1.0, min(2.45, dpi / 120.0))

    def _detect_font_scale(self) -> float:
        try:
            dpi = float(self.winfo_fpixels("1i"))
        except tk.TclError:
            dpi = 96.0
        return max(1.0, min(2.85, dpi / 104.0))

    def _u(self, value: float) -> int:
        return int(round(value * self._unit_scale))

    def _f(self, pixels: int) -> int:
        return -int(round(pixels * self._font_scale))

    def _font(self, pixels: int, weight: str = "normal") -> tuple[str, int] | tuple[str, int, str]:
        family = CJK_UI_FONT if self.language == ZH_CN else UI_FONT
        if weight == "normal":
            return (family, self._f(pixels))
        return (family, self._f(pixels), weight)

    def _text(self, key: str) -> str:
        return _ui_text(self.language, key)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar_panel = tk.Frame(self, width=self._u(SIDEBAR_WIDTH), bg=SIDEBAR)
        self.sidebar_panel.grid(row=0, column=0, sticky="nsew")
        self.sidebar_panel.grid_propagate(False)
        self.sidebar_panel.grid_columnconfigure(0, weight=1)
        self.sidebar_panel.grid_rowconfigure(0, weight=1)

        self.sidebar = tk.Canvas(self.sidebar_panel, width=self._u(SIDEBAR_WIDTH), bg=SIDEBAR, highlightthickness=0, yscrollincrement=self._u(18))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar_scroll = tk.Scrollbar(self.sidebar_panel, orient="vertical", command=self.sidebar.yview, width=self._u(8))
        self.sidebar_scroll.grid(row=0, column=0, sticky="nse")
        self.sidebar.configure(yscrollcommand=self.sidebar_scroll.set)
        self.sidebar.bind("<Configure>", lambda _event: self._render_sidebar())
        self.sidebar.bind("<Button-1>", self._on_sidebar_click)
        self.sidebar.bind("<MouseWheel>", self._on_sidebar_mousewheel)

        self.sidebar_footer = tk.Canvas(self.sidebar_panel, width=self._u(SIDEBAR_WIDTH), height=self._u(104), bg=SIDEBAR, highlightthickness=0)
        self.sidebar_footer.grid(row=1, column=0, sticky="ew")
        self.sidebar_footer.bind("<Configure>", lambda _event: self._render_footer())
        self.sidebar_footer.bind("<Button-1>", self._on_footer_click)

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.sidebar,
            textvariable=self.search_var,
            relief="flat",
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            borderwidth=0,
            font=self._font(15),
        )
        self.search_entry.insert(0, self._text("search"))
        self.search_entry.bind("<FocusIn>", self._clear_search_placeholder)
        self.search_entry.bind("<FocusOut>", self._restore_search_placeholder)
        self.search_entry.bind("<KeyRelease>", self._schedule_search)
        self.search_entry.bind("<Return>", self._perform_search)
        self.search_window = self.sidebar.create_window(self._u(64), self._u(166), window=self.search_entry, anchor="nw", width=self._u(190), height=self._u(30))

        self.main = tk.Canvas(self, bg=BG, highlightthickness=0, yscrollincrement=self._u(22))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main_scroll = tk.Scrollbar(self, orient="vertical", command=self.main.yview, width=self._u(8))
        self.main_scroll.grid(row=0, column=1, sticky="nse")
        self.main.configure(yscrollcommand=self.main_scroll.set)
        self.main.bind("<Configure>", self._on_main_configure)
        self.main.bind("<Button-1>", self._on_card_click)
        self.main.bind("<Motion>", self._on_card_motion)
        self.main.bind("<Leave>", self._on_card_leave)
        self.main.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Return>", lambda _event: self.open_selected_detail())
        self.bind("<Left>", lambda _event: self._move_selection(-1))
        self.bind("<Right>", lambda _event: self._move_selection(1))

    def _round_rect(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        *,
        fill: str,
        outline: str = "",
        width: int = 1,
        tags: str | tuple[str, ...] = "",
    ) -> None:
        r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill, tags=tags)
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill, tags=tags)
        canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline=fill, tags=tags)
        canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline=fill, tags=tags)
        canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=fill, outline=fill, tags=tags)
        canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=fill, outline=fill, tags=tags)
        if not outline:
            return
        canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width, tags=tags)
        canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width, tags=tags)
        canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width, tags=tags)
        canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width, tags=tags)
        canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=outline, width=width, tags=tags)
        canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=outline, width=width, tags=tags)
        canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=outline, width=width, tags=tags)
        canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=outline, width=width, tags=tags)

    def _gradient_rect(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        palette: dict[str, str],
        *,
        outline: str = "",
        width: int = 1,
    ) -> None:
        r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
        rect_w = max(1, x2 - x1)
        rect_h = max(1, y2 - y1)
        top = _blend_hex(palette.get("soft", palette["fill"]), "#ffffff", 0.06)
        mid = palette["fill"]
        bottom = _blend_hex(palette["fill"], "#000000", 0.14)
        self._round_rect(canvas, x1, y1, x2, y2, r, fill=mid)
        bands = max(24, min(96, rect_h // max(1, self._u(3))))
        for band in range(bands):
            band_y1 = y1 + round(rect_h * band / bands)
            band_y2 = y1 + round(rect_h * (band + 1) / bands) + 1
            local_mid_y = ((band_y1 + band_y2) / 2) - y1
            inset = 0
            if r > 0 and local_mid_y < r:
                dy = r - local_mid_y
                inset = round(r - math.sqrt(max(0, r * r - dy * dy)))
            elif r > 0 and local_mid_y > rect_h - r:
                dy = local_mid_y - (rect_h - r)
                inset = round(r - math.sqrt(max(0, r * r - dy * dy)))
            t = band / max(1, bands - 1)
            color = _blend_hex(top, mid, t / 0.55) if t <= 0.55 else _blend_hex(mid, bottom, (t - 0.55) / 0.45)
            canvas.create_rectangle(
                x1 + inset,
                band_y1,
                x1 + rect_w - inset,
                band_y2,
                fill=color,
                outline=color,
            )
        if outline:
            self._round_rect(canvas, x1, y1, x2, y2, r, fill="", outline=outline, width=width)

    def _draw_card_surface(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        radius: int,
        palette: dict[str, str],
        *,
        hovered: bool = False,
    ) -> None:
        scale = 2
        shadow_x = self._u(2) if not hovered else self._u(3)
        shadow_y = self._u(2) if not hovered else self._u(3)
        blur = max(1, self._u(1.4 if not hovered else 1.8))
        margin = max(self._u(4), blur + self._u(1))

        cache_key = (
            width,
            height,
            radius,
            hovered,
            palette.get("soft", ""),
            palette.get("fill", ""),
            shadow_x,
            shadow_y,
            blur,
        )
        cached_photo = self._card_surface_cache.get(cache_key)
        if cached_photo is not None:
            self._card_surface_photos.append(cached_photo)
            self.main.create_image(x - margin, y - margin, image=cached_photo, anchor="nw")
            return

        image_w = max(1, width + shadow_x + margin * 2)
        image_h = max(1, height + shadow_y + margin * 2)
        surface = Image.new("RGBA", (image_w * scale, image_h * scale), (0, 0, 0, 0))

        card_x = margin * scale
        card_y = margin * scale
        card_w = max(1, width * scale)
        card_h = max(1, height * scale)
        radius_s = max(1, radius * scale)

        shadow_layer = Image.new("RGBA", surface.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_alpha = 100 if hovered else 78
        shadow_box = [
            card_x + shadow_x * scale,
            card_y + shadow_y * scale,
            card_x + (shadow_x + width) * scale - 1,
            card_y + (shadow_y + height) * scale - 1,
        ]
        shadow_draw.rounded_rectangle(
            shadow_box,
            radius=radius_s,
            fill=(*_hex_to_rgb("#b9bbc8" if hovered else "#cfd1dc"), shadow_alpha),
        )
        blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(blur * scale))
        surface = Image.alpha_composite(surface, blurred_shadow)

        top = _blend_hex(palette.get("soft", palette["fill"]), "#ffffff", 0.06)
        mid = palette["fill"]
        bottom = _blend_hex(palette["fill"], "#000000", 0.14)
        gradient_column = Image.new("RGBA", (1, card_h), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient_column)
        for yy in range(card_h):
            t = yy / max(1, card_h - 1)
            color = _blend_hex(top, mid, t / 0.55) if t <= 0.55 else _blend_hex(mid, bottom, (t - 0.55) / 0.45)
            gradient_draw.point((0, yy), fill=(*_hex_to_rgb(color), 255))
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        gradient = gradient_column.resize((card_w, card_h), resampling)

        mask = Image.new("L", (card_w, card_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=radius_s, fill=255)
        surface.paste(gradient, (card_x, card_y), mask)

        surface = surface.resize((image_w, image_h), resampling)
        photo = ImageTk.PhotoImage(surface)
        self._card_surface_cache[cache_key] = photo
        self._card_surface_photos.append(photo)
        self.main.create_image(x - margin, y - margin, image=photo, anchor="nw")

    def _draw_gradient_surface(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        width: int,
        height: int,
        radius: int,
        palette: dict[str, str],
    ) -> None:
        scale = 2
        image_w = max(1, width)
        image_h = max(1, height)
        radius_s = max(1, radius * scale)
        cache_key = (
            "gradient",
            image_w,
            image_h,
            radius,
            palette.get("soft", ""),
            palette.get("fill", ""),
        )
        cached_photo = self._card_surface_cache.get(cache_key)
        if cached_photo is not None:
            canvas.create_image(x, y, image=cached_photo, anchor="nw")
            setattr(canvas, "_surface_photo", cached_photo)
            return

        top = _blend_hex(palette.get("soft", palette["fill"]), "#ffffff", 0.06)
        mid = palette["fill"]
        bottom = _blend_hex(palette["fill"], "#000000", 0.14)
        surface_w = image_w * scale
        surface_h = image_h * scale
        gradient_column = Image.new("RGBA", (1, surface_h), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient_column)
        for yy in range(surface_h):
            t = yy / max(1, surface_h - 1)
            color = _blend_hex(top, mid, t / 0.55) if t <= 0.55 else _blend_hex(mid, bottom, (t - 0.55) / 0.45)
            gradient_draw.point((0, yy), fill=(*_hex_to_rgb(color), 255))
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        gradient = gradient_column.resize((surface_w, surface_h), resampling)

        mask = Image.new("L", (surface_w, surface_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, surface_w - 1, surface_h - 1], radius=radius_s, fill=255)

        surface = Image.new("RGBA", (surface_w, surface_h), (0, 0, 0, 0))
        surface.paste(gradient, (0, 0), mask)
        surface = surface.resize((image_w, image_h), resampling)
        photo = ImageTk.PhotoImage(surface)
        self._card_surface_cache[cache_key] = photo
        canvas.create_image(x, y, image=photo, anchor="nw")
        setattr(canvas, "_surface_photo", photo)

    def _draw_sidebar_icon(self, canvas: tk.Canvas, cx: int, cy: int, kind: str, color: str, tags: str) -> None:
        u = self._u
        stroke = max(1, u(1.4))
        if kind == "search":
            canvas.create_oval(cx - u(7), cy - u(7), cx + u(5), cy + u(5), outline=color, width=stroke, tags=tags)
            canvas.create_line(cx + u(4), cy + u(4), cx + u(10), cy + u(10), fill=color, width=stroke, tags=tags)
            return
        if kind == "cards":
            canvas.create_polygon(
                cx - u(8),
                cy - u(6),
                cx + u(8),
                cy - u(6),
                cx + u(5),
                cy + u(7),
                cx - u(11),
                cy + u(7),
                outline=color,
                fill="",
                width=stroke,
                tags=tags,
            )
            return
        if kind == "trusted":
            canvas.create_oval(cx - u(8), cy - u(8), cx + u(8), cy + u(8), outline=color, width=stroke, tags=tags)
            canvas.create_line(cx - u(5), cy, cx - u(1), cy + u(4), cx + u(6), cy - u(5), fill=color, width=stroke, tags=tags)
            return
        if kind == "candidates":
            canvas.create_rectangle(cx - u(8), cy - u(8), cx + u(8), cy + u(8), outline=color, width=stroke, tags=tags)
            for offset in (-5, 0, 5):
                canvas.create_line(cx - u(8), cy + u(offset - 4), cx + u(8), cy + u(offset + 4), fill=color, width=stroke, tags=tags)
            return
        if kind == "model":
            canvas.create_oval(cx - u(9), cy - u(9), cx + u(9), cy + u(9), outline=color, width=stroke, tags=tags)
            canvas.create_oval(cx - u(3), cy - u(3), cx + u(3), cy + u(3), outline=color, width=stroke, tags=tags)
            canvas.create_line(cx - u(12), cy, cx - u(8), cy, fill=color, width=stroke, tags=tags)
            canvas.create_line(cx + u(8), cy, cx + u(12), cy, fill=color, width=stroke, tags=tags)
            return
        if kind == "preference":
            for offset, knob in ((-6, -3), (0, 5), (6, 0)):
                canvas.create_line(cx - u(10), cy + u(offset), cx + u(10), cy + u(offset), fill=color, width=stroke, tags=tags)
                canvas.create_oval(
                    cx + u(knob) - u(2),
                    cy + u(offset) - u(2),
                    cx + u(knob) + u(2),
                    cy + u(offset) + u(2),
                    outline=color,
                    width=stroke,
                    tags=tags,
                )
            return
        if kind == "route":
            canvas.create_line(cx - u(7), cy, cx + u(7), cy, fill=color, width=max(stroke, u(1.6)), tags=tags)
            return
        if kind == "settings":
            canvas.create_oval(cx - u(8), cy - u(8), cx + u(8), cy + u(8), outline=color, width=stroke, tags=tags)
            canvas.create_oval(cx - u(3), cy - u(3), cx + u(3), cy + u(3), outline=color, width=stroke, tags=tags)
            for dx, dy in ((0, -11), (0, 11), (-11, 0), (11, 0), (-8, -8), (8, -8), (-8, 8), (8, 8)):
                canvas.create_line(cx + int(dx * self._unit_scale * 0.72), cy + int(dy * self._unit_scale * 0.72), cx + u(dx), cy + u(dy), fill=color, width=stroke, tags=tags)
            return
        if kind == "about":
            canvas.create_oval(cx - u(8), cy - u(8), cx + u(8), cy + u(8), outline=color, width=stroke, tags=tags)
            canvas.create_line(cx, cy - u(1), cx, cy + u(5), fill=color, width=stroke, tags=tags)
            canvas.create_oval(cx - u(1), cy - u(6), cx + u(1), cy - u(4), fill=color, outline=color, tags=tags)
            return

    def _render_sidebar(self) -> None:
        self.sidebar.delete("chrome")
        self.nav_hitboxes.clear()
        u = self._u
        width = max(int(self.sidebar.winfo_width()), u(SIDEBAR_WIDTH))
        height = max(int(self.sidebar.winfo_height()), u(560))
        self.sidebar.create_rectangle(0, 0, width, height, fill=SIDEBAR, outline=SIDEBAR, tags="chrome")
        self.sidebar.create_line(width - 1, 0, width - 1, height, fill=LINE, tags="chrome")

        if self._brand_icon_photo is not None:
            self.sidebar.create_image(u(50), u(72), image=self._brand_icon_photo, tags="chrome")
        else:
            self._round_rect(self.sidebar, u(24), u(46), u(76), u(98), u(10), fill=ACCENT, tags="chrome")
            self.sidebar.create_text(u(50), u(72), text="KB", fill=BG, font=self._font(17, "bold"), tags="chrome")
        self.sidebar.create_text(u(96), u(52), text="Khaos Brain", anchor="nw", fill=TEXT, font=self._font(19, "bold"), tags="chrome")
        self.sidebar.create_text(u(96), u(83), text="Memory Library", anchor="nw", fill=MUTED, font=self._font(12), tags="chrome")

        self._round_rect(self.sidebar, u(28), u(130), width - u(36), u(174), u(12), fill=BG, outline=LINE, tags="chrome")
        self._draw_sidebar_icon(self.sidebar, u(49), u(152), "search", MUTED, "chrome")
        self.sidebar.coords(self.search_window, u(72), u(140))
        self.sidebar.itemconfigure(self.search_window, width=max(u(140), width - u(122)), height=u(32))

        y = u(206)
        self._nav_row(u(28), y, width - u(32), self._text("all_cards"), "cards", "", active=self.route == "" and not self.searching)
        y += u(48)
        self._nav_row(u(28), y, width - u(32), self._text("trusted"), "trusted", "", active=self.searching == "trusted")
        y += u(48)
        self._nav_row(u(28), y, width - u(32), self._text("candidates"), "candidates", "", active=self.searching == "candidate")
        y += u(48)
        self._nav_row(u(28), y, width - u(32), self._text("models"), "type", "model", active=self.searching == "type:model")
        y += u(48)
        self._nav_row(
            u(28),
            y,
            width - u(32),
            self._text("preferences"),
            "type",
            "preference",
            active=self.searching == "type:preference",
        )
        y += u(58)

        self.sidebar.create_line(u(34), y - u(18), width - u(40), y - u(18), fill=LINE, tags="chrome")
        self.sidebar.create_text(u(28), y, text=self._text("routes"), anchor="nw", fill=TEXT, font=self._font(14), tags="chrome")
        y += u(38)

        for route, label, depth, active, ancestor, count, declared in self._visible_routes():
            self._route_row(u(42), y, width - u(40), route, label, depth, active, ancestor, count, declared)
            y += u(40)
        self.sidebar.configure(scrollregion=(0, 0, width, max(height, y + u(24))))
        self._render_footer()

    def _render_footer(self) -> None:
        self.sidebar_footer.delete("footer")
        self.footer_hitboxes.clear()
        u = self._u
        width = max(int(self.sidebar_footer.winfo_width()), u(SIDEBAR_WIDTH))
        height = max(int(self.sidebar_footer.winfo_height()), u(104))
        self.sidebar_footer.create_rectangle(0, 0, width, height, fill=SIDEBAR, outline=SIDEBAR, tags="footer")
        self.sidebar_footer.create_line(u(34), 0, width - u(40), 0, fill=LINE, tags="footer")
        self._footer_row(self.sidebar_footer, u(28), u(14), width - u(32), self._text("settings"), "settings")
        self._footer_row(self.sidebar_footer, u(28), u(56), width - u(32), self._text("about"), "about")

    @property
    def searching(self) -> str:
        title = getattr(self, "_searching", "")
        return title

    @searching.setter
    def searching(self, value: str) -> None:
        self._searching = value

    def _nav_row(self, x1: int, y1: int, x2: int, label: str, action: str, value: str, *, active: bool) -> None:
        u = self._u
        y2 = y1 + u(42)
        if active:
            self._round_rect(self.sidebar, x1, y1, x2, y2, u(12), fill=SIDEBAR_ACTIVE, tags="chrome")
            self.sidebar.create_line(x1 - u(8), y1 + u(8), x1 - u(8), y2 - u(8), fill=ACCENT, width=max(1, u(2)), tags="chrome")
        icon = {"cards": "cards", "trusted": "trusted", "candidates": "candidates"}.get(action, "route")
        if action == "type":
            icon = "model" if value == "model" else "preference"
        icon_color = ACCENT if active else MUTED
        self._draw_sidebar_icon(self.sidebar, x1 + u(22), y1 + u(21), icon, icon_color, "chrome")
        self.sidebar.create_text(
            x1 + u(56),
            y1 + u(21),
            text=label,
            anchor="w",
            fill=ACCENT if active else TEXT,
            font=self._font(15),
            tags="chrome",
        )
        self.nav_hitboxes.append((x1, y1, x2, y2, action, value))

    def _footer_row(self, canvas: tk.Canvas, x1: int, y1: int, x2: int, label: str, action: str) -> None:
        u = self._u
        y2 = y1 + u(36)
        icon = "settings" if action == "settings" else "about"
        self._draw_sidebar_icon(canvas, x1 + u(22), y1 + u(18), icon, MUTED, "footer")
        canvas.create_text(x1 + u(54), y1 + u(18), text=label, anchor="w", fill=TEXT, font=self._font(14), tags="footer")
        self.footer_hitboxes.append((x1, y1, x2, y2, action))

    def _visible_routes(self) -> list[tuple[str, str, int, bool, bool, int, bool]]:
        rows: list[tuple[str, str, int, bool, bool, int, bool]] = []

        def walk(route: str, depth: int) -> None:
            if route not in self.expanded_routes:
                return
            for item in self.children_by_route.get(route, []):
                child_route = _route_to_string(item.get("route", []))
                active = child_route == self.route
                ancestor = bool(self.route and self.route.startswith(f"{child_route}/"))
                count = navigation_card_count(item)
                rows.append(
                    (
                        child_route,
                        localized_route_segment(item.get("segment") or child_route, self.language),
                        depth,
                        active,
                        ancestor,
                        count,
                        bool(item.get("declared", False)),
                    )
                )
                walk(child_route, depth + 1)

        walk("", 0)
        return rows

    def _route_row(
        self,
        x1: int,
        y1: int,
        x2: int,
        route: str,
        label: str,
        depth: int,
        active: bool,
        ancestor: bool,
        count: int,
        declared: bool,
    ) -> None:
        u = self._u
        y2 = y1 + u(38)
        indent = depth * u(19)
        if active:
            self._round_rect(self.sidebar, x1 - u(10), y1 - u(4), x2, y2 + u(4), u(10), fill=SIDEBAR_ACTIVE, tags="chrome")
            self.sidebar.create_line(x1 - u(16), y1 + u(5), x1 - u(16), y2 - u(5), fill=ACCENT, width=u(2), tags="chrome")
        icon_fill = ACCENT if active else MUTED
        text_fill = ACCENT if active else TEXT if ancestor else MUTED
        self._draw_sidebar_icon(self.sidebar, x1 + indent + u(5), y1 + u(19), "route", icon_fill, "chrome")
        self.sidebar.create_text(
            x1 + indent + u(34),
            y1 + u(19),
            text=label,
            anchor="w",
            fill=text_fill,
            font=self._font(14),
            tags="chrome",
        )
        if count:
            pill_w = u(22) + len(str(count)) * u(8)
            self._round_rect(self.sidebar, x2 - u(42) - pill_w, y1 + u(8), x2 - u(42), y2 - u(8), u(9), fill="#f0f0f3", tags="chrome")
            self.sidebar.create_text(x2 - u(42) - pill_w / 2, y1 + u(19), text=str(count), fill=MUTED, font=self._font(11, "bold"), tags="chrome")
        self.sidebar.create_text(x2 - u(6), y1 + u(19), text="›", anchor="e", fill="#b8b8bd", font=self._font(15), tags="chrome")
        self.nav_hitboxes.append((x1 - u(10), y1 - u(4), x2, y2 + u(4), "route", route))

    def _on_sidebar_click(self, event: tk.Event[Any]) -> None:
        y = int(self.sidebar.canvasy(event.y))
        for x1, y1, x2, y2, action, value in self.nav_hitboxes:
            if x1 <= event.x <= x2 and y1 <= y <= y2:
                if action == "cards":
                    self.load_route("")
                elif action == "trusted":
                    self._load_status_view("trusted")
                elif action == "candidates":
                    self._load_status_view("candidate")
                elif action == "type":
                    self._load_type_view(value)
                elif action == "route":
                    self.load_route(value)
                return

    def _on_footer_click(self, event: tk.Event[Any]) -> None:
        for x1, y1, x2, y2, action in self.footer_hitboxes:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if action == "settings":
                    self._open_settings_window()
                elif action == "about":
                    self._open_utility_window(
                        self._text("about_title"),
                        self._text("about_body").format(
                            github_url=PROJECT_GITHUB_URL,
                            paypal=SUPPORT_PAYPAL,
                        ),
                    )
                return

    def _clear_search_placeholder(self, _event: tk.Event[Any]) -> None:
        if self.search_var.get() in {_ui_text(DEFAULT_LANGUAGE, "search"), _ui_text(ZH_CN, "search")}:
            self.search_var.set("")

    def _restore_search_placeholder(self, _event: tk.Event[Any]) -> None:
        if not self.search_var.get().strip():
            self.search_var.set(self._text("search"))

    def _schedule_search(self, event: tk.Event[Any]) -> None:
        if event.keysym in {
            "Alt_L",
            "Alt_R",
            "Control_L",
            "Control_R",
            "Down",
            "End",
            "Home",
            "Left",
            "Right",
            "Shift_L",
            "Shift_R",
            "Tab",
            "Up",
        }:
            return
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(180, self._run_scheduled_search)

    def _run_scheduled_search(self) -> None:
        self._search_after_id = None
        self._perform_search()

    def _perform_search(self, _event: tk.Event[Any] | None = None, *, query: str | None = None) -> str:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        query_text = (query or self.search_var.get()).strip()
        if not query_text or query_text in {_ui_text(DEFAULT_LANGUAGE, "search"), _ui_text(ZH_CN, "search")}:
            self.load_route(self.route)
            return "break"
        self.searching = query_text
        payload = build_search_payload(self.repo_root, query=query_text, route_hint=self.route, top_k=24, language=self.language)
        self.deck = payload["results"]
        self.selected_index = -1
        self._card_selected_by_user = False
        self.hovered_index = -1
        self._route_heading = self._text("search_title")
        self._route_subtitle = query_text
        self._render_sidebar()
        self._render_main()
        return "break"

    def _load_status_view(self, status: str) -> None:
        self.searching = status
        payload = build_route_view_payload(self.repo_root, route="", language=self.language)
        self.deck = [card for card in payload.get("deck", []) if str(card.get("status") or "").lower() == status]
        self.selected_index = -1
        self._card_selected_by_user = False
        self.hovered_index = -1
        self._route_heading = self._text("trusted") if status == "trusted" else self._text("candidates")
        self._route_subtitle = f"{len(self.deck)} {self._text('cards_suffix')}"
        self._render_sidebar()
        self._render_main()

    def _load_type_view(self, card_type: str) -> None:
        card_type = card_type.strip().lower()
        self.searching = f"type:{card_type}"
        payload = build_route_view_payload(self.repo_root, route="", language=self.language)
        self.deck = [card for card in payload.get("deck", []) if _card_type_value(card) == card_type]
        self.selected_index = -1
        self._card_selected_by_user = False
        self.hovered_index = -1
        self._route_heading = self._text("models") if card_type == "model" else self._text("preferences")
        self._route_subtitle = f"{len(self.deck)} {self._text('cards_suffix')}"
        self._render_sidebar()
        self._render_main()

    def load_route(self, route: str) -> None:
        self.searching = ""
        self.route = route
        payload = build_route_view_payload(self.repo_root, route=route, language=self.language)
        self.children_by_route[route] = navigation_children(payload)
        self.expanded_routes.add(route)
        self.deck = payload.get("deck", [])
        self.selected_index = -1
        self._card_selected_by_user = False
        self.hovered_index = -1
        self._route_heading = _route_title(route, self.language)
        self._route_subtitle = self._text("predictive_memory_cards")
        self._render_sidebar()
        self._render_main()

    def _on_main_configure(self, event: tk.Event[Any]) -> None:
        self._main_width = event.width
        self._main_height = event.height
        self._render_main()

    def _render_main(self) -> None:
        self.main.delete("all")
        self._card_surface_photos.clear()
        self.card_hitboxes.clear()
        u = self._u
        f = self._f
        width = max(self._main_width, int(self.main.winfo_width()), u(760))
        self.main.create_rectangle(0, 0, width, max(self._main_height, u(680)), fill=BG, outline=BG)

        layout = self._main_grid_layout(width)
        content_left = layout["left"]
        visible_columns = min(layout["columns"], max(len(self.deck), 1))
        visible_grid_width = visible_columns * layout["card_w"] + max(0, visible_columns - 1) * layout["gap"]
        grid_right = content_left + visible_grid_width
        header_right = min(width - u(MAIN_MARGIN_X), max(grid_right, content_left + u(780)))
        header_width = max(visible_grid_width, header_right - content_left)

        count_label = f"{len(self.deck)} {self._text('cards_suffix')}"
        count_w = max(u(86), u(34) + len(count_label) * u(8))
        title_top = u(42)
        has_count_room = header_width >= u(620)
        title_right = header_right - count_w - u(28) if has_count_room else header_right
        title_width = max(u(260), title_right - content_left)
        title_item = self.main.create_text(
            content_left,
            title_top,
            text=getattr(self, "_route_heading", self._text("all_cards")),
            anchor="nw",
            fill=TEXT,
            width=title_width,
            font=("Segoe UI", f(26), "bold"),
        )
        title_bbox = self.main.bbox(title_item) or (content_left, title_top, title_right, title_top + u(44))

        if has_count_room:
            count_x2 = header_right
            count_x1 = count_x2 - count_w
            count_y1 = title_top + u(8)
            count_y2 = count_y1 + u(28)
        else:
            count_x1 = content_left
            count_x2 = content_left + count_w
            count_y1 = title_bbox[3] + u(10)
            count_y2 = count_y1 + u(28)
        self._round_rect(self.main, count_x1, count_y1, count_x2, count_y2, u(14), fill="#f7f7f9", outline=LINE_SOFT)
        self.main.create_text(
            (count_x1 + count_x2) / 2,
            (count_y1 + count_y2) / 2,
            text=count_label,
            fill=MUTED,
            font=("Segoe UI", f(11), "bold"),
        )

        subtitle_y = max(title_bbox[3] + u(6), count_y2 + u(6) if not has_count_room else u(78))
        subtitle_item = self.main.create_text(
            content_left + 2,
            subtitle_y,
            text=getattr(self, "_route_subtitle", self._text("predictive_memory_cards")),
            anchor="nw",
            fill=MUTED,
            width=max(u(260), header_width),
            font=("Segoe UI", f(13)),
        )
        subtitle_bbox = self.main.bbox(subtitle_item) or (content_left, subtitle_y, header_right, subtitle_y + u(24))
        header_bottom = subtitle_bbox[3] + u(30)

        if self.route:
            route_y1 = subtitle_bbox[3] + u(14)
            route_y2 = route_y1 + u(30)
            self._round_rect(
                self.main,
                content_left,
                route_y1,
                min(header_right, content_left + u(520)),
                route_y2,
                u(15),
                fill="#f6f6f8",
                outline=LINE_SOFT,
            )
            self.main.create_text(
                content_left + u(18),
                (route_y1 + route_y2) / 2,
                text=_route_label(self.route, self.language),
                anchor="w",
                fill=MUTED,
                width=max(u(220), min(header_width, u(500)) - u(36)),
                font=("Segoe UI", f(12)),
            )
            header_bottom = route_y2 + u(34)

        if not self.deck:
            self.main.create_text(content_left, header_bottom, text=self._text("no_cards"), anchor="nw", fill=MUTED, font=("Segoe UI", f(13)))
            self.main.configure(scrollregion=(0, 0, width, max(self._main_height, u(680))))
            return

        card_w = layout["card_w"]
        card_h = layout["card_h"]
        gap = layout["gap"]
        columns = visible_columns
        start_x = content_left
        start_y = header_bottom

        card_rects: list[tuple[int, dict[str, Any], int, int, int, int]] = []
        for index, card in enumerate(self.deck):
            row = index // columns
            column = index % columns
            x = start_x + column * (card_w + gap)
            y = start_y + row * (card_h + gap)
            card_rects.append((index, card, x, y, card_w, card_h))

        for index, card, x, y, rect_w, rect_h in card_rects:
            if index == self.hovered_index:
                continue
            self._draw_card(index, card, x, y, rect_w, rect_h)

        for index, card, x, y, rect_w, rect_h in card_rects:
            if index != self.hovered_index:
                continue
            lift = u(8)
            self._draw_card(index, card, x - lift, y - lift, rect_w + lift * 2, rect_h + lift * 2, hovered=True)
            break

        rows = (len(self.deck) + columns - 1) // columns
        total_h = start_y + rows * (card_h + gap) + u(42)
        self.main.configure(scrollregion=(0, 0, width, max(total_h, self._main_height)))

    def _main_grid_layout(self, width: int) -> dict[str, int]:
        u = self._u
        usable_width = max(u(360), width - u(MAIN_MARGIN_X) * 2)
        if usable_width >= u(1680):
            columns = 5
        elif usable_width >= u(1120):
            columns = 4
        elif usable_width >= u(760):
            columns = 3
        elif usable_width >= u(520):
            columns = 2
        else:
            columns = 1
        columns = min(MAIN_MAX_COLUMNS, columns)
        gap = u(22) if columns > 1 else 0
        card_w = min(u(360), max(u(230), (usable_width - gap * (columns - 1)) // columns))
        card_h = int(card_w * 0.66)
        grid_width = columns * card_w + (columns - 1) * gap
        left = u(MAIN_MARGIN_X)
        return {
            "left": left,
            "columns": columns,
            "gap": gap,
            "card_w": card_w,
            "card_h": card_h,
            "grid_width": grid_width,
        }

    def _draw_card(self, index: int, card: dict[str, Any], x: int, y: int, width: int, height: int, *, hovered: bool = False) -> None:
        u = self._u
        f = self._f
        palette = _palette(card)

        self._draw_card_surface(x, y, width, height, u(18), palette, hovered=hovered)

        type_label = _card_type_label(card, self.language)
        self.main.create_text(
            x + u(22),
            y + u(22),
            text=type_label,
            anchor="nw",
            fill=palette["muted"],
            font=("Segoe UI", f(8), "bold"),
        )
        confidence = _confidence_label(card)
        if confidence:
            self.main.create_text(
                x + width - u(22),
                y + u(22),
                text=f"{self._text('confidence')} {confidence}",
                anchor="ne",
                fill=palette["muted"],
                font=("Segoe UI", f(8), "bold"),
            )

        title = _cover_title(card, self.language)
        title_step = max(u(20), min(u(26), width // 16))
        title_y = y + u(62)
        title_lines = _text_lines(title, 24, 2)
        for line_index, line in enumerate(title_lines):
            self.main.create_text(
                x + u(22),
                title_y + line_index * title_step,
                text=line,
                anchor="nw",
                fill=palette["deep"],
                width=width - u(44),
                font=self._font(14, "bold"),
            )

        footer_y = y + height - u(48)
        body = _short_text(card.get("predicted_result") or card.get("guidance"), 56)
        body_step = max(u(16), min(u(20), width // 28))
        title_block_bottom = title_y + len(title_lines) * title_step
        body_top = title_block_bottom + u(16)
        body_bottom = footer_y - u(12)
        available_body_lines = max(0, min(2, (body_bottom - body_top) // body_step))
        if available_body_lines:
            body_y = body_top
            for line_index, line in enumerate(_text_lines(body, 38, available_body_lines)):
                self.main.create_text(
                    x + u(22),
                    body_y + line_index * body_step,
                    text=line,
                    anchor="nw",
                    fill=palette["deep"],
                    width=width - u(44),
                    font=self._font(10),
                )

        status = _status_label(card, self.language)
        self.main.create_line(x + u(22), footer_y, x + width - u(22), footer_y, fill=palette["line"])
        pill_w = min(width - u(150), max(u(76), u(34) + len(status) * u(8)))
        self._round_rect(self.main, x + u(22), y + height - u(38), x + u(22) + pill_w, y + height - u(16), u(11), fill=palette["pill"])
        self.main.create_text(
            x + u(22) + pill_w / 2,
            y + height - u(27),
            text=status,
            fill=palette["pill_text"],
            font=("Segoe UI", f(9), "bold"),
        )
        self.main.create_text(
            x + width - u(22),
            y + height - u(27),
            text=_short_id(card.get("id"), 18 if width >= u(310) else 12),
            anchor="e",
            fill=palette["muted"],
            font=("Segoe UI", f(8)),
        )
        self.card_hitboxes.append((x, y, x + width, y + height, index))

    def _on_mousewheel(self, event: tk.Event[Any]) -> None:
        self.main.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_sidebar_mousewheel(self, event: tk.Event[Any]) -> None:
        self.sidebar.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _hit_card(self, event: tk.Event[Any]) -> int | None:
        x = int(self.main.canvasx(event.x))
        y = int(self.main.canvasy(event.y))
        for left, top, right, bottom, index in reversed(self.card_hitboxes):
            if left <= x <= right and top <= y <= bottom:
                return index
        return None

    def _on_card_motion(self, event: tk.Event[Any]) -> None:
        index = self._hit_card(event)
        if index != self.hovered_index:
            self.hovered_index = -1 if index is None else index
            self._render_main()
        cursor = "hand2" if index is not None else ""
        if self.main.cget("cursor") != cursor:
            self.main.configure(cursor=cursor)

    def _on_card_leave(self, _event: tk.Event[Any]) -> None:
        if self.hovered_index >= 0:
            self.hovered_index = -1
            self._render_main()
        if self.main.cget("cursor"):
            self.main.configure(cursor="")

    def _on_card_click(self, event: tk.Event[Any]) -> None:
        index = self._hit_card(event)
        if index is None:
            return
        self.selected_index = index
        self._card_selected_by_user = True
        self.hovered_index = index
        self.open_selected_detail()

    def _move_selection(self, delta: int) -> None:
        if not self.deck:
            return
        if self.selected_index < 0:
            self.selected_index = 0
        self.selected_index = (self.selected_index + delta) % len(self.deck)
        self._card_selected_by_user = True
        self.hovered_index = self.selected_index
        self._render_main()

    def open_selected_detail(self) -> None:
        if self.selected_index < 0 or self.selected_index >= len(self.deck):
            if self.deck:
                self.selected_index = 0
            else:
                return
        self._card_selected_by_user = True
        summary = self.deck[self.selected_index]
        detail = build_card_detail_payload(self.repo_root, str(summary.get("id")), language=self.language)
        if detail is None:
            return
        self._open_detail_window({**detail, "route_reason": summary.get("route_reason")})

    def _open_detail_window(self, card: dict[str, Any]) -> None:
        u = self._u
        f = self._f
        window = tk.Toplevel(self)
        window.title(str(card.get("title") or card.get("id") or "Card"))
        window.geometry(f"{u(940)}x{u(720)}")
        window.minsize(u(760), u(560))
        window.configure(bg="#f7f7f9")
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)

        header_canvas = tk.Canvas(window, height=u(222), bg="#f7f7f9", highlightthickness=0)
        header_canvas.grid(row=0, column=0, sticky="ew", padx=u(28), pady=(u(24), u(10)))

        def render_header(event: tk.Event[Any] | None = None) -> None:
            header_canvas.delete("all")
            canvas_width = int(event.width if event else header_canvas.winfo_width()) or u(860)
            palette = _palette(card)
            banner_h = u(210)
            self._draw_gradient_surface(header_canvas, 0, 0, canvas_width, banner_h, u(26), palette)
            header_canvas.create_text(u(32), u(28), text=_card_type_label(card, self.language), anchor="nw", fill=palette["muted"], font=("Segoe UI", f(12), "bold"))
            header_canvas.create_text(
                u(32),
                u(58),
                text=str(card.get("title") or card.get("id") or ""),
                anchor="nw",
                fill=palette["deep"],
                width=max(u(420), canvas_width - u(84)),
                font=("Segoe UI", f(23), "bold"),
            )
            meta = _status_label(card, self.language)
            confidence = _confidence_label(card)
            if confidence:
                meta += f" · {self._text('confidence')} {confidence}"
            pill_right = u(32) + min(u(260), max(u(128), u(30) + len(meta) * u(8)))
            self._round_rect(header_canvas, u(32), banner_h - u(44), pill_right, banner_h - u(18), u(13), fill=palette["pill"])
            header_canvas.create_text((u(32) + pill_right) / 2, banner_h - u(31), text=meta, fill=palette["pill_text"], font=("Segoe UI", f(10), "bold"))

        header_canvas.bind("<Configure>", render_header)

        body_shell = tk.Frame(window, bg="#f7f7f9")
        body_shell.grid(row=2, column=0, sticky="nsew", padx=u(28), pady=(0, u(24)))
        body_shell.grid_columnconfigure(0, weight=1)
        body_shell.grid_rowconfigure(0, weight=1)
        text = tk.Text(
            body_shell,
            bg=BG,
            fg=TEXT,
            relief="flat",
            wrap="word",
            padx=u(32),
            pady=u(24),
            font=("Segoe UI", f(15)),
            insertbackground=TEXT,
        )
        text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = tk.Scrollbar(body_shell, orient="vertical", command=text.yview, width=u(8))
        detail_scroll.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=detail_scroll.set)
        text.tag_configure("heading", foreground=ACCENT, font=("Segoe UI", f(12), "bold"), spacing1=u(10), spacing3=u(4))
        text.tag_configure("body", foreground=TEXT, font=("Segoe UI", f(15)), spacing3=u(8))
        text.tag_configure("muted", foreground=MUTED, font=("Segoe UI", f(13)))
        text.tag_configure("mono", foreground=MUTED, font=("Consolas", f(12)))

        self._insert_detail_section(text, self._text("if"), card.get("if"))
        self._insert_detail_section(text, self._text("action"), card.get("action"))
        self._insert_detail_section(text, self._text("predict"), card.get("predict"))
        self._insert_detail_section(text, self._text("use"), card.get("use"))
        text.insert("end", f"{self._text('routes_section')}\n", "heading")
        cross_routes = [_route_label(route, self.language) for route in card.get("cross_index") or []]
        text.insert("end", f"{self._text('primary')}: {_route_label(card.get('domain_path'), self.language)}\n")
        text.insert("end", f"{self._text('also')}: {'; '.join(cross_routes) or '-'}\n")
        text.insert("end", f"{self._text('related')}: {'; '.join(card.get('related_cards') or []) or '-'}\n\n")
        history = card.get("recent_history") or []
        if history:
            text.insert("end", f"{self._text('recent_history')}\n", "heading")
            for event in history[:4]:
                created_at = str(event.get("created_at") or "")
                summary = normalize_text(event.get("task_summary") or event.get("rationale") or "-")
                text.insert("end", f"{created_at} · {summary}\n", "muted")
            text.insert("end", "\n")
        text.insert("end", f"{card.get('path') or ''}\n", "mono")
        text.configure(state="disabled")
        window.focus_set()

    def _refresh_after_language_change(self) -> None:
        if self.search_var.get() in {_ui_text(DEFAULT_LANGUAGE, "search"), _ui_text(ZH_CN, "search"), ""}:
            self.search_var.set(self._text("search"))
        current_search = self.searching
        if current_search == "trusted":
            self._load_status_view("trusted")
            return
        if current_search == "candidate":
            self._load_status_view("candidate")
            return
        if current_search.startswith("type:"):
            self._load_type_view(current_search.split(":", 1)[1])
            return
        if current_search:
            self._perform_search(query=current_search)
            return
        self.load_route(self.route)

    def _open_settings_window(self) -> None:
        window = tk.Toplevel(self)
        window.title(self._text("settings_title"))
        u = self._u
        f = self._f
        window_width = u(620)
        window_height = u(360)
        x = self.winfo_rootx() + max(u(80), (self.winfo_width() - window_width) // 2)
        y = self.winfo_rooty() + max(u(80), (self.winfo_height() - window_height) // 3)
        window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        window.minsize(u(540), u(320))
        window.transient(self)
        window.configure(bg="#f7f7f9")
        window.grid_columnconfigure(0, weight=1)

        shell = tk.Frame(window, bg="#f7f7f9")
        shell.grid(row=0, column=0, sticky="nsew", padx=u(34), pady=u(30))
        shell.grid_columnconfigure(0, weight=1)

        tk.Label(
            shell,
            text=self._text("settings_title"),
            bg="#f7f7f9",
            fg=TEXT,
            anchor="w",
            font=("Segoe UI", f(22), "bold"),
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            shell,
            text=self._text("english_canonical"),
            bg="#f7f7f9",
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=u(520),
            font=("Segoe UI", f(12)),
        ).grid(row=1, column=0, sticky="ew", pady=(u(8), u(20)))

        language_display_var = tk.StringVar(value=_language_display(self.language))
        group = tk.Frame(shell, bg=BG, highlightbackground=LINE, highlightthickness=1)
        group.grid(row=2, column=0, sticky="ew", pady=(0, u(24)))
        group.grid_columnconfigure(1, weight=1)
        tk.Label(
            group,
            text="🌐",
            bg=BG,
            fg=TEXT,
            anchor="center",
            font=self._font(22),
        ).grid(row=0, column=0, sticky="n", padx=(u(18), u(10)), pady=(u(18), u(6)))
        tk.Label(
            group,
            text=self._text("display_language"),
            bg=BG,
            fg=TEXT,
            anchor="w",
            font=self._font(15, "bold"),
        ).grid(row=0, column=1, sticky="ew", padx=(0, u(18)), pady=(u(18), u(2)))
        tk.Label(
            group,
            text=self._text("language_hint"),
            bg=BG,
            fg=MUTED,
            anchor="w",
            justify="left",
            wraplength=u(470),
            font=self._font(11),
        ).grid(row=1, column=1, sticky="ew", padx=(0, u(18)), pady=(0, u(12)))

        window.option_add("*TCombobox*Listbox.font", self._font(13))
        style = ttk.Style(window)
        style.configure("Khaos.TCombobox", font=self._font(13), padding=u(8))
        language_combo = ttk.Combobox(
            group,
            textvariable=language_display_var,
            values=list(LANGUAGE_DISPLAY_OPTIONS.values()),
            state="readonly",
            style="Khaos.TCombobox",
            font=self._font(13),
        )
        language_combo.grid(row=2, column=1, sticky="ew", padx=(0, u(18)), pady=(0, u(18)), ipady=u(4))

        actions = tk.Frame(shell, bg="#f7f7f9")
        actions.grid(row=3, column=0, sticky="e")

        def save_language() -> None:
            self.language = _language_from_display(language_display_var.get())
            self.settings["language"] = self.language
            save_desktop_settings(self.repo_root, self.settings)
            self._refresh_after_language_change()
            window.destroy()

        tk.Button(
            actions,
            text=self._text("cancel"),
            command=window.destroy,
            relief="flat",
            bg="#ececf1",
            fg=TEXT,
            padx=u(18),
            pady=u(7),
            font=("Segoe UI", f(12)),
        ).grid(row=0, column=0, padx=(0, u(10)))
        tk.Button(
            actions,
            text=self._text("save"),
            command=save_language,
            relief="flat",
            bg=ACCENT,
            fg=BG,
            padx=u(18),
            pady=u(7),
            font=("Segoe UI", f(12), "bold"),
        ).grid(row=0, column=1)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.lift()
        window.focus_set()

    def _open_utility_window(self, title: str, message: str) -> None:
        window = tk.Toplevel(self)
        window.title(title)
        u = self._u
        f = self._f
        window_width = u(660)
        window_height = u(500)
        x = self.winfo_rootx() + max(u(80), (self.winfo_width() - window_width) // 2)
        y = self.winfo_rooty() + max(u(80), (self.winfo_height() - window_height) // 3)
        window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        window.minsize(u(560), u(430))
        window.transient(self)
        window.configure(bg="#f7f7f9")
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(0, weight=1)

        shell = tk.Frame(window, bg="#f7f7f9")
        shell.grid(row=0, column=0, sticky="nsew", padx=u(34), pady=u(30))
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        title_label = tk.Label(shell, text=title, bg="#f7f7f9", fg=TEXT, anchor="w", font=("Segoe UI", f(22), "bold"))
        title_label.grid(row=0, column=0, sticky="ew")
        body = tk.Label(
            shell,
            text=message,
            bg="#f7f7f9",
            fg=TEXT,
            anchor="nw",
            justify="left",
            wraplength=u(560),
            font=("Segoe UI", f(14)),
        )
        body.grid(row=1, column=0, sticky="nsew", pady=(u(18), u(20)))
        close = tk.Button(
            shell,
            text=self._text("close"),
            command=window.destroy,
            relief="flat",
            bg=ACCENT,
            fg=BG,
            padx=u(18),
            pady=u(7),
            font=("Segoe UI", f(12), "bold"),
        )
        close.grid(row=2, column=0, sticky="e")
        window.bind("<Escape>", lambda _event: window.destroy())
        window.lift()
        window.focus_set()

    def _insert_detail_section(self, widget: tk.Text, label: str, value: Any) -> None:
        widget.insert("end", f"{label}\n", "heading")
        for body in _detail_paragraphs(value, self.language):
            for paragraph in textwrap.wrap(body, width=88) or ["-"]:
                widget.insert("end", f"{paragraph}\n", "body")
            widget.insert("end", "\n")
        widget.insert("end", "\n")


def run_desktop_app(repo_root: str | Path, language: str | None = None) -> None:
    app = KbDesktopApp(repo_root, language=language)
    app.mainloop()
