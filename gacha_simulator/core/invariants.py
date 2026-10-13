"""P64 S11：不变式运行时校验（§3.13）——可开关的 `InvariantChecker`。

**方案出处**：计划 §3.13（本模块的立块依据与四层判据表）+ §3.12.1（判据原文）。
覆盖**分布 / 状态 / 增量 / 生命周期**四层，破坏时立即抛出并指明位置
（**保底名 + 键 + 期望 / 实际**三要素）。

**开关载体（ISSUE-945，强制）**：`enabled: bool` **构造形参**、存为实例字段
（`self.enabled`）、**随实例进 pickle**。禁止任何模块级全局开关：`run_batch_parallel`
把整个 `env`（含 `env.pity_engine`）序列化给每个 worker，checker 实例随该 pickle
图进子进程，故 Windows spawn 出的 worker **自动继承**该设置；模块级全局（或读
`os.environ` 的全局标志）在 spawn 下不继承，父进程的设置传不到 worker，校验只在
主进程生效、并行路径**静默失去校验能力**（同型缺陷先例：commit `38962ab`，
2026-09-30「父进程函数体内注册的插件策略在 spawn 子进程不存在」）。

**挂载层、调用点与开关来源（ISSUE-003，强制）**：实例挂 `PityEngine._invariants`
（构造形参 `invariants=None` 为默认关闭态），调用点 = `PityEngine.before_draw` /
`after_draw` **各一行**。本模块**不 import `pity`**（`engine` / `Pity` 实例一律经
实参传入），故不构成循环导入，也不改变两个实现层模块的单向依赖方向；生产路径传
`invariants=None`，**连实例都不建**（零开销）；`enabled=True` 只由测试夹具产出
（本期不加 env 字段、不加 CLI 开关、不加 TOML 项）。

**四层与入口的分工**（§3.13 的四行表 → 本模块的入口面）：

| 入口 | 覆盖层 | 判据对象 |
|------|--------|----------|
| `check_after_before_draw(pool_id, dist, engine)` | 分布层 | 池的管道输出分布 |
| `check_after_after_draw(pool_id, state, engine)` | 状态层 + 生命周期层 | per-call `PityState` |
| `check_delta(pool_id, dist, delta)`（**M1 不接调用点**，随 S8-6 落地） | 增量层 | 单步的 `p` 与 `δ` |

分布层归前一个入口、状态与生命周期两层归后一个入口，按**实参可得性**分：`dist`
只在前者的实参面内，`state` 只在后者的实参面内（§3.13 只给了两个入口的签名，未
逐层指派入口，该分工是本模块的定稿）。增量层**不复用**这两个入口的理由见 §3.13
的「增量层的入口与调用点」段：两个入口的第二实参只有分布，取不到该步的 δ；故它
自带第三个入口，由 `_apply_delta()` 内部在 `p` 与 `δ` 同时在手处调用。

**四层覆盖边界（S11 审查收口，2026-10-13，逐条实测）**：

- **观测点只有 `before_draw` / `after_draw` 两处**：`PityEngine.get_probabilities`
  （只读查询入口，被 `core/strategy.py` 调用）**不经过任何一层**，故该路径上的
  概率输出与状态**完全不在判据面内**。
- **状态层与生命周期层只在 `after_draw` 之后观测**：`before_draw` 入口只看分布；
  抽内的中间态（一次抽卡内多次 `advance` / `commit`）只有末值可见。
- **四层里最松的是生命周期层**：白名单取 `engine.behaviors` 的**全集**（激活传播
  的目标可以是别的池的保底，故不能只限本池），比「本保底的退役动作」宽，故
  「错误的写入方写进一个**合法的**保底命名空间」不被拦截（详见
  `_check_active_whitelist` 的 docstring）。
- **`InvariantError` 在并行路径上会被吞**（异常语义与失败可见性）：详见
  `InvariantError` 的 docstring 使用约束段。
"""

from dataclasses import dataclass
from typing import Dict, Mapping, Sequence, Tuple

from .pity_modifier import HardModifier, NotOwnedModifier, _higher_rarity_keys
from .pity_primitives import DrawInfo, _EXTERNAL_STATE_KEYS


#: 概率断言容差（§3.12.1 归一性行的「容差 1e-12」）。
TOL = 1e-12

#: F 型算子（§3.13 分布层行的「被 F 豁免的更高稀有度槽位」中的 F）——M1 形态为
#: **绝对赋值 + 更高稀有度豁免**（§3.9 过渡期纪律）的两类实现者。集合与 S10-1 的
#: `kind == 'f'` 一致：`tests/core/test_pity_invariants.py` 的 `_MODIFIER_SPECS` 把
#: `hard` 与 `not_owned` 都标为 `'f'`（两者共用 `_higher_rarity_keys`）。
#:
#: **未触达分支（S11 审查收口，2026-10-13）**：`NotOwnedModifier` 在全库**没有任何
#: preset 构造它**（`gacha_simulator/` 内零个 `NotOwnedModifier(...)` 调用点，
#: 只有类定义本身），故 `_exemption_options` 的豁免分支在**真实配置**下只被
#: `HardModifier` 走过：11 个 registry 类型的假警报扫描与组合扫描都覆盖不到本集合
#: 的第二类：它的行为面只在 `tests/core/test_pity_modifier.py` 的单零件用例与
#: S10-1 的合成组合里有证据，**preset 面为零**。「本项在真实配置下是否成立」属
#: **未验证面**，不因那两条扫描通过而成立。
_EXEMPTION_PART_TYPES = (HardModifier, NotOwnedModifier)

#: 声明集之外的**外部写入键**白名单（§3.1.1 的 L4 例外 2：`selected_card` 由策略层
#: `NonDrawAction` 与 `_build_pity_state_init` 写入、**无任何零件声明它**，而
#: `FateTracker` / `SelectedModifier` 会读它）。
#:
#: **一处声明（S11 审查收口 F3，2026-10-13）**：常量与它存在的理由都住在叶子层
#: `core/pity_primitives.py`，本模块与编排层 `core/pity.py` 都从那里取**同一
#: 对象**（本行即该 import）。原先本模块**重写了一份**（内容相等、对象不同），
#: 靠 `test_external_state_keys_mirror_matches_engine` 逐元素拦漂移；下沉后那条
#: 守卫退化为「同一对象自比」的恒真断言，已由改判**身份**（`is`，而非 `==`）
#: 的 `test_external_state_keys_has_a_single_declaration` 取代。身份判据更严：
#: 连「又抄一份内容相同的副本」也拦得住，而相等判据拦不住。
#:
#: 引用叶子层**不违反**「不 import `pity`」约束（§3.13）：`pity_primitives` /
#: `pity_modifier` 是叶子层与实现层，编排层单向依赖它们，本模块亦然，不成环。

#: 生命周期层的键（§3.13 生命周期行）——三处写入方之外的写入即违规。
_ACTIVE_KEY = '_active'


class InvariantError(Exception):
    """不变式破坏——校验器抛出的**唯一**异常类型。

    **类型选择的理由（两条）**：不继承 `ConfigError`（那是配置错误，构造期由
    S10-2 / `_validate_behaviors` 抛）也不继承 `ValueError`（本库用它标「编程错误」
    面的重名判定）；本类是**运行期自洽性**失败，语义独立（与那两类的处置路径也不同：
    配置错误在构造期就得挡下，本类是运行中的状态自洽性）。

    **使用约束（S11 审查收口 F1，2026-10-13，必读）**：本类**会**落进兜底 `except`
    的捕获面内。`service/batch_simulator.py` 的三处 `try` 包装
    （worker 侧 `_wk_run_single`、`run_batch_parallel` 的 `workers<=1` 顺序分支、
    同函数的 `mp_failed` 单进程兜底，合计覆盖 4 个 `_run_single` 调用点）一律写
    `except Exception`，故**走 `run_batch_parallel` / 并行路径时，不变式破坏表现为
    静默的失败计数**（父进程汇总成「N/M 次模拟失败」，写进 `BatchResult.warnings`），
    **不向调用方抛异常**；要看到本异常本身，必须走非并行入口（直接调
    `PityEngine.before_draw` / `after_draw`，异常自这两个调用点抛给调用方）。

    这条约束的前提（三处包装均为 catch-all）由
    `tests/core/test_pity_invariant_checker.py::TestErrorTypeAndSwallow` 的 AST 判据
    钉住：包装若收窄到不含 `Exception`，该用例转红，提示同批订正本段。**该形态是
    「§六 的等价性 harness 注入 `enabled=True`」的真实陷阱**：harness 若走并行路径
    且只断言「未抛异常」，不变式破坏会被吞成失败计数而假绿。
    """


@dataclass(frozen=True)
class _DrawProbe:
    """`_higher_rarity_keys` 的实参面最小载体：该助手只读 `ctx.draw`。

    刻意**不**构造完整的 `PityContext`——后者要 `state` / `current` 两个本层拿不到
    也无需要的实参，塞 `state=None` 的假 ctx 比一个单字段载体更易误导。
    """

    draw: DrawInfo


def _names_label(names: Sequence[str]) -> str:
    """保底名标签（异常信息的「保底名」要素）：单个 `'x'`，多个 `('x', 'y')`。"""
    if not names:
        return "''"
    if len(names) == 1:
        return f"'{names[0]}'"
    return '(' + ', '.join(f"'{n}'" for n in names) + ')'


class InvariantChecker:
    """可开关的不变式校验（§3.13）——仅在 debug / test 模式启用，生产传 None。"""

    def __init__(self, enabled: bool = False):
        # 开关载体 = 构造形参、存为实例字段（ISSUE-945）：随实例进 pickle，故并行
        # 路径的 worker 自动继承。**不得**改成模块级全局或读环境变量的全局标志。
        self.enabled = bool(enabled)
        # 计数型计数器单调性的记忆（状态层）：键 = (命名空间, 键名)，值 = 上次观测值。
        # **按 state 对象身份隔离**：worker 内同一 engine 被 N 场模拟复用、每场一个新
        # state（`run_simulation` 首行 `clone()`），跨场沿用旧记忆会让「新场初值 <
        # 上场终值」误报。故只在身份变化时清空，不跨 state 累积。
        self._counter_state = None
        self._counter_memory: Dict[Tuple[str, str], int] = {}

    # ── 入口一：分布层（调用点 = PityEngine.before_draw）──

    def check_after_before_draw(self, pool_id: str, dist: Mapping[str, float],
                                engine) -> None:
        """分布层（§3.13 分布行；判据原文见 §3.12.1 的归一性行与非负性行）。

        调用点：`PityEngine.before_draw` 的「该池的全部保底跑完、返回值之前」。
        """
        if not self.enabled:
            return
        spec = engine.get_spec(pool_id)
        if spec is None:
            # 池不在 `pool_specs` 内时引擎在调度前就早退（返回基础分布的副本），
            # 本行只是与那条路径对齐的防御性守卫，正常调用不可达。
            return
        self._check_distribution(pool_id, dist, engine, spec,
                                 _pool_pities(engine, pool_id))

    # ── 入口二：状态层 + 生命周期层（调用点 = PityEngine.after_draw）──

    def check_after_after_draw(self, pool_id: str, state, engine) -> None:
        """状态层（§3.12.1 状态键合法行）+ 生命周期层（§3.13 生命周期行）。

        调用点：`PityEngine.after_draw` 的「该池的全部保底跑完、返回值之前」。
        两层都在 per-call `state` 上判，故不依赖 `pool_specs` 是否有本池。

        **观测点与覆盖边界（S11 审查收口 F7/F8，2026-10-13）**：本入口只在
        `after_draw` 之后观测一次，故抽内的中间态（同一次抽卡内多次 `advance` /
        `commit`）不可见；`PityEngine.get_probabilities`（只读查询入口）**不调用
        本入口也不调用分布层入口**，该路径完全不在四层判据内。四层之中本入口
        携带的生命周期层最松（白名单取 `engine.behaviors` 全集），详见
        `_check_active_whitelist` 的 docstring。
        """
        if not self.enabled:
            return
        pities = _pool_pities(engine, pool_id)
        self._check_declared_state(state, pities)
        self._check_counters_monotonic(state, pities)
        self._check_active_whitelist(state, engine)

    # ── 入口三：增量层（M1 只实现、不接调用点；S8-6 在 _apply_delta 内调用）──

    def check_delta(self, pool_id: str, dist: Mapping[str, float],
                    delta: Mapping[str, float]) -> None:
        """增量层（§3.13 增量行 / §3.12.1 增量合法性行）：`p + δ ≥ 0`；δ 在 p 的
        支撑上不全为 0。

        **M1 不接调用点**（计划 §七 S11 的硬约束）：M1 槽位级管道没有增量表示，
        两个入口的第二实参只有分布、取不到该步的 δ；本方法随 S8-6 由
        `_apply_delta()` 内部调用（那里 `p` 与 `δ` 同时在手）。此刻仅由
        `tests/core/test_pity_invariant_checker.py` 直接驱动。
        """
        if not self.enabled:
            return
        label = f"池 {pool_id!r}"
        for key, d in delta.items():
            p = float(dist.get(key, 0.0))
            combined = p + float(d)
            if combined < -TOL:
                raise InvariantError(
                    f"[增量层] {label} 键 {key!r}：期望 p + δ >= 0，实际 "
                    f"{p!r} + {float(d)!r} = {combined!r}"
                    f"（§3.12.1 增量合法性行）")
        support = [k for k, v in dist.items() if v > 0.0]
        if not support:
            # 输入分布无支撑时该式无判别力（对齐 S10-1 的同名断言前置），不报错。
            return
        if not any(float(delta.get(k, 0.0)) != 0.0 for k in support):
            raise InvariantError(
                f"[增量层] {label} 键 'δ'：期望 δ 在 p 的支撑 {support} 上不全为 0"
                f"（触发的步不得是静默空操作），实际 δ = {dict(delta)!r}"
                f"（§3.12.1 增量合法性行）")

    # ── 分布层 ──

    def _check_distribution(self, pool_id: str, dist: Mapping[str, float],
                            engine, spec, pities) -> None:
        """非负性（§3.12.1 非负性行）+ 归一性（M1 scope 感知式，见下）。

        **归一性在本入口是「有限取值集取一」**，不是单式——这是与 S10-1 对齐的
        结果，理由两条，都是实参面的事实而非宽松处理：

        1. S10-1 的管道判据本就是分两支的：F 步未触发的那一抽断言 `Σp == 1`
           （`test_pipeline_total_equals_last_f_step_exemption` 的 `if not fired_f`
           支与 `test_pipeline_total_is_one_without_f_part`），触发的那一抽断言
           `Σp == 1 + Σp(豁免槽位)`。**判据域由「本次是否真有 F 算子参与」决定**
           （§3.12.1 归一性行的例外条原文即写作「当参与本次 `before_draw` 的算子含
           低于最高稀有度的 F 型时」）。
        2. 本入口的签名由 ISSUE-003 固定为 `(pool_id, dist, engine)`，**看不到 F 是否
           触发**：触发与否取决于算子的内联条件（`counter >= τ`），而该条件只能靠
           重写一份谓词或回放零件才能取得，两条路都与 S10-2 收口提出的「镜像谓词与
           生产判据各写一份口径会持续分叉」相悖。故本层接受**可达取值集**
           （`_exemption_options`）：无 F 触发时的 `1`，与各 F 零件各自的
           `1 + Σp(该零件的豁免槽位)`。

        **豁免量按本入口的输出分布度量**，其有效性依据是执行顺序（`_resolve_order`
        的排序键以稀有度 rank 为首）：F 零件的豁免集是**严格高于**其 scope 的稀有度
        之槽位，而一个能把质量搬进该集合的转移算子，其 scope 必高于该 F 的 scope、
        即 rank 更小、**排在 F 之前**；排在 F 之后的转移算子（rank 相同或更大）其目标
        集与源组同在该豁免集之外，故豁免集上的质量在 F 之后不再变动，输出 Σ 恒等于
        `1 + Σp(豁免槽位)`。实测（2026-10-13）：同池 `hard(scope='sr')` +
        `soft(scope='ssr')`（后者 rank 更小、先执行）连跑 6 抽，输出 Σ 依次为
        1.209 / 1.409 / …，逐抽等于 `1 + Σp(ssr 两槽)`，无假警报。

        **已登记的盲区（两条，方向相反；都是实参面所限，不是疏漏）**：

        1. **F 触发了但豁免被整体丢掉**（豁免槽位归零）时 `Σp` 退化为 `1`，落进
           第一分支而被接受。该形态在**步级**由 S10-1 的
           `test_f_step_exemption_keeps_original_values`（豁免槽位逐位保留原值）
           拦截；本入口按定义看不到步，故该盲区由那里覆盖。
        2. **对偶方向（S11 审查 2026-10-13 实测）**：F **未**触发（真期望
           `Σ = 1.0`）时，把 `Σ` 人为抬到 `1 + m`（`m` = 该 F 零件豁免槽位上的
           质量，实测 1.009 恰等于豁免量）**被接受**。原因是取值集是**无条件
           析取**：F 零件的选项**不附带「该零件本抽必须已触发」的前提**，故它同时
           为「真触发」与「未触发但 Σ 被抬到同一量」两态背书。本层看不到触发与否，
           该区分只能落在步级判据上。已由
           `test_f_not_fired_but_raised_to_exemption_mass_is_accepted` 把「接受」
           钉成已知行为：将来收紧取值集时该用例转红，提醒同批改写本段。

        **复现纪律（S11 审查的方法学警告，2026-10-13）**：复现第 1 条盲区**不得**
        用「把 `_higher_rarity_keys` 换成空元组」的写法：该助手经 from-import 进
        `tests/core/test_pity_invariants.py`（S10-1）**与本层**两侧，把它换掉会让
        「截获判据」与「被测对象」**同向失明**、结果假绿（看似盲区、实则判据也瞎了）。
        正确复现是**保住助手、只丢豁免**（手工把豁免槽位上的质量清掉）。同理，若
        「改助手本身」成为真故障，S10-1 的豁免类用例**挡不住**（其期望值与生产值
        同源）；这正是 `tests/core/test_pity_invariant_checker.py` 的 `_EXEMPT`
        写死字面量的理由。
        """
        names = [name for name, _bh in pities]
        label = _names_label(names)
        # ── 非负性（§3.12.1 非负性行「所有卡的概率 ≥ 0」）──
        for key, value in dist.items():
            # 写成 `not (value >= 0.0)` 而非 `value < 0.0`：NaN 在后者下为假、
            # 会静默漏过；此写法与 S10-1 的同名断言（`assert value >= 0.0`，
            # 其注释明写「NaN 亦在此判据下失败」）同式。
            if not (value >= 0.0):
                raise InvariantError(
                    f"[分布层] 保底 {label} 键 {key!r}：期望 p >= 0，实际 {value!r}"
                    f"（池 {pool_id!r} 的管道输出；§3.12.1 非负性行）")

        # ── 归一性（M1 scope 感知式 + 无 F 参与时的退化式）──
        options = _exemption_options(spec, dist, engine, pities)
        total = float(sum(dist.values()))
        if any(abs(total - expected) <= TOL for _label, expected in options):
            return
        detail = '；'.join(
            f'{expected!r}（{option_label}）' for option_label, expected in options)
        raise InvariantError(
            f"[分布层] 保底 {label} 键 'Σp'：期望 {detail}；实际 {total!r}"
            f"（池 {pool_id!r} 的管道输出；§3.12.1 归一性行的 scope 感知式）")

    # ── 状态层 ──

    def _check_declared_state(self, state, pities) -> None:
        """运行期键集 ⊆ 三族声明集（§3.12.1 状态键合法行 / ISSUE-501）。

        比对集 = `Pity._declared_keys`（`Pity.__init__` 汇总的 `trackers` /
        `modifiers` / `lifecycle` 三个元组），**不自行遍历零件推断**——否则
        §3.12.1 / §3.12.2 / §3.13 三处会各有一套口径（ISSUE-501 明写）。

        判两个命名空间面：
        - **保底命名空间**（`Pity._name`）：键 ⊆ 三族声明集 ∪ `_active` ∪ 外部白名单。
          `_active` 属生命周期层（由 `Lifecycle.initialize` / 激活传播 / 退役动作写），
          `Lifecycle.state_keys()` 只声明 `triggers`，故该键另设白名单（§3.13 生命周期行）。
        - **零件命名空间**（`X_soft` 等，`Pity._namespaces`）：键 ⊆ **该命名空间的
          声明键集** ∪ `_active`，声明集**从零件派生**（S11 审查收口 F5，见下段）。
          `NamespaceTracker.state_keys()` 为空元组（§3.1.1），该命名空间的 `_active`
          由 `Lifecycle.initialize` 的推广作用域写入（ISSUE-407），故 `X_soft` 类
          命名空间下除它之外任何键都属「写进未声明键」（与 S10-1 的
          `test_part_namespace_writes_are_only_active` 同口径）。

        **零件命名空间的声明集从零件派生，不写死 `{_active}`（F5，2026-10-13）**：
        原先此处把允许集写死为 `{_active}`（等价于「该命名空间的声明集恒为空」），
        只在「零件命名空间 ≠ 保底命名空间、且其零件是 `NamespaceTracker`」的形态下
        正确。**退化形态 `NamespaceTracker(namespace=<保底名>)` 下该判据对合法配置
        假警报**（它与保底命名空间本就是同一份 `state.data[<保底名>]`，其中的 `counter`
        等三族声明键是合法的）：审查 2026-10-13 实测复现（`Pity(name='p',
        trackers=[CounterTracker('sr'), NamespaceTracker('p')])` → `[状态层]
        保底 'p' 键 ['counter']`）。preset 一律用 `f'{name}_soft'`，故生产当前
        不可达，但那是**同一个类换个实参**的巧合而非保证。现行判据：命名空间与
        保底同名时取三族并集，否则取「声明了该命名空间的零件」的 `state_keys()`
        并集（`X_soft` 下仍只许 `{_active}`，口径不变）。

        **旧类兼容分支**（无 `_declared_keys` 的 behavior）无声明集可比，跳过。
        """
        for name, bh in pities:
            declared = getattr(bh, '_declared_keys', None)
            if declared is None:
                continue
            allowed = (set(declared['trackers']) | set(declared['modifiers'])
                       | set(declared['lifecycle']) | {_ACTIVE_KEY}
                       | set(_EXTERNAL_STATE_KEYS))
            namespace = state.data.get(name) or {}
            undeclared = sorted(k for k in namespace if k not in allowed)
            if undeclared:
                raise InvariantError(
                    f"[状态层] 保底 '{name}' 键 {undeclared!r}：期望 该命名空间的键"
                    f"集合含于三族声明集 ∪ {{{_ACTIVE_KEY!r}}} ∪ "
                    f"{sorted(_EXTERNAL_STATE_KEYS)}（= {sorted(allowed)}）；"
                    f"实际 出现了未声明的键 {undeclared!r}"
                    f"（§3.12.1 状态键合法行 / ISSUE-501：声明集取自 "
                    f"`Pity._declared_keys`）")
            for part_ns in (getattr(bh, '_namespaces', ()) or ()):
                # F5：允许集**从声明集派生**，不写死 `{_ACTIVE_KEY}`（理由见 docstring
                # 的「零件命名空间的声明集从零件派生」段）。同名退化形态下该命名空间
                # 就是保底命名空间，故直接复用 `allowed`（三族并集 + 外部白名单），
                # 否则取「声明了该命名空间的零件」的 `state_keys()` 并集。
                if part_ns == name:
                    part_allowed = set(allowed)
                else:
                    part_allowed = {_ACTIVE_KEY}
                    for _group in (
                        getattr(bh, '_trackers', None) or (),
                        getattr(bh, '_modifiers', None) or (),
                        (getattr(bh, '_lifecycle', None),),
                    ):
                        for _part in _group:
                            if _part is None:
                                continue
                            if getattr(_part, 'namespace', None) == part_ns:
                                part_allowed.update(_part.state_keys())
                foreign = sorted(k for k in (state.data.get(part_ns) or {})
                                 if k not in part_allowed)
                if foreign:
                    raise InvariantError(
                        f"[状态层] 保底 '{name}' 键 {foreign!r}：期望 零件命名空间 "
                        f"'{part_ns}' 内只有该命名空间的声明键集 ∪ {_ACTIVE_KEY!r}"
                        f"（= {sorted(part_allowed)}；`NamespaceTracker.state_keys()` "
                        f"为空集，故 `X_soft` 只许 {_ACTIVE_KEY!r}）；"
                        f"实际 该命名空间出现 {foreign!r}"
                        f"（§3.12.1 状态键合法行 / ISSUE-407）")

    def _check_counters_monotonic(self, state, pities) -> None:
        """计数型计数器的值单调、重置时归零（§3.13 状态行末句）。

        判据面 = 本池保底命名空间内**值为 `int` 且非 `bool`** 的键（`bool` 是
        Flag 的载体：`guaranteed` / `_active` / `cr_intercepted` 等，其值本来就翻转，
        不在「计数型」内）。**「除重置外」的口径取「归零」**：现存三类计数器的重置
        动作都是 `Counter.reset()`（`set(…, 0)`）——`CounterTracker.commit` 命中重置、
        `FateTracker.commit` 的 `clear` 动作、`StreakTracker.commit` 的命中归零；
        `FiniteActive` 的 `triggers` 只增不减。故值下降且**非 0** 即破坏。

        记忆按 `state` 对象身份隔离（见 `__init__` 的说明）；本入口只被
        `after_draw` 调用，故观测点是「每次抽后」。

        **已知的判据边界（S11 审查收口 (C)，2026-10-13，四类）**：

        1. **只判「本池保底命名空间」内的键**：零件命名空间（`X_soft`）里的计数器
           完全不判。今天不存在这类计数器（`NamespaceTracker` 不声明任何键），属
           **结构性盲面**（该面当前无对象），不是漏网；将来某零件在自己的命名空间内
           放计数器，本层对它失明。
        2. **非 `int` 数值被静默跳过**：`float` 型计数器（若将来出现）既不参与判据、
           也不产生任何提示。
        3. **「重置 = 归零」是当前三类计数器的实现事实，不是结构保证（活耦合）**：
           逐处核对 `CounterTracker.commit` / `FateTracker.commit` /
           `StreakTracker.commit` 的重置动作都是 `Counter.reset()`（写 0），故
           「下降且非 0 即破坏」今天是准的。但「重置」在语义上不必然归零，一旦出现
           「重置到非零」的语义，**合法重置会被本条误报为破坏**。最近的活边界是
           计划 §六 G16 第 1 条登记的候选（「保底触发时归零」：把 *永不重置* 的
           计数器改成 *触发时重置*，即给本判据引入一种**新的重置来源**）。G16-2
           落地时须同批复核本判据的「什么算合法下降」。
        4. **同一抽内先升后降不可见**：观测点是「每次抽后」，故抽内多次
           `advance` / `commit` 只有末值进入记忆（判据看不到抽内轨迹）。
        """
        if self._counter_state is not state:
            self._counter_state = state
            self._counter_memory = {}
        for name, _bh in pities:
            for key, value in (state.data.get(name) or {}).items():
                if isinstance(value, bool) or not isinstance(value, int):
                    continue
                mark = (name, key)
                previous = self._counter_memory.get(mark)
                if previous is not None and value < previous and value != 0:
                    raise InvariantError(
                        f"[状态层] 保底 '{name}' 键 {key!r}：期望 计数型计数器单调"
                        f"不降（重置时归零），实际 由 {previous!r} 降为 {value!r}"
                        f"（§3.13 状态行「计数型计数器的值单调（除重置外）」）")
                self._counter_memory[mark] = value

    # ── 生命周期层 ──

    def _check_active_whitelist(self, state, engine) -> None:
        """`_active` 的写入面白名单（§3.13 生命周期行）。

        `_active` 只由三处写入：**构造期 `Lifecycle.initialize` 的初始写入**、
        **引擎的激活传播**（`PityEngine.after_draw` 沿 `depends_on` 图写 `True`）、
        **本保底的退役动作**（`Lifecycle.deactivate` 写 `False`）。三者的写入面都是
        「某保底的命名空间」或其「零件命名空间」，故白名单取该两者之并集（引擎级：
        激活传播的目标可以是别的池的保底，故取 `engine.behaviors` 全集而非本池）。

        判两条：命名空间在白名单内、值为 `bool`（三处写入方分别写 `True` / `True` /
        `False`，无第四种取值）。**ISSUE-202**：构造期写入若不列入白名单，本不变式
        会对**每条**非 `depends_on` 保底在构造期写 `_active=True` 报假警报。

        白名单外的写入实测形态：`state.set('某个非保底命名空间', '_active', True)`。

        **判据的宽度（S11 审查收口 F8，2026-10-13）**：白名单取 `engine.behaviors`
        的**全集**（各保底命名空间 ∪ 各零件命名空间），比「本保底的退役动作」宽得多，
        故本层是四层里最松的一层：**「错误的写入方写进一个合法的保底命名空间」不被
        拦截**（例如引擎外的代码往别的池的保底里写 `_active=False`，只要该命名空间
        在白名单内即通过）。单池判据反而做不到这一点：激活传播的目标可以是别的池的
        保底，收窄到「本池」会对合法形态假警报（`test_engine_activation_propagation_is_whitelisted`
        即该形态）。故本层的判据面只覆盖「命名空间不在白名单内」与「值不是 bool」两条。
        """
        allowed = set()
        for name, bh in (getattr(engine, 'behaviors', None) or {}).items():
            allowed.add(name)
            allowed.update(getattr(bh, '_namespaces', ()) or ())
        for ns, data in state.data.items():
            if _ACTIVE_KEY not in data:
                continue
            value = data[_ACTIVE_KEY]
            if ns not in allowed:
                raise InvariantError(
                    f"[生命周期层] 保底 '{ns}' 键 {_ACTIVE_KEY!r}：期望 该命名空间在"
                    f"生命周期层的写入面内（保底命名空间或零件命名空间，"
                    f"白名单 {sorted(allowed)}）；实际 命名空间 '{ns}' 不在白名单内"
                    f"（值 {value!r}）（§3.13 生命周期行：只允许构造期 initialize / "
                    f"引擎激活传播 / 本保底退役动作三处写入）")
            if not isinstance(value, bool):
                raise InvariantError(
                    f"[生命周期层] 保底 '{ns}' 键 {_ACTIVE_KEY!r}：期望 bool"
                    f"（三处写入方写 True / True / False），实际 {value!r}"
                    f"（{type(value).__name__}）（§3.13 生命周期行）")


def _pool_pities(engine, pool_id: str) -> Sequence[Tuple[str, object]]:
    """本池的保底列表 `[(name, behavior)]`（引擎的公开成员面）。

    经 `PityEngine.get_behaviors_for_pool` 取，**不自行遍历** `pity_defs` /
    `behaviors` 过滤——池内序与池成员判定归引擎（P82-1 的 `_pool_order`）。
    """
    return list(engine.get_behaviors_for_pool(pool_id))


def _exemption_options(spec, dist: Mapping[str, float], engine,
                       pities) -> Sequence[Tuple[str, float]]:
    """可达的 Σp 取值集 `[(来源说明, 期望值)]`（§3.12.1 归一性行的两支）。

    - `('无 F 参与（F 型算子未触发）', 1.0)`——非 F 算子一律守恒
      （§3.12.1 的转移族 `Σδ = 0`，S10-1 的 `test_transfer_step_preserves_total`），
      故无 F 触发时管道输出恒为 1。
    - 每个 F 型算子一条 `('保底 X 的 F 零件豁免槽位 [...]，其上质量 m', 1 + m)`——
      **逐零件分开列，不取并集**：并集会在「池内多个 F 型算子、只有其中一个触发」
      时给出不可达的期望值（实测形态：`hard(scope='sr')` 与 `hard(scope='r')` 同池、
      后者阈值未到，输出 Σ = 1.009，而并集式 `E = {ssr 槽} ∪ {ssr 槽, sr 槽}` 给出
      1 + 1.009 = 2.009 的假警报）。

    **ISSUE-903（S11 审查收口 F2，2026-10-13，M2 的反转义务，强制）**：本函数的
    F 零件选项（`1 + m`）**只对 M1 的槽位级管道成立**。S8 起 `_apply_delta`
    （§3.9.2）无条件归一化，且转移族恒有 `Σδ = 0` 使其退化为恒等，故 S8 起管道
    输出恒有 `Σp ≡ 1`（§3.9.5）；届时本选项对**合法配置**抛假警报（ISSUE-903 的
    反向失配：M1 与本式相符、M2 与之相悖，两个里程碑的期望值相反）。**S8 起此处
    须把 F 零件选项整体移除、只留 `1.0`**：`_EXEMPTION_PART_TYPES` 的遍历、
    `_DrawProbe` 的构造与 `_higher_rarity_keys` 的调用同批删除，`options` 退化为
    单元素列表（`_check_distribution` 的判据随之成为恒等断言 `Σp = 1`，其 docstring
    的「有限取值集取一」段与本条同批改写；`tests/core/test_pity_invariant_checker.py`
    的分布层正例与 `tests/core/test_pity_invariants.py` 的三处断言也按 S8-6 ⑤
    同步改写）。该义务由
    `test_issue_903_f_part_options_track_pipeline_normalization` 作**里程碑绊线**
    机械把守：它以「真管道的输出 Σ 是否已归一化」为判据（不扫 S8 的实现符号），
    S8 落地而本选项未删即转红。

    **豁免集与 S10-1 共用同一生产助手**：`_higher_rarity_keys`（`pity_modifier.py`
    模块级，`HardModifier` / `NotOwnedModifier` 共用）是豁免集的唯一实现，S10-1 的
    `exempted` 与生产算子的豁免循环都取自它。本层**不另写一份谓词**（S10-2 收口已
    提出「镜像谓词与生产判据各写一份口径会持续分叉」的隐患）。

    F 型集合 = 本池各保底的 `modifiers` 中属于 `_EXEMPTION_PART_TYPES` 者，scope
    取该零件自己的 `_scope`；`DrawInfo` 由池 spec 与引擎的稀有度表重建，与
    `PityEngine.before_draw` 构造的那份同源（`scope_cards` / `card_to_slot` /
    `rarity_rank` 三项即该助手读的全部字段）。
    """
    draw = DrawInfo(
        pool_id='', pool_instance_id='', reward_id='', reward_rarity='',
        is_featured=False,
        scope_cards=spec.scope_cards,
        featured_cards=spec.featured_cards,
        scope_slots=spec.scope_slots,
        featured_slots=spec.featured_slots,
        card_to_slot=spec.card_to_slot,
        base_probabilities=dict(dist),
        rarity_rank=getattr(engine, '_rarity_rank', None) or {},
    )
    probe = _DrawProbe(draw)
    options: list = [('无 F 参与（F 型算子未触发）', 1.0)]
    for name, bh in pities:
        for mod in (getattr(bh, '_modifiers', None) or ()):
            if not isinstance(mod, _EXEMPTION_PART_TYPES):
                continue
            keys = tuple(dict.fromkeys(_higher_rarity_keys(probe, mod._scope)))
            mass = float(sum(dist.get(k, 0.0) for k in keys))
            options.append((
                f"保底 '{name}' 的 F 零件豁免槽位 {sorted(keys)}，其上质量 {mass!r}",
                1.0 + mass))
    return options
