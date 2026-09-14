"""pywebview 最小示例，验证换头计划（POC 阶段 0）的关键技术风险。

验证点：
1. WebView2 在本机可用（Win 11 系统自带，不捆绑浏览器内核）
2. JS → Python 桥（前端按钮触发 numpy 模拟，替代 Qt signal/slot）
3. Python → JS 主动推送（evaluate_js 更新前端状态，替代 Qt 信号反向回传）
4. Plotly 图表在 WebView2 中的渲染

运行：python tools/poc_webview/main.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import webview

_HERE = Path(__file__).resolve().parent


class Api:
    """暴露给 JS 的桥接 API（前端通过 window.pywebview.api.* 调用）。"""

    def hello(self) -> str:
        """JS → Python：连通性测试。"""
        return "Python 桥已连通"

    def get_charts(self) -> dict:
        """JS → Python：拉取垂直切片的 4 张 ChartSpec（charts.json）。

        数据由 build_charts.py 生成，经 spec_to_json 序列化为纯 JSON。
        验证点：中量数据（336KB）跨 JS-Python 桥一次传输的体验。
        """
        path = _HERE / "charts.json"
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def run_simulation(self, n: int = 2000) -> dict:
        """JS → Python：模拟抽卡，返回直方图数据给前端渲染。

        简单模型：单抽出货率 0.6%，几何分布模拟出货所需抽数。
        实际项目中这一步就是 run_batch_parallel() 的入口，前端零改动。
        """
        rng = np.random.default_rng(42)
        draws = rng.geometric(0.006, size=int(n))
        hist, edges = np.histogram(draws, bins=30)
        return {
            "x": [str(int(e)) for e in edges[:-1]],
            "y": hist.astype(int).tolist(),
            "mean": float(draws.mean()),
            "n": int(n),
        }


def main() -> None:
    api = Api()
    index_url = (_HERE / "comparison.html").as_uri()
    window = webview.create_window(
        "GachaStat 垂直切片：ChartSpec 双库对比",
        url=index_url,
        js_api=api,
        width=1200,
        height=1400,
    )

    def _on_loaded() -> None:
        # Python → JS 主动推送：页面加载后由 Python 侧注入状态（替代 Qt 信号反向回传）
        window.evaluate_js("setStatus('Python 主动推送已到达');")

    window.events.loaded += _on_loaded
    webview.start()


if __name__ == "__main__":
    main()
