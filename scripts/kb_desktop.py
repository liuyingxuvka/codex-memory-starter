from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_repo_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))


_bootstrap_repo_imports()

from local_kb.store import resolve_repo_root  # noqa: E402
from local_kb.ui_data import build_overview_payload, build_route_view_payload  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open the local Khaos Brain desktop card viewer.")
    parser.add_argument("--repo-root", default="auto")
    parser.add_argument("--route", default="", help="Initial route for check output.")
    parser.add_argument(
        "--language",
        default="",
        choices=["", "en", "zh-CN"],
        help="Display language. Omit it to use the saved desktop setting.",
    )
    parser.add_argument("--check", action="store_true", help="Validate UI data without opening a desktop window.")
    return parser


def _show_startup_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Khaos Brain", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main() -> None:
    args = build_parser().parse_args()
    try:
        repo_root = resolve_repo_root(args.repo_root)
    except FileNotFoundError as exc:
        _show_startup_error(str(exc))
        raise SystemExit(2) from exc

    if args.check:
        check_language = args.language or "en"
        route_payload = build_route_view_payload(repo_root, route=args.route, language=check_language)
        overview = build_overview_payload(repo_root)
        print(
            json.dumps(
                {
                    "ok": True,
                    "entry_count": overview["entry_count"],
                    "route": route_payload["route_label"],
                    "deck_count": len(route_payload["deck"]),
                    "primary_count": len(route_payload["cards"]["primary"]),
                    "cross_count": len(route_payload["cards"]["cross"]),
                    "language": check_language,
                    "first_card_title": route_payload["deck"][0]["title"] if route_payload["deck"] else "",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    from local_kb.desktop_app import run_desktop_app

    run_desktop_app(repo_root, language=args.language or None)


if __name__ == "__main__":
    main()
