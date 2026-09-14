"""链路穿透测试：前端触发真实 run_batch_parallel() → 结果跨桥 → ECharts 渲染。

与垂直切片（静态 charts.json 演示数据）的本质区别：
这里跑的是真实模拟引擎，从 config.toml 加载真实配置，前端拿到真实模拟结果。

验证点：
1. 真实并行模拟从前端触发（替代 Qt QThread 的启动模式）
2. 真实模拟结果跨 JS-Python 桥返回（数据量与耗时，验证大数据跨桥）
3. 结果 → ChartSpec 数据 → ECharts 端到端渲染

运行：python tools/poc_webview/chain_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import webview

_HERE = Path(__file__).resolve().parent


def _load_config_store():
    """从 config.toml 加载真实 ConfigStore（与 GUI 相同的路径）。"""
    from gacha_simulator.core.config_store import ConfigStore
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.paths import get_config_dir
    store = ConfigStore()
    load_toml(os.path.join(get_config_dir(), 'config.toml'), store)
    return store


def _to_native(obj):
    """把聚合结果中的 numpy 类型/可序列化对象转为纯 Python（可跨桥 JSON）。"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if hasattr(obj, 'to_dict'):
        try:
            return _to_native(obj.to_dict())
        except Exception:
            pass
    return obj


def _extract_total_draws(aggregate_data):
    """从聚合结果提取 total_draws 序列（真实模拟数据）。"""
    draws = []
    for agg in aggregate_data:
        if isinstance(agg, dict) and agg.get('total_draws') is not None:
            draws.append(float(agg['total_draws']))
    return draws


class Api:
    """JS → Python 桥。"""

    def run_batch(self, n: int, workers: int) -> dict:
        """启动真实并行模拟并返回完整聚合结果。

        同步执行（Python 主进程跑 run_batch_parallel）。
        大数据跨桥验证：完整 aggregate_data 随返回值一次跨桥传输。
        """
        from gacha_simulator.service.batch_simulator import (
            SimulationEnvBuilder,
            run_batch_parallel,
        )

        store = _load_config_store()
        env = SimulationEnvBuilder.from_config_store(store)
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        strategy_key = getattr(store, 'strategy_key', '')

        t0 = time.time()
        batch = run_batch_parallel(
            env=env,
            target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=int(n),
            max_workers=int(workers),
            seed=42,
            strategy_key=strategy_key,
            strategy_params=getattr(store, 'strategy_params', None),
        )
        elapsed = time.time() - t0

        ext = getattr(batch, 'extraction', None) or {}
        aggregate_data = ext.get('aggregates', []) or []
        total_draws = _extract_total_draws(aggregate_data)

        native_aggregates = _to_native(aggregate_data)
        payload_kb = len(json.dumps(native_aggregates, ensure_ascii=False)) / 1024

        return {
            "config": os.path.basename(os.path.join(
                __import__('gacha_simulator.paths', fromlist=['get_config_dir']).get_config_dir(),
                'config.toml',
            )),
            "n_requested": int(n),
            "n_results": len(native_aggregates),
            "elapsed_s": round(elapsed, 2),
            "payload_kb": round(payload_kb, 1),
            "mean_draws": round(sum(total_draws) / len(total_draws), 2) if total_draws else 0,
            "total_draws": total_draws,
            "aggregate_sample": native_aggregates[0] if native_aggregates else {},
        }


def main() -> None:
    api = Api()
    index_url = (_HERE / "chain_test.html").as_uri()
    window = webview.create_window(
        "链路穿透：真实模拟 → 前端",
        url=index_url,
        js_api=api,
        width=1000,
        height=760,
    )

    def _on_loaded() -> None:
        window.evaluate_js("setStatus('Python 就绪');")

    window.events.loaded += _on_loaded
    webview.start()


if __name__ == "__main__":
    main()
