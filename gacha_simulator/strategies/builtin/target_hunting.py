"""指定池追卡策略——只从指定池子抽卡。"""
from __future__ import annotations

from typing import List

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.param_descriptor import StringListParam
from gacha_simulator.core.action import Action


@register_strategy('target_hunting', '指定池追卡',
    params=[StringListParam('target_pool_ids', '目标池ID列表', default=[])])
class TargetHuntingStrategy(Strategy):
    def __init__(self, target_pool_ids: List[str]):
        self.target_pool_ids = target_pool_ids

    @classmethod
    def description(cls) -> str:
        return "指定池抽卡：只从指定池子抽卡"

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction
        target_pools = [p for p in ctx.current_pools if p.id in self.target_pool_ids]
        for pool in target_pools:
            if ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                return DrawAction(pool_id=pool.id)
        return WaitAction(duration=3600)
