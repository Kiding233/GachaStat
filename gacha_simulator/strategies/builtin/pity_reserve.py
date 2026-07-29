"""保底预留策略——只在保底概率≥阈值时才抽卡。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
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
            if not self._pool_needs_target(pool.id, ctx):
                continue

            pool_probs = ctx.get_pity_probabilities(pool.id)
            if pool_probs:
                ssr_prob = sum(p for cid, p in pool_probs.items() if cid in ctx.ssr_ids)
                if ssr_prob >= self.pity_threshold_pct:
                    return DrawAction(pool_id=pool.id)
            else:
                return DrawAction(pool_id=pool.id)

        wait_time = 86400
        for pool in ctx.current_pools:
            if hasattr(pool, 'available_until') and pool.available_until and pool.available_until > ctx.state.real_time:
                wait_time = min(wait_time, pool.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
