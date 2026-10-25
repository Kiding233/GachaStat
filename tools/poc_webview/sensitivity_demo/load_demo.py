"""敏感性扫描 UI 方案 demo 启动器。

用法：
    python load_demo.py            # 方案甲：GUI（PyQt6 仿制）
    python load_demo.py webui      # 方案乙：WebUI
    python load_demo.py <名字>      # 同目录下任意页面

两页都是纯静态 HTML，可用性不依赖本脚本（双击也能开）；本脚本只为省去
手动定位文件。方案乙复用 `../layout_demo/libs/`（Vue 3 ＋ Element Plus 的
本地副本），故需与本目录的相对位置保持不变。

与 `../layout_demo/load_demo.py` 的分工：那边是通用布局探针（工作区骨架），
这边只放敏感性扫描这一个专题的两套交互方案，互不合并。
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

_HERE = Path(__file__).resolve().parent
_TITLES = {
    "gui": "敏感性扫描 · 方案甲（GUI）",
    "webui": "敏感性扫描 · 方案乙（WebUI）",
}


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "gui"
    page = _HERE / (arg if arg.endswith(".html") else f"{arg}.html")
    if not page.exists():
        cands = ", ".join(sorted(p.stem for p in _HERE.glob("*.html")))
        raise SystemExit(f"找不到页面：{page}\n本目录可用的页面：{cands}")
    # 与 layout_demo 同尺寸：配置区行宽约 1060px 时 11 个标签刚好一行。
    webview.create_window(
        _TITLES.get(page.stem, page.stem),
        page.as_uri(),
        width=1520,
        height=950,
    )
    webview.start()


if __name__ == "__main__":
    main()
