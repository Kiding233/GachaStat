"""P64 叶子原语层（§3.1.6）——保底引擎的最底层构件，仅依赖标准库。

本模块由 S1a 自 `core/pity.py` 迁出，`pity.py` 保留 re-export，故既有导入路径
（`from gacha_simulator.core.pity import PityState` 等）与 `core/__init__.py` 的导出
一律不变——**语义与接口完全保留，仅换存放文件**。

依赖方向（§3.1.6，强制）：本模块只依赖标准库；实现层
（`pity_tracker.py` / `pity_modifier.py`）单向依赖本模块、不 import `pity.py`；
编排层 `pity.py` 依赖本模块 + 两个实现层模块。三个 `_*_TYPES` 集合常量放在本层，
是因为 §3.1.4 骨架的 `Pity` 不继承 `CounterBasedBehavior`，裸名引用它们否则
`NameError`。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── P60 新增：DrawInfo (frozen) + PityContext (可变载体) ──

@dataclass(frozen=True)
class DrawInfo:
    """抽卡上下文中不可变的部分——本次抽卡的静态事实。"""
    pool_id: str
    pool_instance_id: str
    reward_id: str
    reward_rarity: str
    is_featured: bool
    scope_cards: Mapping[str, tuple] = field(default_factory=dict)
    featured_cards: Mapping[str, tuple] = field(default_factory=dict)
    scope_slots: Mapping[str, tuple] = field(default_factory=dict)
    featured_slots: Mapping[str, tuple] = field(default_factory=dict)
    card_to_slot: Mapping[str, str] = field(default_factory=dict)
    base_probabilities: Mapping[str, float] = field(default_factory=dict)
    rarity_rank: Mapping[str, int] = field(default_factory=dict)


@dataclass
class PityContext:
    """管道中流转的可变载体。"""
    draw: DrawInfo
    current: Dict[str, float]
    state: 'PityState'


# ── P60 新增：Counter / Flag 微抽象 ──

@dataclass
class Counter:
    """PityState 计数器遥控器——记住地址，封装操作。"""
    _state: 'PityState'
    _name: str
    _key: str = "counter"

    def incr(self, delta: int = 1) -> int:
        return self._state.incr(self._name, self._key, delta)

    def reset(self) -> None:
        self._state.set(self._name, self._key, 0)

    def value(self) -> int:
        return self._state.get(self._name, self._key, 0)

    def reached(self, threshold: int) -> bool:
        return self.value() >= threshold


@dataclass
class Flag:
    """PityState 布尔标志遥控器。"""
    _state: 'PityState'
    _name: str
    _key: str

    def set(self) -> None:
        self._state.set(self._name, self._key, True)

    def clear(self) -> None:
        self._state.set(self._name, self._key, False)

    def is_set(self) -> bool:
        return self._state.get(self._name, self._key, False)


# ── P60 新增：跨 type 生命周期参数 ──

@dataclass(frozen=True)
class LifecycleConfig:
    """跨 type 共享的生命周期参数。P56 扩展 deactivate_on_early_hit / depends_on。

    frozen=True：纵深防御——阻止运行时意外修改。
    """
    deactivate_on_early_hit: bool = False         # P56 扩展
    depends_on: Optional[str] = None              # P56 扩展


class PityState:
    """三层嵌套 namespace 容器——每个 behavior 通过自身 name 存取任意类型数据。"""

    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}

    def get(self, name: str, key: str, default=None):
        """读取 behavior name 下 key 的值。"""
        return self.data.get(name, {}).get(key, default)

    def set(self, name: str, key: str, value):
        """写入 behavior name 下 key 的值。"""
        self.data.setdefault(name, {})[key] = value

    def incr(self, name: str, key: str, delta=1) -> int:
        """递增 behavior name 下 key 的计数器值。"""
        v = self.get(name, key, 0) + delta
        self.set(name, key, v)
        return v

    def clone(self) -> 'PityState':
        ps = PityState()
        ps.data = {name: dict(ns) for name, ns in self.data.items()}
        return ps

    def to_dict(self) -> Dict[str, Any]:
        return {"data": {name: dict(ns) for name, ns in self.data.items()}}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PityState':
        ps = cls()
        if "data" in d:
            # 防御性复制——确保 from_dict() 返回的 PityState 与输入 dict 完全解耦
            ps.data = {name: dict(ns) for name, ns in d["data"].items()}
        # P81 B9：P60 之前的 {"counters": {...}} 旧序列化格式的自动升级分支已删除
        # （其生产者只有测试；真实数据均为 to_dict() 产出的 {"data": {...}} 新格式）。
        return ps

# ── btype 分类集合（P64 S1a：自 CounterBasedBehavior 的类属性升为模块级常量）──
# 消费面：`Pity` 骨架（§3.1.4，不继承 CounterBasedBehavior 故须裸名可取）、
# `CounterBasedBehavior`（保留为同对象别名）、`config_toml` 的同名拷贝
# （由 tests/core/test_pity_config_toml.py::TestDuplicatedConstants 钉住相等）。
_SOFT_TYPES = frozenset({'soft_interval', 'soft_additive', 'soft_step'})
_HARD_TYPES = frozenset({'hard'})
# ISSUE-105：`rotating_inverse`（G1 幻塔连中后必歪）是**事件驱动型**，故本集合的
# 内容须追加它，不是原样迁移。落地先于该类型的注册（S6a），提前列出无副作用。
_EVENT_DRIVEN_TYPES = frozenset({'rotating', 'targeted', 'targeted_soft',
                                 'rotating_cr', 'rotating_cr_soft', 'rotating_soft',
                                 'rotating_inverse'})

__all__ = [
    'Counter', 'Flag', 'DrawInfo', 'PityContext', 'LifecycleConfig', 'PityState',
    '_SOFT_TYPES', '_HARD_TYPES', '_EVENT_DRIVEN_TYPES',
]
