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
        # P61（ISSUE-303/315）：target_pool_ids 匹配口径为 banner.id
        target_banners = [b for b in ctx.banners if b.id in self.target_pool_ids]
        for banner in target_banners:
            pool = banner.active_pool
            if ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                return DrawAction(banner_id=banner.id)
        return WaitAction(duration=3600)
