"""GachaStat UI 探针启动器。

用法：
    python load_demo.py                      # 工作区布局探针（index.html）
    python load_demo.py tabs_showcase        # 标签页样式对照页
    python load_demo.py <名字或文件名>        # 同目录下任意页面

页面本身是纯静态 HTML，可用性不依赖本脚本（双击也能开）；
本脚本只是为了省去手动定位文件。
"""
from __future__ import annotations

import sys
from pathlib import Path

import webview

_HERE = Path(__file__).resolve().parent
_TITLES = {
    "index": "GachaStat 工作区布局探针",
    "tabs_showcase": "GachaStat 标签页样式对照",
}


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "index"
    page = _HERE / (arg if arg.endswith(".html") else f"{arg}.html")
    if not page.exists():
        cands = ", ".join(sorted(p.stem for p in _HERE.glob("*.html")))
        raise SystemExit(f"找不到页面：{page}\n本目录可用的页面：{cands}")
    webview.create_window(
        _TITLES.get(page.stem, page.stem),
        page.as_uri(),
        width=1280,
        height=720,
    )
    webview.start()


if __name__ == "__main__":
    main()
