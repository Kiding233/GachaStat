"""P64 S11：不变式运行时校验的**专属**测试（§3.13）。

**被测对象** = `core/invariants.py` 的 `InvariantChecker`（运行时校验器）**加**它的
两个调用点（`PityEngine.before_draw` / `after_draw` 各一行，ISSUE-003）。与
`tests/core/test_pity_invariants.py`（S10-1）**被测对象不同**：那份文件的被测对象是
**管道本身**（§七 S10-1 明写「两者被测对象不同，不得混用」），本文件只在需要
「生产管道的真实输出」时借它当输入源（正例的分布由真引擎跑出来，不是手捏的）。

**四层与本文件的用例面**（判据原文出处逐条标注在用例 docstring 内）：

| 层 | 入口 | 用例组 |
|----|------|--------|
| 分布 | `check_after_before_draw` | `TestDistributionLayer` |
| 状态 | `check_after_after_draw` | `TestStateLayer` |
| 生命周期 | `check_after_after_draw` | `TestLifecycleLayer` |
| 增量 | `check_delta`（**S8-6 已接线**，调用点 = 骨架内循环） | `TestDeltaLayer` |

**与 S10-1 的判据口径关系（S8-2 起）**：两边的归一性判据都是**恒等断言
`Σp = 1`**（ISSUE-903 的反转义务已落地：S8 起 `_apply_delta` 无条件归一化，M1 的
「scope 感知式 + F 零件可达取值集」整体消失，`_exemption_options` /
`_EXEMPTION_PART_TYPES` / `_DrawProbe` 三个符号随之删除）。理由见
`InvariantChecker._check_distribution` 的 docstring；本文件另有一条
`test_issue_903_reversal_is_landed` 把「机制已删、判据是恒等」这一反转钉住。

**开关来源**：本文件的夹具是 `enabled=True` 的**唯一**产出源（本期不加 env 字段 /
CLI 开关 / TOML 项）；生产路径传 `invariants=None`。
"""

import ast
import inspect
import pathlib
import pickle
import random

import pytest

import gacha_simulator
from gacha_simulator.core import invariants as invariants_mod
from gacha_simulator.core import pity_primitives as pity_primitives_mod
from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.invariants import InvariantChecker, InvariantError
from gacha_simulator.core.pity import (
    _EXTERNAL_STATE_KEYS,
    HardModifier,
    NamespaceTracker,
    Pity,
    PityEngine,
    PityState,
    PoolPitySpec,
)
from gacha_simulator.core.pity_tracker import CounterTracker

# ══════════════════════════════════════════════════════════════════
# 〇、AST 判据本体（可对合成源码驱动；S11 审查收口 F4）
# ══════════════════════════════════════════════════════════════════

def _pity_import_offenders(source: str):
    """源码里引用编排层 `pity` 的 import 片段（空列表 = 干净）。

    判据抽成模块级函数，好让 `test_ast_criterion_catches_all_static_import_forms`
    用**合成源码**逐形态驱动它（判据自身也要有牙齿）。命中面两类，见
    `TestSwitchCarrier.test_invariants_module_does_not_import_pity` 的 docstring。
    """
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or '')
            # F4：被导入的**名字**也是命中面（`from . import pity` 一类）
            modules.extend(a.name for a in node.names)
    return [m for m in modules
            if m.split('.')[-1] == 'pity' or m.endswith('core.pity')]


@pytest.mark.parametrize('source', [
    'from .pity import Pity',
    'from .pity import Pity, PityEngine',
    'import gacha_simulator.core.pity',
    'import gacha_simulator.core.pity as pity_mod',
    'from . import pity',
    'from gacha_simulator.core import pity',
    '''def f():
    from gacha_simulator.core import pity''',
])
def test_ast_criterion_catches_all_static_import_forms(source):
    """**判据自身的牙齿**（S11 审查收口 F4）：七种静态 import 写法逐条命中。

    前四种由「模块名末段」拦、后三种只有「被导入的名字」这一条能拦；原判据对后
    三种全盲（审查对合成源实测的十种写法里，`from . import pity` /
    `from gacha_simulator.core import pity` 判不出）。变异面：拿掉
    `_pity_import_offenders` 里的 `node.names` 一行，末三条即转红。
    """
    assert _pity_import_offenders(source), f'判据漏掉了写法：{source!r}'


@pytest.mark.parametrize('source', [
    'from .pity_modifier import HardModifier',
    'from .pity_primitives import DrawInfo, _EXTERNAL_STATE_KEYS',
    'from .pity_tracker import CounterTracker',
    'import gacha_simulator.core.pity_primitives',
    'from . import pity_modifier',
])
def test_ast_criterion_does_not_false_alarm_on_leaf_and_impl_layers(source):
    """阴性对照：叶子层 / 实现层的 `pity_*` 导入**不得**被判违规（假警报会让
    判据被无视，比漏报更坏）。`_pity_import_offenders` 的末段谓词对
    `pity_modifier` / `pity_primitives` / `pity_tracker` 分别取末段与后缀比较，
    两者都不命中。"""
    assert _pity_import_offenders(source) == [], f'判据对合法导入假警报：{source!r}'


# ══════════════════════════════════════════════════════════════════
# 一、夹具：合法配置 + 三要素断言助手
# ══════════════════════════════════════════════════════════════════

_POOL = 's11_pool'
_RANK = {'ssr': 0, 'sr': 1, 'r': 2}

#: 基础分布是**卡级**（S8 起管道为卡级，D20 / §3.9.1）：键即卡 id，Σ = 1.0。
#: `hard(scope='sr')` 触发后（S8 形态）：A = `scope_cards['sr']` 收下 `p(Q)`、
#: Q = 更低稀有度（r）整组搬空、更高稀有度（ssr 两张卡）**不写增量即逐位保留**
#: ： 输出 `{'ssr_up': 0.003, 'ssr_std': 0.006, 'sr_std': 0.991, 'r_std': 0.0}`、
#: **Σ = 1**（M1 的槽位级形态是「绝对赋值 + 豁免」，输出 Σ = 1.009，见下方
#: `TestDistributionLayer` 的改写记录）。
_BASE = {'ssr_up': 0.003, 'ssr_std': 0.006, 'sr_std': 0.091, 'r_std': 0.9}

#: **宽池形**的基础分布（`_wide_spec` 的卡集：sr 也有 UP 卡）。与 `_BASE` 的关系是
#: 「把 sr 的那一份质量拆成两张卡」：`sr_std` 的 0.091 = `sr_up` 0.01 + `sr_std` 0.081，
#: Σ 仍为 1.0。卡级管道下 `dist` 必须覆盖 A / Q 会用到的**每一张卡**（缺键即
#: `KeyError`，不是静默恒等），故两种池形各配一份。
_WIDE_BASE = {'ssr_up': 0.003, 'ssr_std': 0.006,
              'sr_up': 0.01, 'sr_std': 0.081, 'r_std': 0.9}

#: 更高稀有度的**卡集**（rank < rank('sr') 的稀有度之全部卡）。**写死字面量**，
#: 不写成「与生产助手比对」：若生产侧的豁免集计算坏掉，期望值与生产值会同向偏移。
#: S8 起它在断言里的角色由「被 F 豁免的槽位」变为「不写增量、逐位保留的卡」
#: （§3.9.5 的「U 外的卡逐位不变」），判据方向相同。
_HIGHER_CARDS = ('ssr_up', 'ssr_std')


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


def _preset_counter(state: PityState, name: str = 'p_hard', value: int = 1) -> None:
    """把某保底的计数预置到阈值（`_engine` 的默认 `threshold=1`）。

    只读查询路径不推进计数（`CounterTracker.advance` 在 `readonly=True` 时早退），
    故「查询时该保底已达阈值」只能靠预置 state 得到；不预置则该保底在查询路径上
    恒不触发、增量层探针恒零命中（见 `test_get_probabilities_stays_outside_the_delta_layer`）。
    """
    state.set(name, 'counter', value)


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

        **原稿误记在 S7b，GATE-check-3（2026-10-09）改归本步**：S7b 排在 S11 之前、
        其时本类尚不存在，故该用例**从未在 S7b 存在过**（不是「移入」）；出处是计划
        GATE-check-3 的「原写 S7b……改归 S11」，`tests/service/test_batch_simulator.py`
        的 pickle 段落亦明写「`InvariantChecker` 的 round-trip 不在本步……由排在
        S7b 之后的 S11 产出」（该文件里没有本类的任何引用）。
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
        import 本模块，反向即成环）。判据 = AST 扫 import 节点，命中面**两类**
        （S11 审查收口 F4，2026-10-13 补第二类）：

        - `from .pity import …` / `import …pity`：**模块名**末段即 `pity`；
        - `from . import pity` / `from gacha_simulator.core import pity`：模块名
          是 `.` 或 `gacha_simulator.core`、**不含** `pity`，命中面在**被导入的
          名字**上（原判据只看模块名，这两类全部漏网；前一类在模块级会因循环
          import 直接 `ImportError`，故本条是双保险）。

        `pity_modifier` / `pity_primitives` / `pity_tracker` 是允许的（叶子层与
        实现层，无环）。

        **判据边界（已知不拦）**：`importlib.import_module('…core.pity')` 一类
        **动态导入** AST 判据按定义看不到，且它是「函数内惰性 import」的合法写法
        （本模块若真要取编排层符号只能这么写），故不计为缺口。
        """
        offending = _pity_import_offenders(inspect.getsource(invariants_mod))
        assert not offending, f'checker 引用了编排层 pity：{offending}'


# ══════════════════════════════════════════════════════════════════
# 四、分布层（§3.13 分布行 / §3.12.1 归一性 + 非负性行）
# ══════════════════════════════════════════════════════════════════

class TestDistributionLayer:
    """分布层判据（§3.12.1 归一性 + 非负性行）：**S8 起的恒等口径**。

    本组在 S8-2 随判据本身同批改写（ISSUE-903 的反转义务，S8-6 ⑤ 的一部分提前
    执行）：M1 的「scope 感知式 + F 零件可达取值集」整体消失，判据成为恒等断言
    `Σp = 1`，故本组原先围绕 `Σ = 1.009` 与豁免槽位的四条用例按新语义重写（**不是
    放宽**：`Σ ≠ 1` 从「有合法例外值」变成「一律是缺陷」，判据面反而更严）。
    """

    def test_legal_hard_sr_config_no_alarm(self):
        """**正例**（§六 S11 明列）：`hard(scope='sr')` 的合法配置、`Σ = 1`，
        `check_after_before_draw` **不得报错**。

        同时钉住「该输出由生产管道跑出来」这一点：走真引擎的 `before_draw`（它内部
        就调用本入口），断言输出与 S8 的机制表逐条相符：A（sr 卡）收下 `p(Q)`、
        Q（更低稀有度 r 卡）整组搬空、**更高稀有度的两张卡逐位保留**（§3.9.5 的
        「U 外的卡逐位不变」，即 M1「豁免」在增量形式下的对应物）。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        assert probs == {'ssr_up': 0.003, 'ssr_std': 0.006,
                         'sr_std': 0.991, 'r_std': 0.0}, (
            f'生产管道输出与 S8 机制表不符：{probs}')
        for c in _HIGHER_CARDS:
            assert probs[c] == _BASE[c], f'更高稀有度卡 {c} 须逐位保留'
        assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)
        # 显式再走一次入口（不依赖引擎调用的间接性）
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_f_not_fired_total_one_is_accepted(self):
        """无 F 参与的抽次：`Σp = 1` 必须被接受（S8 起这是**唯一**合法取值）。

        `threshold=99` 使 F 全程不触发，输出即基础分布、Σ = 1.0。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker, threshold=99)
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_total_raised_to_former_exemption_mass_now_raises(self):
        """**旧盲区的反转（S8 起）**：把 Σ 抬到 **1.009**（M1 的合法期望值、
        恰等于旧「豁免量」）**必须抛错**。

        M1 期该形态是**已登记的盲区**（取值集无条件析取、F 零件选项不附带「本抽
        已触发」的前提，故「未触发但 Σ 被抬到同一量」被接受）。S8 起判据是恒等
        断言，该形态成为明确的违规：本用例把这条反转钉住，使「判据退回 M1 的
        取值集形态」在测试期即失败。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker, threshold=99)
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)

        broken = dict(probs)
        broken['r_std'] = broken['r_std'] + sum(probs.get(c, 0.0)
                                                for c in _HIGHER_CARDS)
        assert sum(broken.values()) == pytest.approx(1.009, abs=invariants_mod.TOL)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_before_draw(_POOL, broken, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', "'Σp'")

    def test_negative_probability_raises(self):
        """**负例 ①**（§六 S11）：人为把一个卡概率改为负值 → 必须抛错，且异常信息
        含保底名 + 键 + 期望 / 实际三要素（§3.12.1 非负性行）。"""
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['sr_std'] = -0.5
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_before_draw(_POOL, broken, engine)
        _assert_three_elements(str(excinfo.value), 'p_hard', "'sr_std'")

    def test_total_not_one_raises(self):
        """**负例 ②**（§六 S11）：把 Σ 改到 1.2 → 必须抛错，三要素齐备，
        且期望值恰为 `1.0`（S8 起无「合法的例外值」可枚举）。

        改的是 `r_std` 卡（已被 F 步搬空）：全部分量非负，故只有归一性一条判据
        能拦下它。
        """
        checker = InvariantChecker(enabled=True)
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['r_std'] = 0.2
        assert sum(broken.values()) == pytest.approx(1.2, abs=1e-9)
        with pytest.raises(InvariantError) as excinfo:
            checker.check_after_before_draw(_POOL, broken, engine)
        message = str(excinfo.value)
        _assert_three_elements(message, 'p_hard', "'Σp'")
        assert '1.0' in message, f'期望值须为 1.0：{message}'
        assert '1.2' in message, f'实际值缺失：{message}'

    def test_multiple_f_parts_partial_fire_no_alarm(self):
        """池内**多个** F 型零件、只有其中一个触发时不得假警报。

        `hard(scope='sr')`（阈值 1，触发）与 `hard(scope='r')`（阈值 99，不触发）
        同池：前者把 r 卡搬进 sr 卡，后者不动作，输出 Σ = 1.0。M1 期本用例守的是
        「取值集逐零件分列、不取并集」；S8 起判据无取值集，本用例守的是**同一条
        事实的恒等形态**：多个 F 零件并存时输出仍精确归一（F 零件若退回「造质量」
        的绝对赋值形态，本条即红）。
        """
        checker = InvariantChecker(enabled=True)
        defs = [PityDef(name='h_sr', btype='hard', scope='sr', threshold=1),
                PityDef(name='h_r', btype='hard', scope='r', threshold=99)]
        engine, state = _engine(invariants=checker, pities=defs)
        probs = engine.before_draw(_POOL, state, dict(_BASE))
        assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)
        checker.check_after_before_draw(_POOL, probs, engine)

    def test_transfer_after_f_keeps_total_one(self):
        """F 步之后的转移算子照常作用时，Σ 恒为 1（转移族 `Σδ = 0`）。

        同池 `hard(scope='sr')`（阈值 1）与 `soft(scope='ssr')`：后者 scope 的 rank
        更小、**排在前者之前**执行（`_resolve_order` 的首键是稀有度 rank），连跑
        4 抽每抽输出 Σ = 1.0（M1 期本用例的期望值是 `1 + Σp(豁免槽位)` 且单调
        抬升，S8 起该形态消失）。
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
            assert totals[-1] == pytest.approx(1.0, abs=invariants_mod.TOL)
            engine.after_draw(_POOL, state, 'r_std')
        assert len(totals) == 4

    def test_disabled_checker_is_a_no_op(self):
        """`enabled=False`（构造默认值）时四层判据一律不跑——生产关闭态的判据面。"""
        checker = InvariantChecker()
        assert checker.enabled is False
        engine, state = _engine(invariants=checker)
        probs = engine.before_draw(_POOL, state, dict(_BASE))

        broken = dict(probs)
        broken['sr_std'] = -0.5
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

    def test_part_namespace_aliasing_pity_name_no_alarm(self):
        """**F5（S11 审查收口）**：零件命名空间 == 保底命名空间（`NamespaceTracker`
        的退化形态 `namespace=<保底名>`）**不得**假警报。

        该形态下 `state.data[<保底名>]` 同时是保底命名空间与零件命名空间，其中的
        `counter` 是三族声明集内的**合法**键；判据若把零件命名空间的允许集写死为
        `{_active}`，即对这份合法 state 抛 `[状态层] 保底 'p' 键 ['counter']`
        （审查 2026-10-13 实测复现）。preset 一律用 `f'{name}_soft'`，故当前生产
        不可达，但那是**同一个类换个实参**的巧合，不是保证。

        修法：允许集**从声明集派生**（同名时取三族并集，与保底命名空间那条判据
        同口径）；`X_soft` 类命名空间下仍只许 `{_active}`（上一条用例即其反例面）。

        构造面不经 `PityDef` / `create_behavior`（preset 不产该形态），故直接建
        `Pity` 并直调 `_check_declared_state`：`check_after_after_draw` 的保底列表
        取自 `engine.get_behaviors_for_pool`，本形态**无法**经引擎产出。
        """
        checker = InvariantChecker(enabled=True)
        state = PityState()
        pity = Pity(name='p', state=state, scope='sr', btype='hard',
                    trackers=[CounterTracker('sr'), NamespaceTracker('p')],
                    modifiers=[HardModifier('sr')])
        assert pity._namespaces == ('p',), (
            f'前提：零件命名空间须与保底同名，实测 {pity._namespaces}')

        state.set('p', 'counter', 1)
        assert state.data['p'] == {'_active': True, 'counter': 1}
        checker._check_declared_state(state, [('p', pity)])      # 不抛：F5 的修复面

        # 阴性对照：同一份 state 里写进未声明键，判据仍有牙齿
        state.set('p', 'countr', 1)
        with pytest.raises(InvariantError) as excinfo:
            checker._check_declared_state(state, [('p', pity)])
        _assert_three_elements(str(excinfo.value), 'p', 'countr')

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
# 七、增量层（§3.12.1 增量合法性行；S8-6 已接线：调用点 = 骨架内循环）
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

    def test_delta_entry_is_wired_into_the_skeleton_inner_loop(self, monkeypatch):
        """增量层的调用点：**骨架内循环**（S8-6 接线）；两个引擎入口仍**不**调用它。

        原用例（M1）断言「跑一遍引擎的两个入口，`check_delta` 零命中」，依据是计划
        §3.13 的「M1 不接调用点」硬约束（M1 槽位级管道没有增量表示，两个入口的第二
        实参只有分布）。S8-6 按计划落地该层的调用点后，该断言的前半**必然反转**：
        `engine.before_draw` 现在会命中 `check_delta`（骨架内循环逐 Modifier 判一次）。
        故本用例改写为**三条并列事实**，判据面比原来更宽：

        ① **正面**：`enabled=True` 时跑一次 `engine.before_draw`，探针**必被命中**
           恰一次（`hard(scope='sr')` 首抽即触发、δ 非空），且两个实参同键空间。
           原用例无法区分「已接线」与「接线被删」；本条即补上那个方向。
        ② **边界**：**单独**调用两个入口 `check_after_before_draw` /
           `check_after_after_draw` 时，探针**仍零命中**（§3.13「增量层不复用两个
           入口」的理由未变：两个入口的第二实参只有分布、取不到该步的 δ）。
        ③ **关闭态**：`invariants=None`（生产默认）时探针零命中。

        **与计划原文的落点差异**：§3.13 与 S8-6 写「由 `_apply_delta()` 内部调用」，
        而 S8-1 已把该函数迁到叶子层、签名收为 `(dist, d)`，**取不到 `pool_id` 与
        校验器**，故不可执行；三条候选的裁决与理由见 `Pity.before_draw` 的内循环注记
        （取「调用点移到骨架内循环」）。
        """
        hits = []

        def _probe(self, pool_id, dist, delta):
            hits.append((pool_id, dict(dist), dict(delta)))

        monkeypatch.setattr(InvariantChecker, 'check_delta', _probe)

        # ① 正面：骨架内循环真的走到增量层（探针本身可用的阳性对照即本断言）
        engine, state = _engine(invariants=InvariantChecker(enabled=True))
        engine.before_draw(_POOL, state, dict(_BASE))
        assert len(hits) == 1, (
            f'骨架内循环须命中增量层恰一次（hard(scope=sr) 首抽即触发），实测 {hits}')
        pool_id, dist, delta = hits[0]
        assert pool_id == _POOL, f'pool_id 须取自 ctx.draw.pool_id，实测 {pool_id!r}'
        assert set(delta) <= set(dist), (
            f'增量层的两个实参须同键空间（卡级），实测 δ 多出 {set(delta) - set(dist)}')

        # ② 边界：两个入口单独调用时不得命中增量层
        hits.clear()
        checker = InvariantChecker(enabled=True)
        checker.check_after_before_draw(_POOL, dict(_BASE), engine)
        checker.check_after_after_draw(_POOL, state, engine)
        assert hits == [], f'两个入口不得调用增量层，实测命中 {hits}'

        # ③ 关闭态：invariants=None 时连调用点都不进（生产零开销）
        hits.clear()
        engine_off, state_off = _engine(invariants=None)
        engine_off.before_draw(_POOL, state_off, dict(_BASE))
        assert hits == [], f'invariants=None 时不得命中增量层，实测 {hits}'

    def test_get_probabilities_stays_outside_the_delta_layer(self, monkeypatch):
        """**边界守卫**（S8-6 审查收口补）：只读查询入口 `PityEngine.get_probabilities`
        不写 `ctx.invariants`，故该路径**不在增量层的判据面内**。

        `check_delta` 的调用点只有一个（骨架内循环，读 `ctx.invariants`），而该字段
        **只由 `PityEngine.before_draw` 写**（`pity.py:2208`）：`get_probabilities` 虽
        同样以骨架的 `before_draw(ctx, readonly=True)` 调度，但不写该字段，故校验器
        挂上后只读查询仍零命中。这是 §3.13 已登记的「四层覆盖边界」（只读查询不在
        判据面内），此前**零守卫**（S8-6 审查实测：把 `before_draw` 里那一行
        `ctx.invariants = self._invariants` 复制进 `get_probabilities`，全量测试 0 红）。

        两条并列断言：① 增量层探针零命中（**探针的非恒真**由紧随其后的阳性对照钉住：
        同一探针在同引擎的 `before_draw` 上必命中）；② 查询输出与「校验器关闭」时
        **一致**（防将来无声扩边把查询路径也纳入判据面，或反过来让返回随开关而变）。

        **夹具须预置计数（`_preset_counter`）**：只读查询不推进计数
        （`CounterTracker.advance` 在 `readonly=True` 时早退），计数留在 0 则
        `compute_delta` 恒返 `None`、内循环根本不进增量层，于是「探针零命中」对
        该变异**恒真**（S8-6 审查实测：不预置时该变异不被本用例捕获）。预置到阈值后
        查询路径上该保底确实产出增量，探针才有判别力。
        """
        hits = []

        def _probe(self, pool_id, dist, delta):
            hits.append((pool_id, dict(dist), dict(delta)))

        monkeypatch.setattr(InvariantChecker, 'check_delta', _probe)

        # ① 只读查询路径不得进入增量层
        engine, state = _engine(invariants=InvariantChecker(enabled=True))
        _preset_counter(state)
        queried = engine.get_probabilities(_POOL, state, dict(_BASE))
        assert hits == [], f'只读查询不得进入增量层，实测命中 {hits}'

        # 阳性对照：同一探针在 before_draw 上必命中（否则上面那条恒真）
        engine.before_draw(_POOL, state, dict(_BASE))
        assert len(hits) == 1, (
            f'探针自身失灵（同引擎的 before_draw 也未命中增量层）：{hits}')

        # ② 查询输出不随校验器开关变化
        off_engine, off_state = _engine(invariants=None)
        _preset_counter(off_state)
        off_queried = off_engine.get_probabilities(_POOL, off_state, dict(_BASE))
        assert queried == off_queried, (
            f'只读查询的输出不得随校验器开关变化，实测 {queried} vs {off_queried}')

    def test_delta_entry_argument_face_is_pinned_by_values(self, monkeypatch):
        """增量层**实参面**（S8-6 审查收口补）：`check_delta(pool_id, dist, delta)` 的
        两个实参由**两条独立通道**逐键取值比对，故「两个实参对调」这一变异必红，且
        红的理由**不是键集大小**。

        **为什么既有断言不够**：同组 `test_delta_entry_is_wired_into_the_skeleton_inner_loop`
        只判 `set(delta) <= set(dist)`（同键空间），而判据本体 `p + δ ≥ 0` **对 p 与
        δ 对称**，对调后照样成立；该对调在本组夹具下**只是偶然**被那条键集断言命中
        （`out` 的键集恰比该步的 `d` 大）。本用例改判**值**，与键集是否等大无关：

        - `dist` 实参 == 该步的输入分布（`_BASE` 的原值，即归一化**之前**的 p）；
        - `delta` 实参 == `HardModifier.compute_delta` 的返回值。

        两条期望值都不由被判对象给出：前者是测试自带的常量，后者由另一次插桩记录。
        """
        hits = []
        returned = []

        monkeypatch.setattr(InvariantChecker, 'check_delta',
                            lambda self, pool_id, dist, delta:
                            hits.append((pool_id, dict(dist), dict(delta))))
        original_compute_delta = HardModifier.compute_delta

        def _spy(self, view, dist, ctx):
            d = original_compute_delta(self, view, dist, ctx)
            returned.append(None if d is None else dict(d))
            return d

        monkeypatch.setattr(HardModifier, 'compute_delta', _spy)

        engine, state = _engine(invariants=InvariantChecker(enabled=True))
        engine.before_draw(_POOL, state, dict(_BASE))

        assert len(hits) == 1 and len(returned) == 1, (
            f'该步须恰有一次增量层调用与一次 Modifier 求值，实测 {hits} / {returned}')
        _pool_id, dist, delta = hits[0]

        expected_input = dict(_BASE)
        for key in sorted(set(dist) | set(expected_input)):
            assert dist.get(key, 0.0) == expected_input.get(key, 0.0), (
                f'{key!r} 键：dist 实参须是该步的输入分布（归一化之前），'
                f'实测 {dist.get(key, 0.0)!r}，期望 {expected_input.get(key, 0.0)!r}')

        expected_delta = returned[0]
        assert expected_delta is not None, '该步的 Modifier 须产出增量，否则本用例无判别力'
        for key in sorted(set(delta) | set(expected_delta)):
            assert delta.get(key, 0.0) == expected_delta.get(key, 0.0), (
                f'{key!r} 键：delta 实参须是 compute_delta 的返回值，'
                f'实测 {delta.get(key, 0.0)!r}，期望 {expected_delta.get(key, 0.0)!r}')


# ══════════════════════════════════════════════════════════════════
# 八、全 preset 面的假警报扫描（校验器可用性的前提）
# ══════════════════════════════════════════════════════════════════

#: 每个 registry 类型一份最小合法 `PityDef` 的公共取值。
_PRESET_COMMON = dict(soft_start=1, soft_end=3, soft_increment=10.0, threshold=2,
                      counter_init=1, guaranteed_init=True, fate_points_init=1,
                      selected_card_init='sr_up', fate_threshold=2,
                      cr_counter_threshold=3, cr_base_rate=0.0, max_triggers=0)

def _preset_btype_list():
    from gacha_simulator.core.pity import BEHAVIOR_REGISTRY
    return sorted(BEHAVIOR_REGISTRY)


@pytest.mark.parametrize('btype', _preset_btype_list())
def test_every_registry_type_runs_without_false_alarm(btype):
    """**校验器可用性的前提**：11 个 registry 类型各跑一段抽卡序列，四层判据全程
    不得报错。

    「生产关闭」不等于「启用即炸」：本层若对合法配置假警报（ISSUE-011 / ISSUE-903
    的形态），它就只是噪声源。故对每个类型单独造一台引擎（一池一保底，避免组合
    规则的干扰），以固定种子抽 25 抽（奖励按调整后的分布抽样，与「先定分布、
    再抽奖励」的引擎同形；S8 起 `probs` 的键即卡 id，可直接当奖励 id），断言不抛
    `InvariantError`。
    """
    kw = dict(_PRESET_COMMON)
    # `targeted` / `rotating_inverse` 的 scope 取 ssr（前者靠 UP 卡触发，后者方向相反）
    kw['scope'] = 'ssr' if btype in ('targeted', 'rotating_inverse') else 'sr'
    defs = [PityDef(name='p', btype=btype, **kw)]
    engine, state = _engine(invariants=InvariantChecker(enabled=True), pities=defs,
                            spec=_wide_spec(['p']))

    rng = random.Random(7)
    for _ in range(25):
        probs = engine.before_draw(_POOL, state, dict(_WIDE_BASE))
        roll = rng.random()
        acc = 0.0
        pick = 'r'
        for slot, value in probs.items():
            acc += value
            if roll <= acc:
                pick = slot
                break
        engine.after_draw(_POOL, state, pick)
    assert state.get('p', '_active') is True


# ══════════════════════════════════════════════════════════════════
# 九、外部白名单的「一处声明」纪律（F3 的下沉面；镜像守卫已随下沉退役）
# ══════════════════════════════════════════════════════════════════
def test_external_state_keys_has_a_single_declaration():
    """`_EXTERNAL_STATE_KEYS` 在三个消费模块间是**同一对象**（S11 审查收口 F3）。

    常量已**下沉到叶子层** `core/pity_primitives.py`，`core/pity.py` 与
    `core/invariants.py` 都从那里 import，故不存在「两处声明 + 逐元素守卫」的镜像面。

    本用例**取代**原 `test_external_state_keys_mirror_matches_engine`（下沉后它退化
    为「同一对象自比」的恒真断言，判别力归零，故删除；删除是安全的：它拦的漂移面
    已随重复声明一并消失）。新用例判**身份**而非相等，判别力更强：`==` 拦不住
    「又抄一份内容相同的副本」，`is` 拦得住：

    - `invariants` / `pity` 任一侧被改回本地副本，`is` 立即为假（转红）；
    - 叶子层的值本身被改，三处**同变**（这正是「一处声明」的效果：漂移面不存在），
      此时由末行的字面量断言拦下。
    """
    assert invariants_mod._EXTERNAL_STATE_KEYS is pity_primitives_mod._EXTERNAL_STATE_KEYS
    assert _EXTERNAL_STATE_KEYS is pity_primitives_mod._EXTERNAL_STATE_KEYS
    assert pity_primitives_mod._EXTERNAL_STATE_KEYS == frozenset({'selected_card'}), (
        f'外部写入键白名单的内容已变：'
        f'{sorted(pity_primitives_mod._EXTERNAL_STATE_KEYS)}')


# ══════════════════════════════════════════════════════════════════
# 十、异常的类型选择与「被兜底 except 吞掉」的使用约束（F1）
# ══════════════════════════════════════════════════════════════════

def _batch_simulator_source() -> str:
    """`service/batch_simulator.py` 的源码文本（按包路径定位，不 import 服务层）。"""
    return (pathlib.Path(gacha_simulator.__file__).parent
            / 'service' / 'batch_simulator.py').read_text(encoding='utf-8')


class TestErrorTypeAndSwallow:
    """`InvariantError` 的**类型选择**与**实际捕获行为**分开钉（S11 审查收口 F1）。

    审查的订正内容：类型选择合适，但原 docstring 称「不落进任何 `except` 兜底分支的
    捕获面内」为**假**：`batch_simulator` 的每一处 `_run_single` 包装都写
    `except Exception`，本类异常在并行路径上是**静默的失败计数**。两条约束各有一处
    用例，防止「理由」再被写成想当然。
    """

    def test_type_choice_is_independent_of_config_and_value_errors(self):
        """类型选择（审查裁定为**合适**）：不继承 `ConfigError` / `ValueError`。

        本类是**运行期自洽性**失败，与「配置错误」（构造期由 S10-2 /
        `_validate_behaviors` 抛）和「编程错误」（本库用 `ValueError` 标重名判定）
        的处置路径都不同。变异面：改成继承其中任一类即红。
        """
        assert issubclass(InvariantError, Exception)
        assert not issubclass(InvariantError, (ConfigError, ValueError))

    def test_batch_paths_wrap_run_single_in_catch_all(self):
        """**使用约束的前提**（F1 订正后的实际行为）：`batch_simulator` 的每一处
        `_run_single` 调用都在 `except Exception` 之内，故本类异常在其中**被吞**、
        计成「N/M 次模拟失败」（父进程写进 `BatchResult.warnings`），不向调用方抛。

        判据按 AST 扫**该文件**（不跑端到端并行：那条面属 `tests/service/`，且 spawn
        的开销与平台差异会淹没本用例的判别力）。本约束的前提住在服务层却决定本类的
        可观测性，故跨文件判据是必要代价：包装若收窄到不含 `Exception`，本用例转红
        → 同批订正 `InvariantError` docstring 的使用约束段。

        计数写死为 3（三处 `try`：worker 侧 `_wk_run_single`、`run_batch_parallel`
        的顺序分支与单进程兜底，合计 4 个 `_run_single` 调用点）：数量变化说明包装
        结构被改，须同批复核本约束，而不是让判据静默失效（`all([])` 为真）。
        """
        tree = ast.parse(_batch_simulator_source())
        wraps = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            calls_run_single = any(
                isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                and x.func.id == '_run_single' for x in ast.walk(node))
            if not calls_run_single:
                continue
            wraps.append(any(
                h.type is None
                or (isinstance(h.type, ast.Name) and h.type.id == 'Exception')
                for h in node.handlers))
        assert len(wraps) == 3, (
            f'包装 `_run_single` 的 try 语句数由 3 变为 {len(wraps)}，'
            f'须同批复核 `InvariantError` 的使用约束（并行路径的失败可见性）')
        assert all(wraps), (
            f'有 `_run_single` 的包装不再捕获 `Exception`（实测 {wraps}）：'
            f'`InvariantError` 的 docstring 使用约束段须同批订正')


# ══════════════════════════════════════════════════════════════════
# 十一、ISSUE-903 里程碑绊线（M2 的反转义务落在代码上，F2）
# ══════════════════════════════════════════════════════════════════
def test_issue_903_reversal_is_landed():
    """ISSUE-903 的**反转义务已落地**（S8-2 执行；原里程碑绊线改写）。

    原绊线的判据是「管道输出 Σ 是否已归一化 ⟺ 取值集是否只剩 `1.0`」，S8 落地时
    它转红并要求同批改写，本用例即那次改写的结果，钉住**反转后的状态**：

    ==============================  ==================================================
    面                              现行判据
    ==============================  ==================================================
    F 选项机制                      `_exemption_options` / `_EXEMPTION_PART_TYPES` /
                                    `_DrawProbe` 三个符号**已整体删除**（S8 起无
                                    「合法的例外值」可枚举，机制本身失去对象）
    分布层判据                      恒等断言 `Σp = 1`：1.0 通过、1.009（M1 的合法
                                    期望值）抛错
    ==============================  ==================================================

    **判别力**：把 F 选项机制加回模块（或把判据退回取值集形态）时，前两条断言必红。
    """
    # ① 机制已删除（三个符号都不在模块面上）
    for gone in ('_exemption_options', '_EXEMPTION_PART_TYPES', '_DrawProbe'):
        assert not hasattr(invariants_mod, gone), f'{gone} 应随 S8 删除'

    # ② 判据是恒等断言：1.0 通过、1.009 抛错
    checker = InvariantChecker(enabled=True)
    engine, state = _engine(invariants=checker, threshold=1)
    probs = engine.before_draw(_POOL, state, dict(_BASE))
    assert sum(probs.values()) == pytest.approx(1.0, abs=invariants_mod.TOL)
    checker.check_after_before_draw(_POOL, probs, engine)

    legacy = dict(probs)
    legacy['r_std'] = legacy['r_std'] + sum(probs.get(c, 0.0)
                                            for c in _HIGHER_CARDS)
    assert sum(legacy.values()) == pytest.approx(1.009, abs=invariants_mod.TOL)
    with pytest.raises(InvariantError):
        checker.check_after_before_draw(_POOL, legacy, engine)
