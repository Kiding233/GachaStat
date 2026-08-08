"""ChartSpec → 纯 JSON 序列化器（垂直切片核心验证点）。

验证「ChartSpec 作为前后端数据契约」是否成立：
不经过 PlotlyRenderer，直接把 ChartSpec 序列化推给前端，
由前端 Plotly.js / ECharts 各自渲染。若此路径通，换头时后端面板代码几乎不动。
"""
from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np


def _clean(obj):
    """递归把 numpy 类型与 dataclass 转为原生 Python 可序列化对象。"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if hasattr(obj, "__dataclass_fields__"):
        return _clean(asdict(obj))
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


def spec_to_dict(spec) -> dict:
    """单个 ChartSpec → 纯 Python dict（可直接 json.dumps）。"""
    return _clean(asdict(spec))


def spec_to_json(spec) -> str:
    return json.dumps(spec_to_dict(spec), ensure_ascii=False)


def specs_to_json_file(charts: dict[str, object], path: str) -> None:
    """{key: ChartSpec} → JSON 文件（供前端一次拉取）。"""
    payload = {key: spec_to_dict(spec) for key, spec in charts.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
