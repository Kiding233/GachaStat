"""GachaStat 工作区 UI 布局探针启动器。

一次性探针，用于评估「左树 + 右侧详情/分析双模式」的布局方案。
数据全假，不接 Python 后端；Vue 3 与 Element Plus 走 cdnjs，需联网。

运行：python tools/poc_webview/layout_demo/load_demo.py
或直接用浏览器打开同目录的 index.html。
"""
from __future__ import annotations

from pathlib import Path

import webview

_HERE = Path(__file__).resolve().parent
_INDEX = _HERE / "index.html"


def main() -> None:
    if not _INDEX.exists():
        raise SystemExit(f"找不到探针页面：{_INDEX}")
    webview.create_window(
        "GachaStat 工作区布局探针",
        _INDEX.as_uri(),
        width=1560,
        height=920,
    )
    webview.start()


if __name__ == "__main__":
    main()
