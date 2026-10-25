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
| `check_delta(pool_id, dist, delta)`（**S8-6 已接线**） | 增量层 | 单步的 `p` 与 `δ` |

分布层归前一个入口、状态与生命周期两层归后一个入口，按**实参可得性**分：`dist`
只在前者的实参面内，`state` 只在后者的实参面内（§3.13 只给了两个入口的签名，未
逐层指派入口，该分工是本模块的定稿）。增量层**不复用**这两个入口的理由见 §3.13
的「增量层的入口与调用点」段：两个入口的第二实参只有分布，取不到该步的 δ；故它
自带第三个入口。**该入口的调用点在 S8-6 落地（与计划原文不同，见下）**。

**增量层调用点的最终形态（S8-6，2026-10-14，与原写不符）**：计划 §3.13 写「由
`_apply_delta()` 内部在 `p` 与 `δ` 同时在手处调用」，而 S8-1 已把 `_apply_delta`
迁到叶子层 `pity_primitives.py`、签名收为 `(dist, d)`，**取不到 `pool_id` 与校验器**，
故该写法不可执行（S8 审查 F5 登记，S8-6 裁决）。三条候选的取舍与理由写在
`Pity.before_draw` 的内循环注记：**取「调用点移到骨架内循环」**，校验器经
`PityContext.invariants` 进骨架（引擎只在 `before_draw` 写该字段，`get_probabilities`
按下方「四层覆盖边界」不写）。故本模块实例有**三**个可达路径：两个引擎入口 + 骨架
内循环里的增量层。

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

from typing import Dict, Mapping, Sequence, Tuple

from .pity_primitives import _EXTERNAL_STATE_KEYS


#: 概率断言容差（§3.12.1 归一性行的「容差 1e-12」）。
TOL = 1e-12

#: ~~`_EXEMPTION_PART_TYPES`（F 型算子集合：`HardModifier` / `NotOwnedModifier`）~~
#: **随 S8 删除**（ISSUE-903 的反转义务，2026-10-13 登记 / S8-2 落地）：F 型的
#: 「更高稀有度豁免」是 **M1 槽位级管道**的形态（`apply` 返回分布、输出 `Σ = 1 + m`），
#: S8 起 `_apply_delta` 无条件归一化，且转移族恒有 `Σδ = 0` 使其退化为恒等，故
#: 管道输出**恒有 `Σp ≡ 1`**（§3.9.5）。届时旧集合对合法配置抛假警报（M1 与本式
#: 相符、M2 与之相悖，两个里程碑的期望值相反）。
#: 同批删除的还有：本集合的遍历、`_DrawProbe` 载体（它的唯一消费者是
#: `_higher_rarity_keys`，该助手随 S8 的 Modifier 改写从 `pity_modifier.py` 删除）、
#: 以及 `_exemption_options`（退化为恒等断言 `Σp = 1`）。

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

    # ── 入口三：增量层（S8-6 已接线：调用点 = `Pity.before_draw` 的内循环）──

    def check_delta(self, pool_id: str, dist: Mapping[str, float],
                    delta: Mapping[str, float]) -> None:
        """增量层（§3.13 增量行 / §3.12.1 增量合法性行）：`p + δ ≥ 0`；δ 在 p 的
        支撑上不全为 0。

        **调用点（S8-6 落地，2026-10-14）**：`Pity.before_draw` 的内循环，在每个
        Modifier 的增量**作用到分布之前**调用（`p` 与 `δ` 同时在手、尚未归一化），
        校验器经 `PityContext.invariants` 进骨架。**M1 期只实现、不接调用点**
        （计划 §七 S11 的硬约束）：M1 槽位级管道没有增量表示，两个入口的第二实参只有
        分布、取不到该步的 δ。**计划原文「由 `_apply_delta()` 内部调用」不可执行**
        （S8-1 已把它迁到叶子层、签名收为 `(dist, d)`，取不到 `pool_id` 与校验器），
        三条候选的裁决与理由见 `Pity.before_draw` 的内循环注记。
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
        """非负性（§3.12.1 非负性行）+ 归一性（**S8 起的恒等断言 `Σp = 1`**）。

        **归一性口径在本入口已完成里程碑切换（ISSUE-903 的反转义务，S8-2 落地）**：

        - **M1（S8 前）** 是 scope 感知式 `Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，
          实现形态是「可达取值集取一」（`_exemption_options`：无 F 触发时的 `1`，
          与各 F 零件各自的 `1 + Σp(该零件的豁免槽位)`）：F 型的「绝对赋值 + 更高
          稀有度豁免」会造出 `Σ > 1`（实测 `hard(scope='sr')` 得 `Σ = 1.009`）。
        - **S8 起** 管道改用卡级增量：`_apply_delta`（§3.9.2）**无条件归一化**，而
          转移族恒有 `Σδ = 0` 使其退化为恒等（§3.9.5 的「`Σ(p + δ) ≠ 1`」行已记
          本条消失），故**管道输出恒有 `Σp ≡ 1`**。此时旧的取值集式对**合法配置**
          抛假警报（M1 与本式相符、M2 与之相悖，两个里程碑的期望值相反），故本判据
          退化为单式断言，`_exemption_options` / `_EXEMPTION_PART_TYPES` /
          `_DrawProbe` 同批删除。**这是一处口径的净简化，不是放宽**：S8 后 `Σp ≠ 1`
          一律是缺陷，没有「合法的例外值」需要枚举。

        **判据域的两条已知边界（S8 后仍成立）**：本入口按定义只看得见**输出分布**，
        看不见中间步（`Σ(p + δ) ≠ 1` 之类的步级异常由增量层 `check_delta` 在骨架内循环
        的调用点判，见本模块 docstring 的「增量层调用点的最终形态」段）；
        `PityEngine.get_probabilities`（只读查询入口）不经
        本入口，其输出不在判据面内（模块 docstring 的「四层覆盖边界」段）。
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

        # ── 归一性（S8 起：恒等断言）──
        total = float(sum(dist.values()))
        if abs(total - 1.0) <= TOL:
            return
        raise InvariantError(
            f"[分布层] 保底 {label} 键 'Σp'：期望 1.0；实际 {total!r}"
            f"（池 {pool_id!r} 的管道输出；§3.12.1 归一性行，S8 起的恒等口径）")

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
           计数器改成 *触发时重置*，即给本判据引入一种**新的重置来源**）。
           **该边界已于 2026-10-15 复核（`reset = "on_effective"` 落地）**：新的
           重置来源仍走 `Counter.reset()`（`CounterTracker._reset_condition` 命中
           `on_effective` 分支 → `commit` 调 `Counter.reset()`，写 0），故判据
           「下降且非 0 即破坏」**无需改动**；复核证据是
           `tests/core/test_pity_reset_on_effective.py::TestEngineEffectiveReset::test_invariant_checker_accepts_the_new_state_key`
           （`enabled=True` 下跑完整调度、含一次归零，不抛 `InvariantError`）。
           该条仍是**活耦合**：将来出现「重置到非零」的语义时须重判。
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
