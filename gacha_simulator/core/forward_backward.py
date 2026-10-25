#!/usr/bin/env python3
"""
搜索过程记录数据结构。

现存：最少资源二分搜索的步骤 / 结果记录（`ResourceSearchStep` / `ResourceSearchResult`）。

P81 §三 C2（2026-09-17）删除了前进法 / 后退法目标优化的四类步骤与结果记录：其唯一
使用者 `gui/strategy_panel.py` 已在 C1 归档，且贪心法实现已迁至 `retreat_search.py`
（`search_max_targets*`），不再经这些结构传递。四个符号名见 P81 §三 C2（代码中不再
出现，以便零命中验收可达）。

**注**：本模块名 `forward_backward` 现已名不副实（不再含前进/后退内容）。
其名实不符与「三个旧面板删除后的命名清理轮」同批，见
`docs/01-活跃/panels/方案搜索/05-笔记.md:86`，不在 C2 处置范围。
"""

from typing import List, Dict
from dataclasses import dataclass




@dataclass
class ResourceSearchStep:
    iteration: int
    resource_value: float
    success_probability: float
    phase: str
    lo_bound: float
    hi_bound: float


@dataclass
class ResourceSearchResult:
    steps: List[ResourceSearchStep]
    min_resource: float
    final_success_probability: float
    cost_per_draw: float
    target_specs: Dict[str, int]
    total_iterations: int
