"""按需追卡策略——优先兑换→按目标追卡→等待下一个池。"""
from __future__ import annotations

from typing import Dict, Optional

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy, next_event_wait,
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

    def _pool_needs_target(self, banner_id: str, ctx: StrategyContext) -> bool:
        # P61（ISSUE-303/315）：匹配口径为 banner.id（TargetCard.pool_ids 钉死为 banner 级键）
        self._ensure_pool_to_targets(ctx)
        for t in self._pool_to_targets.get(banner_id, []):
            ac_val = ctx.acquired.get(t.card_id, 0)
            if ac_val < t.quantity_needed:
                return True
        return False

    def _get_needed_card_exchange(self, ctx: StrategyContext) -> Optional[str]:
        for t in ctx.target_cards.targets:
            if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                continue
            for banner in ctx.all_banners:
                pool = banner.active_pool
                if pool.is_exchange and pool.exchange_card_id == t.card_id:
                    if banner.is_available(ctx.state.real_time) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                        return banner.id
        return None

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction

        exchange_banner_id = self._get_needed_card_exchange(ctx)
        if exchange_banner_id:
            return DrawAction(banner_id=exchange_banner_id)

        for banner in ctx.banners:
            pool = banner.active_pool
            if not pool.is_exchange and self._pool_needs_target(banner.id, ctx) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                return DrawAction(banner_id=banner.id)

        return WaitAction(duration=next_event_wait(ctx))
