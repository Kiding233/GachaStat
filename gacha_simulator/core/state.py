from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import copy
from .pool import Pool, CostOption


@dataclass
class GachaState:
    resources: Dict[str, float] = field(default_factory=dict)
    pity_counters: Dict[str, int] = field(default_factory=dict)
    real_time: float = 0.0
    total_actions: int = 0
    extra_state: Dict[str, Any] = field(default_factory=dict)

    def can_afford(self, cost) -> bool:
        if isinstance(cost, dict):
            return self._can_afford_option(cost)
        if isinstance(cost, list):
            return any(self._can_afford_option(opt) for opt in cost)
        return False

    def _can_afford_option(self, option: CostOption) -> bool:
        for resource, amount in option.items():
            if self.resources.get(resource, 0) < amount:
                return False
        return True

    def choose_cost_option(self, cost) -> Optional[CostOption]:
        if isinstance(cost, dict):
            if self._can_afford_option(cost):
                return cost
            return None
        if isinstance(cost, list):
            for option in cost:
                if self._can_afford_option(option):
                    return option
            return None
        return None

    def spend(self, cost) -> Optional[CostOption]:
        chosen = self.choose_cost_option(cost)
        if chosen is None:
            return None
        for resource, amount in chosen.items():
            if resource in self.resources:
                self.resources[resource] -= amount
                if self.resources[resource] < 0:
                    self.resources[resource] = 0
        return chosen

    def _choose_option_from(self, cost, resources: dict) -> Optional[CostOption]:
        """从给定资源快照中选择最优 cost option（不修改真实资源）。"""
        if isinstance(cost, dict):
            if all(resources.get(r, 0) >= a for r, a in cost.items()):
                return cost
            return None
        if isinstance(cost, list):
            for option in cost:
                if all(resources.get(r, 0) >= a for r, a in option.items()):
                    return option
            return None
        return None

    def can_afford_batch(self, cost, batch_size: int = 1) -> bool:
        """模拟 batch_size 次独立抽卡的费用选择。

        每次独立选择最优 cost option，资源快照逐次递减。
        支持 free_draw:1 > draw_resource:160 等 OR 优先级资源自动切换。

        batch_size=1 退化到 can_afford()。
        """
        if batch_size <= 1:
            return self.can_afford(cost)
        remaining = dict(self.resources)
        for _ in range(batch_size):
            option = self._choose_option_from(cost, remaining)
            if option is None:
                return False
            for res, amt in option.items():
                remaining[res] -= amt
        return True

    def gain(self, gains: Dict[str, float]) -> None:
        for resource, amount in gains.items():
            self.resources[resource] = self.resources.get(resource, 0) + amount

    def get_available_pools(self, pools: List[Pool]) -> List[Pool]:
        return [pool for pool in pools if pool.is_available_at(self.real_time)]

    def clone(self) -> 'GachaState':
        return GachaState(
            resources=self.resources.copy(),
            pity_counters=self.pity_counters.copy(),
            real_time=self.real_time,
            total_actions=self.total_actions,
            extra_state=copy.deepcopy(self.extra_state) if self.extra_state else {},
        )
