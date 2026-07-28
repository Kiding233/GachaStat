from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import copy
from .pool import Pool, CostOption
from .overflow import OverflowBand, match_overflow_bands


@dataclass
class GachaState:
    resources: Dict[str, float] = field(default_factory=dict)
    acquired: Dict[str, int] = field(default_factory=dict)          # ← P60：卡牌持有一等公民
    acquired_by_path: Dict[str, Dict[str, int]] = field(default_factory=dict)  # ← P63：路径切片
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
            acquired=self.acquired.copy(),                           # ← P60
            acquired_by_path={cid: dict(paths) for cid, paths in self.acquired_by_path.items()},  # ← P63
            real_time=self.real_time,
            total_actions=self.total_actions,
            extra_state=copy.deepcopy(self.extra_state) if self.extra_state else {},
        )

    # ── P60 新增：卡牌持有操作 ──

    def add_card(
        self,
        card_id: str,
        path: str = "unknown",
        overflow_bands: Optional[List[OverflowBand]] = None,
        initial_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, float]:
        """获得一张卡。返回本次触发的溢出资源。

        Args:
            card_id: 卡片 ID。
            path: 获得路径——"draw" | "milestone_gift" | "exchange" | "event_gift"。
            overflow_bands: 该卡的分段表（已解析），None 则跳过溢出计算。
            initial_counts: 初始持有数映射（用于正确计算 total_holding）。
                            当 overflow_bands 非 None 时必须传入。

        Returns:
            本次触发的溢出资源 dict；无规则时返回 {}。
        """
        # 防御性校验：传了 bands 就必须传 initial_counts
        if overflow_bands is not None and initial_counts is None:
            raise ValueError(
                f"add_card('{card_id}'): 传入了 overflow_bands 但未传入 initial_counts——"
                f"无法正确计算 total_holding 定位分段表区间"
            )

        self.acquired[card_id] = self.acquired.get(card_id, 0) + 1

        # 路径切片记录
        if card_id not in self.acquired_by_path:
            self.acquired_by_path[card_id] = {}
        self.acquired_by_path[card_id][path] = \
            self.acquired_by_path[card_id].get(path, 0) + 1

        # 溢出资源计算
        if overflow_bands:
            total = initial_counts.get(card_id, 0) + self.acquired[card_id]
            return match_overflow_bands(overflow_bands, total)

        return {}

    def get_card_count(self, card_id: str) -> int:
        """模拟中获得的该卡数量（不含初始持有）。"""
        return self.acquired.get(card_id, 0)

    def total_holding(self, card_id: str, initial_counts: Dict[str, int]) -> int:
        """含初始持有的总数量。"""
        return initial_counts.get(card_id, 0) + self.acquired.get(card_id, 0)
