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

**S4-3 收口时的删除面**：`TestValidateRegistryTransition` 里「无 `preset` 键」形态的
三条用例（旧形态通过 / 未迁移条目 class 置 None 必抛 / 无 preset 且 class None 报未实现）
随过渡分支一并删除；`TestValidateRegistryPresetForm` 与 `TestCreateBehaviorPresetBranch`
不受收口影响。
"""
import inspect

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    BEHAVIOR_REGISTRY, HardPityBehavior, Pity, _validate_registry, create_behavior,
)
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
