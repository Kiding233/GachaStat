"""目标即停策略——抽到当期up/目标卡就停止。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.param_descriptor import BoolParam
from gacha_simulator.core.action import Action


@register_strategy('stop_on_target', '目标即停',
    params=[
        BoolParam('stop_on_featured', '抽到up即停', default=True),
        BoolParam('stop_on_any_target', '抽到任意目标即停', default=False),
    ])
class StopOnTargetStrategy(Strategy):
    lookahead = None

    def __init__(self, stop_on_featured: bool = True, stop_on_any_target: bool = False):
        self.stop_on_featured = stop_on_featured
        self.stop_on_any_target = stop_on_any_target

    @classmethod
    def description(cls) -> str:
        return "目标即停：抽到当期up/目标卡就停止"

    def _pool_needs_target(self, pool_id: str, ctx: StrategyContext) -> bool:
        for t in ctx.target_cards.targets:
            if pool_id in t.pool_ids and ctx.acquired.get(t.card_id, 0) < t.quantity_needed:
                return True
        return False

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction

        if self.stop_on_featured and ctx.last_draw_pity_triggered:
            return WaitAction(duration=0)
        if self.stop_on_any_target:
            for t in ctx.target_cards.targets:
                if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                    return WaitAction(duration=0)

        for t in ctx.target_cards.targets:
            if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                continue
            for pool in ctx.all_pools:
                if pool.is_exchange and pool.exchange_card_id == t.card_id:
                    if pool.is_available_at(ctx.state.real_time) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                        return DrawAction(pool_id=pool.id)

        for pool in ctx.current_pools:
            if not pool.is_exchange and self._pool_needs_target(pool.id, ctx) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                return DrawAction(pool_id=pool.id)

        wait_time = 86400
        for pool in ctx.current_pools:
            if hasattr(pool, 'available_until') and pool.available_until and pool.available_until > ctx.state.real_time:
                wait_time = min(wait_time, pool.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
