"""不抽卡策略——始终等待，一次都不抽，用于计算不抽卡的资源基线水平。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy, next_event_wait,
)
from gacha_simulator.core.action import Action


@register_strategy('no_draw', '不抽卡基线')
class NoDrawStrategy(Strategy):
    """不抽卡策略：始终等待，一次都不抽。用于计算不抽卡基线资源水平。"""

    @classmethod
    def description(cls) -> str:
        return "不抽卡：始终等待，用于计算基线资源水平"

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import WaitAction
        # P79 枯竭态契约：唯一入口 next_event_wait(ctx)——原为内联的
        # min(86400, 最近关闭时刻 - real_time) 复刻，随本策略开放给用户
        # 一并收敛到统一实现（含 86400 硬上限与负值兜底）。
        return WaitAction(duration=next_event_wait(ctx))
