"""按需追卡策略——优先兑换→按目标追卡→等待下一个池。"""
from __future__ import annotations

from typing import Dict, Optional

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.action import Action


@register_strategy('smart', '按需追卡')
class SmartStrategy(Strategy):
    lookahead = None

    def __init__(self):
        self._pool_to_targets: Dict[str, list] = {}
        self._last_target_cards_id: int = 0

    @classmethod
    def description(cls) -> str:
        return "按需追卡：优先兑换→按目标追卡→等待下一个池"

    def _ensure_pool_to_targets(self, ctx: StrategyContext):
        tc_id = id(ctx.target_cards)
        if tc_id != self._last_target_cards_id:
            self._pool_to_targets.clear()
            for t in ctx.target_cards.targets:
                for pid in t.pool_ids:
                    if pid not in self._pool_to_targets:
                        self._pool_to_targets[pid] = []
                    self._pool_to_targets[pid].append(t)
            self._last_target_cards_id = tc_id

    def _pool_needs_target(self, pool_id: str, ctx: StrategyContext) -> bool:
        self._ensure_pool_to_targets(ctx)
        for t in self._pool_to_targets.get(pool_id, []):
            ac_val = ctx.acquired.get(t.card_id, 0)
            if ac_val < t.quantity_needed:
                return True
        return False

    def _get_needed_card_exchange(self, ctx: StrategyContext) -> Optional[str]:
        for t in ctx.target_cards.targets:
            if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                continue
            for pool in ctx.all_pools:
                if pool.is_exchange and pool.exchange_card_id == t.card_id:
                    if pool.is_available_at(ctx.state.real_time) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                        return pool.id
        return None

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction

        exchange_pool_id = self._get_needed_card_exchange(ctx)
        if exchange_pool_id:
            return DrawAction(pool_id=exchange_pool_id)

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
