"""生成 4 种真实感 ChartSpec 并序列化为 charts.json（垂直切片数据源）。

数据语义：模拟抽卡出货所需抽数分布。
- bar:       4 种策略的平均出货次数（分类比较柱状图）
- histogram: 单策略出货抽数分布（概率质量分布 PMF）
- cdf:       同一样本的累积分布
- ridge:     4 策略出货抽数分布对比（多行直方图山脊线）

运行：python tools/poc_webview/build_charts.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gacha_simulator.visualization.chart_spec import bar, cdf, histogram, ridge
from spec_to_json import specs_to_json_file

_RNG = np.random.default_rng(42)


def simulate_draws(n: int, base_rate: float = 0.006, hard_pity: int = 90) -> np.ndarray:
    """模拟带硬保底的出货所需抽数（几何分布 + 保底截断，近似真实卡池）。"""
    draws = _RNG.geometric(base_rate, size=n)
    return np.minimum(draws, hard_pity)


def build() -> dict:
    n = 4000
    strategies = {
        "固守流": 0.0060,
        "定轨流": 0.0065,
        "退守流": 0.0055,
        "纯抽流": 0.0058,
    }
    strategy_draws = {name: simulate_draws(n, rate) for name, rate in strategies.items()}

    charts = {}

    # 1. 柱状图：各策略平均出货次数（分类比较）
    charts["bar"] = bar(
        list(strategies.keys()),
        np.array([float(np.mean(v)) for v in strategy_draws.values()]),
        title="各策略平均出货次数（柱状图）",
        ylabel="平均出货抽数",
    )

    # 2. 概率质量分布：固守流出货抽数直方图
    charts["histogram"] = histogram(
        strategy_draws["固守流"],
        title="固守流出货抽数分布（概率质量分布）",
        xlabel="出货所需抽数",
        ylabel="频数",
        nbins=30,
    )

    # 3. 累积分布：固守流出货抽数 CDF
    charts["cdf"] = cdf(
        strategy_draws["固守流"],
        title="固守流出货抽数累积分布（CDF）",
        xlabel="出货所需抽数",
        ylabel="累积概率",
    )

    # 4. 山脊线：4 策略出货抽数分布对比
    charts["ridge"] = ridge(
        strategy_draws,
        title="各策略出货抽数分布对比（山脊线图）",
        xlabel="出货所需抽数",
    )

    return charts


if __name__ == "__main__":
    charts = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts.json")
    specs_to_json_file(charts, out)
    print(f"charts.json 已生成到 {out}，共 {len(charts)} 张图：{', '.join(charts.keys())}")
