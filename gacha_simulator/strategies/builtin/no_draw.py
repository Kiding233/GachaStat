"""不抽卡基线策略——始终等待，用于计算不抽卡的资源基线水平。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.action import Action


@register_strategy('no_draw', '不抽卡基线', internal=True)
class NoDrawStrategy(Strategy):
    """不抽卡策略：始终等待，一次都不抽。用于计算不抽卡基线资源水平。"""

    @classmethod
    def description(cls) -> str:
        return "不抽卡：始终等待，用于计算基线资源水平"

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import WaitAction
        wait_time = 86400
        for pool in ctx.current_pools:
            if hasattr(pool, 'available_until') and pool.available_until and pool.available_until > ctx.state.real_time:
                wait_time = min(wait_time, pool.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
