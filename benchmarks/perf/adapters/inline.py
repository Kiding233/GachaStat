"""`inline` 路径适配器。

**驱动逻辑来自 `scripts/profile_sim.py`（`2a` 修复后）**——按 §3.2 约束 A，适配器
**只接管已有入口、不新写驱动**。该脚本的驱动形态是：加载配置 → `from_config_store`
建 env → `SharedResultCollector` + `extract_aggregate` → `run_batch_parallel(...,
on_result=collector.on_result)`。

**本路径不是任何用户路径**（§3.3 / `02-实施.md` §5.4）：

- `is_user_path = False` 强制标注，使它在任何报告中自带「这不是用户路径」的标签
- 它的价值是提供一条**纯计算基线**；风险是极易被误读为「这就是模拟的真实耗时」
- 实证依据：`scripts/profile_sim.py:93-111` 测「单次模拟耗时」的办法是在主进程串行
  跑 20 次 `run_simulation_compact`，这绕开了子进程插桩的难题，但同时换掉了执行环境
  ——没有 spawn、没有 IPC、没有 extractor。那个数字不描述 GUI 里的任何一次模拟

**`collector = True`**（§3.4 表）：本适配器**确实**向 `run_batch_parallel` 传
`on_result`（其驱动来源 `profile_sim.py:53` 即如此），这与三条产品入口（均为 `False`）
相反。**平台不因 `collector` 改变驱动方式**——它是申报值，由 T3 断言。

**`function` 档可达**（§3.8 D1 注入通道表）：适配器直接构造 `env`，故四字段能按
「构造后赋值」的注入点落上去；`workers >= 2` 时走 MPPool 路径。
"""

from __future__ import annotations

import logging
import os
import time
from typing import List

from benchmarks.perf.adapters.base import (
    Adapter,
    SingleRun,
    new_run_id,
    register_adapter,
)
from benchmarks.perf.plan import Plan
from benchmarks.perf.profilers.stage import (
    map_product_stage_times,
    normalize_resources,
    normalize_stages,
)

logger = logging.getLogger(__name__)

__all__ = ['InlineAdapter']


@register_adapter
class InlineAdapter(Adapter):
    """直接构造 `GachaService` 运行环境的纯计算路径。"""

    name = 'inline'
    is_user_path = False
    collector = True
    #: 本路径没有分发器（同 `cli`）
    absent_stages = ('dispatch',)

    def available(self) -> bool:
        """无额外依赖——只要共享的批量模拟入口可导入即可。"""
        try:
            from gacha_simulator.core.streaming import SharedResultCollector  # noqa: F401
            from gacha_simulator.service.batch_simulator import run_batch_parallel  # noqa: F401
        except Exception as exc:  # pragma: no cover - 取决于环境
            logger.debug('inline 路径不可用：%s', exc)
            return False
        return True

    # ── 单次驱动 ─────────────────────────────────────────

    def _run_once(self, plan: Plan) -> SingleRun:
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.core.streaming import SharedResultCollector, extract_aggregate
        from gacha_simulator.service.batch_simulator import (
            SimulationEnvBuilder,
            run_batch_parallel,
        )

        warnings: List[str] = []
        # 本路径在本进程内跑 run_batch_parallel，故 run_id 由本进程生成即可
        # （§3.8 D3 的「生成点与消费点同进程」那一行）。
        run_id = new_run_id()

        started = time.perf_counter()
        store = load_toml(plan.config_path)
        config_load = time.perf_counter() - started

        env_started = time.perf_counter()
        env = SimulationEnvBuilder.from_config_store(store)
        env_build = time.perf_counter() - env_started

        # §3.8 D1：四字段由调用方在 env 构造完成后**直接赋值**，不经 builder 的显式
        # keyword 表。顺序是硬要求：先设字段、再调 run_batch_parallel。
        self._apply_profile_fields(env, plan, run_id, warnings)

        target_specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
        collector = SharedResultCollector()
        collector.add_extractor('aggregate', extract_aggregate)

        simulate_started = time.perf_counter()
        batch = run_batch_parallel(
            env=env,
            target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=plan.n,
            max_workers=plan.workers,
            seed=plan.seed,
            strategy_key=plan.strategy_key,
            strategy_params=plan.strategy_params,
            on_result=collector.on_result,      # ← 本路径的申报依据
            collect_perf=True,                  # 本路径在进程内，回传统一直接取，成本仅为一次 dumps
        )
        simulate_wall = time.perf_counter() - simulate_started

        wall = time.perf_counter() - started
        warnings.extend(getattr(batch, 'warnings', []) or [])

        raw_stages = {'config_load': config_load, 'env_build': env_build}
        product = map_product_stage_times(getattr(batch, 'stage_times', None))
        if product:
            raw_stages.update(product)
        elif simulate_wall:
            # `collect_perf` 未生效时的兜底：至少给出模拟段的墙钟，不假装三段都在
            raw_stages['simulate'] = simulate_wall
        stages, stage_warnings = normalize_stages(raw_stages, absent_by_design=self.absent_stages)
        warnings.extend(stage_warnings)

        resources, resource_warnings = normalize_resources(
            packet_bytes=getattr(batch, 'packet_bytes', None),
            subject=plan.subject,
        )
        warnings.extend(resource_warnings)

        return SingleRun(
            wall=wall,
            stages=stages,
            resources=resources,
            functions=None,                     # `6c` 的父进程侧合并填充
            return_compact=True,                # 本路径不设 env.return_compact，取默认 True
            run_id=run_id,
            warnings=warnings,
        )

    @staticmethod
    def _apply_profile_fields(env, plan: Plan, run_id: str, warnings: List[str]) -> None:
        """把 `Plan` 的四个 `profile_*` 字段落到 `env`（§3.8 D1）。

        `profile_dir` 取 **run 级目录** `<plan.profile_dir>/<run_id>`——D3 要求 run 级
        子目录以隔离同一进程内的多次 `run_batch_parallel` 调用（no_draw 基线重跑不得
        混入主模拟的剖面），而 `env` 只有这一个字段可用，故把 `run_id` 折进它的取值。
        与 `1e-2` 在 `cli.py` 侧的落法一致，使 `6b` 写入与 `6c` 扫描两侧口径相同。

        D7：目录不可写**一律软降级**——绝不因剖析失败导致模拟失败。
        """
        if not plan.profile_enabled:
            return
        run_dir = os.path.join(plan.profile_dir, run_id)
        try:
            os.makedirs(run_dir, exist_ok=True)
        except OSError as exc:
            warnings.append(
                f'profile 目录不可写（{run_dir}）：{exc}——本次不做剖析（§3.8 D7 软降级）'
            )
            return
        env.profile_enabled = True
        env.profile_dir = run_dir
        env.profile_skip = plan.profile_skip
        env.profile_count = plan.profile_count
