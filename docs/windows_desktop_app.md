# Windows Desktop App

## 中文

这个桌面入口是给人类看卡片用的。它不替代 Codex 的 KB 检索、反馈或 Sleep/Dream/Architect 维护流程。

推荐的人类入口有三层：

- 直接打开：`python scripts/open_khaos_brain_ui.py --repo-root .`
- 打包后打开：双击 `dist/KhaosBrain.exe`，或通过下面的桌面快捷方式打开。
- 让 Codex 打开：使用 `$khaos-brain-open-ui`。

### 打包 exe

第一次打包前安装 PyInstaller：

```powershell
python -m pip install --user pyinstaller
```

然后构建：

```powershell
python scripts/build_desktop_exe.py --repo-root . --json
```

构建结果是：

```text
dist/KhaosBrain.exe
```

这个 exe 只打包桌面查看器代码和公开 UI 图标资源。它不会把 `kb/private/`、`kb/history/`、`kb/candidates/` 或任何真实经验卡片封进二进制。运行时仍然通过 `--repo-root` 读取当前仓库里的文件型 KB。

### 创建桌面快捷方式

```powershell
python scripts/install_desktop_shortcut.py --repo-root . --json
```

快捷方式会优先指向已经构建好的 `dist/KhaosBrain.exe`。如果 exe 还不存在，可以加 `--prefer-python` 创建 Python 回退入口。默认不传语言参数，让应用沿用 UI 中保存的显示语言；需要固定语言时可以加 `--language en` 或 `--language zh-CN`。

## English

The desktop entry is for human card browsing. It does not replace Codex KB retrieval, feedback, or Sleep/Dream/Architect maintenance.

Recommended human entry points:

- Open directly: `python scripts/open_khaos_brain_ui.py --repo-root .`
- Open after packaging: double-click `dist/KhaosBrain.exe`, or use the desktop shortcut below.
- Ask Codex to open it: use `$khaos-brain-open-ui`.

### Build the exe

Install PyInstaller once:

```powershell
python -m pip install --user pyinstaller
```

Build:

```powershell
python scripts/build_desktop_exe.py --repo-root . --json
```

Output:

```text
dist/KhaosBrain.exe
```

The exe bundles only viewer code and public UI icon assets. It does not bundle `kb/private/`, `kb/history/`, `kb/candidates/`, or real memory cards. At runtime it still reads the file-based KB from `--repo-root`.

### Create a desktop shortcut

```powershell
python scripts/install_desktop_shortcut.py --repo-root . --json
```

The shortcut prefers `dist/KhaosBrain.exe` when it exists. Use `--prefer-python` to create a Python fallback shortcut before building the exe. By default it omits the language argument so the app can use the saved display setting; pass `--language en` or `--language zh-CN` only when a fixed language is needed.
