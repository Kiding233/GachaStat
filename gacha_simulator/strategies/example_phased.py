"""示例插件策略——两阶段抽卡：前期高阈值保守，后期低阈值激进。

此文件同时作为策略插件开发参考和 UI 测试基准。
放入 strategies/ 目录后，应用启动时自动发现并在策略下拉框中可用。

使用方式：
  1. 确保此文件在 strategies/ 目录下（开发环境为 gacha_simulator/strategies/）
  2. 启动应用 → 策略下拉框出现「两阶段策略」
  3. 点击「工具 → 插件管理」可查看/启用/禁用此插件
"""

from __future__ import annotations

from gacha_simulator.core.strategy import (
    register_strategy, Strategy, StrategyContext,
    DrawSegmentStrategy, PityReserveStrategy,
)
from gacha_simulator.core.param_descriptor import FloatParam, IntParam
from gacha_simulator.core.action import Action


@register_strategy('plugin/example_phased', '两阶段策略',
    params=[
        FloatParam('early_threshold', '前期阈值(%)', default=80.0, min_val=0.0, max_val=100.0),
        FloatParam('late_threshold', '后期阈值(%)', default=50.0, min_val=0.0, max_val=100.0),
        IntParam('switch_at', '切换抽数', default=50, min_val=1),
    ])
class PhasedPlanStrategy(Strategy):
    """前 N 抽高阈值保守（只在保底概率高时抽），后期低阈值激进（见池就抽）。

    组合模式示例：使用 DrawSegmentStrategy 按抽数分段，每段使用不同的
    PityReserveStrategy 实例。更复杂的策略可以通过 PriorityChainStrategy
    或 ConditionalStrategy 进一步组合。
    """

    def __init__(self, early_threshold=80.0, late_threshold=50.0, switch_at=50):
        self.early_threshold = early_threshold
        self.late_threshold = late_threshold
        self.switch_at = switch_at

        # 使用复合策略 Building Block 组合内置策略
        self.inner = DrawSegmentStrategy([
            (0, switch_at, PityReserveStrategy(pity_threshold_pct=early_threshold)),
            (switch_at, None, PityReserveStrategy(pity_threshold_pct=late_threshold)),
        ])

    @classmethod
    def description(cls) -> str:
        return "前N抽高阈值保守，后期低阈值激进"

    def select_action(self, ctx: StrategyContext) -> Action:
        return self.inner.select_action(ctx)
