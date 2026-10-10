"""P64 S4-1：registry schema 改造（过渡判据 + `create_behavior` 的 preset 分支，§3.2）。

覆盖：
- `_validate_registry()` 的**过渡判据**（GATE-3 定稿）两形态判定：含 `preset` 键判
  其可调用（导入期**不调用 preset、不校验返回键集**，ISSUE-405）；无 `preset` 键
  （尚未迁移）走旧判据（`class` 非 None 且为 `PityBehavior` 子类）；
- **过渡期两种条目形态都自洽**：现有 10 条旧形态经 `_validate_registry()` 通过 +
  人为注入的 preset 形态条目亦通过；
- 非法条目**必抛**（非 callable 的 `preset`、未迁移条目 `class` 置 `None`），
  **不得只测「不抛」**；
- `create_behavior` 的 preset 分支：按名取键构造 `Pity`、两道**互补**校验各抛
  `ConfigError`（查多未知键 / 查漏 `lifecycle`）、无 preset 且 `class` 为 `None` 时报未实现；
- `Pity.__init__` 签名不含旧类分支的两个注入点（`target_featured` / `reset`）。

**P64 S4-2 追加（本文件下半的 `TestCounterPresetsS42`）**：counter 驱动四类
（`soft_interval` / `soft_additive` / `soft_step` / `hard`）的 preset 工厂本体——
条目原子形态、五键全集、`flags` / `counters` 的**消费者断言**、`priority` 走构造形参、
`_target_of` 的 `target=` 选择子、裁决 7B 的类型级硬拒、以及「工厂不是模块级常量实例」。

**S4-3 收口时的删除面**：`TestValidateRegistryTransition` 里「无 `preset` 键」形态的
三条用例（旧形态通过 / 未迁移条目 class 置 None 必抛 / 无 preset 且 class None 报未实现）
随过渡分支一并删除；`TestValidateRegistryPresetForm` 与 `TestCreateBehaviorPresetBranch`
不受收口影响。
"""
import inspect

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    BEHAVIOR_REGISTRY, HardPityBehavior, Pity, _preset_hard, _preset_soft_step,
    _target_of, _validate_registry, create_behavior,
)
from gacha_simulator.core.pity_modifier import HardModifier, SoftModifier
from gacha_simulator.core.pity_primitives import PityState
from gacha_simulator.core.pity_tracker import AlwaysActive, CounterTracker


# ══════════════════════════════════════════════════════════════════
# 临时 registry 条目注入装置
# ══════════════════════════════════════════════════════════════════

_FAKE_VALID = '_s4_1_fake_valid_preset'
_FAKE_FLAGS = '_s4_1_fake_flags_counters'
_FAKE_UNKNOWN_KEY = '_s4_1_fake_unknown_key'
_FAKE_NO_LIFECYCLE = '_s4_1_fake_no_lifecycle'
_FAKE_BAD_PRESET = '_s4_1_fake_bad_preset'
_FAKE_LEGACY_NONE = '_s4_1_fake_legacy_none'


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
# `_validate_registry()` 过渡判据
# ══════════════════════════════════════════════════════════════════

class TestValidateRegistryTransition:
    """过渡判据：「无 `preset` 键」形态沿用旧判据（S4-3 收口删除）。"""

    def test_current_entries_pass_validate_registry(self):
        """现有 10 条目（S4-1 时全为旧形态）经判据通过（**显式重跑**，不只靠导入）。"""
        # 条目数用 `>=` 而非 `== 10`（S4-1 审查 minor）：S6a 注册 `rotating_inverse`、
        # S9-3 再增两条后，写死的等值断言必红，而那不是本用例要守的东西。此处只守
        # 「既有条目未被误删」这一下限。
        assert len(BEHAVIOR_REGISTRY) >= 10
        _validate_registry()  # 不抛即通过

    def test_unmigrated_entry_with_class_none_raises(self):
        """未迁移条目（无 `preset` 键）把 `class` 置 `None` 则判据必抛。

        这正是过渡判据相对旧判据**收严**的那一格：旧代码 `if cls is not None`
        会把 `class: None` 静默放过，条目既无 preset 又无 class 即「构造时必炸」。
        """
        entry = _entry(**{'class': None})
        BEHAVIOR_REGISTRY[_FAKE_LEGACY_NONE] = entry
        try:
            with pytest.raises(TypeError, match='必须提供 PityBehavior 子类'):
                _validate_registry()
        finally:
            BEHAVIOR_REGISTRY.pop(_FAKE_LEGACY_NONE, None)

    def test_unmigrated_entry_with_non_subclass_raises(self):
        """未迁移条目的 `class` 不是 `PityBehavior` 子类则判据必抛。"""
        entry = _entry(**{'class': dict})
        BEHAVIOR_REGISTRY[_FAKE_LEGACY_NONE] = entry
        try:
            with pytest.raises(TypeError, match='必须提供 PityBehavior 子类'):
                _validate_registry()
        finally:
            BEHAVIOR_REGISTRY.pop(_FAKE_LEGACY_NONE, None)


class TestValidateRegistryPresetForm:
    """过渡判据：「含 `preset` 键」形态判其可调用（S4-3 收口后为唯一形态）。"""

    def test_callable_preset_passes(self, registry_entries):
        """preset 形态条目通过判据：两种形态在过渡期都自洽。"""
        registry_entries(_FAKE_VALID, _entry(preset=_preset_valid))
        _validate_registry()

    def test_non_callable_preset_raises(self, registry_entries):
        """`preset` 非 callable 则判据必抛（导入期唯一的 preset 侧判据）。"""
        registry_entries(_FAKE_BAD_PRESET, _entry(preset='not-callable'))
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

        「原子」的含义：`class` 置空与 `preset` 赋值必须在同一条目上同时成立——
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

        上界取五键全集而非子集判断的补集——子集式（`<= set(x)`）不拒绝多余键，
        「`flags` / `counters` 成了死键」在其下不可见（AUDIT-BREAK-3）。
        """
        for t in _C42_TYPES:
            built = BEHAVIOR_REGISTRY[t]['preset'](PityDef(name=t, btype=t))
            assert isinstance(built, dict), t
            assert _REQUIRED_KEYS <= set(built) <= _KEY_UNIVERSE, (t, sorted(built))

    def test_preset_is_factory_not_module_level_instance(self):
        """③ 工厂不是模块级常量实例（ISSUE-005）：两次调用返回互不相同的零件。

        模块级赋值会让同一 preset 的所有保底共享同一批 Counter/Flag 遥控器，
        `_rebind_state` 把它们重绑到最后调度的保底——串扰既跨保底又跨模拟。
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

        `SoftModifier` 的构造形参只有 `(scope, deltas)`——若有人给它加 `target=`
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
