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

    def _pool_needs_target(self, banner_id: str, ctx: StrategyContext) -> bool:
        # P61（ISSUE-303/315）：匹配口径为 banner.id
        for t in ctx.target_cards.targets:
            if banner_id in t.pool_ids and ctx.acquired.get(t.card_id, 0) < t.quantity_needed:
                return True
        return False

    def _qualified_key(self, banner) -> str:
        # P61（ISSUE-327）：pool_quotas 参数键全限定 {banner_id}.{pool_id}——多 Banner 同名 main 配额不串池
        return f"{banner.id}.{banner.active_pool_id}"

    def _quota_for(self, banner) -> Optional[int]:
        """配额查询——全限定键优先，单 Banner 单池场景裸 pool id 兼容回退（ISSUE-327）。

        全限定键 {banner_id}.{pool_id} 命中（多 Banner 同名池配额不串池）；未配置时
        回退裸 pool id（如 'main'），兼容用户旧配置（{main: 100}）。多 Banner 场景
        用户须写全限定键——裸键回退仅作单 Banner 便利。
        """
        quota = self.pool_quotas.get(self._qualified_key(banner))
        if quota is None:
            quota = self.pool_quotas.get(banner.active_pool_id)
        return quota

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
            quota = self._quota_for(banner)
            # P61（ISSUE-002）：配额抽数改读 banner.pool_draws（裸池字典键），
            # 不再用 ctx.pool_draw_counts（其键已全限定化、裸键查询恒 0）
            drawn = banner.pool_draws.get(banner.active_pool_id, 0)
            if quota is None or drawn < quota:
                if self._pool_needs_target(banner.id, ctx):
                    return DrawAction(banner_id=banner.id)

        for banner in ctx.banners:
            pool = banner.active_pool
            if not pool.is_exchange and ctx.state.can_afford_batch(pool.cost, pool.batch_size):
                quota = self._quota_for(banner)
                drawn = banner.pool_draws.get(banner.active_pool_id, 0)
                if quota is None or drawn < quota:
                    return DrawAction(banner_id=banner.id)

        wait_time = 86400
        for banner in ctx.banners:
            if banner.available_until and banner.available_until > ctx.state.real_time:
                wait_time = min(wait_time, banner.available_until - ctx.state.real_time)
        if wait_time <= 0:
            wait_time = 3600
        return WaitAction(duration=wait_time)
