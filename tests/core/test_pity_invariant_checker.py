"""P64 S11：不变式运行时校验的**专属**测试（§3.13）。

**被测对象** = `core/invariants.py` 的 `InvariantChecker`（运行时校验器）**加**它的
两个调用点（`PityEngine.before_draw` / `after_draw` 各一行，ISSUE-003）。与
`tests/core/test_pity_invariants.py`（S10-1）**被测对象不同**：那份文件的被测对象是
**管道本身**（§七 S10-1 明写「两者被测对象不同，不得混用」），本文件只在需要
「生产管道的真实输出」时借它当输入源（例如正例的 `Σ = 1.009` 由真引擎跑出来，
不是手捏的）。

**四层与本文件的用例面**（判据原文出处逐条标注在用例 docstring 内）：

| 层 | 入口 | 用例组 |
|----|------|--------|
| 分布 | `check_after_before_draw` | `TestDistributionLayer` |
| 状态 | `check_after_after_draw` | `TestStateLayer` |
| 生命周期 | `check_after_after_draw` | `TestLifecycleLayer` |
| 增量 | `check_delta`（**M1 不接调用点**） | `TestDeltaLayer` |

**与 S10-1 的判据口径关系**：豁免集一律取自生产助手 `_higher_rarity_keys`
（`pity_modifier.py` 模块级，S10-1 的 `exempted` 与生产算子的豁免循环共用它），
**不另写一份谓词**；归一性在运行期入口取**可达取值集**（无 F 触发时 `Σp = 1`，
各 F 零件各自的 `Σp = 1 + Σp(该零件的豁免槽位)`），与 S10-1 的管道判据同形，
理由与被登记的盲区见 `InvariantChecker._check_distribution` 的 docstring。

**开关来源**：本文件的夹具是 `enabled=True` 的**唯一**产出源（本期不加 env 字段 /
CLI 开关 / TOML 项）；生产路径传 `invariants=None`。
"""

import ast
import inspect
import pickle
import random

import pytest

from gacha_simulator.core import invariants as invariants_mod
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.invariants import InvariantChecker, InvariantError
from gacha_simulator.core.pity import (
    _EXTERNAL_STATE_KEYS,
    PityEngine,
    PityState,
    PoolPitySpec,
)

# ══════════════════════════════════════════════════════════════════
# 一、夹具：合法配置 + 三要素断言助手
# ══════════════════════════════════════════════════════════════════

_POOL = 's11_pool'
_RANK = {'ssr': 0, 'sr': 1, 'r': 2}

#: 基础分布（Σ = 1.0）。`hard(scope='sr')` 触发后：目标集（sr）绝对赋值到 1.0、
#: 更低稀有度（r）归零、更高稀有度（ssr 两槽）原值保留 —— 输出
#: `{'ssr_featured': 0.003, 'ssr': 0.006, 'sr': 1.0, 'r': 0.0}`、**Σ = 1.009**，
#: 与 §3.12.1 实测例（`{ssr:0.006, ssr_featured:0.003, sr:1.0, r:0.0}`，Σ = 1.009）
#: 逐位同形（池形与 S10-1 的 `STANDARD_SHAPE` 同源）。
_BASE = {'ssr_featured': 0.003, 'ssr': 0.006, 'sr': 0.091, 'r': 0.9}

#: 被 F 豁免的槽位集（`_higher_rarity_keys` 的返回值：rank < rank('sr') 的稀有度
#: 之全部卡投影到槽位名）。**写死字面量**，不写成「与助手比对」，理由同 S10-1 的
#: `test_hard_below_top_rarity_scope_aware_shape`：若助手自身坏掉，期望值与生产值
#: 会同向偏移，只有字面集能钉住它。
_EXEMPT = ('ssr_featured', 'ssr')


def _spec(pity_names=('p_hard',)) -> PoolPitySpec:
    return PoolPitySpec(
        pity_names=list(pity_names),
        scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_std',),
                     'r': ('r_std',)},
        featured_cards={'ssr': ('ssr_up',)},
        scope_slots={'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)},
        featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)},
        card_to_slot={'ssr_up': 'ssr_featured', 'ssr_std': 'ssr',
                      'sr_std': 'sr', 'r_std': 'r'},
        featured_ids={'ssr_up'},
        ssr_ids={'ssr_up', 'ssr_std'},
    )


def _wide_spec(pity_names) -> PoolPitySpec:
    """宽池形：`sr` 也有 featured 卡（使 `sr` 上的目标集集中型算子可触发）。"""
    return PoolPitySpec(
        pity_names=list(pity_names),
        scope_cards={'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_up', 'sr_std'),
                     'r': ('r_std',)},
        featured_cards={'ssr': ('ssr_up',), 'sr': ('sr_up',)},
        scope_slots={'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr', 'sr_featured'),
                     'r': ('r',)},
        featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr_featured',),
                        'r': ('r',)},
        card_to_slot={'ssr_up': 'ssr_featured', 'ssr_std': 'ssr',
                      'sr_up': 'sr_featured', 'sr_std': 'sr', 'r_std': 'r'},
        featured_ids={'ssr_up', 'sr_up'},
        ssr_ids={'ssr_up', 'ssr_std'},
    )


def _engine(invariants=None, *, threshold=1, pities=None, state=None, spec=None):
    """造一台引擎。`threshold=1` 时 `hard(scope='sr')` 在**首次** `before_draw` 即触发
    （`CounterTracker.advance` 在 Modifier 链之前把 counter 由 0 推到 1）。"""
    state = PityState() if state is None else state
    defs = pities if pities is not None else [
        PityDef(name='p_hard', btype='hard', scope='sr', threshold=threshold)]
    if spec is None:
        spec = _spec(tuple(d.name for d in defs))
    engine = PityEngine({_POOL: spec}, defs,
                        state=state, rarity_rank=_RANK, invariants=invariants)
    return engine, state


def _assert_three_elements(message: str, name: str, key: str) -> None:
    """异常信息的三要素（§六 S11 负例条）：**保底名 + 键 + 期望值 / 实际值**。"""
    assert name in message, f'异常信息缺保底名 {name!r}：{message}'
    assert key in message, f'异常信息缺键 {key!r}：{message}'
    assert '期望' in message and '实际' in message, f'异常信息缺期望/实际：{message}'


class _CountingChecker(InvariantChecker):
    """替身：只记录两个入口的调用次数。

    **刻意不调 `super()`**：ISSUE-003 的两条验收断言的对象是「入口**被实际调用**」
    （不得只断言「类存在」），与真实判据解耦后，调用点被删掉时本替身的计数必为 0。
    """

    def __init__(self, enabled: bool = True):
        super().__init__(enabled)
        self.before_calls = 0
        self.after_calls = 0

    def check_after_before_draw(self, pool_id, dist, engine) -> None:
        self.before_calls += 1

    def check_after_after_draw(self, pool_id, state, engine) -> None:
        self.after_calls += 1


# ══════════════════════════════════════════════════════════════════
# 二、调用点（ISSUE-003 的两条强制验收 + 默认关闭态）
# ══════════════════════════════════════════════════════════════════

class TestCallSites:
    """`PityEngine.before_draw` / `after_draw` 各一行的调用点（§3.13「调用点与构造源」段）。"""

    def test_enabled_checker_entries_are_actually_called(self):
        """验收断言 ①：`invariants=InvariantChecker(enabled=True)` 的替身跑一次
        `before_draw` / `after_draw` 后，**两个入口各被实际调用至少一次**。"""
        checker = _CountingChecker(enabled=True)
        engine, state = _engine(invariants=checker)

        engine.before_draw(_POOL, state, dict(_BASE))
        engine.after_draw(_POOL, state, 'sr_std')

        assert checker.before_calls >= 1, (
            'before_draw 的调用点未生效：check_after_before_draw 零调用')
        assert checker.after_calls >= 1, (
            'after_draw 的调用点未生效：check_after_after_draw 零调用')

    def test_default_none_builds_no_instance_and_calls_nothing(self, monkeypatch):
        """验收断言 ②：`invariants=None`（默认关闭态）时引擎**不建实例**、两个入口
        **零调用**（生产路径零开销的依据）。

        零调用的断言面用类级探针（而非「实例上的计数」）：此刻根本没有实例，
        只有把类方法本身换掉才能观察到「有没有人被调」。探针的**非恒真**由本用例
        尾部的阳性对照钉住（同一探针在 `enabled=True` 的引擎上必须记录到调用）。
        """
        seen = []
        monkeypatch.setattr(InvariantChecker, 'check_after_before_draw',
                            lambda self, pool_id, dist, engine: seen.append('before'))
        monkeypatch.setattr(InvariantChecker, 'check_after_after_draw',
                            lambda self, pool_id, state, engine: seen.append('after'))

        # ── 默认关闭态：不建实例、零调用 ──
        engine, state = _engine(invariants=None)
        assert engine._invariants is None, '默认态须不建实例（挂载字段为 None）'
        engine.before_draw(_POOL, state, dict(_BASE))
        engine.after_draw(_POOL, state, 'sr_std')
        assert seen == [], f'invariants=None 时入口被调用：{seen}'

        # ── 阳性对照：同一探针在启用态的引擎上必须记录到两个入口 ──
        enabled_engine, enabled_state = _engine(
            invariants=InvariantChecker(enabled=True))
        enabled_engine.before_draw(_POOL, enabled_state, dict(_BASE))
        enabled_engine.after_draw(_POOL, enabled_state, 'sr_std')
        assert seen == ['before', 'after'], (
            f'探针自身失灵（启用态下也记录不到调用）：{seen}')


# ══════════════════════════════════════════════════════════════════
# 三、开关载体 = 构造形参、随实例进 pickle（ISSUE-945）
# ══════════════════════════════════════════════════════════════════

class TestSwitchCarrier:
    """`enabled` 是**构造形参**、存为实例字段、随实例进 pickle（禁模块级全局）。"""

    @pytest.mark.parametrize('enabled', [True, False])
    def test_enabled_flag_survives_pickle_round_trip(self, enabled):
        """pickle round-trip 后 `enabled` 字段相等。

        **该用例由 S7b 移入本步**（GATE-check-3，2026-10-09）：S7b 排在 S11 之前、
        其时本类尚不存在；`tests/service/test_batch_simulator.py` 的 pickle 段落已
        明写它不在 S7b（该文件里没有本类的任何引用，`-k pickle` 不含本用例）。
        """
        restored = pickle.loads(pickle.dumps(InvariantChecker(enabled=enabled)))
        assert restored.enabled is enabled, (
            f'pickle round-trip 后 enabled 由 {enabled!r} 变为 {restored.enabled!r}')
        assert type(restored) is InvariantChecker

    def test_checker_rides_engine_pickle_and_still_fires(self):
        """挂在 `engine._invariants` 上的实例随**引擎**进 pickle 图（ISSUE-945 的
        理由：`run_batch_parallel` 把整个 `env` 序列化给 worker，故 spawn 出的
        worker 自动继承该设置）——还原后 `enabled` 仍为 True 且入口照常被调用。"""
        checker = _CountingChecker(enabled=True)
        engine, _state = _engine(invariants=checker)
        restored = pickle.loads(pickle.dumps(engine))

        assert restored._invariants is not None
        assert restored._invariants.enabled is True
        state = PityState()
        restored.before_draw(_POOL, state, dict(_BASE))
        restored.after_draw(_POOL, state, 'sr_std')
        assert restored._invariants.before_calls >= 1
        assert restored._invariants.after_calls >= 1

    def test_invariants_module_does_not_import_pity(self):
        """ISSUE-003 的硬约束：checker 自身**不 import `pity`**（`pity.py` 单向
        import 本模块，反向即成环）。按 AST 扫 import 节点，`pity_modifier` /
        `pity_primitives` / `pity_tracker` 是允许的（叶子层与实现层，无环）。"""
        tree = ast.parse(inspect.getsource(invariants_mod))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or '')
        offending = [m for m in modules
                     if m.split('.')[-1] == 'pity'
                     or m.endswith('core.pity')]
        assert not offending, f'checker 引用了编排层 pity：{offending}'


# ══════════════════════════════════════════════════════════════════
# 四、分布层（§3.13 分布行 / §3.12.1 归一性 + 非负性行）
# ══════════════════════════════════════════════════════════════════

class TestDistributionLayer:

    def test_legal_hard_sr_config_no_alarm(self):
        """**正例**（§六 S11 明列）：`hard(scope='sr')` 的合法配置、Σ = 1.009，
        `check_after_before_draw` **不得报错**（归一性按 scope 感知口径）。

        同时钉住「该 Σ 由生产管道跑出来」这一点：走真引擎的 `before_draw`（它内部
        就调用本入口），断言输出与 §3.12.1 的实测形态逐位相同。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        assert probs == {'ssr_featured': 0.003, 'ssr': 0.006, 'sr': 1.0, 'r': 0.0}, (
            f'生产管道输出与 §3.12.1 的实测形态不符：{probs}')
        assert sum(probs.values()) == pytest.approx(1.009, abs=invariants_mod.TOL)
        # 显式再走一次入口（不依赖引擎调用的间接性）
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_f_not_fired_total_one_is_accepted(self):
        """无 F 参与的抽次：`Σp = 1` 必须被接受。

        §3.12.1 归一性行的例外条以「**参与本次** `before_draw` 的算子含 F 型」为
        前提，S10-1 的同名管道判据也分两支（`if not fired_f: Σ == 1`）。本用例即该
        分支的运行期守卫：`threshold=99` 使 F 全程不触发，输出 Σ = 1.0，而豁免槽位
        上仍持有 0.009 的质量——若本层写成单式 `Σp = 1 + Σp(豁免槽位)`，本条必红
        （对合法配置的假警报，正是 ISSUE-011 要消除的形态）。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker, threshold=99)
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_negative_probability_raises(self):
        """**负例 ①**（§六 S11）：人为把一个卡概率改为负值 → 必须抛错，且异常信息
        含保底名 + 键 + 期望 / 实际三要素（§3.12.1 非负性行）。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['sr'] = -0.5
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_before_draw(_POOL, broken, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', "'sr'")

    def test_total_beyond_exemption_raises(self):
        """**负例 ②**（§六 S11）：把 Σ 改到 1.2（**超出 F 豁免量**）→ 必须抛错，
        三要素齐备（§3.12.1 归一性行的 scope 感知式）。

        改的是 `r` 槽（已被 F 归零）：全部分量非负，故只有归一性一条判据能拦下它。
        期望值即 `1 + 0.009 = 1.009`，豁免槽位集写死为 `_EXEMPT`。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['r'] = 0.2
        assert sum(broken.values()) == pytest.approx(1.209, abs=1e-9)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_before_draw(_POOL, broken, engine)
        message = str(excinfo.value)
        _assert_three_elements(message, 'p_hard', "'Σp'")
        assert '1.009' in message, f'期望值须含豁免量：{message}'
        assert '1.209' in message, f'实际值缺失：{message}'
        for key in _EXEMPT:
            assert key in message, f'豁免槽位 {key!r} 未出现在异常信息内：{message}'

    def test_multiple_f_parts_partial_fire_no_alarm(self):
        """池内**多个** F 型零件、只有其中一个触发时不得假警报（可达取值集逐零件列）。

        实测形态（2026-10-13）：`hard(scope='sr')`（阈值 1，触发）与
        `hard(scope='r')`（阈值 99，全程不触发）同池，输出
        `{'ssr_featured': 0.003, 'ssr': 0.006, 'sr_featured': 0.1099, 'sr': 0.8901}`、
        Σ = 1.009。若把两个零件的豁免集取**并集**，期望值会变成
        `1 + (0.009 + 1.0) = 2.009`（不可达）→ 对合法配置假警报；本用例钉住
        「逐零件分列」这一形态。
        """
        checker = InvariantChecker(enabled=True)
        defs = [PityDef(name='h_sr', btype='hard', scope='sr', threshold=1),
                PityDef(name='h_r', btype='hard', scope='r', threshold=99)]
        engine, state = _engine(invariants=checker, pities=defs)
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        assert sum(probs.values()) == pytest.approx(1.009, abs=invariants_mod.TOL)
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_transfer_after_f_keeps_exemption_mass(self):
        """排在 F 之后的转移算子把质量搬进豁免槽位时，Σ 仍等于 `1 + Σp(豁免槽位)`。

        实测形态（2026-10-13，见 `_check_distribution` 的 docstring）：同池
        `hard(scope='sr')` 与 `soft(scope='ssr')` 并存——后者 scope 的 rank 更小、
        **排在前者之前**执行（`_resolve_order` 的首键是稀有度 rank），故 F 之后
        不再有算子改动豁免集，连跑 6 抽的 Σ 依次为 1.209 / 1.409 / …，
        逐抽等于 `1 + Σp(ssr 两槽)`。
        """
        checker = InvariantChecker(enabled=True)
        defs = [PityDef(name='h_sr', btype='hard', scope='sr', threshold=1),
                PityDef(name='s_ssr', btype='soft_interval', scope='ssr',
                        soft_start=1, soft_end=9, soft_increment=20.0)]
        engine, state = _engine(invariants=checker, pities=defs)
        totals = []
        for _ in range(4):
            probs = engine.before_draw(_POOL, state, dict(_BASE))
            totals.append(sum(probs.values()))
            exempt_mass = sum(probs.get(k, 0.0) for k in _EXEMPT)
            assert totals[-1] == pytest.approx(1.0 + exempt_mass,
                                               abs=invariants_mod.TOL)
            engine.after_draw(_POOL, state, 'r_std')
        assert totals[0] > 1.0 and totals == sorted(totals), (
            f'软保底推进须让 Σ 单调抬升，实测 {totals}')

    def test_disabled_checker_is_a_no_op(self):
        """`enabled=False`（构造默认值）时四层判据一律不跑——生产关闭态的判据面。"""
        checker = InvariantChecker()
        assert checker.enabled is False
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['sr'] = -0.5
        checker.check_after_before_draw(_POOL, broken, engine)
        checker.check_delta(_POOL, {'a': 0.1}, {'a': -1.0})


# ══════════════════════════════════════════════════════════════════
# 五、状态层（§3.12.1 状态键合法行 / §3.13 状态行的单调性末句）
# ══════════════════════════════════════════════════════════════════

class TestStateLayer:

    def test_legal_draw_sequence_passes(self):
        """合法配置连跑若干抽，状态层与生命周期层全程不报错（生产形态的阳性对照）。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        for reward in ('sr_std', 'r_std', 'ssr_up', 'r_std'):
            engine.before_draw(_POOL, state, dict(_BASE))
            engine.after_draw(_POOL, state, reward)
        assert state.data['p_hard']['_active'] is True

    def test_undeclared_state_key_raises(self):
        """**负例（状态层）**：运行期出现未声明键 → 必须抛错，三要素齐备。

        §3.12.1 状态键合法行的「Tracker 写入的键在其自己声明的键集内」——比对集
        = `Pity._declared_keys`（ISSUE-501）。`'countr'` 是 `'counter'` 的典型拼错，
        正是该行要拦的静默失效形态。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        engine.before_draw(_POOL, state, dict(_BASE))
        engine.after_draw(_POOL, state, 'sr_std')

        state.set('p_hard', 'countr', 3)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_after_draw(_POOL, state, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', 'countr')

    def test_external_state_key_is_whitelisted(self):
        """`selected_card` 在声明集之外却合法（§3.1.1 的 L4 例外 2：策略层
        `NonDrawAction` 与 `_build_pity_state_init` 写它、无零件声明它）——白名单
        不留则该键在真配置上必报假警报。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        engine.after_draw(_POOL, state, 'sr_std')
        state.set('p_hard', 'selected_card', 'sr_std')
        checker.check_after_after_draw(_POOL, state, engine)

    def test_part_namespace_foreign_write_raises(self):
        """零件命名空间（`X_soft`）内除 `_active` 外的写入 → 必须抛错。

        口径同 S10-1 的 `test_part_namespace_writes_are_only_active`：
        `NamespaceTracker.state_keys()` 为空元组（§3.1.1），该命名空间的 `_active`
        由 `Lifecycle.initialize` 的推广作用域写入（ISSUE-407）。**零件命名空间由
        三个 `_soft` 复合类型产出**（`NamespaceTracker(namespace=f'{name}_soft')`），
        故本用例取 `rotating_soft`（`soft_interval` 不产该命名空间）。
        """
        checker = InvariantChecker(enabled=True)
        defs = [PityDef(name='p_rotsoft', btype='rotating_soft', scope='ssr',
                        soft_start=1, soft_end=2, soft_increment=10.0)]
        engine, state = _engine(invariants=checker, pities=defs)
        engine.after_draw(_POOL, state, 'ssr_std')          # 基线：不报错

        part_ns = 'p_rotsoft_soft'
        assert set(state.data.get(part_ns) or {}) == {'_active'}, (
            f'零件命名空间须只含生命周期层的 `_active`，实测 {state.data}')

        state.set(part_ns, 'counter', 1)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_after_draw(_POOL, state, engine)
        _assert_three_elements(str(excinfo.value), 'p_rotsoft', 'counter')

    def test_counter_decrease_raises_and_reset_is_accepted(self):
        """计数型计数器单调不降，「除重置外」的口径 = **归零**（§3.13 状态行末句）。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        state.set('p_hard', 'counter', 5)
        checker.check_after_after_draw(_POOL, state, engine)   # 首次观测：无基线

        state.set('p_hard', 'counter', 0)
        checker.check_after_after_draw(_POOL, state, engine)   # 重置归零：合法

        state.set('p_hard', 'counter', 4)
        checker.check_after_after_draw(_POOL, state, engine)   # 回升：合法
        state.set('p_hard', 'counter', 3)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_after_draw(_POOL, state, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', 'counter')

    def test_counter_memory_is_isolated_per_state_object(self):
        """单调性记忆按 `state` 对象身份隔离（worker 内同一引擎跨场复用、每场一个新
        state；跨场沿用旧记忆会让「新场初值 < 上场终值」误报）。"""
        checker = InvariantChecker(enabled=True)
        engine, _ = _engine(invariants=checker)
        first = PityState()
        first.set('p_hard', 'counter', 9)
        checker.check_after_after_draw(_POOL, first, engine)

        second = PityState()
        second.set('p_hard', 'counter', 2)
        checker.check_after_after_draw(_POOL, second, engine)   # 不报错


# ══════════════════════════════════════════════════════════════════
# 六、生命周期层（§3.13 生命周期行 / ISSUE-202）
# ══════════════════════════════════════════════════════════════════

class TestLifecycleLayer:

    def test_active_outside_whitelist_raises(self):
        """**负例 ③**（§六 S11）：在**白名单以外**写 `_active` → 必须抛错，三要素齐备。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        engine.after_draw(_POOL, state, 'sr_std')

        state.set('ghost_pity', '_active', True)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_after_draw(_POOL, state, engine)
        _assert_three_elements(str(excinfo.value), 'ghost_pity', '_active')

    def test_active_non_bool_raises(self):
        """`_active` 的值域是 bool（三处写入方分别写 True / True / False）。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        engine.after_draw(_POOL, state, 'sr_std')

        state.set('p_hard', '_active', 1)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_after_draw(_POOL, state, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', '_active')

    def test_engine_activation_propagation_is_whitelisted(self):
        """第二处合法写入方：**引擎的激活传播**（`depends_on`）把 `_active=True` 写进
        依赖方命名空间——该命名空间本无 `_active`（`DependentActive.initialize` 是
        空实现），若白名单只认「构造期写过 `_active` 的命名空间」即误报。"""
        checker = InvariantChecker(enabled=True)
        defs = [
            PityDef(name='p_src', btype='hard', scope='ssr', threshold=1),
            PityDef(name='p_dep', btype='hard', scope='sr', threshold=1,
                    depends_on='p_src'),
        ]
        engine, state = _engine(invariants=checker, pities=defs)
        assert state.get('p_dep', '_active', False) is False, (
            'DependentActive 的构造期 initialize 不写 `_active`，本用例的前提')

        engine.before_draw(_POOL, state, dict(_BASE))
        engine.after_draw(_POOL, state, 'ssr_up')       # p_src 触发 → 传播

        assert state.get('p_dep', '_active', False) is True, '激活传播未发生，用例无观测对象'
        checker.check_after_after_draw(_POOL, state, engine)


# ══════════════════════════════════════════════════════════════════
# 七、增量层（§3.12.1 增量合法性行；M1 只实现、不接调用点）
# ══════════════════════════════════════════════════════════════════

class TestDeltaLayer:

    def test_legal_delta_passes(self):
        checker = InvariantChecker(enabled=True)
        checker.check_delta(_POOL, {'sr': 0.4, 'r': 0.6}, {'sr': -0.4, 'r': 0.4})

    def test_negative_combined_probability_raises(self):
        """`p + δ ≥ 0`（§3.12.1 增量合法性行）——按 `p` 与 `δ` 逐位相加判。"""
        checker = InvariantChecker(enabled=True)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_delta(_POOL, {'sr': 0.1, 'r': 0.9}, {'sr': -0.5})
        _assert_three_elements(str(excinfo.value), _POOL, "'sr'")

    def test_zero_delta_on_support_raises(self):
        """δ 在 p 的支撑上不全为 0（触发的步不得是静默空操作）。"""
        checker = InvariantChecker(enabled=True)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_delta(_POOL, {'sr': 0.1, 'r': 0.9}, {'sr': 0.0, 'r': 0.0})
        _assert_three_elements(str(excinfo.value), _POOL, "'δ'")

    def test_empty_support_is_skipped(self):
        """输入分布无支撑时该式无判别力（对齐 S10-1 的同名断言前置），不报错。"""
        checker = InvariantChecker(enabled=True)
        checker.check_delta(_POOL, {'sr': 0.0, 'r': 0.0}, {'sr': 0.0, 'r': 0.0})

    def test_delta_entry_is_not_wired_into_the_two_engine_entries(self, monkeypatch):
        """**M1 硬约束**：增量层**不复用**两个入口（§3.13「增量层的入口与调用点」段：
        两个入口的第二实参只有分布、取不到该步的 δ），调用点随 S8-6 落在
        `_apply_delta()` 内部。本用例把 `check_delta` 换成「一被调用就炸」的探针，
        跑一遍引擎的两个入口：探针不得被命中。"""
        hits = []

        def _probe(self, pool_id, dist, delta):
            hits.append((pool_id, dict(dist), dict(delta)))

        monkeypatch.setattr(InvariantChecker, 'check_delta', _probe)
        engine, state = _engine(invariants=InvariantChecker(enabled=True))
        engine.before_draw(_POOL, state, dict(_BASE))
        engine.after_draw(_POOL, state, 'sr_std')
        assert hits == [], f'M1 不得把增量层接进两个入口，实测命中 {hits}'

        # 阳性对照：探针本身可用（直接调用即命中）
        InvariantChecker(enabled=True).check_delta(_POOL, {'sr': 1.0}, {'sr': 0.0})
        assert len(hits) == 1


# ══════════════════════════════════════════════════════════════════
# 八、全 preset 面的假警报扫描（校验器可用性的前提）
# ══════════════════════════════════════════════════════════════════

#: 每个 registry 类型一份最小合法 `PityDef` 的公共取值。
_PRESET_COMMON = dict(soft_start=1, soft_end=3, soft_increment=10.0, threshold=2,
                      counter_init=1, guaranteed_init=True, fate_points_init=1,
                      selected_card_init='sr_up', fate_threshold=2,
                      cr_counter_threshold=3, cr_base_rate=0.0, max_triggers=0)

#: 槽位 -> 代表卡（抽样反查表；与 `_wide_spec` 的 `card_to_slot` 互逆）。
_SLOT_TO_CARD = {'ssr_featured': 'ssr_up', 'ssr': 'ssr_std',
                 'sr_featured': 'sr_up', 'sr': 'sr_std', 'r': 'r_std'}


def _preset_btype_list():
    from gacha_simulator.core.pity import BEHAVIOR_REGISTRY
    return sorted(BEHAVIOR_REGISTRY)


@pytest.mark.parametrize('btype', _preset_btype_list())
def test_every_registry_type_runs_without_false_alarm(btype):
    """**校验器可用性的前提**：11 个 registry 类型各跑一段抽卡序列，四层判据全程
    不得报错。

    「生产关闭」不等于「启用即炸」：本层若对合法配置假警报（ISSUE-011 的形态），
    它就只是噪声源。故对每个类型单独造一台引擎（一池一保底，避免组合规则的干扰），
    以固定种子抽 25 抽（奖励按调整后的分布抽样，与「先定分布、再抽奖励」的引擎
    同形），断言不抛 `InvariantError`。
    """
    kw = dict(_PRESET_COMMON)
    # `targeted` / `rotating_inverse` 的 scope 取 ssr（前者靠 UP 卡触发，后者方向相反）
    kw['scope'] = 'ssr' if btype in ('targeted', 'rotating_inverse') else 'sr'
    defs = [PityDef(name='p', btype=btype, **kw)]
    engine, state = _engine(invariants=InvariantChecker(enabled=True), pities=defs,
                            spec=_wide_spec(['p']))

    rng = random.Random(7)
    for _ in range(25):
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        roll = rng.random()
        acc = 0.0
        pick = 'r'
        for slot, value in probs.items():
            acc += value
            if roll <= acc:
                pick = slot
                break
        engine.after_draw(_POOL, state, _SLOT_TO_CARD[pick])
    assert state.get('p', '_active') is True


# ══════════════════════════════════════════════════════════════════
# 九、外部白名单的镜像守卫（ISSUE-501 式的「一处声明」纪律）
# ══════════════════════════════════════════════════════════════════
def test_external_state_keys_mirror_matches_engine():
    """`invariants._EXTERNAL_STATE_KEYS` 与编排层 `pity._EXTERNAL_STATE_KEYS` 逐元素
    相同。

    `core/invariants.py` 受 ISSUE-003 的「不 import `pity`」约束、无法引用该常量，
    故在本地重写了一份；**漂移由本用例拦截**（不是靠人眼），任何一侧增删键即红。
    """
    assert invariants_mod._EXTERNAL_STATE_KEYS == _EXTERNAL_STATE_KEYS, (
        f'外部写入键白名单两处不一致：invariants='
        f'{sorted(invariants_mod._EXTERNAL_STATE_KEYS)} / '
        f'pity={sorted(_EXTERNAL_STATE_KEYS)}')
    assert _EXTERNAL_STATE_KEYS == frozenset({'selected_card'})
