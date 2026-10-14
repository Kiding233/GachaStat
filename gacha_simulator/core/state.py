from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import copy
from .pool import CostOption
from .overflow import OverflowBand, match_overflow_bands


class SimView:
    """模拟级状态的只读视图（P64 S9-2 / §3.10.2）：保底侧读玩家持有的唯一入口。

    **只暴露 `owns` 一个源**（`pity_modifier.KNOWN_SIM_SOURCES` 即它）：`balance()`
    已于 2026-10-06 删除（全库零使用，§3.10.2 的「删除的符号」段）。持有的是
    `GachaState` 的**活引用**（O(1) 包装，不复制任何账本）：`owns` 每次现读，故同一
    抽内 `add_card` 之后的读取反映最新持有。

    **与 `StateView` 的分工**（§3.10.2 末段）：`StateView`（`core/pity.py`）限定
    **单个保底命名空间**的状态视野、关闭跨保底读；本类暴露**模拟级只读事实**
    （玩家持有），二者不可互相替代。
    """

    __slots__ = ('_state',)

    def __init__(self, state: 'GachaState') -> None:
        self._state = state

    def owns(self, card_id: str) -> int:
        """该卡持有张数（`total_holding` 口径，**含初始持有**，ISSUE-009）；0 即未拥有。"""
        return self._state.total_holding(card_id)


@dataclass
class GachaState:
    resources: Dict[str, float] = field(default_factory=dict)
    acquired: Dict[str, int] = field(default_factory=dict)          # ← P60：卡牌持有一等公民
    acquired_by_path: Dict[str, Dict[str, int]] = field(default_factory=dict)  # ← P63：路径切片
    real_time: float = 0.0
    total_actions: int = 0
    extra_state: Dict[str, Any] = field(default_factory=dict)
    # P64 S9-2（§四 core/state.py 行）：本场模拟的**初始持有**：原为
    # `GachaService.run_simulation` 的局部变量与四处传参，现升为 state 字段，
    # 成为 `total_holding` / `SimView.owns` 的**单一真相源**（2026-09-29 定稿）。
    initial_counts: Dict[str, int] = field(default_factory=dict)

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

    def clone(self) -> 'GachaState':
        return GachaState(
            resources=self.resources.copy(),
            acquired=self.acquired.copy(),                           # ← P60
            acquired_by_path={cid: dict(paths) for cid, paths in self.acquired_by_path.items()},  # ← P63
            real_time=self.real_time,
            total_actions=self.total_actions,
            extra_state=copy.deepcopy(self.extra_state) if self.extra_state else {},
            initial_counts=self.initial_counts.copy(),              # ← P64 S9-2
        )

    # ── P60 新增：卡牌持有操作 ──

    def add_card(
        self,
        card_id: str,
        path: str = "unknown",
        overflow_bands: Optional[List[OverflowBand]] = None,
    ) -> Dict[str, float]:
        """获得一张卡。返回本次触发的溢出资源。

        Args:
            card_id: 卡片 ID。
            path: 获得路径——"draw" | "milestone_gift" | "exchange" | "event_gift"。
            overflow_bands: 该卡的分段表（已解析），None 则跳过溢出计算。

        Returns:
            本次触发的溢出资源 dict；无规则时返回 {}。

        **P64 S9-2 变更**：`initial_counts` 形参**移除**（原「传了 bands 必须传
        counts，否则 ValueError」的守卫同批删除）：初始持有改读 `self.initial_counts`
        字段。该守卫的触发条件已不存在（初始持有不再由调用方传入），保留它只会让
        「忘记传参」重新变成一次静默的少算：原形态下调用方漏传即 ValueError（显式），
        而形参移除后漏设字段的形态是**计数偏小**，故单一真相源是唯一的收敛方向。
        """
        self.acquired[card_id] = self.acquired.get(card_id, 0) + 1

        # 路径切片记录
        if card_id not in self.acquired_by_path:
            self.acquired_by_path[card_id] = {}
        self.acquired_by_path[card_id][path] = \
            self.acquired_by_path[card_id].get(path, 0) + 1

        # 溢出资源计算（初始持有取自 state 字段，单一真相源）
        if overflow_bands:
            return match_overflow_bands(overflow_bands, self.total_holding(card_id))

        return {}

    def get_card_count(self, card_id: str) -> int:
        """模拟中获得的该卡数量（不含初始持有）。"""
        return self.acquired.get(card_id, 0)

    def total_holding(self, card_id: str) -> int:
        """含初始持有的总数量（`self.initial_counts` 与 `self.acquired` 同为一个 state
        的字段，口径一致由构造保证，ISSUE-009）。"""
        return self.initial_counts.get(card_id, 0) + self.acquired.get(card_id, 0)

    def sim_view(self) -> SimView:
        """构造本 state 的 `SimView`（P64 S9-2 / §3.10.2）。

        两条送达通道（`Banner.draw` 与 `StrategyContext.get_pity_probabilities`）
        **各自就地调本方法**，不新增形参、不经服务层透传：材料全在 state 上，
        故视图由 state 自产（O(1)）。
        """
        return SimView(self)
