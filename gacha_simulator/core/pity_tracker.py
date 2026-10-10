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

import random
from typing import Optional

from .pity_primitives import (
    Counter, Flag, LifecycleConfig, PityContext, PityState,
)

__all__ = ['Tracker', 'CounterTracker', 'FlagTracker', 'StreakTracker',
           'FateTracker', 'NamespaceTracker',
           'Lifecycle', 'AlwaysActive', 'FiniteActive', 'DependentActive',
           'DependentFiniteActive']


def _is_trigger_rarity(scope: str, ctx: PityContext) -> bool:
    """出触发稀有度判定——事件驱动型 Tracker 的公共门控。

    旧 `RotatingBehavior._is_trigger_rarity` / `RotatingCRBehavior.after_draw` /
    `TargetedBehavior._is_trigger_rarity` 均为 `rarity == scope`，三处逐字同源。
    """
    return ctx.draw.reward_rarity == scope


def _judge_hit(judge: str, ctx: PityContext, state: PityState, name: str) -> bool:
    """命中判据（§3.1.1 的 `judge` 形参）。

    - `'featured'`：`draw.is_featured`（rotating 族）
    - `'selected'`：`draw.reward_id == state[name]['selected_card']`（targeted 族；
      该键由策略层 `NonDrawAction` 写入，Tracker 只读、不声明，§3.1.1 L4 例外 2）
    """
    if judge == 'featured':
        return bool(ctx.draw.is_featured)
    if judge == 'selected':
        return ctx.draw.reward_id == state.get(name, 'selected_card')
    raise ValueError(f"未知 judge={judge!r}（可用：('featured', 'selected')）")


_JUDGES = ('featured', 'selected')


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


class FlagTracker(Tracker):
    """标记型 Tracker——出触发稀有度时按 `judge` 命中/未命中翻转一个标记键。

    **`scope` 形参不在计划签名表内（本步补入，2026-10-10）**：§3.1.1 的签名表与
    §3.2 / §3.3 / §3.10.3 的 preset 代码一律写作 `FlagTracker(judge, hit, miss, flag)`
    四参，而同表「语义」列与 §3.1.1 的 M4 表都要求「**出 scope 时**」这一门控，
    旧 `RotatingBehavior.after_draw` / `did_fire` 亦均以
    `reward_rarity == scope` 为前提。缺该形参则门控无处可落：出「非 scope 稀有度
    的 featured 卡」（如保 SSR 的池子里出 featured 的 SR）会翻转标记并报
    `did_reset=True`，与旧类实测不符（旧类该情形下 `guaranteed` 保持未置位、
    `did_fire` 为 False），M1 的「与旧类逐场一致」随之不成立。故本步取最小改动，
    把 `scope` 补为**首个形参**；S4-2 / S4-3 的 preset 调用点须相应传
    `scope=_norm_scope(pdef)`（计划正文的四处 `FlagTracker(...)` 代码块需同步）。

    | 形参 | 语义 | 取值来源（§3.2） |
    |------|------|------------------|
    | `scope` | 触发稀有度——只有出该稀有度时才参与翻转与 `did_reset` | `_norm_scope(pdef)` |
    | `judge` | 命中判据：`'featured'`（`draw.is_featured`）/ `'selected'`（`draw.reward_id == state[name]['selected_card']`） | rotating 用 `'featured'`；targeted 族用 `'selected'` |
    | `hit` / `miss` | 命中 / 未命中时对标记的动作，取值 `'set'` / `'clear'` | rotating：`hit='clear'` / `miss='set'`；G1：`hit='set'` / `miss='clear'` |
    | `flag` | 被写的标记键 | `'guaranteed'`（rotating）/ `'forced_loss'`（G1） |

    两族实例（§3.2 preset 表）：

    - rotating：`FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")`
    - G1 `rotating_inverse`：`FlagTracker(judge="featured", hit="set", miss="clear", flag="forced_loss")`

    **N1 相位**：非计数型，`advance` / `prepare` 均 no-op，全部状态变更落在 `commit`
    （旧 `RotatingBehavior.after_draw` 即「先判触发稀有度、再按命中置位/清位」）。

    **M4 `did_reset`**：判据是**「本次写入的是 flag 的初值侧」**——两个在用标记
    （`guaranteed` / `forced_loss`）的初值均为 `False`，故走到 `clear` 的那一支即
    「回到初始状态」。这与 §3.1.1 M4 表的两行**逐字一致**：
    rotating（`hit='clear'`）得「出 scope ∧ `is_featured`」，targeted 族
    （`hit='clear'`）得「出 scope ∧ `reward_id == selected`」。对 G1 的
    `rotating_inverse`（`hit='set'` / `miss='clear'`）本式给出「出 scope ∧ 未命中」
    ——该类型**不在 M4 六行表内**，此处置按 M4 的统一语义（「本次抽卡是否让本保底
    回到初始状态」）推导，而非照抄某一行；若改按「judge 命中」实现，G1 会在标记被
    **置位**时报 `did_reset=True`，与统一语义相反。

    **`skip_reset` 对本 Tracker 无影响**：`deactivate_on_early_hit` 对事件驱动型由
    `_build_pity` 硬拒（H3），故 `Pity` 传 `skip_reset=True` 的路径对事件驱动型
    不可达；旧 `RotatingBehavior.after_draw` 亦无跳过分支。此处**不写**跳过分支，
    以与旧实现逐行同构。

    **读 `selected_card`**：`judge='selected'` 读该键，而它**不由本 Tracker 声明**
    （写入者是策略层 `NonDrawAction`，§3.1.1 L4 例外 2），故 `state_keys()` 只含
    `flag`。
    """

    _ACTIONS = ('set', 'clear')

    def __init__(self, scope: str, judge: str, hit: str, miss: str, flag: str):
        self._scope = scope
        if judge not in _JUDGES:
            raise ValueError(f"FlagTracker: 未知 judge={judge!r}（可用：{_JUDGES}）")
        for name, action in (('hit', hit), ('miss', miss)):
            if action not in self._ACTIONS:
                raise ValueError(
                    f"FlagTracker: 未知 {name}={action!r}（可用：{self._ACTIONS}）")
        self._judge = judge
        self._hit = hit
        self._miss = miss
        self._flag = flag
        self._flag_ctl: Optional[Flag] = None

    # ── 契约成员 ──

    def rebind(self, state: PityState, name: str) -> None:
        self._flag_ctl = Flag(state, name, self._flag)

    def commit(self, ctx: PityContext, state: PityState, name: str,
               skip_reset: bool = False) -> None:
        if not _is_trigger_rarity(self._scope, ctx):
            return
        if self._action(ctx, state, name) == 'set':
            self._flag_ctl.set()
        else:
            self._flag_ctl.clear()

    def did_reset(self, ctx: PityContext, state: PityState, name: str) -> bool:
        if not _is_trigger_rarity(self._scope, ctx):
            return False
        return self._action(ctx, state, name) == 'clear'

    def state_keys(self) -> tuple:
        return (self._flag,)

    # ── 内部 ──

    def _action(self, ctx: PityContext, state: PityState, name: str) -> str:
        """本次该对标记做哪个动作（`commit` 与 `did_reset` 的唯一判据）。"""
        return self._hit if _judge_hit(self._judge, ctx, state, name) else self._miss


class StreakTracker(Tracker):
    """连续未命中计数 + 抽前随机拦截判定（`rotating_cr` 的「捕获明光」）。

    | 形参 | 语义 | 取值来源（§3.2） |
    |------|------|------------------|
    | `scope` | 触发稀有度（同 `FlagTracker`，见其 docstring 的补入说明） | `_norm_scope(pdef)` |
    | `judge` | `cr_counter` 的命中判据（`'featured'`） | 机制语义固定 |
    | `threshold` | `cr_counter` 的封顶档位数 | `pdef.cr_counter_threshold`（`None` → 3） |
    | `base_rate` | 每抽的固定拦截率 | `pdef.cr_base_rate`（`None` → 0.0） |
    | `state_probs` | 逐档拦截概率表 | `pdef.cr_state_probs`（`None` → `[0.0]*threshold + [1.0]`） |
    | `flag` | 拦截结果标记键 | `'cr_intercepted'` |
    | `guard_flag` | 抽前守卫标记键（已置位则不掷骰） | `'guaranteed'` |

    **N1 相位（裁决 6B′，2026-10-10 改判）**：掷骰归 **`prepare`**（`Pity.before_draw`
    内、`advance` 之后、Modifier 链之前），与旧 `RotatingCRBehavior.before_draw`
    同相位；`advance` 为 no-op（`cr_counter` **不属计数型**——旧实现只在
    `after_draw` 累加与清零，若按「计数器」字面划入计数型，`advance` 会每抽多推
    一次，§3.1.1 N1 显式例外）。`commit` 收窄为**只更新 `cr_counter`**。

    **随机数消耗协议（H4，逐条复刻旧实现）**：`prepare` 里四条路径**不消耗随机数**
    ——① `readonly=True`（只读查询早退）；② `guard_flag` 已置位（抽前已 guaranteed）；
    ③ `state_prob >= 1.0`（确定性触发）；④ `state_prob <= 0`（掷骰的前置条件是
    `state_prob > 0`）；另有 ⑤ 空 `state_probs`（`idx = min(0, -1) = -1`，不进分支）
    与 ⑥ `base_rate == 0`（不进 `and` 的右侧）。其余路径的掷骰次数与次序与旧实现
    逐位相同。

    **flag 每抽写**：掷骰路径下成功置位、失败清位（旧实现只在命中分支 `return`，
    照搬会让「上次掷中」的标记残留到下一抽、拦截率被静默抬高）。`guard_flag`
    已置位的早退路径**清位**（同样防脏残留；该路径下 `guaranteed` 已强制 featured，
    输出与旧实现一致）；`readonly` 早退路径**不写**（纯查询不得改状态，故该路径下
    Modifier 也不得消费本标记——旧实现的只读查询从不应用拦截）。

    **`commit` 的 `was_guaranteed` 读点**：`cr_counter` 的归零条件是
    「出 scope ∧ **抽前** `guaranteed` 未置位 ∧ 命中」，抽前值由
    **`[StreakTracker, FlagTracker]` 的顺序契约**保证——`StreakTracker.commit` 先跑，
    此时 `FlagTracker` 尚未在本抽翻转 `guaranteed`（§3.1.1「Tracker 顺序是契约」）。

    **M4 `did_reset` 恒 False**：`cr_counter` 归零是 rotating 族**内部子状态**的重置，
    不构成「本保底回到初始状态」；判据由同族的 `FlagTracker` 提供。返回 False 使
    `Pity.did_fire = any(tr.did_reset(...))` 与旧 `RotatingBehavior.did_fire`
    （`rotating_cr` 经 MRO 落到的就是它）逐字一致。

    **`skip_reset` 无影响**：同 `FlagTracker`（事件驱动型不可配
    `deactivate_on_early_hit`，该路径不可达；旧实现亦无跳过分支）。
    """

    def __init__(self, scope: str, judge: str, threshold=None, base_rate=None,
                 state_probs=None, flag: str = 'cr_intercepted',
                 guard_flag: str = 'guaranteed'):
        if judge not in _JUDGES:
            raise ValueError(f"StreakTracker: 未知 judge={judge!r}（可用：{_JUDGES}）")
        self._scope = scope
        self._judge = judge
        self._max = threshold if threshold is not None else 3
        self._base_rate = base_rate if base_rate is not None else 0.0
        if state_probs is not None:
            self._state_probs = (list(state_probs)
                                 if isinstance(state_probs, (list, tuple))
                                 else [0.0] * self._max + [1.0])
        else:
            self._state_probs = [0.0] * self._max + [1.0]
        self._flag = flag
        self._guard_flag = guard_flag
        self._cr_counter: Optional[Counter] = None
        self._flag_ctl: Optional[Flag] = None
        self._guard_ctl: Optional[Flag] = None

    # ── 契约成员 ──

    def rebind(self, state: PityState, name: str) -> None:
        self._cr_counter = Counter(state, name, "cr_counter")
        self._flag_ctl = Flag(state, name, self._flag)
        self._guard_ctl = Flag(state, name, self._guard_flag)

    def prepare(self, ctx: PityContext, state: PityState, name: str,
                readonly: bool) -> None:
        if readonly:
            return                      # 纯查询：不掷骰、不写状态
        if self._guard_flag and self._guard_ctl.is_set():
            self._flag_ctl.clear()      # 抽前已 guaranteed：不掷骰，清位防脏残留
            return
        if self._roll_hit(ctx, state, name):
            self._flag_ctl.set()
        else:
            self._flag_ctl.clear()

    def commit(self, ctx: PityContext, state: PityState, name: str,
               skip_reset: bool = False) -> None:
        if not _is_trigger_rarity(self._scope, ctx):
            return
        if self._guard_flag and self._guard_ctl.is_set():
            return                      # 抽前已 guaranteed → cr_counter 不动
        if _judge_hit(self._judge, ctx, state, name):
            self._cr_counter.reset()
        else:
            self._cr_counter.incr()

    def did_reset(self, ctx: PityContext, state: PityState, name: str) -> bool:
        return False

    def state_keys(self) -> tuple:
        return ('cr_counter', self._flag)

    # ── 内部 ──

    def _roll_hit(self, ctx: PityContext, state: PityState, name: str) -> bool:
        """本次是否拦截为 100% UP（逐行复刻旧 `RotatingCRBehavior.before_draw`）。"""
        if self._base_rate > 0 and random.random() < self._base_rate:
            return True
        idx = min(self._cr_counter.value(), len(self._state_probs) - 1)
        if idx >= 0:
            state_prob = self._state_probs[idx]
            if state_prob >= 1.0:
                return True
            if state_prob > 0 and random.random() < state_prob:
                return True
        return False


#: 定轨族的状态键词表（§3.2 targeted 行）——`FateTracker` 的 `keys` 形参是**扁平
#: 键名元组**，而同一动作对计数器与标记的作用不同（`clear` = 计数器归零 / 标记清位，
#: `accumulate` = 计数器 +1 / 标记置位），故键的类别必须显式给出。本表是**唯一来源**，
#: 未知键一律抛 `ValueError`（不静默当成标记处理）。
_FATE_KEY_KINDS = {
    'fate_points': 'counter',
    'losses': 'counter',
    'guaranteed': 'flag',
    'lost_rotating': 'flag',
}


class FateTracker(Tracker):
    """定轨（targeted）族的状态追踪——命中定轨卡则清零，未命中则累积。

    | 形参 | 语义 | 取值来源（§3.2） |
    |------|------|------------------|
    | `scope` | 触发稀有度（同 `FlagTracker`） | `_norm_scope(pdef)` |
    | `judge` | 命中判据（`'selected'`，即 `reward_id == selected_card`） | 机制语义固定 |
    | `hit` / `miss` | 命中 / 未命中时的动作，取值 `'clear'`（计数器归零、标记清位）/ `'accumulate'`（计数器 +1、标记置位） | 机制语义固定 |
    | `keys` | 被写的键名元组（**只含「写」的键**） | `('fate_points', 'losses', 'guaranteed', 'lost_rotating')` |

    **`hit` / `miss` 的取值由 S1 定稿（§3.1.1 该行明写）**：本步取 `'clear'` /
    `'accumulate'` 两值，逐行对齐旧 `TargetedBehavior.after_draw` 的命中 / 未命中
    两分支（命中：`fate_points.reset()` + `guaranteed.clear()` +
    `lost_rotating.clear()` + `losses.reset()`；未命中：四个键分别 incr / set）。
    其余取值一律抛 `ValueError`，不静默退化。

    **N1 相位**：非计数型，`advance` / `prepare` 均 no-op；状态变更全在 `commit`。

    **两处早退（逐行对齐旧实现）**：① 出非 scope 不动；② `selected_card` 为
    `None` 时**整段不动**（旧 `after_draw` 的 `if selected is None: return`）——
    缺这一条则「未定轨」会被当成「未命中」而累积 `losses` / 置位 `guaranteed`。

    **M4 `did_reset`** = 出 scope ∧ 命中定轨（§3.1.1 M4 表行）。`selected_card`
    为 `None` 时 `reward_id == None` 恒假，故自然为 False——与旧
    `TargetedBehavior.did_fire`（`trigger_rarity ∧ _is_hit`，而 `_is_hit` 在
    `selected is None` 时返回 False）逐字一致。

    **`selected_card` 是读的键**：由策略层 `NonDrawAction` 写入，不进
    `state_keys()`（§3.1.1 L4 例外 2）。

    **`skip_reset` 无影响**：同 `FlagTracker`（事件驱动型不可配
    `deactivate_on_early_hit`）。
    """

    _ACTIONS = ('clear', 'accumulate')

    def __init__(self, scope: str, judge: str, hit: str, miss: str, keys):
        if judge not in _JUDGES:
            raise ValueError(f"FateTracker: 未知 judge={judge!r}（可用：{_JUDGES}）")
        for nm, action in (('hit', hit), ('miss', miss)):
            if action not in self._ACTIONS:
                raise ValueError(
                    f"FateTracker: 未知 {nm}={action!r}（可用：{self._ACTIONS}）")
        unknown = [k for k in keys if k not in _FATE_KEY_KINDS]
        if unknown:
            raise ValueError(
                f"FateTracker: 未知状态键 {unknown}（词表见 _FATE_KEY_KINDS）")
        self._scope = scope
        self._judge = judge
        self._hit = hit
        self._miss = miss
        self._keys = tuple(keys)
        self._ctls: dict = {}

    # ── 契约成员 ──

    def rebind(self, state: PityState, name: str) -> None:
        self._ctls = {
            key: (Counter(state, name, key) if kind == 'counter'
                  else Flag(state, name, key))
            for key, kind in ((k, _FATE_KEY_KINDS[k]) for k in self._keys)
        }

    def commit(self, ctx: PityContext, state: PityState, name: str,
               skip_reset: bool = False) -> None:
        if not _is_trigger_rarity(self._scope, ctx):
            return
        if state.get(name, 'selected_card') is None:
            return                      # 未定轨：整段不动（旧实现的早退）
        action = (self._hit if _judge_hit(self._judge, ctx, state, name)
                  else self._miss)
        for key in self._keys:
            ctl = self._ctls[key]
            is_counter = _FATE_KEY_KINDS[key] == 'counter'
            if action == 'clear':
                if is_counter:
                    ctl.reset()
                else:
                    ctl.clear()
            elif is_counter:            # 'accumulate'
                ctl.incr()
            else:
                ctl.set()

    def did_reset(self, ctx: PityContext, state: PityState, name: str) -> bool:
        if not _is_trigger_rarity(self._scope, ctx):
            return False
        return _judge_hit(self._judge, ctx, state, name)

    def state_keys(self) -> tuple:
        return self._keys


class NamespaceTracker(Tracker):
    """命名空间载体（ISSUE-407）——**语义为空**，唯一作用是声明一个命名空间。

    三个 `_soft` 类型的 preset 用它产出 `X_soft` 命名空间（§3.10.3 配套 1），使该
    命名空间在 `PityState` 中存在、可被 `Lifecycle.initialize` 写入 `_active`、
    并进快照比对。旧实现由内层 `SoftStepBehavior(name + '_soft', …)` 经
    `CounterBasedBehavior.__init__` **隐式**产生该命名空间（写入 `_active: True`）。

    `advance` / `prepare` / `commit` / `did_reset` 全为基类的 no-op 默认实现、
    `state_keys()` 返回 `()`（不声明任何状态键）；**构造后 `state` 中不新增任何键**
    ——`X_soft._active` 由 `Lifecycle.initialize` 的推广作用域写入，不由本零件写。
    """

    def __init__(self, namespace: str):
        if not namespace:
            raise ValueError('NamespaceTracker: namespace 不得为空')
        self.namespace = namespace


# ══════════════════════════════════════════════════════════════════
# Lifecycle 族（§3.1.3）——正交包装层
# ══════════════════════════════════════════════════════════════════

class Lifecycle:
    """Lifecycle 基类——五方法协议 + 两个只读属性代理 + `state_keys()` + `namespace`。

    | 方法 | 语义 |
    |------|------|
    | `initialize(state, name, namespaces=())` | **构造期**写入初始 `_active`（`Always` 维对 `name` 与每个 `namespaces` 成员各写 `True`；`Dependent` 维空实现） |
    | `is_active(state, name)` | `before_draw` / `after_draw` 首行早退的判据 |
    | `should_deactivate(ctx, state, name, fired)` | 退役判定，**先于** `commit`（§3.1.4 的 ISSUE-018）。第四实参 `fired` 由 `Pity` 用 `any(tr.did_reset(...))` 算好后传入——Lifecycle 自身拿不到该判据 |
    | `deactivate(state, name)` | 清 `_active`（**只清 `name` 的**，退役只作用于本保底） |
    | `rebind(state, name, namespaces=())` | 把本生命周期为 `name` 与 `namespaces` 中**每个**命名空间持有的 `_active` Flag 重绑到 per-call `state`（纯重定向）。**实参面与 `initialize` 严格对称**（ISSUE-917） |

    两个只读属性 `deactivate_on_early_hit` 与 `depends_on` **一律由基类对 `self._cfg`
    统一代理**（ISSUE-406）——`PityEngine._build_activation_graph` 对**每一条**
    behavior 无条件读 `lc.depends_on`，未代理即每次 `PityEngine(...)` 构造
    `AttributeError`；「`depends_on` 由 `DependentActive` 从同一 `cfg` 读出」的写法
    已废止。

    **`_ns_active`（ISSUE-917 取形态 ①）**：每个命名空间各持一个 `_active` Flag
    （键 = `name` 与 `namespaces` 的并集），`rebind` 对**并集中每个** Flag 重定向。
    形态 ②（只持 `name` 的 Flag、`namespaces` 的 `_active` 在 `initialize` 里
    `state.set` 一次）已否决：该键成为 write-once，worker 内连跑第 2..N 场时仍指
    上一场的 state 且无从重绑。形态 ① 与旧实现同构（内层 `SoftStepBehavior` 持
    `X_soft` 的 `_active`，经 `SoftPityMixin._rebind_state` 委托重绑）。

    **`state_keys()`**：基类返回 `()`；`FiniteActive` / `DependentFiniteActive` 在
    `max_triggers > 0` 时返回 `('triggers',)`——「已触发次数」落在 state 的保底
    命名空间下，**不得放在 Lifecycle 对象内**（对象在同一 worker 内跨模拟复用，
    对象内计数会跨模拟泄漏，破坏「固定种子可复现」）。
    """

    namespace: Optional[str] = None

    def __init__(self, cfg: LifecycleConfig = None):
        self._cfg = cfg if cfg is not None else LifecycleConfig()
        self._ns_active: dict = {}

    # ── 两个只读属性（ISSUE-406：统一代理，不得只代理前者）──

    @property
    def deactivate_on_early_hit(self) -> bool:
        return bool(self._cfg.deactivate_on_early_hit)

    @property
    def depends_on(self) -> Optional[str]:
        return self._cfg.depends_on

    # ── 五方法协议 ──

    def initialize(self, state: PityState, name: str, namespaces=()) -> None:
        """构造期写入初始 `_active`——具体写入面由 `_writes_active` 决定。"""
        self._bind_active(state, name, namespaces)
        if self._writes_active:
            for flag in self._ns_active.values():
                flag.set()

    def is_active(self, state: PityState, name: str) -> bool:
        return bool(state.get(name, '_active', False))

    def should_deactivate(self, ctx: PityContext, state: PityState, name: str,
                          fired: bool) -> bool:
        """退役判定——触发次数用尽（`_count_triggers`）或 `deactivate_on_early_hit`。"""
        if self._count_triggers(state, name, fired):
            return True
        return bool(fired and self.deactivate_on_early_hit)

    def deactivate(self, state: PityState, name: str) -> None:
        """清 `_active`——**只清 `name` 的**（命名空间的 `_active` 与旧实现内层
        `SoftStepBehavior._active` 同形：构造期写一次、此后不再被触碰）。"""
        flag = self._ns_active.get(name) or Flag(state, name, '_active')
        flag.clear()

    def rebind(self, state: PityState, name: str, namespaces=()) -> None:
        """纯重定向——实参面与 `initialize` 严格对称（ISSUE-917）。"""
        self._bind_active(state, name, namespaces)

    def state_keys(self) -> tuple:
        return ()

    # ── 内部 ──

    #: 激活维：True = 构造期写 `_active`（`Always` 维）；False = 空实现（`Dependent` 维）
    _writes_active: bool = True

    def _bind_active(self, state: PityState, name: str, namespaces) -> None:
        self._ns_active = {
            ns: Flag(state, ns, '_active')
            for ns in (name,) + tuple(ns for ns in (namespaces or ()) if ns != name)
        }

    def _count_triggers(self, state: PityState, name: str, fired: bool) -> bool:
        """触发次数累计与上限判定——基类不计数，由 `Finite*` 覆写。"""
        return False


class AlwaysActive(Lifecycle):
    """永远生效（激活维 Always / 退役维 Never）——两者都未配置时的默认。"""


class FiniteActive(Lifecycle):
    """触发 N 次后退役（福利保底）——激活维 Always / 退役维 AfterN(N)。

    计数载体是 state 的保底命名空间下的 `triggers` 键（见基类 docstring），
    **只在 `fired` 时累加**：无条件累加会让 `triggers` 变成「激活后的**抽数**」
    而非「**触发次数**」，`max_triggers=2` 会在第 2 抽就退役，与「触发 N 次后
    退役」相反。
    """

    def __init__(self, cfg: LifecycleConfig = None, max_triggers: int = 0):
        super().__init__(cfg)
        self._max_triggers = max_triggers or 0

    def state_keys(self) -> tuple:
        return ('triggers',) if self._max_triggers > 0 else ()

    def _count_triggers(self, state: PityState, name: str, fired: bool) -> bool:
        if not fired or self._max_triggers <= 0:
            return False
        n = state.get(name, 'triggers', 0) + 1
        state.set(name, 'triggers', n)
        return n >= self._max_triggers


class DependentActive(Lifecycle):
    """依赖另一个 Pity 激活（激活维 Dependent / 退役维 Never）。

    `initialize` 为**空实现**——`_active` 由引擎的 `depends_on` 传播写入
    （旧 `PityEngine.after_draw` 的激活传播同源）。
    """

    _writes_active = False


class DependentFiniteActive(FiniteActive):
    """被激活后触发 N 次退役（激活维 Dependent / 退役维 AfterN(N)）。

    退役计数**自激活后起算**——`after_draw` 首行的 `is_active` 早退在
    `should_deactivate` 之前（§3.1.4 骨架），故由调用位置天然保证。
    """

    _writes_active = False
