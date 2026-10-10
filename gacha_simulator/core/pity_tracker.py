"""P64 实现层——Tracker 家族（§3.1.1）。

Tracker 是纯函数式的状态追踪器：`(State, Event) -> State`。事件 = `PityContext`
（含 `DrawInfo.reward_rarity` / `is_featured` / `reward_id` 与 `PityState`）。每个
Tracker 只读写 `PityState` 中自己声明的键。

**依赖方向（§3.1.6，强制）**：本模块**单向**依赖 `pity_primitives`，**不 import
`pity.py`**——`pity.py` 反向依赖本模块（Pity 骨架、preset 工厂、registry 条目），
双向模块级 import 会构成循环导入。

**协议成员（§3.1.1，强制）**：`rebind` / `advance` / `prepare` / `commit` /
`did_reset` / `state_keys()` / `namespace`。前五个由 `Pity`（§3.1.4）按 N1 相位与
M4 语义调用，故**方法必须存在、不得省略**（无状态零件写空实现）；`state_keys()`
是 §3.12 / §3.13 与 S10-2 的唯一比对集输入；`namespace` 是 §3.10.3 两级 view 分配
的唯一输入。
"""

from typing import Optional

from .pity_primitives import Counter, PityContext, PityState

__all__ = ['Tracker', 'CounterTracker']


class Tracker:
    """Tracker 协议（§3.1.1）——六个契约成员，全部给出「无状态零件」的默认实现。

    默认实现即协议对 no-op 零件的定义：`rebind` / `advance` / `prepare` / `commit`
    空实现、`did_reset` 恒 False、`state_keys()` 返回 `()`、`namespace` 为 None。
    子类只覆写自己真正承担的相位。
    """

    #: 命名空间声明面（ISSUE-407）：None = 不做命名空间切换，`Pity` 传默认 view；
    #: `'<ns>'` = 本零件声明独立命名空间，`Pity` 传 `StateView(state, part.namespace)`。
    namespace: Optional[str] = None

    def rebind(self, state: PityState, name: str) -> None:
        """P75 纪律：把本 Tracker 内部的 `Counter` / `Flag` 重绑到 per-call `state`。

        **纯重定向、不复制旧值**——初始值完全由 per-call state（阶段 3 完整快照）
        承载。`Pity._rebind_state` 对其**无条件**调用，故方法必须存在；无自身状态
        键的零件可继承本空实现，但不得省略。
        """
        pass

    def advance(self, ctx: PityContext, state: PityState, name: str,
                readonly: bool) -> None:
        """N1 首段——`Pity.before_draw` 首段调用。

        计数型 Tracker（`CounterTracker`）：`readonly=True` 只读不写，否则
        `counter += 1`。非计数型：no-op。
        """
        pass

    def prepare(self, ctx: PityContext, state: PityState, name: str,
                readonly: bool) -> None:
        """N1 中段——`Pity.before_draw` 内、`advance` 之后、本保底 Modifier 链之前。

        供「抽前需要读 state 并消费随机源」的零件使用（`StreakTracker` 在此掷骰，
        裁决 6B′）。`CounterTracker` 为 no-op。
        """
        pass

    def commit(self, ctx: PityContext, state: PityState, name: str,
               skip_reset: bool = False) -> None:
        """N1 末段——`Pity.after_draw` 调用。

        `skip_reset=True` 是 `deactivate_on_early_hit` 的例外通道：Lifecycle 判定
        本次退役时，重置动作**同序判定、退役则跳过重置**（旧
        `CounterBasedBehavior.after_draw` 在 `_on_reset()` 返回 True 时提前 return
        即此语义，实测第 5 抽命中后 counter 仍为 5）。
        """
        pass

    def did_reset(self, ctx: PityContext, state: PityState, name: str) -> bool:
        """M4 统一语义——「本次抽卡是否让本保底回到初始状态」。

        `Pity.did_fire = any(tr.did_reset(...))`，供 `PityEngine.after_draw` 的
        `depends_on` 激活传播与 `Pity.after_draw` 的 `Lifecycle.should_deactivate`
        两处共用，不得各写一套。
        """
        return False

    def state_keys(self) -> tuple:
        """声明键集（ISSUE-501）——本 Tracker **写入**的 `PityState` 键名。

        只读常量、由构造形参决定、不依赖 state，故可在构造期直接取用（不需要
        `rebind`）。汇总点只有 `Pity.__init__` 的 `_declared_keys` 一处。
        """
        return ()


class CounterTracker(Tracker):
    """计数型 Tracker——每抽 +1，出金按 `reset_on` 重置。

    | 形参 | 语义 | 取值来源（§3.2 取值来源表） |
    |------|------|------------------------------|
    | `scope` | 触发稀有度 | `pdef.scope` |
    | `reset_on` | `'scope'`（出触发稀有度即重置）/ `'featured'`（仅 featured 重置）/ `'never'`（永不重置，G16） | `pdef.reset`，空串回退 `scope` |
    | `init` | 计数初值 | `pdef.counter_init` |

    **N1 相位**：`counter` 属**计数型**，在 `before_draw` 的 `advance` 段推进，
    故「每抽加一次」表现为「第 N 抽读到的值为 N」（旧
    `CounterBasedBehavior.before_draw` 先自增再算概率，实测
    `hard(threshold=90)` 首次 100% 落在第 90 抽）。`prepare` 为 no-op。

    **M4 `did_reset`**：与 `commit` 的重置条件**严格同条件**（旧
    `did_fire = _should_reset(ctx)`）。`'featured'` 分支**保留无 scope 门控的不
    对称**（只看 `is_featured`）——这是 `reset` 配置的既有语义，不在「did_fire
    统一」的范围内（§3.1.1 三点声明第 2 条）。

    **G16 自然落位**：`reset_on='never'` 去掉重置规则即可，无需特殊分支。
    """

    def __init__(self, scope: str, reset_on: Optional[str] = None, init: int = 0):
        self._scope = scope
        # 空串（None）回退 scope——对齐 create_behavior「仅在 pdef.reset 为 truthy
        # 时透传该参数」的既有语义（空串即「出触发稀有度即重置」）
        self._reset_on = reset_on if reset_on else scope
        self.init = init
        self._counter: Optional[Counter] = None

    # ── 契约成员 ──

    def rebind(self, state: PityState, name: str) -> None:
        self._counter = Counter(state, name, "counter")

    def advance(self, ctx: PityContext, state: PityState, name: str,
                readonly: bool) -> None:
        if readonly:
            return
        self._counter.incr()

    def commit(self, ctx: PityContext, state: PityState, name: str,
               skip_reset: bool = False) -> None:
        if skip_reset:
            return
        if self._reset_condition(ctx):
            self._counter.reset()

    def did_reset(self, ctx: PityContext, state: PityState, name: str) -> bool:
        return self._reset_condition(ctx)

    def state_keys(self) -> tuple:
        return ('counter',)

    # ── 内部 ──

    def _reset_condition(self, ctx: PityContext) -> bool:
        """本次抽卡是否满足重置条件（`commit` 与 `did_reset` 的唯一判据）。"""
        if self._reset_on == "featured":
            # 有意保留的不对称：只看 is_featured、无 scope 门控
            return ctx.draw.is_featured
        if self._reset_on == "never":
            # G16 幻塔「出金不重置」
            return False
        return ctx.draw.reward_rarity == self._reset_on
