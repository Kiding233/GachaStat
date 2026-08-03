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
        # P61：等待下一个活动池开启。banner 维度不可用性由 gacha_service 层过滤，
        # 此处仅需返回固定等待（无具体 banner 目标，始终等待 86400s 由模拟层拆分为 WaitAction）。
        return WaitAction(duration=86400)
