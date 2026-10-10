"""P64 S4-1 / S4-2 / S4-3：registry schema 改造（preset 判据 + `create_behavior` 的 preset 分支，§3.2）。

覆盖：
- `_validate_registry()` 的**收口判据**（GATE-3 定稿）：**条目一律判 `preset` 可调用**
  （导入期**不调用 preset、不校验返回键集**，ISSUE-405）；
- 非法条目**必抛**（非 callable 的 `preset`、缺 `preset` 键），**不得只测「不抛」**；
- `create_behavior` 的 preset 分支：按名取键构造 `Pity`、两道**互补**校验各抛
  `ConfigError`（查多未知键 / 查漏 `lifecycle`）、无 preset 且 `class` 为 `None` 时报未实现；
- `Pity.__init__` 签名不含旧类分支的两个注入点（`target_featured` / `reset`）。

**P64 S4-2 追加（`TestCounterPresetsS42`）**：counter 驱动四类
（`soft_interval` / `soft_additive` / `soft_step` / `hard`）的 preset 工厂本体，
条目原子形态、五键全集、`flags` / `counters` 的**消费者断言**、`priority` 走构造形参、
`_target_of` 的 `target=` 选择子、裁决 7B 的类型级硬拒、以及「工厂不是模块级常量实例」。

**P64 S4-3 追加（`TestEventPresetsS43` / `TestRotatingCrTrackerOrder`）**：事件驱动六类
（`rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` /
`targeted_soft`）的 preset 工厂本体，条目原子形态、五键全集、`flags` / `counters`
消费者断言、「工厂不是模块级常量实例」、三个 `_soft` 类型的 `NamespaceTracker` 载体与
`X_soft._active` 落点、事件驱动族一律不写 `target=`、以及 `rotating_cr` 的
**`[StreakTracker, FlagTracker]` 顺序契约**（语义级用例，顺序对调即 `cr_counter`
恒为 0）。**GATE-3 收口断言**（10 条目一律 `class: None` + 可调用 `preset`）亦在本段。

**S4-3 收口已完成的删除面**：`TestValidateRegistryTransition`（过渡判据的三条用例：
现有条目经旧判据通过 / 未迁移条目 `class` 置 `None` 必抛 / 未迁移条目 `class`
非子类必抛）已随 `_validate_registry()` 的「无 `preset` 键」分支一并删除。收口后
「无 `preset` 键的条目必抛」这一格由 `TestValidateRegistryPresetForm` 与
`TestEventPresetsS43` 承接（消息与收口判据同源）。
`TestValidateRegistryPresetForm` 与 `TestCreateBehaviorPresetBranch` 不受收口影响：
后者里的 `test_no_preset_and_class_none_raises_value_error` / `test_legacy_branch_still_works`
守的是 `create_behavior` 的**旧类兼容分支**（保留到发布前，见 GATE-5），与
`_validate_registry()` 的过渡判据不是同一条代码路径，故不随收口删除。
"""
import inspect

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    BEHAVIOR_REGISTRY, HardPityBehavior, Pity, PityEngine, _preset_hard,
    _preset_soft_step, _preset_targeted, _preset_targeted_soft, _target_of,
    _validate_registry, create_behavior,
)
from gacha_simulator.core.pity_modifier import (
    HardModifier, SelectedModifier, SoftModifier,
)
from gacha_simulator.core.pity_primitives import (
    DrawInfo, PityContext, PityState,
)
from gacha_simulator.core.pity_tracker import (
    AlwaysActive, CounterTracker, FateTracker, FlagTracker, NamespaceTracker,
    StreakTracker,
)


# ══════════════════════════════════════════════════════════════════
# 临时 registry 条目注入装置
# ══════════════════════════════════════════════════════════════════

_FAKE_VALID = '_s4_1_fake_valid_preset'
_FAKE_FLAGS = '_s4_1_fake_flags_counters'
_FAKE_UNKNOWN_KEY = '_s4_1_fake_unknown_key'
_FAKE_NO_LIFECYCLE = '_s4_1_fake_no_lifecycle'
_FAKE_BAD_PRESET = '_s4_1_fake_bad_preset'
_FAKE_LEGACY_NONE = '_s4_1_fake_legacy_none'
_FAKE_LEGACY_PROBE = '_s4_4_fake_legacy_probe'


class _LegacyKwargsProbe(HardPityBehavior):
    """记录 `create_behavior` 传给旧类分支的构造实参名（S4-4 的 `lifecycle` 键防线）。"""

    def __init__(self, **kw):
        self.received_kwargs = set(kw)
        super().__init__(**kw)


@pytest.fixture
def registry_entries():
    """向 `BEHAVIOR_REGISTRY` 注入临时条目，用后精确还原（只弹自己加的那些）。

    模块导入期的 `_validate_registry()` 已跑完，故注入条目不参与导入期校验：
    用例须**显式调用** `_validate_registry()` 才能验到判据本体。
    """
    added = []

    def _add(key, entry):
        assert key not in BEHAVIOR_REGISTRY, f'临时键 {key} 与真实条目重名'
        BEHAVIOR_REGISTRY[key] = entry
        added.append(key)

    yield _add
    for key in added:
        BEHAVIOR_REGISTRY.pop(key, None)


def _entry(**over):
    base = {'display_name': 'S4-1 临时条目', 'default_scope': 'ssr', 'params': {}}
    base.update(over)
    return base


def _preset_valid(pdef):
    return {
        'trackers': [CounterTracker(scope=pdef.scope or 'ssr')],
        'modifiers': [],
        'lifecycle': AlwaysActive(),
    }


def _preset_with_flags(pdef):
    return {
        'trackers': [],
        'modifiers': [],
        'lifecycle': AlwaysActive(),
        'flags': {'guaranteed': True},
        'counters': {'counter': 7},
    }


def _preset_unknown_key(pdef):
    built = _preset_valid(pdef)
    built['bogus'] = 1
    return built


def _preset_no_lifecycle(pdef):
    return {'trackers': [], 'modifiers': []}


# ══════════════════════════════════════════════════════════════════
# `_validate_registry()` 收口判据（GATE-3：条目一律判 `preset` 可调用）
#
# 过渡判据（「无 `preset` 键」形态沿用旧 `PityBehavior` 子类判据）的三条用例已随
# §七 S4-3 的收口删除（见模块 docstring 的「删除面」段）。
# ══════════════════════════════════════════════════════════════════

class TestValidateRegistryPresetForm:
    """收口判据：「含 `preset` 键」形态判其可调用（收口后为唯一形态）。"""

    def test_callable_preset_passes(self, registry_entries):
        """preset 形态条目通过判据。"""
        registry_entries(_FAKE_VALID, _entry(preset=_preset_valid))
        _validate_registry()

    def test_non_callable_preset_raises(self, registry_entries):
        """`preset` 非 callable 则判据必抛（导入期唯一的 preset 侧判据）。"""
        registry_entries(_FAKE_BAD_PRESET, _entry(preset='not-callable'))
        with pytest.raises(TypeError, match='必须为可调用的 preset 工厂函数'):
            _validate_registry()

    def test_missing_preset_key_raises(self, registry_entries):
        """**缺 `preset` 键**的条目必抛（S4-3 收口后 `.get()` 与显式 `None` 同判据）。

        本条承接被删的过渡判据用例的「必抛」覆盖：收口前该形态走旧 `PityBehavior`
        子类判据（`class` 为子类即通过），收口后 `class` 已不再是判据输入，
        缺 `preset` 键与 `preset: None` 报同一条消息。
        """
        registry_entries(_FAKE_LEGACY_NONE, _entry(**{'class': HardPityBehavior}))
        with pytest.raises(TypeError, match='必须为可调用的 preset 工厂函数'):
            _validate_registry()

    def test_validate_registry_does_not_call_preset(self, registry_entries):
        """导入期判据**只判可调用、不调用 preset**（ISSUE-405）。

        preset 体内抛错时判据仍须通过；否则任一 preset 的运行期错误会把
        「`PityEngine` 构造期可见」升级为**整包导入失败**。
        """
        def _boom(pdef):
            raise RuntimeError('preset 体内运行期错误：判据不得触发它')

        registry_entries(_FAKE_VALID, _entry(preset=_boom))
        _validate_registry()  # 不抛即证明 preset 未被调用


# ══════════════════════════════════════════════════════════════════
# `create_behavior` 的 preset 分支
# ══════════════════════════════════════════════════════════════════

class TestCreateBehaviorPresetBranch:

    def test_valid_preset_returns_pity(self, registry_entries):
        """preset 分支按名取键构造统一骨架 `Pity`（非旧类、非 dict）。"""
        registry_entries(_FAKE_VALID, _entry(preset=_preset_valid))
        state = PityState()
        bh = create_behavior(PityDef(name='s41', btype=_FAKE_VALID), state)
        assert isinstance(bh, Pity)
        assert bh._name == 's41'
        assert bh._btype == _FAKE_VALID
        assert bh._scope == 'ssr'
        assert len(bh._trackers) == 1

    def test_flags_and_counters_are_consumed(self, registry_entries):
        """可选两键 `flags` / `counters` 被 `Pity.__init__` 消费（仅 truthy 才写 state）。"""
        registry_entries(_FAKE_FLAGS, _entry(preset=_preset_with_flags))
        state = PityState()
        create_behavior(PityDef(name='s41f', btype=_FAKE_FLAGS), state)
        assert state.get('s41f', 'guaranteed') is True
        assert state.get('s41f', 'counter') == 7

    def test_unknown_key_raises_config_error(self, registry_entries):
        """查多：preset 返回未声明键则抛 `ConfigError`（不得静默成死代码）。

        断言消息含「未声明键」，与查漏那条消息**必须可区分**，故两道校验
        合并成一道时本用例与下一条至少一条必红。
        """
        registry_entries(_FAKE_UNKNOWN_KEY, _entry(preset=_preset_unknown_key))
        with pytest.raises(ConfigError, match='未声明键'):
            create_behavior(PityDef(name='s41u', btype=_FAKE_UNKNOWN_KEY), PityState())

    def test_missing_lifecycle_raises_config_error(self, registry_entries):
        """查漏：preset 返回 dict 缺必需键 `lifecycle` 则抛 `ConfigError`（ISSUE-301）。

        不得静默取骨架默认值（`AlwaysActive()`）：那会让 `deactivate_on_early_hit`
        / `depends_on` 两类配置静默失效。
        """
        registry_entries(_FAKE_NO_LIFECYCLE, _entry(preset=_preset_no_lifecycle))
        with pytest.raises(ConfigError, match="缺少必需键 'lifecycle'"):
            create_behavior(PityDef(name='s41m', btype=_FAKE_NO_LIFECYCLE), PityState())

    def test_no_preset_and_class_none_raises_value_error(self, registry_entries):
        """既无 `preset` 又无 `class` 则报未实现（旧分支的既有语义不变）。"""
        registry_entries(_FAKE_LEGACY_NONE, _entry(**{'class': None}))
        with pytest.raises(ValueError, match='尚未实现'):
            create_behavior(PityDef(name='s41n', btype=_FAKE_LEGACY_NONE), PityState())

    def test_legacy_branch_still_works(self, registry_entries):
        """旧类兼容分支未被 preset 分支改坏（保留到发布前，见 GATE-5）。

        **用注入的合成旧条目，不写死真实条目**（S4-1 审查 minor）：写死 `hard` 的版本
        在 S4-2 把 `hard` preset 化后必红，而那时旧分支本身仍应可用。S4-3 收口删除
        旧分支时，本用例随旧分支一并删除。
        """
        registry_entries(_FAKE_LEGACY_NONE, _entry(**{'class': HardPityBehavior}))
        bh = create_behavior(PityDef(name='s41l', btype=_FAKE_LEGACY_NONE),
                             PityState())
        assert not isinstance(bh, Pity), '旧分支不得返回骨架 Pity'
        assert isinstance(bh, HardPityBehavior)
        assert bh._btype == _FAKE_LEGACY_NONE

    def test_legacy_branch_no_longer_injects_lifecycle(self, registry_entries):
        """S4-4：旧 `lifecycle_kwargs` 段已删除，旧类分支不再注入 `LifecycleConfig`。

        `deactivate_on_early_hit` / `depends_on`（连同退役维的 `max_triggers`）到
        Lifecycle 对象的转换**只有一处**：模块级 `build_lifecycle(pdef)`，经 preset
        分支的 `lifecycle=` 键消费（§3.1.3 / ISSUE-301）。旧类分支若仍注入，即构成
        第二个转换点，而两处各留一半时的失效模式（两类配置静默失效）没有对照实现
        可发现。

        **必须走真实构造路径**：只断言 `build_lifecycle` 的产出测不出这段代码是否
        仍然存在。探测类记录 `create_behavior` 传给旧类的构造实参名。
        """
        registry_entries(_FAKE_LEGACY_PROBE, _entry(**{'class': _LegacyKwargsProbe}))
        bh = create_behavior(
            PityDef(name='s44l', btype=_FAKE_LEGACY_PROBE,
                    deactivate_on_early_hit=True, depends_on='other',
                    max_triggers=2),
            PityState())
        # 反向断言在前：分支未执行时下面的「不含」可因 `received_kwargs` 为空而假绿
        assert {'name', 'state', 'scope', 'btype'} <= bh.received_kwargs, (
            bh.received_kwargs)
        assert 'lifecycle' not in bh.received_kwargs, (
            '旧类分支仍在注入 LifecycleConfig，与 preset 分支的 build_lifecycle '
            '构成第二转换点（§3.1.3：同一转换不得留两处）')

    def test_preset_branch_passes_priority_and_pools(self, registry_entries):
        """preset 分支透传 `priority` / `pools`（S4-1 审查 low：原无断言覆盖）。

        `PityDef.pools` 已存在；`priority` 字段属 S4b，此处以 `setattr` 注入验透传
        本身，`getattr(pdef, 'priority', 0)` 的回退面由下行缺省情形覆盖。
        """
        registry_entries(_FAKE_VALID, _entry(preset=_preset_valid))

        pd = PityDef(name='s41p', btype=_FAKE_VALID)
        pd.pools = ('pool_a', 'pool_b')
        bh = create_behavior(pd, PityState())
        assert bh._pools == ('pool_a', 'pool_b')

        default = create_behavior(PityDef(name='s41q', btype=_FAKE_VALID), PityState())
        assert default._pools == ('*',)
        assert default._priority == 0


# ══════════════════════════════════════════════════════════════════
# 骨架形参面：旧类分支的两个注入点不得接回 preset 分支
# ══════════════════════════════════════════════════════════════════

def test_pity_init_signature_excludes_legacy_injection_params():
    """`Pity.__init__` 不含 `target_featured` / `reset`（AUDIT-BREAK-2）。

    旧类分支的 `params` dict 里这两键在骨架无对应形参，若被接回 preset 分支即
    `TypeError: unexpected keyword argument`：本断言是防回归的静态闸门。
    """
    params = set(inspect.signature(Pity.__init__).parameters)
    assert 'target_featured' not in params
    assert 'reset' not in params


# ══════════════════════════════════════════════════════════════════
# P64 S4-2：counter 驱动 preset（4 类）
# ══════════════════════════════════════════════════════════════════

_C42_TYPES = ('soft_interval', 'soft_additive', 'soft_step', 'hard')
_KEY_UNIVERSE = {'trackers', 'modifiers', 'lifecycle', 'flags', 'counters'}
_REQUIRED_KEYS = {'trackers', 'modifiers', 'lifecycle'}


class TestCounterPresetsS42:
    """四类 preset 工厂本体（§3.2 / §七 S4-2 的验收面）。"""

    def test_registry_entries_atomic_preset_form(self):
        """① 四条 registry 条目已原子地 `class: None` + 可调用 `preset`。

        「原子」的含义：`class` 置空与 `preset` 赋值必须在同一条目上同时成立，
        条目既无 `preset` 又无 `class` 时，导入期的 `_validate_registry()` 即
        `TypeError`。故 `python -c "import gacha_simulator.core.pity"` 通过本身就是
        本断言的另一半（导入期已跑过判据）。
        """
        for t in _C42_TYPES:
            entry = BEHAVIOR_REGISTRY[t]
            assert entry['class'] is None, f'{t}: class 未置 None'
            assert callable(entry['preset']), f'{t}: preset 不可调用'

    def test_preset_key_sets_within_five_key_universe(self):
        """② 四类 preset 均可构造，返回 dict ⊆ 五键全集且含三必需键。

        上界取五键全集而非子集判断的补集，子集式（`<= set(x)`）不拒绝多余键，
        「`flags` / `counters` 成了死键」在其下不可见（AUDIT-BREAK-3）。
        """
        for t in _C42_TYPES:
            built = BEHAVIOR_REGISTRY[t]['preset'](PityDef(name=t, btype=t))
            assert isinstance(built, dict), t
            assert _REQUIRED_KEYS <= set(built) <= _KEY_UNIVERSE, (t, sorted(built))

    def test_preset_is_factory_not_module_level_instance(self):
        """③ 工厂不是模块级常量实例（ISSUE-005）：两次调用返回互不相同的零件。

        模块级赋值会让同一 preset 的所有保底共享同一批 Counter/Flag 遥控器，
        `_rebind_state` 把它们重绑到最后调度的保底，串扰既跨保底又跨模拟。
        """
        for factory, t in ((_preset_soft_step, 'soft_step'), (_preset_hard, 'hard')):
            pd = PityDef(name=t, btype=t)
            a, b = factory(pd), factory(pd)
            assert a['trackers'][0] is not b['trackers'][0], t
            assert a['modifiers'][0] is not b['modifiers'][0], t
            assert a['lifecycle'] is not b['lifecycle'], t

    def test_counter_preset_is_named_hard(self):
        """`_preset_hard` 的 Tracker 是 `CounterTracker`，`counters` 取 `pdef.counter_init`。"""
        built = _preset_hard(PityDef(name='h', btype='hard', counter_init=5))
        assert isinstance(built['trackers'][0], CounterTracker)
        assert built['counters'] == {'counter': 5}

    def test_consumer_counters_written_into_state(self):
        """消费者断言（AUDIT-BREAK-3 强制）：`counters` 被 `Pity.__init__` 真写进 state。

        判据取「声明了初值但没人读」这一失效模式的反面：`counter_init=5` 经
        preset → `create_behavior` 后必须是 `state.get(name, 'counter') == 5`。
        本批四类均不含 flag（无 `flags` 键），flag 侧的消费者由
        `TestCreateBehaviorPresetBranch::test_flags_and_counters_are_consumed` 覆盖。
        """
        state = PityState()
        bh = create_behavior(
            PityDef(name='h', btype='hard', counter_init=5, guaranteed_init=True), state)
        assert isinstance(bh, Pity)
        assert state.get('h', 'counter') == 5
        # 本批四类不声明 flag：`guaranteed_init=True` 不该写出 `guaranteed` 键
        assert state.get('h', 'guaranteed') is None, 'counter 驱动型不得声明 flag'

    def test_consumer_counters_truthy_rule(self):
        """`counters` 走 L4 truthy 规则：`counter_init=0` 不预建键（对齐 `_build_pity_state_init`）。"""
        state = PityState()
        create_behavior(PityDef(name='h', btype='hard', counter_init=0), state)
        assert state.get('h', 'counter') is None

    def test_priority_passed_as_constructor_param(self):
        """④ `priority` 经**构造形参**传入（§3.6 M3 / ISSUE-203），非构造后设属性。"""
        bh = create_behavior(PityDef(name='p', btype='hard', priority=7), PityState())
        assert bh._priority == 7
        assert create_behavior(PityDef(name='p0', btype='hard'), PityState())._priority == 0

    def test_hard_reset_never_no_typeerror(self):
        """⑤ `hard` + `reset='never'` 返回 `Pity` 且不抛 `TypeError`（AUDIT-BREAK-2）。

        `reset` 在旧类分支是注入的 `params` 键，骨架无该形参；preset 分支走
        `CounterTracker.reset_on`，故不得有注入路径。
        """
        bh = create_behavior(PityDef(name='x', btype='hard', reset='never'), PityState())
        assert isinstance(bh, Pity)
        assert bh._trackers[0]._reset_on == 'never'

    def test_real_entry_rejects_unknown_key_and_missing_lifecycle(self, monkeypatch):
        """⑥ 两道互补校验对**真实条目**同样生效（不只对注入的合成 preset）。

        改造真实 `hard` 条目的 preset 返回体：多一键 → 查多；缺 `lifecycle` → 查漏。
        两者消息可区分，合并成一道时至少一条必红。
        """
        real = BEHAVIOR_REGISTRY['hard']['preset']

        monkeypatch.setitem(BEHAVIOR_REGISTRY['hard'], 'preset',
                            lambda pdef: {**real(pdef), 'foo': 1})
        with pytest.raises(ConfigError, match='未声明键'):
            create_behavior(PityDef(name='h', btype='hard'), PityState())

        monkeypatch.setitem(
            BEHAVIOR_REGISTRY['hard'], 'preset',
            lambda pdef: {k: v for k, v in real(pdef).items() if k != 'lifecycle'})
        with pytest.raises(ConfigError, match="缺少必需键 'lifecycle'"):
            create_behavior(PityDef(name='h', btype='hard'), PityState())


class TestTargetFeaturedS42:
    """`_target_of(pdef)` + `hard` 的 `target=` 键（ISSUE-403）+ 裁决 7B 的类型级硬拒。"""

    def test_target_of_selector(self):
        """`target_featured=True → 'featured'`，否则 `'scope'`；缺省同 False。"""
        assert _target_of(PityDef(name='h', btype='hard', target_featured=True)) == 'featured'
        assert _target_of(PityDef(name='h', btype='hard', target_featured=False)) == 'scope'
        assert _target_of(PityDef(name='h', btype='hard')) == 'scope'

    def test_preset_hard_writes_target_key(self):
        """`_preset_hard` 的 `HardModifier` 带 `target=_target_of(pdef)`。

        漏写不报错（`HardModifier` 的 `target` 默认 `'scope'`）：`target_featured=True`
        的配置会把目标集由 featured 卡集静默放宽为 scope 全集，故本断言是唯一捕获面。
        """
        mod = _preset_hard(PityDef(name='h', btype='hard', target_featured=True))['modifiers'][0]
        assert isinstance(mod, HardModifier)
        assert mod._target == 'featured'
        assert _preset_hard(PityDef(name='h', btype='hard'))['modifiers'][0]._target == 'scope'

    def test_preset_soft_does_not_write_target_key(self):
        """`_preset_soft_step` **不写** `target=`（裁决 7B：soft 无该消费路径）。

        `SoftModifier` 的构造形参只有 `(scope, deltas)`，若有人给它加 `target=`
        即与 7B 的硬拒面互斥（照计划验收必红、按 7B 施工则验收不可执行）。
        """
        for t in ('soft_interval', 'soft_additive', 'soft_step'):
            mod = _preset_soft_step(PityDef(name='s', btype=t))['modifiers'][0]
            assert isinstance(mod, SoftModifier)
            assert set(inspect.signature(SoftModifier.__init__).parameters) == {
                'self', 'scope', 'deltas'}
            assert not hasattr(mod, '_target')

    @pytest.mark.parametrize('btype', ['soft_interval', 'soft_additive', 'soft_step'])
    def test_ruling_7b_soft_target_featured_rejected(self, btype):
        """裁决 7B 类型级硬拒：`soft_*` + `target_featured=true` 经 `create_behavior` 抛 `ConfigError`。

        校验点在 `create_behavior`（preset 构造前）而非 `_build_pity`：等价性 harness
        与直构 `PityDef` 的路径绕过 TOML 层，防线须盖住构造入口。
        """
        with pytest.raises(ConfigError, match='不支持 target_featured=true'):
            create_behavior(PityDef(name='s', btype=btype, target_featured=True), PityState())

    def test_ruling_7b_hard_still_accepts_target_featured(self):
        """`hard` 族不受 7B 影响：手册 10 处 `target_featured = true` 全在 `type = "hard"`。"""
        bh = create_behavior(PityDef(name='h', btype='hard', target_featured=True), PityState())
        assert isinstance(bh, Pity)
        assert bh._modifiers[0]._target == 'featured'

    def test_norm_scope_normalizes_preset_scope(self):
        """`_norm_scope` 是 scope 的唯一归一化点（ISSUE-503）：preset 与骨架同源。

        不归一化会让 `Pity._scope`（小写）与零件 `_scope`（原值）分叉，
        `scope_cards.get('SSR', ())` 取空 → 该保底静默恒等、不报错。
        """
        from gacha_simulator.core.pity import _norm_scope

        assert _norm_scope(PityDef(name='h', btype='hard', scope='SSR')) == 'ssr'
        assert _norm_scope(PityDef(name='h', btype='hard', scope='')) == 'ssr'
        bh = create_behavior(PityDef(name='h', btype='hard', scope='SSR'), PityState())
        assert bh._scope == 'ssr'
        assert bh._trackers[0]._scope == 'ssr'
        assert bh._modifiers[0]._scope == 'ssr'


# ══════════════════════════════════════════════════════════════════
# P64 S4-3：事件驱动 preset（6 类）+ GATE-3 收口
# ══════════════════════════════════════════════════════════════════

_C43_TYPES = ('rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft',
              'targeted', 'targeted_soft')
_ALL_TYPES = _C42_TYPES + _C43_TYPES          # 10 条目全集
_SOFT_FAMILY = ('rotating_soft', 'rotating_cr_soft', 'targeted_soft')

# ── 夹具：ssr（含 featured）/ sr / r 三稀有度池（与 S1b 起的 tracker 单测同形）──
_FX_SCOPE_CARDS = {'ssr': ('up', 'std'), 'sr': ('sr1',), 'r': ('r1',)}
_FX_FEATURED_CARDS = {'ssr': ('up',)}
_FX_SCOPE_SLOTS = {'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)}
_FX_FEATURED_SLOTS = {'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)}
_FX_CARD_TO_SLOT = {'up': 'ssr_featured', 'std': 'ssr', 'sr1': 'sr', 'r1': 'r'}
_FX_BASE = {'ssr_featured': 0.006, 'ssr': 0.004, 'sr': 0.05, 'r': 0.94}


def _fx_draw(rarity='ssr', featured=False):
    return DrawInfo(
        pool_id='p', pool_instance_id='p_0', reward_id='std',
        reward_rarity=rarity, is_featured=featured,
        scope_cards=_FX_SCOPE_CARDS, featured_cards=_FX_FEATURED_CARDS,
        scope_slots=_FX_SCOPE_SLOTS, featured_slots=_FX_FEATURED_SLOTS,
        card_to_slot=_FX_CARD_TO_SLOT, base_probabilities=_FX_BASE,
        rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )


def _fx_build(btype, **kw):
    """经 `create_behavior` 构造 preset 形态的 `Pity` 并完成首次 rebind。

    `_rebind_state` 是**必需**的一步：S4-2 删除了 `PityEngine._rebind_state` 的
    `state is self._state` 早退后，零件的 Counter / Flag 只在本方法里绑定；
    未经它直接驱动即在 `Tracker.advance` 处 `AttributeError`。
    """
    pdef = PityDef(name='fx', btype=btype, scope='ssr', **kw)
    state = PityState()
    bh = create_behavior(pdef, state)
    bh._rebind_state(state)
    return bh, state


class TestEventPresetsS43:
    """六类 preset 工厂本体（§3.2 / §3.10.3 / §七 S4-3 的验收面）。"""

    def test_gate3_all_entries_preset_form(self):
        """**GATE-3 收口**：10 条目一律 `class: None` + 可调用 `preset`（ISSUE-015 终局）。

        收口后 `_validate_registry()` 的「无 `preset` 键」过渡分支已删除，
        故本断言与导入期判据是同一条纪律的两面：条目既无 `preset` 又无 `class`
        时导入即失败。
        """
        assert set(BEHAVIOR_REGISTRY) >= set(_ALL_TYPES)
        for t in _ALL_TYPES:
            entry = BEHAVIOR_REGISTRY[t]
            assert entry['class'] is None, f'{t}: class 未置 None'
            assert callable(entry['preset']), f'{t}: preset 不可调用'
        _validate_registry()          # 显式重跑收口判据（不只靠导入期那一次）

    def test_all_ten_presets_construct_in_engine(self):
        """全部 10 类经 `PityEngine` 构造后 `len(engine.behaviors) == 1`（§六 ISSUE-204）。

        `PityEngine.__init__` 对 preset 构造失败只 `logger.warning` 后**跳过**
        （不抛），跳过会让 `_resolve_order` / `_validate_behaviors` 在截断后的列表上
        执行、形成「配置里写了保底、运行时该保底不存在且无可见报错」。逐类单独建
        engine 是**唯一**能同时容纳 10 类的形态：规则 3 禁同 scope 两个事件驱动型，
        故「一个 engine 装 10 条同 scope 保底」在任何合法配置下都不存在。
        """
        for t in _ALL_TYPES:
            engine = PityEngine(pool_specs={}, pity_defs=[
                PityDef(name=f'n_{t}', btype=t, scope='ssr')],
                state=PityState(), rarity_rank={'ssr': 0, 'sr': 1, 'r': 2})
            assert len(engine.behaviors) == 1, f'{t}: preset 构造失败被静默跳过'
            assert isinstance(engine.behaviors[f'n_{t}'], Pity)

    def test_mixed_engine_behavior_count_equals_defs(self):
        """合法混合配置（5 条、scope 不冲突）下 `len(engine.behaviors) == len(pity_defs)`。"""
        defs = [
            PityDef(name='m_hard', btype='hard', scope='ssr', threshold=90),
            PityDef(name='m_soft', btype='soft_step', scope='ssr',
                    deltas=((73, 0.0), (17, 5.88))),
            PityDef(name='m_rot', btype='rotating', scope='ssr'),
            PityDef(name='m_tgt', btype='targeted', scope='sr'),
            PityDef(name='m_rot_soft', btype='rotating_soft', scope='r',
                    deltas=((74, 0.0), (16, 6.0))),
        ]
        engine = PityEngine(pool_specs={}, pity_defs=defs, state=PityState(),
                            rarity_rank={'ssr': 0, 'sr': 1, 'r': 2})
        assert len(engine.behaviors) == len(defs)

    def test_preset_key_sets_within_five_key_universe(self):
        """六类 preset 返回 dict ⊆ 五键全集且含三必需键（AUDIT-BREAK-3 的上界口径）。"""
        for t in _C43_TYPES:
            built = BEHAVIOR_REGISTRY[t]['preset'](PityDef(name=t, btype=t))
            assert isinstance(built, dict), t
            assert _REQUIRED_KEYS <= set(built) <= _KEY_UNIVERSE, (t, sorted(built))

    def test_preset_is_factory_not_module_level_instance(self):
        """工厂不是模块级常量实例（ISSUE-005）：两次调用返回互不相同的零件。

        模块级赋值会让同一 preset 的所有保底共享同一批 Counter/Flag 遥控器，
        `_rebind_state` 把它们重绑到最后调度的保底，串扰既跨保底又跨模拟。
        """
        pd = PityDef(name='x', btype='rotating_soft')
        factory = BEHAVIOR_REGISTRY['rotating_soft']['preset']
        a, b = factory(pd), factory(pd)
        for i in range(len(a['trackers'])):
            assert a['trackers'][i] is not b['trackers'][i]
        for i in range(len(a['modifiers'])):
            assert a['modifiers'][i] is not b['modifiers'][i]
        assert a['lifecycle'] is not b['lifecycle']
        # 六类逐一确认 trackers / modifiers 非空（空列表下的身份断言恒真、无信息量）
        for t in _C43_TYPES:
            built = BEHAVIOR_REGISTRY[t]['preset'](PityDef(name=t, btype=t))
            assert built['trackers'] and built['modifiers'], t

    @pytest.mark.parametrize('btype', _C43_TYPES)
    def test_event_presets_write_no_target_key(self, btype):
        """六类一律不写 `target=`（ISSUE-403）：`target_featured=True` 不改变零件构成。

        旧实现忽略事件驱动族的 `target_featured`（`RotatingBehavior.__init__` 收进
        `**kwargs` 后丢弃，三个 `_soft` 变体内层也未传该值），故把 `_preset_hard`
        的 `_target_of(pdef)` 照抄到本族即为语义漂移。`HardModifier` 是 `target` 的
        **唯一消费者**，故「modifiers 里无 `HardModifier`」+「无零件带 `_target`」
        两条共同钉住该契约（漏写不报错，`target` 默认 `'scope'`）。
        """
        built = BEHAVIOR_REGISTRY[btype]['preset'](
            PityDef(name='tf', btype=btype, target_featured=True))
        for mod in built['modifiers']:
            # 实质守卫有两条（S4-3 审查 low 订正：原先还断言 `not hasattr(mod,
            # '_target')`，而本族三个 Modifier 类都不定义该属性，任何现状变异都不会
            # 让它变红，属无判别力的冗余）。
            # ① `HardModifier` 是 `target` 的**唯一**消费者，本族出现它即语义漂移；
            # ② 本族三个 Modifier 的构造签名都不收 `target`，故「preset 在
            # `target_featured=True` 下能构造成功」本身即排除漏传（漏传会
            # `TypeError`，上面的构造即用例本体）。
            assert not isinstance(mod, HardModifier), btype
        # 本族不是 7B 的硬拒面（7B 只拒 `soft_*` 前缀三型），构造不得抛
        bh = create_behavior(
            PityDef(name='tf', btype=btype, target_featured=True), PityState())
        assert isinstance(bh, Pity)

    @pytest.mark.parametrize('btype', _SOFT_FAMILY)
    def test_soft_family_has_namespace_carrier(self, btype):
        """三个 `_soft` 类型的 preset 必须含 `NamespaceTracker(namespace=f'{name}_soft')`
        （ISSUE-407，强制）。

        缺它则 `X_soft` 命名空间不存在、`Lifecycle.initialize` 的推广写入无处落，
        `PityState.to_dict()` 的快照口径随之与旧实现不一致（ISSUE-023 的
        `X_soft: {_active: True}` 是 S1–S5 逐场一致的前提）。
        """
        built = BEHAVIOR_REGISTRY[btype]['preset'](PityDef(name='ns', btype=btype))
        carriers = [tr for tr in built['trackers'] if isinstance(tr, NamespaceTracker)]
        assert len(carriers) == 1, f'{btype}: 命名空间载体缺失或重复'
        assert carriers[0].namespace == 'ns_soft'
        assert carriers[0].state_keys() == (), '载体语义为空，不声明任何状态键'

    @pytest.mark.parametrize('btype', _SOFT_FAMILY)
    def test_soft_namespace_active_written_by_lifecycle(self, btype):
        """`X_soft: {_active: True}` 由 `Lifecycle.initialize` 的推广作用域写入（ISSUE-407）。"""
        bh, state = _fx_build(btype)
        assert state.get('fx', '_active') is True
        assert state.get('fx_soft', '_active') is True, 'X_soft 的 _active 未写入'
        # `X_soft` 只含 `_active`（旧实现在该空间也只有这一个键）
        assert state.to_dict()['data']['fx_soft'] == {'_active': True}

    def test_soft_counter_lands_in_default_namespace(self):
        """软计数落在默认 view（`X` 命名空间），对齐旧 mixin 的 `X.counter`（§3.10.3）。

        软计数若落进 `X_soft`，`SoftModifier`（读默认 view）恒读到 0、
        软保底静默失效；本断言是该失效模式的唯一捕获面。
        """
        bh, state = _fx_build('rotating_soft', deltas=((74, 0.0), (16, 6.0)))
        bh.before_draw(PityContext(draw=_fx_draw(), current=dict(_FX_BASE), state=state))
        assert state.get('fx', 'counter') == 1
        assert 'counter' not in state.to_dict()['data']['fx_soft']

    def test_flags_counters_consumers(self):
        """`flags` / `counters` 被 `Pity.__init__` 真写进 state（AUDIT-BREAK-3 消费者断言）。

        逐条对齐旧类的构造期写入：`rotating` 族 `guaranteed_init`、`targeted` 族
        `guaranteed_init` + `fate_points_init`、三个 `_soft` 类型的软计数
        `counter_init`。判据取「声明了初值但没人读」这一失效模式的反面。
        """
        _, st = _fx_build('rotating', guaranteed_init=True)
        assert st.get('fx', 'guaranteed') is True

        _, st = _fx_build('targeted', guaranteed_init=True, fate_points_init=3)
        assert st.get('fx', 'guaranteed') is True
        assert st.get('fx', 'fate_points') == 3

        _, st = _fx_build('targeted_soft', counter_init=7, fate_points_init=2)
        assert st.get('fx', 'counter') == 7
        assert st.get('fx', 'fate_points') == 2

    def test_consumers_truthy_rule(self):
        """truthy 规则：初值为 0 / False 时不预建键（对齐 `_build_pity_state_init`）。"""
        _, st = _fx_build('rotating_soft', counter_init=0, guaranteed_init=False)
        assert st.get('fx', 'counter') is None
        assert st.get('fx', 'guaranteed') is None

    def test_targeted_selected_modifier_tau_from_pdef(self):
        """`SelectedModifier` 的 `tau` 取 `pdef.fate_threshold`，`None` 回退 1（§3.2 补登行）。

        漏写 `tau=` 即该字段静默失效、阈值恒取缺省 1：`targeted(fate_threshold=0)`
        （G19 尘白禁区不歪池）会从「定轨即必出」退化为「定轨后须等 1 抽」。
        """
        built = _preset_targeted(PityDef(name='t', btype='targeted', fate_threshold=2))
        mod = built['modifiers'][0]
        assert isinstance(mod, SelectedModifier)
        assert mod._tau == 2
        assert _preset_targeted(PityDef(name='t', btype='targeted'))['modifiers'][0]._tau == 1
        assert _preset_targeted(
            PityDef(name='t', btype='targeted', fate_threshold=0))['modifiers'][0]._tau == 0
        assert _preset_targeted_soft(
            PityDef(name='t', btype='targeted_soft', fate_threshold=3)
        )['modifiers'][1]._tau == 3

    def test_targeted_fate_tracker_keys_and_judge(self):
        """`FateTracker` 的 `judge='selected'` 与四键写面由机制语义固定（§3.2 该行）。"""
        for factory, t in ((_preset_targeted, 'targeted'),
                           (_preset_targeted_soft, 'targeted_soft')):
            tr = factory(PityDef(name='t', btype=t))['trackers'][0]
            assert isinstance(tr, FateTracker)
            assert tr._judge == 'selected'
            assert tr.state_keys() == ('fate_points', 'losses',
                                       'guaranteed', 'lost_rotating')

    def test_cr_params_reach_streak_tracker(self):
        """`cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` 逐条取自 `pdef`。

        这三项不写即 `StreakTracker` 落默认值（阈值 3 / 基础率 0 / `[0.0]*3+[1.0]`），
        配置被静默忽略。
        """
        built = BEHAVIOR_REGISTRY['rotating_cr_soft']['preset'](
            PityDef(name='cr', btype='rotating_cr_soft',
                    cr_counter_threshold=5, cr_base_rate=0.0125,
                    cr_state_probs=[0.0, 0.1, 1.0]))
        streak = built['trackers'][0]
        assert isinstance(streak, StreakTracker)
        assert streak._max == 5
        assert streak._base_rate == 0.0125
        assert streak._state_probs == [0.0, 0.1, 1.0]
        # 缺省路径：三项全 None 时落 tracker 自带的缺省，与旧类同源
        d = BEHAVIOR_REGISTRY['rotating_cr']['preset'](
            PityDef(name='cr', btype='rotating_cr'))['trackers'][0]
        assert (d._max, d._base_rate, d._state_probs) == (3, 0.0, [0.0, 0.0, 0.0, 1.0])


class TestRotatingCrTrackerOrder:
    """`rotating_cr` / `rotating_cr_soft` 的 `[StreakTracker, FlagTracker]` 顺序契约。

    顺序是**语义的一部分**（RULING-6B′ / §3.1.1「Tracker 顺序是契约」条）：
    `StreakTracker.commit` 的归零条件含「抽前 `guaranteed` 未置位」一项，而
    `Pity.after_draw` 按 `trackers` 列表顺序调 `commit`。`FlagTracker` 排在前面时，
    两处读点取到同一个（抽后的）值，`cr_counter` 恒为 0。
    """

    _CR_SEQ = [('ssr', False), ('ssr', True)] * 4

    def test_tracker_order_is_streak_then_flag(self):
        """两个类型的 `trackers[0]` / `trackers[1]` 必须是 `StreakTracker` / `FlagTracker`。"""
        for t in ('rotating_cr', 'rotating_cr_soft'):
            built = BEHAVIOR_REGISTRY[t]['preset'](PityDef(name='cr', btype=t))
            assert isinstance(built['trackers'][0], StreakTracker), t
            assert isinstance(built['trackers'][1], FlagTracker), t

    def test_order_contract_pinned_semantically(self):
        """语义级：错位抽卡序列下 `cr_counter` 轨迹 == 旧类；顺序对调即恒 0。

        序列为「出 ssr 未命中 / 出 ssr 命中」交替四轮，故 `guaranteed` 每轮置位后
        又被命中清掉。轨迹 `[1, 1, 2, 2, 3, 3, 4, 4]` 的**奇数位**即「未命中累计
        +1」、偶数位即「命中当轮由抽前 `guaranteed` 短路、计数不动」——两者都要求
        `StreakTracker.commit` 读到的是**抽前**的 `guaranteed`（块报告的牙齿实测：
        顺序对调后该轨迹退化为全 0）。
        """
        from gacha_simulator.core.pity import RotatingCRBehavior

        bh, state = _fx_build('rotating_cr', cr_counter_threshold=3,
                              cr_state_probs=[0.0, 0.0, 0.0, 1.0])
        old_state = PityState()
        old = RotatingCRBehavior('fx', old_state, scope='ssr',
                                 cr_counter_threshold=3,
                                 cr_state_probs=[0.0, 0.0, 0.0, 1.0])
        old._rebind_state(old_state)

        traj_new, traj_old = [], []
        for rarity, featured in self._CR_SEQ:
            draw = _fx_draw(rarity, featured)
            bh.before_draw(PityContext(draw=draw, current=dict(_FX_BASE), state=state))
            old.before_draw(PityContext(draw=draw, current=dict(_FX_BASE),
                                        state=old_state))
            bh.after_draw(PityContext(draw=draw, current=dict(_FX_BASE), state=state))
            old.after_draw(PityContext(draw=draw, current=dict(_FX_BASE),
                                       state=old_state))
            traj_new.append(state.get('fx', 'cr_counter', 0))
            traj_old.append(old_state.get('fx', 'cr_counter', 0))

        assert traj_new == [1, 1, 2, 2, 3, 3, 4, 4]
        assert traj_new == traj_old, '与旧类的 cr_counter 轨迹必须逐位相同（M1 口径）'


class TestRedistributeScopeExportStillPresent:
    """`_redistribute_scope` 的导出**不属 S4-3 的删除面**（AUDIT-BREAK-8 C 项）。

    该符号随 **S8-4** 删（它是 S8 的替换对象）；S4-3 只删 10 个旧行为类 +
    `SoftPityMixin`。误删会使 S8 前的 `tests/core/test_pity_rotating.py` 导入即失败。
    """

    def test_redistribute_scope_exported_knowingly(self):
        import gacha_simulator.core as core_pkg
        assert '_redistribute_scope' in core_pkg.__all__
        assert callable(core_pkg._redistribute_scope)


# ══════════════════════════════════════════════════════════════════
# P64 S4-3：AUDIT-BREAK-8——10 个旧行为类 + `SoftPityMixin` 的 re-export 退役
# ══════════════════════════════════════════════════════════════════

# 随 S4-3 从 `gacha_simulator.core` 的公共面退役的 11 个符号。
# **不含** `_redistribute_scope`：它的导出随 S8-4 删（AUDIT-BREAK-8 的 C 项）。
_RETIRED_EXPORTS = (
    'SoftStepBehavior', 'CounterBasedBehavior', 'HardPityBehavior',
    'RotatingBehavior', 'RotatingSoftBehavior', 'RotatingCRBehavior',
    'RotatingCRSoftBehavior', 'TargetedBehavior', 'TargetedSoftBehavior',
    'SoftPityMixin',
)


class TestAuditBreak8ExportRetirement:
    """`core/__init__.py` 的双删面（AUDIT-BREAK-8）：import 与 `__all__` 必须同批。

    两个方向各有一条断言，因为它们**症状不同**：只删 `__all__` 留下仍可访问的
    re-export（旧类继续被新代码用，正是本步要消除的诱惑）；只删 import 留下指向
    未定义名字的 `__all__` 条目（`from gacha_simulator.core import *` 即
    `AttributeError`，而 `import gacha_simulator.core` 本身不报错）。
    """

    def test_old_classes_retired_from_package_face(self):
        """11 个符号既不在 `__all__`、也不作为本包属性存在（双删面同批）。"""
        import gacha_simulator.core as core_pkg
        for name in _RETIRED_EXPORTS:
            assert name not in core_pkg.__all__, \
                f'{name} 仍在 core.__all__（只删 import 的残留）'
            assert not hasattr(core_pkg, name), \
                f'{name} 仍是 core 的属性（只删 __all__ 的残留）'

    def test_old_class_bodies_survive_until_release(self):
        """旧类**本体**保留到发布前（GATE-5）：`core.pity` 的导入路径不受影响。

        S5a 的等价性 harness 直接 import 旧类构造对照物，故本体删除的时点是
        「发布前一次性移除旧保底类」，不是本步。
        """
        from gacha_simulator.core import pity as pity_mod
        for name in _RETIRED_EXPORTS:
            assert hasattr(pity_mod, name), f'{name} 的本体不该在本步删除（GATE-5）'

    def test_all_exports_resolvable(self):
        """`__all__` 的每个名字都必须是本包可解析属性（re-export 不得悬空）。

        `__all__` 是纯字符串列表，删除 import 而留下条目**不会**让
        `import gacha_simulator.core` 报错，只会让 `import *` 与 `getattr` 在
        使用期炸；本断言把该形态提前到测试期暴露。
        """
        import gacha_simulator.core as core_pkg
        missing = [n for n in core_pkg.__all__ if not hasattr(core_pkg, n)]
        assert missing == [], f'__all__ 含无法解析的名字（re-export 悬空）：{missing}'


# ══════════════════════════════════════════════════════════════════
# P64 S4-4：10 个 preset 的 `lifecycle` 键接线（§六 ISSUE-301 / ISSUE-032）
# ══════════════════════════════════════════════════════════════════
# `lifecycle` 键的取值为 **Lifecycle 对象**（不是 `LifecycleConfig` 参数袋），由
# `build_lifecycle(pdef)` 按 §3.1.3 的两个正交维度产出。本组按**四组合取值表**
# 逐 btype 断言类型与两维字段的保真：只断言「键存在」（S4-2 / S4-3 已有）时，
# 键里的对象接错类、或两维之一被吞（`depends_on` 非空即忽略 `max_triggers` 的
# 旧写法）都测不出来。

_LIFECYCLE_FOUR_COMBINATIONS = [
    (None, 0, 'AlwaysActive'),
    (None, 2, 'FiniteActive'),
    ('src', 0, 'DependentActive'),
    ('src', 3, 'DependentFiniteActive'),
]


@pytest.mark.parametrize('btype', sorted(BEHAVIOR_REGISTRY))
@pytest.mark.parametrize('depends_on, max_triggers, want', _LIFECYCLE_FOUR_COMBINATIONS)
def test_preset_lifecycle_matches_four_combination_table(
        btype, depends_on, max_triggers, want):
    """`Pity._lifecycle` 按 §3.1.3 的四组合表产出（逐 btype × 逐组合）。"""
    pdef = PityDef(name='s44_lc', btype=btype, depends_on=depends_on,
                   max_triggers=max_triggers)
    bh = create_behavior(pdef, PityState())

    assert isinstance(bh, Pity), f'{btype} 未走 preset 分支'
    assert type(bh._lifecycle).__name__ == want, (
        f'{btype}（depends_on={depends_on!r}, max_triggers={max_triggers}）'
        f'→ {type(bh._lifecycle).__name__}，期望 {want}（§3.1.3 四组合表）')
    # 两维**独立**取值：`depends_on` 非空不吞 `max_triggers`（2026-09-28 修正）
    assert bh._lifecycle.depends_on == depends_on
    expect_keys = ('triggers',) if max_triggers > 0 else ()
    assert bh._lifecycle.state_keys() == expect_keys


@pytest.mark.parametrize('btype', sorted(BEHAVIOR_REGISTRY))
def test_preset_lifecycle_carries_deactivate_on_early_hit(btype):
    """§六 ISSUE-301 ②：`deactivate_on_early_hit` 一路带入，**不得恒 False**。

    `create_behavior` 是配置面唯一的装配入口，故逐 btype 走真实构造；只在
    `build_lifecycle` 层断言时，「preset 返回的 dict 里该对象被换成别的实例」
    这一失效模式不可见。
    """
    off = create_behavior(PityDef(name='s44_off', btype=btype), PityState())
    on = create_behavior(
        PityDef(name='s44_on', btype=btype, deactivate_on_early_hit=True),
        PityState())
    assert off._lifecycle.deactivate_on_early_hit is False
    assert on._lifecycle.deactivate_on_early_hit is True
