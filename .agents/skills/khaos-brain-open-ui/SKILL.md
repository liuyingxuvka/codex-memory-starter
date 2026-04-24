---
name: khaos-brain-open-ui
description: Open the local Khaos Brain desktop card browser for human review. Use when the user asks to open, show, view, inspect, or create a human-facing entry for the Khaos Brain UI, desktop app, card browser, or Windows shortcut. Do not use this for AI KB retrieval or feedback; use the predictive KB retrieval workflow for that.
---

# Khaos Brain Open UI

## Overview

Open the local desktop card viewer for humans. This skill is an entry-point helper only; it does not change card content and does not replace preflight/postflight KB workflows.

## Workflow

1. Resolve the predictive KB repository root. In this repository, use the current workspace root.
2. Prefer the unified launcher:

   ```powershell
   python scripts/open_khaos_brain_ui.py --repo-root .
   ```

3. If the user asks for a packaged app first, build it:

   ```powershell
   python scripts/build_desktop_exe.py --repo-root . --json
   ```

4. If the user wants a Windows desktop icon, create or refresh the shortcut:

   ```powershell
   python scripts/install_desktop_shortcut.py --repo-root . --json
   ```

## Boundaries

- The viewer is read-only for normal browsing.
- The exe bundles viewer code and public UI assets only. KB cards stay file-based and are read from `--repo-root`.
- Do not use this skill for AI memory preflight, retrieval scoring, feedback capture, card promotion, or maintenance. Use the existing predictive KB retrieval and maintenance workflows for those.
