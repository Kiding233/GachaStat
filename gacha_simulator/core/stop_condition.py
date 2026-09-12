from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from .param_descriptor import (
    FloatParam, IntParam, StrParam, ListParam, DictParam,
)

if TYPE_CHECKING:
    from .state import GachaState
    from .info_vector import InfoVector
    from ..service.gacha_service import SimulationStats


class StopCondition(ABC):
    @abstractmethod
    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        pass

    @abstractmethod
    def description(self) -> str:
        pass


class FixedActionCountCondition(StopCondition):
    def __init__(self, max_actions: int):
        self.max_actions = max_actions

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        if stats:
            return stats.total_actions >= self.max_actions
        return len(history) >= self.max_actions

    def description(self) -> str:
        return f"抽满 {self.max_actions} 次后停止"


class ResourceThresholdCondition(StopCondition):
    def __init__(self, resource: str, threshold: float, operator: str = '<='):
        self.resource = resource
        self.threshold = threshold
        self.operator = operator

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        current = state.resources.get(self.resource, 0)
        if self.operator == '<=':
            return current <= self.threshold
        elif self.operator == '>=':
            return current >= self.threshold
        elif self.operator == '==':
            return current == self.threshold
        return False

    def description(self) -> str:
        return f"资源 {self.resource} {self.operator} {self.threshold}"


class TargetAcquiredCondition(StopCondition):
    def __init__(self, target_id: str, quantity: int = 1):
        self.target_id = target_id
        self.quantity = quantity

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        # P60：优先从 state.acquired 直读（单一真相源）
        count = state.get_card_count(self.target_id)
        if count <= 0:  # 回退——state.acquired 可能为 0（兼容旧调用路径）
            count = sum(1 for iv in history if iv.card_id == self.target_id)
        return count >= self.quantity

    def description(self) -> str:
        return f"获得 {self.quantity} 张 {self.target_id}"


class LastDrawCardCondition(StopCondition):
    def __init__(self, card_id: str):
        self.card_id = card_id

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        if stats:
            return stats.last_draw_card_id == self.card_id
        if not history:
            return False
        return history[-1].card_id == self.card_id

    def description(self) -> str:
        return f"抽到 {self.card_id} 后停止"


class TimeLimitCondition(StopCondition):
    def __init__(self, max_time: float):
        self.max_time = max_time

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        return state.real_time >= self.max_time

    def description(self) -> str:
        return f"现实时间达到 {self.max_time} 秒"


class AllPoolsEndCondition(StopCondition):
    def __init__(self, end_time: float):
        self.end_time = end_time

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        return state.real_time >= self.end_time

    def description(self) -> str:
        return "所有池结束"


class ConsecutivePoolTargetCondition(StopCondition):
    def __init__(self, pool_schedules: list, pool_targets: dict,
                 resource_name: str = 'draw_resource', end_time: float = None):
        self.pool_schedules = sorted(pool_schedules, key=lambda x: x[2])
        self.pool_targets = pool_targets
        self.resource_name = resource_name
        self.end_time = end_time

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        if state.resources.get(self.resource_name, 0) <= 0:
            return True
        if self.end_time is not None and state.real_time >= self.end_time:
            return True
        if stats:
            for pool_id, _start, end in self.pool_schedules:
                if state.real_time < end:
                    break
                target_card = self.pool_targets.get(pool_id)
                if target_card and stats.card_counts.get(target_card, 0) < 1:
                    return True
        return False

    def description(self) -> str:
        return "资源耗尽或连续池目标未达成"


class CompositeStopCondition(StopCondition):
    def __init__(self, conditions: list, mode: str = 'any'):
        self.conditions = conditions
        self.mode = mode

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        if self.mode == 'any':
            return any(c.check(state, history, stats) for c in self.conditions)
        else:
            return all(c.check(state, history, stats) for c in self.conditions)

    def description(self) -> str:
        ops = ' 或 ' if self.mode == 'any' else ' 且 '
        return ops.join(c.description() for c in self.conditions)


class NotCondition(StopCondition):
    """否定节点——对单个子条件取反（P79 5.6）。

    由 ``mode='not'`` 判别，**不是** registry 的 ``type``——``not`` 是表达式的
    运算符，不需要往 STOP_CONDITION_REGISTRY 注册。
    """

    def __init__(self, child: StopCondition):
        self.child = child

    def check(self, state: 'GachaState', history: List['InfoVector'],
              stats: Optional['SimulationStats'] = None) -> bool:
        return not self.child.check(state, history, stats)

    def description(self) -> str:
        # StopCondition.description 是抽象方法，且 CompositeStopCondition.description
        # 会逐个调用子节点——漏实现会在实例化或 GUI 摘要列渲染时抛 TypeError。
        return f"非({self.child.description()})"


STOP_CONDITION_REGISTRY = {
    'all_pools_end': {
        'display_name': '所有池结束',
        'description': '所有池子到期后停止',
        'class': AllPoolsEndCondition,
        'params': [
            FloatParam('end_time', '结束时间(秒)', default=0.0),
        ],
    },
    'fixed_action_count': {
        'display_name': '固定次数',
        'description': '抽满指定次数后停止',
        'class': FixedActionCountCondition,
        'params': [
            IntParam('max_actions', '最大操作数', default=100),
        ],
    },
    'resource_threshold': {
        'display_name': '资源阈值',
        'description': '资源达到阈值时停止',
        'class': ResourceThresholdCondition,
        'params': [
            StrParam('resource', '资源名', default='draw_resource'),
            FloatParam('threshold', '阈值', default=0.0),
            StrParam('operator', '比较运算符', default='<='),
        ],
    },
    'target_acquired': {
        'display_name': '目标获得',
        'description': '获得指定目标卡后停止',
        'class': TargetAcquiredCondition,
        'params': [
            StrParam('target_id', '目标卡ID', default=''),
            IntParam('quantity', '数量', default=1),
        ],
    },
    'last_draw_card': {
        'display_name': '抽到即停',
        'description': '最后一次抽到指定卡时停止',
        'class': LastDrawCardCondition,
        'params': [
            StrParam('card_id', '卡牌ID', default=''),
        ],
    },
    'time_limit': {
        'display_name': '时间限制',
        'description': '模拟时间达到限制后停止',
        'class': TimeLimitCondition,
        'params': [
            FloatParam('max_time', '最大时间(秒)', default=86400.0),
        ],
    },
    'consecutive_pool_target': {
        'display_name': '连续池目标',
        'description': '资源耗尽或连续池目标未达成时停止',
        'class': ConsecutivePoolTargetCondition,
        'params': [
            ListParam('pool_schedules', '池时间表'),
            DictParam('pool_targets', '池目标卡'),
            StrParam('resource_name', '资源名', default='draw_resource'),
            FloatParam('end_time', '最大时间(秒)', default=0.0),
        ],
        'internal': True,
    },
}


def create_stop_condition(tree: Optional[Dict[str, Any]]) -> Optional[StopCondition]:
    """从递归条件树构造停止条件对象（P79 5.6）。

    ``tree`` 为 ``None`` / 空字典时返回 ``None``——语义是「空树 = 仅引擎硬边界
    收口」，与接线前的行为等价（见 5.6「空树规范化」）。

    节点三形态互斥且穷尽，按 **「``conditions`` → ``mode`` → ``type``」** 分派：

    1. 复合节点——``mode ∈ {"any", "all"}`` + ``conditions: [...]``
    2. 否定节点——``mode = "not"`` + ``conditions: [恰好 1 项]``
    3. 叶子节点——``type = <registry key>`` + 平铺参数（**无 ``conditions``**）

    ``conditions`` 在场时一律不查 registry——判别键是「是否出现 conditions」，
    故未知 ``type`` 只在叶子形态下才抛 ``ValueError``。
    """
    if not tree:
        return None
    return _build_stop_condition_node(tree)


def _build_stop_condition_node(node: Dict[str, Any]) -> StopCondition:
    """树分派的单节点构造（递归）。"""
    if not isinstance(node, dict):
        raise ValueError(
            f"停止条件节点须为字典，收到 {type(node).__name__}: {node!r}")

    children = node.get('conditions')
    if children is not None:
        # ── 复合 / 否定节点 ──
        if not isinstance(children, list):
            raise ValueError(
                f"conditions 须为数组，收到 {type(children).__name__}: {children!r}")
        mode = node.get('mode')
        if mode == 'not':
            # 否定节点恰带一个子节点：多子节点时直接取 children[0] 会静默丢弃其余，
            # 而 conditions 在场即不查 registry、不会触发 ValueError，故须显式校验。
            if len(children) != 1:
                raise ValueError(
                    f"否定节点（mode='not'）恰带一个子节点，当前 {len(children)} 个")
            return NotCondition(_build_stop_condition_node(children[0]))
        if mode in ('any', 'all'):
            return CompositeStopCondition(
                [_build_stop_condition_node(c) for c in children], mode)
        raise ValueError(
            f"复合节点的 mode 须为 'any' / 'all' / 'not'，收到 {mode!r}")

    # ── 叶子节点 ──
    node_type = node.get('type')
    if node_type is None:
        raise ValueError(f"叶子节点缺少 'type' 键: {node!r}")
    entry = STOP_CONDITION_REGISTRY.get(node_type)
    if entry is None:
        raise ValueError(f"Unknown stop condition: {node_type!r}. "
                         f"Available: {list(STOP_CONDITION_REGISTRY.keys())}")
    param_defs = entry.get('params', [])
    # 叶子键白名单过滤（5.6）：构造参数只取「registry 声明键 ∩ 叶子表键」——
    # `type`（以及 TOML 表中可能残留的 `mode`）不是构造参数，整体透传会抛
    # TypeError: __init__() got an unexpected keyword argument 'type'。
    declared = {pdesc.key for pdesc in param_defs}
    resolved = {k: v for k, v in node.items() if k in declared}
    for pdesc in param_defs:
        resolved.setdefault(pdesc.key, pdesc.default)
    return entry['class'](**resolved)


def stop_condition_type_to_key(display_name: str) -> str:
    for key, entry in STOP_CONDITION_REGISTRY.items():
        if entry['display_name'] == display_name:
            return key
    return 'all_pools_end'


def stop_condition_key_to_type(key: str) -> str:
    entry = STOP_CONDITION_REGISTRY.get(key)
    return entry['display_name'] if entry else '所有池结束'
