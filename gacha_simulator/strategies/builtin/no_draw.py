"""不抽卡基线策略——始终等待，用于计算不抽卡的资源基线水平。"""
from __future__ import annotations

from gacha_simulator.core.strategy import (
    Strategy, StrategyContext, register_strategy,
)
from gacha_simulator.core.action import Action


@register_strategy('no_draw', '不抽卡基线', internal=True)
class NoDrawStrategy(Strategy):
    """不抽卡策略：始终等待，一次都不抽。用于计算不抽卡基线资源水平。"""

    @classmethod
    def description(cls) -> str:
        return "不抽卡：始终等待，用于计算基线资源水平"

    def select_action(self, ctx: StrategyContext) -> Action:
        from gacha_simulator.core.action import WaitAction
        # P61（§3.4 迁移方案 / ISSUE-001）：取最近关闭时刻（banner.available_until -
        # real_time，秒减秒），等待到最近关闭时刻推进 real_time。不抽卡基线：始终等待，
        # 用于计算不抽卡资源基线。
        wait_time = 86400
        for banner in ctx.banners:
            if banner.available_until and banner.available_until > ctx.state.real_time:
                wait_time = min(wait_time, banner.available_until - ctx.state.real_time)
        return WaitAction(duration=wait_time)
