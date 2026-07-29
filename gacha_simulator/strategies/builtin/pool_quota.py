"""指定池配额策略——在指定池子抽指定数量后切换。"""
from __future__ import annotations

from typing import Dict, Optional

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.param_descriptor import PoolIntMapParam
from gacha_simulator.core.action import Action


@register_strategy('pool_quota', '指定池配额',
    params=[PoolIntMapParam('pool_quotas', '各池配额', default={})])
class PoolQuotaStrategy(Strategy):
    lookahead = None

    def __init__(self, pool_quotas: Optional[Dict[str, int]] = None):
        self.pool_quotas = pool_quotas or {}

    @classmethod
    def description(cls) -> str:
        return "指定池配额：在指定池子抽指定数量后切换"

    def _pool_needs_target(self, pool_id: str, ctx: StrategyContext) -> bool:
        for t in ctx.target_cards.targets:
            if pool_id in t.pool_ids and ctx.acquired.get(t.card_id, 0) < t.quantity_needed:
                return True
        return False

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction

        for t in ctx.target_cards.targets:
            if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                continue
            for pool in ctx.all_pools:
                if pool.is_exchange and pool.exchange_card_id == t.card_id:
                    if pool.is_available_at(ctx.state.real_time) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                        return DrawAction(pool_id=pool.id)

        for pool in ctx.current_pools:
            if pool.is_exchange or not ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                continue
            pid = pool.id
            quota = self.pool_quotas.get(pid)
            drawn = ctx.pool_draw_counts.get(pid, 0)
            if quota is None or drawn < quota:
                if self._pool_needs_target(pool.id, ctx):
                    return DrawAction(pool_id=pid)

        for pool in ctx.current_pools:
            if not pool.is_exchange and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                pid = pool.id
                quota = self.pool_quotas.get(pid)
                drawn = ctx.pool_draw_counts.get(pid, 0)
                if quota is None or drawn < quota:
                    return DrawAction(pool_id=pid)

        wait_time = 86400
        for pool in ctx.current_pools:
            if hasattr(pool, 'available_until') and pool.available_until and pool.available_until > ctx.state.real_time:
                wait_time = min(wait_time, pool.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
