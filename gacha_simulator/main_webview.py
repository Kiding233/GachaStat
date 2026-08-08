#!/usr/bin/env python3
"""GachaStat Web 视图入口（P74 换头计划阶段 1b/2）——与 python -m gacha_simulator.main（PyQt6 旧 UI）平行。

运行新 UI（生产，加载 Vite build 产物 dist/）：
    python -m gacha_simulator.main_webview
    或 python gacha_simulator/main_webview.py（脚本方式，自动注入项目根到 sys.path）

开发模式（Vite dev server 热重载）：
    python -m gacha_simulator.main_webview --dev

双 UI 并行：main.py 仍启动旧 PyQt6 UI，二者互不影响（共用 core 引擎与 config.toml）。
"""
from __future__ import annotations

import os
import sys

# 脚本方式运行（python gacha_simulator/main_webview.py）时注入项目根到 sys.path，
# 与 main.py 的路径处理一致；-m 方式下包已在路径中。
this_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(this_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from gacha_simulator.webui.api import GachaApi  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
_DIST_INDEX = os.path.join(_PROJECT, 'tools', 'poc_webview', 'ui_compare', 'dist', 'index.html')
_DEV_URL = 'http://127.0.0.1:5173/'


def _index_url():
    if os.path.exists(_DIST_INDEX):
        return _DIST_INDEX
    return _DEV_URL


def main() -> None:
    import webview

    dev_mode = '--dev' in sys.argv
    url = _DEV_URL if dev_mode else _index_url()
    api = GachaApi()

    window = webview.create_window(
        'GachaStat',
        url=url,
        js_api=api,
        width=1560,
        height=920,
    )
    api.attach_window(window)
    webview.start()


if __name__ == '__main__':
    main()
