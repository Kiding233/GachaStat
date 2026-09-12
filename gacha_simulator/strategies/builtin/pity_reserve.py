"""保底预留策略——只在保底概率≥阈值时才抽卡。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy, next_event_wait,
)
from gacha_simulator.core.param_descriptor import FloatParam
from gacha_simulator.core.action import Action


@register_strategy('pity_reserve', '保底预留',
    params=[FloatParam('pity_threshold_pct', '保底概率阈值(%)', default=80.0, min_val=0.0, max_val=100.0)])
class PityReserveStrategy(Strategy):
    lookahead = None

    def __init__(self, pity_threshold_pct: float = 80.0):
        self.pity_threshold_pct = pity_threshold_pct / 100.0

    @classmethod
    def description(cls) -> str:
        return "保底预留：只在大保底概率≥阈值时才抽卡"

    def _pool_needs_target(self, banner_id: str, ctx: StrategyContext) -> bool:
        # P61（ISSUE-303/315）：匹配口径为 banner.id
        for t in ctx.target_cards.targets:
            if banner_id in t.pool_ids and ctx.acquired.get(t.card_id, 0) < t.quantity_needed:
                return True
        return False

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import DrawAction, WaitAction

        for t in ctx.target_cards.targets:
            if ctx.acquired.get(t.card_id, 0) >= t.quantity_needed:
                continue
            for banner in ctx.all_banners:
                pool = banner.active_pool
                if pool.is_exchange and pool.exchange_card_id == t.card_id:
                    if banner.is_available(ctx.state.real_time) and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                        return DrawAction(banner_id=banner.id)

        for banner in ctx.banners:
            pool = banner.active_pool
            if pool.is_exchange or not ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                continue
            if not self._pool_needs_target(banner.id, ctx):
                continue

            # P61（ISSUE-002）：get_pity_probabilities 改传全限定键（strategy.py 经 banners
            # 维度拆分定位 active_pool），不再传裸 pool.id（查询不到全限定 spec、保底阈值退化基础概率）
            qualified_key = f"{banner.id}.{banner.active_pool_id}"
            pool_probs = ctx.get_pity_probabilities(qualified_key)
            if pool_probs:
                ssr_prob = sum(p for cid, p in pool_probs.items() if cid in ctx.ssr_ids)
                if ssr_prob >= self.pity_threshold_pct:
                    return DrawAction(banner_id=banner.id)
            else:
                return DrawAction(banner_id=banner.id)

        return WaitAction(duration=next_event_wait(ctx))
