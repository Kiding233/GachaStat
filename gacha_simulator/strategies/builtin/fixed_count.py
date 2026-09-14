"""固定次数策略——抽指定次数后停止。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy, next_event_wait,
)
from gacha_simulator.core.param_descriptor import IntParam
from gacha_simulator.core.action import Action


@register_strategy('fixed_count', '固定次数',
    params=[IntParam('count', '抽卡次数', default=100, min_val=1)])
class FixedCountStrategy(Strategy):
    def __init__(self, count: int):
        self.count = count

    @classmethod
    def description(cls) -> str:
        return "抽指定次数后停止"

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import WaitAction, DrawAction
        if ctx.total_draws >= self.count:
            return WaitAction(duration=next_event_wait(ctx))
        if not ctx.banners:
            return WaitAction(duration=next_event_wait(ctx))
        return DrawAction(banner_id=ctx.banners[0].id)
