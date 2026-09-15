"""`_validate_behaviors()` 四条规则的回归测试。

背景：该函数是保底配置的**唯一安全网**，此前 `tests/` 下零引用（无任何断言覆盖）。
本文件补齐四条规则的触发路径，并记录两项现状异常（见下）。

覆盖：
- 规则 2/3/4 经 `PityEngine` 构造路径触发（同 scope 双 hard / 双事件驱动 / 同 btype 双 soft）
- 规则 1（name 重名）经直接调用触发——构造路径不可达
- 边界：同 scope 但 btype 不同 的两个 soft 不冲突

发现记录（2026-09-15，编写本测试时发现）：
1. **规则 1 在构造路径不可达**：`PityEngine.__init__` 先把 behavior 存入
   `self.behaviors[pdef.name]`，同名条目被后者静默覆盖，传到
   `_validate_behaviors()` 的列表中已无重名元素。故该规则只在直接调用时生效。
2. **scope 未接通**：`create_behavior()` 从不读取 `PityDef.scope`，behavior 的
   `_scope` 恒取自 `BEHAVIOR_REGISTRY` 条目的 `default_scope`（10 个条目全为
   `"ssr"`）。因此 `_validate_behaviors()` 的「同 scope」判断实际等价于「全局」，
   跨 scope 的互斥豁免当前不可能达成。两类现状断言见 `TestScopeNotWired`。

以上两项均待裁决，裁决后本文件需相应更新。
"""

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    PityEngine,
    PityState,
    _validate_behaviors,
    create_behavior,
)

_RARITY = {'ssr': 0, 'weapon': 1}


def _engine(pity_defs):
    """最小构造——pool_specs 留空，只走 behavior 注册 + 校验路径。"""
    return PityEngine(
        pool_specs={}, pity_defs=pity_defs, state=PityState(), rarity_rank=_RARITY,
    )


class TestValidConfigPasses:
    """合法配置不抛异常——各 btype 的最小可构造形态。"""

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
        """直接调用可触发——这是该规则唯一可达的路径（见模块 docstring 发现 1）。"""
        st = PityState()
        bh1 = create_behavior(
            PityDef(name='dup', btype='hard', scope='ssr', threshold=90), st)
        bh2 = create_behavior(
            PityDef(name='dup', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90), st)
        with pytest.raises(ValueError, match='重复的 behavior name'):
            _validate_behaviors([bh1, bh2])

    def test_duplicate_name_engine_path_silently_overwrites(self):
        """现状记录：经构造路径重名不报错——被 dict 静默覆盖，只留后一条。

        若将来在 PityEngine 构造前做重名检查，本用例需改为断言抛错。
        """
        engine = _engine([
            PityDef(name='dup', btype='hard', scope='ssr', threshold=90),
            PityDef(name='dup', btype='hard', scope='ssr', threshold=80),
        ])
        assert len(engine.behaviors) == 1
        assert engine.behaviors['dup']._threshold == 80  # 后者覆盖前者


class TestScopeNotWired:
    """现状记录：scope 未接通（见模块 docstring 发现 2）。

    期望（按设计）：不同 scope 的同类保底不互斥。
    实际：`PityDef.scope` 被忽略，`_scope` 恒为 `default_scope`（"ssr"），
    两条不同 scope 的 hard 仍判为同 scope 冲突。

    待该项裁决后，`test_different_scope_hard_still_conflicts` 应改为
    正向断言（构造不抛异常）。
    """

    def test_behavior_scope_ignores_pitydef_scope(self):
        """写 scope='weapon'，behavior 实得 'ssr'。"""
        engine = _engine([
            PityDef(name='h', btype='hard', scope='weapon', threshold=90),
        ])
        assert engine._behavior_list[0]._scope == 'ssr'

    def test_different_scope_hard_still_conflicts(self):
        """跨 scope 豁免当前不可能达成——两条不同 scope 的 hard 仍冲突。"""
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine([
                PityDef(name='h1', btype='hard', scope='ssr', threshold=90),
                PityDef(name='h2', btype='hard', scope='weapon', threshold=80),
            ])
