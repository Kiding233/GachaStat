"""`_validate_behaviors()` 四条规则的回归测试。

背景：该函数是保底配置的**唯一安全网**，此前 `tests/` 下零引用（无任何断言覆盖）。
本文件补齐四条规则的触发路径，并记录两项现状异常（见下）。

覆盖：
- 规则 2/3/4 经 `PityEngine` 构造路径触发（同 scope 双 hard / 双事件驱动 / 同 btype 双 soft）
- 规则 1（name 重名）经直接调用触发：构造路径不可达
- 边界：同 scope 但 btype 不同 的两个 soft 不冲突

修复记录（2026-09-16，两项现状异常均已修复）：
1. **规则 1 构造路径不可达** 已修：`PityEngine.__init__` 现在在构造 behavior 前
   先做重名校验，重名直接抛 `ValueError`（此前被 dict 静默覆盖，只留后者）。
2. **scope 未接通** 已修：`create_behavior()` 现在优先读取 `PityDef.scope`，
   缺省时回退 `BEHAVIOR_REGISTRY` 的 `default_scope`。跨稀有度保底配置自此生效，
   `_validate_behaviors()` 的「同 scope」判断按真实 scope 工作。

对应断言见 `TestNameDuplicate` 与 `TestScopeWired`。
"""

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    PityEngine,
    PityState,
    _validate_behaviors,
    create_behavior,
)

_RARITY = {'ssr': 0, 'sr': 1, 'r': 2}


def _engine(pity_defs):
    """最小构造：pool_specs 留空，只走 behavior 注册 + 校验路径。"""
    return PityEngine(
        pool_specs={}, pity_defs=pity_defs, state=PityState(), rarity_rank=_RARITY,
    )


class TestValidConfigPasses:
    """合法配置不抛异常：各 btype 的最小可构造形态。"""

    def test_single_hard(self):
        _engine([PityDef(name='h', btype='hard', scope='ssr', threshold=90)])

    def test_single_soft_interval(self):
        _engine([PityDef(name='s', btype='soft_interval', scope='ssr',
                         soft_start=73, soft_end=90)])

    def test_single_rotating(self):
        _engine([PityDef(name='r', btype='rotating', scope='ssr')])

    def test_two_soft_with_different_btype(self):
        """边界：同 scope 但 btype 不同 → 规则 4 只禁「同 btype」。"""
        _engine([
            PityDef(name='s1', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
            PityDef(name='s2', btype='soft_additive', scope='ssr',
                    soft_start=70, soft_increment=6),
        ])


class TestScopeOverlapConflicts:
    """规则 2/3/4：经 PityEngine 构造路径触发 ConfigError。"""

    def test_two_hard_same_scope(self):
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine([
                PityDef(name='h1', btype='hard', scope='ssr', threshold=90),
                PityDef(name='h2', btype='hard', scope='ssr', threshold=80),
            ])

    def test_two_event_driven_same_scope(self):
        with pytest.raises(ConfigError, match='两个事件驱动型'):
            _engine([
                PityDef(name='r1', btype='rotating', scope='ssr'),
                PityDef(name='r2', btype='rotating', scope='ssr'),
            ])

    def test_two_soft_same_btype_same_scope(self):
        with pytest.raises(ConfigError, match='存在两个软保底'):
            _engine([
                PityDef(name='s1', btype='soft_interval', scope='ssr',
                        soft_start=73, soft_end=90),
                PityDef(name='s2', btype='soft_interval', scope='ssr',
                        soft_start=70, soft_end=85),
            ])


class TestNameDuplicate:
    """规则 1：name 重名 → ValueError。"""

    def test_duplicate_name_direct_call(self):
        """直接调用可触发：这是该规则唯一可达的路径（见模块 docstring 发现 1）。"""
        st = PityState()
        bh1 = create_behavior(
            PityDef(name='dup', btype='hard', scope='ssr', threshold=90), st)
        bh2 = create_behavior(
            PityDef(name='dup', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90), st)
        with pytest.raises(ValueError, match='重复的 behavior name'):
            _validate_behaviors([bh1, bh2])

    def test_duplicate_name_via_engine_raises(self):
        """构造路径亦抛错（2026-09-16 修复：此前被 dict 静默覆盖、只留后者）。"""
        with pytest.raises(ValueError, match='重复的保底 name'):
            _engine([
                PityDef(name='dup', btype='hard', scope='ssr', threshold=90),
                PityDef(name='dup', btype='soft_interval', scope='ssr',
                        soft_start=73, soft_end=90),
            ])


class TestScopeWired:
    """scope 已接通（2026-09-16 修复）：`PityDef.scope` 现在传递到 behavior。

    修复前 `create_behavior()` 只读 registry 的 `default_scope`（全为 "ssr"），
    `PityDef.scope` 被静默忽略，跨稀有度保底无法配置。
    """

    def test_behavior_scope_follows_pitydef(self):
        """写 scope='sr'，behavior 实得 'sr'（此前恒为 registry 的 'ssr'）。"""
        engine = _engine([
            PityDef(name='h', btype='hard', scope='sr', threshold=90),
        ])
        assert engine._behavior_list[0]._scope == 'sr'

    def test_empty_scope_falls_back_to_registry_default(self):
        """scope 缺省时回退 registry 的 default_scope（'ssr'）。"""
        engine = _engine([
            PityDef(name='h', btype='hard', scope='', threshold=90),
        ])
        assert engine._behavior_list[0]._scope == 'ssr'

    def test_different_scope_hard_coexist(self):
        """跨 scope 的同类保底现在可以共存（互斥判断按真实 scope 走）。"""
        engine = _engine([
            PityDef(name='h1', btype='hard', scope='ssr', threshold=90),
            PityDef(name='h2', btype='hard', scope='sr', threshold=80),
        ])
        assert len(engine.behaviors) == 2
