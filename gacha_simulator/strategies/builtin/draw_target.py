"""目标池抽卡策略——最差影响分析专用：从目标池抽卡。"""
from __future__ import annotations

from typing import List, Optional, Set

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.param_descriptor import StringListParam, StrParam
from gacha_simulator.core.action import DrawAction, WaitAction


@register_strategy('draw_target', '目标池抽卡',
    params=[
        StringListParam('target_card_ids', '目标卡ID列表', default=[]),
        StrParam('pool_id', '目标池ID', default=''),
    ],
    internal=True)
class DrawTargetStrategy(Strategy):
    """最差影响分析专用：从目标池抽卡。"""

    lookahead = None

    def __init__(self, target_card_ids: Optional[List[str]] = None, pool_id: str = ''):
        self.target_card_ids: Set[str] = set(target_card_ids or [])
        self.pool_id = pool_id

    @classmethod
    def description(cls) -> str:
        return "最差影响分析：从目标池抽卡"

    def select_action(self, ctx: StrategyContext):
        for pool in ctx.current_pools:
            if (not self.pool_id or pool.id == self.pool_id) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                return DrawAction(pool_id=pool.id)

        wait_time = 86400
        for pool in ctx.current_pools:
            if (pool.available_until is not None
                    and pool.available_until > ctx.state.real_time):
                wait_time = min(wait_time, pool.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
