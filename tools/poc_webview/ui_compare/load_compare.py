"""GachaStat UI 演示启动器（P74 阶段 1a）。

一键启动：若 Vite dev server 未运行则自动拉起，再打开 pywebview 窗口。

运行：python tools/poc_webview/ui_compare/load_compare.py
（等价手动两步：npm run dev + 本脚本；本脚本已自动做第一步）
"""
from __future__ import annotations

import subprocess
import time
import urllib.request
from pathlib import Path

import webview

_HERE = Path(__file__).resolve().parent
_DEV_URL = "http://127.0.0.1:5173/"


def _vite_running() -> bool:
    try:
        urllib.request.urlopen(_DEV_URL, timeout=1)
        return True
    except Exception:
        return False


def _ensure_vite() -> None:
    if _vite_running():
        return
    print("Vite dev server 未运行，正在启动…")
    subprocess.Popen(
        ["npx", "vite"],
        cwd=str(_HERE),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for _ in range(40):
        time.sleep(0.5)
        if _vite_running():
            print("Vite dev server 就绪：", _DEV_URL)
            return
    print("警告：Vite 启动超时，请手动在 ui_compare/ 下运行 npm run dev")


def main() -> None:
    _ensure_vite()
    webview.create_window(
        "GachaStat UI 演示（阶段 1a）",
        _DEV_URL,
        width=1560,
        height=920,
    )
    webview.start()


if __name__ == "__main__":
    main()
