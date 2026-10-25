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

import fnmatch

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.pity import (
    BEHAVIOR_REGISTRY,
    Pity,
    PityEngine,
    PityState,
    PoolPitySpec,
    _validate_behaviors,
    create_behavior,
)

_RARITY = {'ssr': 0, 'sr': 1, 'r': 2}


def _engine_with_pools(pity_defs, pool_ids):
    """按 `PityDef.pools` 的 fnmatch 口径生成 `pool_specs` 后构造引擎。

    生成式与 `service/batch_simulator.py` 的 `spec_pity_names` 段同源（全限定键
    `{banner_id}.{pool_id}` + `pools == ('*',)` 短路 + `fnmatch.fnmatch`），
    故本辅助产出的 `pity_names` 就是运行时那份「哪个保底绑哪个池」的事实。
    """
    pool_specs = {}
    for pid in pool_ids:
        names = [d.name for d in pity_defs
                 if d.pools == ('*',)
                 or any(fnmatch.fnmatch(pid, ptn) for ptn in d.pools)]
        pool_specs[pid] = PoolPitySpec(pity_names=names)
    return PityEngine(pool_specs=pool_specs, pity_defs=pity_defs,
                      state=PityState(), rarity_rank=_RARITY)


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


class TestEngineConstructFailure:
    """S4-5（ISSUE-204）：`PityEngine` 构造失败由「`logger.warning` 后跳过」改为抛 `ConfigError`。

    旧形态的失效链：构造失败的那条保底被 `except Exception → logger.warning` 从
    `self.behaviors` 里删掉，紧随其后的 `_resolve_order` / `_validate_behaviors` 于是跑在
    **截断后**的列表上，同 scope 互斥校验（规则 2/3/4）失去语义，形成「配置里写了保底、
    运行时该保底不存在且无可见报错」。
    """

    def test_engine_construct_failure_raises_config_error(self, monkeypatch):
        """构造失败抛 `ConfigError`，且排序/校验**不得**在截断后的列表上执行。

        失败项取 7B 类型级硬拒（`soft_*` + `target_featured=true`，`create_behavior`
        内抛 `ConfigError`）：它与同 scope 的 `hard` 本属**互斥**组合，旧形态下该条被
        跳过、`_validate_behaviors` 只见 `hard` 一条、静默通过。
        """
        import gacha_simulator.core.pity as pity_mod

        calls = []
        real_resolve = pity_mod._resolve_order
        real_validate = pity_mod._validate_behaviors

        def _spy_resolve(behaviors, rarity_rank=None):
            calls.append(('resolve', [getattr(b, '_name', None) for b in behaviors]))
            return real_resolve(behaviors, rarity_rank)

        def _spy_validate(behaviors, pool_specs=None):
            # 签名与调用点同步（缺陷 13 起 `_validate_behaviors` 收 `pool_specs`
            # 第二实参）：替身不改判据，只记录「谁被传了进来」。
            calls.append(('validate', [getattr(b, '_name', None) for b in behaviors]))
            return real_validate(behaviors, pool_specs)

        monkeypatch.setattr(pity_mod, '_resolve_order', _spy_resolve)
        monkeypatch.setattr(pity_mod, '_validate_behaviors', _spy_validate)

        with pytest.raises(ConfigError, match='bad_soft'):
            _engine([
                PityDef(name='ok_hard', btype='hard', scope='ssr', threshold=90),
                PityDef(name='bad_soft', btype='soft_interval', scope='ssr',
                        soft_start=73, soft_end=90, target_featured=True),
            ])
        assert calls == [], (
            '构造失败后仍在**截断后**的列表上执行了排序/校验——旧形态下这里会拿到 '
            '[ok_hard] 并静默通过（同 scope 互斥校验失去语义）')

        # 反向：全部可构造时，两者在**完整**列表（2 条）上执行，即列表未被截断
        _engine([
            PityDef(name='ok_hard', btype='hard', scope='ssr', threshold=90),
            PityDef(name='ok_rot', btype='rotating', scope='ssr'),
        ])
        assert [len(names) for _kind, names in calls] == [2, 2], (
            f'合法配置下排序/校验须在完整列表上执行，实得 {calls}')

    def test_engine_construct_unknown_type_raises_config_error(self):
        """未知 `btype`（`create_behavior` 首行 `KeyError`）同样归为 `ConfigError`。

        ISSUE-204 的措辞是「**任一** preset 构造失败抛 `ConfigError`」：只放行
        `ConfigError` 会让 `KeyError` 这类失败形态以非配置错误的类型逃逸，而它的
        成因同样是配置写错。
        """
        with pytest.raises(ConfigError, match='未知类型'):
            _engine([PityDef(name='u', btype='未知类型', scope='ssr')])


# ══════════════════════════════════════════════════════════════════
# P64 S9-3：G3 双实现的两个 type（§3.10.4 配套第 1 条）
# ══════════════════════════════════════════════════════════════════

_SKIP_TYPE = 'hard_exclude_owned_skip'
_ANY_TYPE = 'hard_exclude_owned_any'


class TestHardExcludeOwned:
    """`hard_exclude_owned_skip` / `hard_exclude_owned_any` 的 registry 接线。

    **本组只验构造与接线**（GATE-6 的块级最小验收）：两条 type 经 `create_behavior`
    能构造出 `Pity`、`on_all_owned` 形态随构造参数正确落到 `NotOwnedModifier`、preset
    四键齐全（trackers / modifiers / lifecycle / counters）、`threshold` 缺省回退 50、
    `CounterTracker.reset_on` 取 `pdef.reset or scope`（**不得写死 `"scope"`**）。

    **G3 的「全拥有」行为断言随 §3.10.4 的待确认项挂起**：该分支（候选 a / 候选 b）
    零直接信源、两形态并列，机制定稿前均不作为已定稿验收，故归 S9-4（§六 G3 专项
    ③a / ③b）。本组不断言两形态的语义后果。
    """

    @staticmethod
    def _wired(btype, want, scope='ssr', **kw):
        """构造一次并返回（preset 产出的 dict, behavior 实例）。"""
        pdef = PityDef(name='g3_' + want, btype=btype, scope=scope, **kw)
        built = BEHAVIOR_REGISTRY[btype]['preset'](pdef)
        return built, create_behavior(pdef, PityState())

    def _assert_common(self, btype, want, **kw):
        from gacha_simulator.core.pity import CounterTracker
        from gacha_simulator.core.pity_modifier import NotOwnedModifier

        entry = BEHAVIOR_REGISTRY[btype]
        assert entry['class'] is None, f'{btype}: class 未置 None'
        assert callable(entry['preset']), f'{btype}: preset 不可调用'
        assert entry['default_scope'] == 'ssr', f'{btype}: default_scope 须为 ssr'
        assert entry['params']['threshold']['default'] == 50, (
            f'{btype}: threshold 的 params 默认值须为 50（与机制一致，hard 为 90）')

        built, bh = self._wired(btype, want, **kw)
        # 四键齐全（§3.10.4 配套第 1 条，对照 _preset_hard）
        assert set(built) == {'trackers', 'modifiers', 'lifecycle', 'counters'}, (
            f'{btype}: preset 须四键齐全，实得 {sorted(built)}')

        assert isinstance(bh, Pity), f'{btype}: 未走 preset 分支'
        assert bh._btype == btype
        assert bh.is_hard is True, f'{btype}: 须在 _HARD_TYPES 内（同 scope 互斥判据）'
        assert bh.is_soft is False and bh.is_event_driven is False

        assert len(bh._modifiers) == 1
        mod = bh._modifiers[0]
        assert isinstance(mod, NotOwnedModifier), (
            f'{btype}: modifiers[0] 须为 NotOwnedModifier，实得 {type(mod).__name__}')
        assert mod._on_all_owned == want, (
            f'{btype}: 形态未随构造参数落到 NotOwnedModifier '
            f'（实得 {mod._on_all_owned!r}，期望 {want!r}）')
        assert mod._scope == 'ssr'
        assert mod.uses_sim == ('owns',), f'{btype}: 须申报读取 ctx.sim 的 owns 源'
        assert mod.state_keys() == ('counter',)

        assert len(bh._trackers) == 1
        tr = bh._trackers[0]
        assert isinstance(tr, CounterTracker), f'{btype}: trackers[0] 须为 CounterTracker'
        assert tr._scope == 'ssr'
        assert bh._lifecycle is not None, f'{btype}: lifecycle 缺则生命周期三字段静默失效'
        return bh, mod

    def test_create_behavior_hard_exclude_owned_skip(self):
        """`hard_exclude_owned_skip`（形态 a）的构造与接线（§3.10.4 候选 a）。"""
        _bh, mod = self._assert_common(_SKIP_TYPE, 'skip')
        assert mod._threshold == 50, 'threshold 缺省须回退 50（PityDef.threshold 默认 None）'

    def test_create_behavior_hard_exclude_owned_any(self):
        """`hard_exclude_owned_any`（形态 b）的构造与接线（§3.10.4 候选 b）。"""
        _bh, mod = self._assert_common(_ANY_TYPE, 'any')
        assert mod._threshold == 50, 'threshold 缺省须回退 50（PityDef.threshold 默认 None）'

    def test_two_forms_differ_only_in_on_all_owned(self):
        """两条 type **除 `on_all_owned` 取值外完全同构**（§3.10.4 配套第 1 条）。

        逐项对照 preset 产出：键集、tracker / modifier 的类与构造实参、lifecycle 的
        类与两维字段全部相同；唯一差异是 `_on_all_owned`。
        """
        pdef_kw = dict(threshold=37, counter_init=4, reset='featured')
        built_s, bh_s = self._wired(_SKIP_TYPE, 'skip', **pdef_kw)
        built_a, bh_a = self._wired(_ANY_TYPE, 'any', **pdef_kw)

        assert set(built_s) == set(built_a)
        assert type(bh_s._lifecycle).__name__ == type(bh_a._lifecycle).__name__
        assert bh_s._lifecycle.state_keys() == bh_a._lifecycle.state_keys()
        assert type(bh_s._trackers[0]).__name__ == type(bh_a._trackers[0]).__name__
        assert (bh_s._trackers[0]._scope, bh_s._trackers[0]._reset_on) == \
               (bh_a._trackers[0]._scope, bh_a._trackers[0]._reset_on)
        assert type(bh_s._modifiers[0]).__name__ == type(bh_a._modifiers[0]).__name__
        assert bh_s._modifiers[0]._threshold == 37
        assert bh_a._modifiers[0]._threshold == 37
        # 唯一差异
        assert (bh_s._modifiers[0]._on_all_owned,
                bh_a._modifiers[0]._on_all_owned) == ('skip', 'any')

    def test_threshold_param_is_consumed(self):
        """`threshold` 经 `PityDef.threshold` 直取（`tau` 的唯一来源）。"""
        _, bh = self._wired(_SKIP_TYPE, 'skip', threshold=50)
        assert bh._modifiers[0]._threshold == 50
        _, bh2 = self._wired(_ANY_TYPE, 'any', threshold=120)
        assert bh2._modifiers[0]._threshold == 120

    def test_reset_on_follows_pitydef_reset(self):
        """`CounterTracker.reset_on` 取 `pdef.reset or _norm_scope(pdef)`。

        **不得写死 `"scope"`**：写死会让 `reset` 配置被静默忽略（§3.2 取值来源表）。
        判别性：`reset='never'`（G16）与缺省 `''`（回退 scope）在写死形态下同值。
        """
        _, bh_never = self._wired(_SKIP_TYPE, 'skip', reset='never')
        assert bh_never._trackers[0]._reset_on == 'never'
        _, bh_default = self._wired(_ANY_TYPE, 'any')
        assert bh_default._trackers[0]._reset_on == 'ssr'
        _, bh_featured = self._wired(_ANY_TYPE, 'any', reset='featured')
        assert bh_featured._trackers[0]._reset_on == 'featured'

    def test_counters_init_is_consumed(self):
        """`counters` 键的消费：`counter_init` 非零时写进 per-call state。

        缺该键则「已垫抽数」静默归零（§3.10.4 配套第 1 条明列该键为原稿遗漏项）。
        """
        _, bh = self._wired(_SKIP_TYPE, 'skip', counter_init=7)
        assert bh._state.get(bh._name, 'counter', 0) == 7

    def test_display_names_carry_form_and_are_distinct(self):
        """两条 `display_name` **带形态括注且不得同名**（§3.10.4 的命名口径，强制）。

        「形态写进 type key 与 display_name」（GUI 下拉与「关于」页面同源呈现）：
        只差一个字的短名会让用户读不出形态。
        """
        name_s = BEHAVIOR_REGISTRY[_SKIP_TYPE]['display_name']
        name_a = BEHAVIOR_REGISTRY[_ANY_TYPE]['display_name']
        assert name_s != name_a
        for nm in (name_s, name_a):
            assert '全拥有' in nm, f'display_name 须带形态括注，实得 {nm!r}'
            assert '排除已获得' in nm, f'display_name 须点明机制，实得 {nm!r}'

    def test_scope_normalized_from_pitydef(self):
        """scope 经 `_norm_scope` 归一（ISSUE-503）：骨架与零件同源，不得分叉。"""
        _, bh = self._wired(_SKIP_TYPE, 'skip', scope='SSR')
        assert bh._scope == 'ssr'
        assert bh._trackers[0]._scope == 'ssr'
        assert bh._modifiers[0]._scope == 'ssr'

    def test_two_forms_same_scope_conflict(self):
        """两条 type 同 scope 共存被规则 2 拒（它们是一对**互斥**的并列假设）。

        判据来自 `_HARD_TYPES`（`is_hard`）：缺该集合的注册时本用例必红，即
        「形态 a 与形态 b 同时生效」这一无意义配置不再静默通过。
        """
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine([
                PityDef(name='g3_s', btype=_SKIP_TYPE, scope='ssr'),
                PityDef(name='g3_a', btype=_ANY_TYPE, scope='ssr'),
            ])

    def test_g3_types_construct_in_engine(self):
        """两条 type 经 `PityEngine` 各自可构造（不抛，behavior 数正确）。"""
        engine = _engine([PityDef(name='g3_s', btype=_SKIP_TYPE, scope='ssr')])
        assert len(engine.behaviors) == 1
        engine2 = _engine([PityDef(name='g3_a', btype=_ANY_TYPE, scope='ssr')])
        assert len(engine2.behaviors) == 1

    def test_btype_order_tier_is_one(self):
        """`_BTYPE_ORDER` 两条同取 1（counter 驱动，与 `hard` 同级，§3.10.4 注册面补全④）。

        缺键时 `_resolve_order` 的 `.get(btype, 99)` 落到 99（排全部已知类型之后）；
        P82 接线后排序键是概率管道顺序的唯一来源，故缺键会静默改序。
        """
        from gacha_simulator.core.pity import _BTYPE_ORDER

        assert _BTYPE_ORDER[_SKIP_TYPE] == 1
        assert _BTYPE_ORDER[_ANY_TYPE] == 1
        assert _BTYPE_ORDER[_SKIP_TYPE] == _BTYPE_ORDER['hard']


# ══════════════════════════════════════════════════════════════════
# 缺陷 13（2026-10-15 修复）：规则 2/3/4 下沉为「按池分组后的组内判据」
# ══════════════════════════════════════════════════════════════════
# 缺陷本体（`docs/01-活跃/subsystems/保底系统/04-问题.md` 缺陷 13）：`_validate_behaviors`
# 在 `PityEngine.__init__` 里对**全部** behaviors 执行，而**概率管道是池级**的
# （`_pool_order` 按 `PoolPitySpec.pity_names` 过滤，池间保底从不共同执行）。故互斥
# 判据的适用域应是「同一池内」：两条同 scope 保底若 `pools` **完全不相交**，它们永不
# 同时执行，不该被判互斥。真实游戏「角色池一个硬保底、武器池一个硬保底」是常态，
# 手册 §1.4 的原神旗舰示例正是这个形状（修复前无法加载）。
#
# 修复口径：规则 2/3/4 改为**按池分组后的组内判据**（组 = 该池 `pity_names` 里的保底，
# 与运行时绑定同源）；**部分重叠仍互斥**（存在共同匹配的池即同组，`('*',)` 与任何具体
# 池都相交）；**规则 1（重名）保持全局**（`name` 是 `engine.behaviors` 与 `PityState`
# 命名空间的键）。无池信息（`pool_specs` 缺省或空）时回退为单一全局组，即既有语义。


class TestPoolScopedMutexRules:
    """规则 2/3/4 的适用域下沉到池级（缺陷 13）。"""

    def test_disjoint_pools_are_accepted(self):
        """① 两条同 scope `hard` 各绑一池（池集完全不相交）→ **放行**。

        这是缺陷 13 的最小复现形态：修复前抛
        `ConfigError: 同 scope 'ssr' 存在两个硬保底`。
        """
        defs = [
            PityDef(name='hard_a', btype='hard', scope='ssr', threshold=90,
                    pools=('pool_a',)),
            PityDef(name='hard_b', btype='hard', scope='ssr', threshold=90,
                    pools=('pool_b',)),
        ]
        engine = _engine_with_pools(defs, ['pool_a', 'pool_b'])
        assert set(engine.behaviors) == {'hard_a', 'hard_b'}
        assert engine.get_behaviors_for_pool('pool_a')[0][0] == 'hard_a'
        assert engine.get_behaviors_for_pool('pool_b')[0][0] == 'hard_b'

    def test_overlapping_pools_are_still_rejected(self):
        """② 两条同 scope `hard` 绑**同一池** → 仍拒（组内判据不变）。"""
        defs = [
            PityDef(name='hard_a', btype='hard', scope='ssr', threshold=90,
                    pools=('pool_a',)),
            PityDef(name='hard_b', btype='hard', scope='ssr', threshold=80,
                    pools=('pool_a',)),
        ]
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine_with_pools(defs, ['pool_a'])

    def test_partially_overlapping_pools_are_still_rejected(self):
        """② 部分重叠（`hard_b` 同时绑两池）→ 仍拒：它们在 `pool_a` 内共同执行。"""
        defs = [
            PityDef(name='hard_a', btype='hard', scope='ssr', threshold=90,
                    pools=('pool_a',)),
            PityDef(name='hard_b', btype='hard', scope='ssr', threshold=80,
                    pools=('pool_a', 'pool_b')),
        ]
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine_with_pools(defs, ['pool_a', 'pool_b'])

    def test_wildcard_pattern_intersects_any_concrete_pool(self):
        """③ `('*',)` 与具体池**必相交**（`*` 匹配任何全限定键）→ 仍拒。

        推论：`('*',)` 与任何保底都同组，故「默认绑全部池的保底」与「显式绑某池的
        保底」仍互斥。这是正确行为（它们确实会在该池内同时执行）。
        """
        defs = [
            PityDef(name='hard_all', btype='hard', scope='ssr', threshold=90),
            PityDef(name='hard_b', btype='hard', scope='ssr', threshold=80,
                    pools=('pool_b',)),
        ]
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine_with_pools(defs, ['pool_a', 'pool_b'])

    def test_duplicate_name_stays_global_across_disjoint_pools(self):
        """④ 规则 1（重名）**保持全局**：池集不相交也拒（`name` 是引擎与状态命名
        空间的键，与池无关）。"""
        defs = [
            PityDef(name='dup', btype='hard', scope='ssr', threshold=90,
                    pools=('pool_a',)),
            PityDef(name='dup', btype='rotating', scope='ssr',
                    pools=('pool_b',)),
        ]
        with pytest.raises(ValueError, match='重复的保底 name'):
            _engine_with_pools(defs, ['pool_a', 'pool_b'])

    def test_event_driven_and_soft_rules_are_pool_scoped(self):
        """规则 3 / 规则 4 同批下沉：不相交池的两条事件驱动型 / 两条同 btype 软
        保底均放行。"""
        defs = [
            PityDef(name='rot_a', btype='rotating', scope='ssr', pools=('pool_a',)),
            PityDef(name='rot_b', btype='rotating', scope='ssr', pools=('pool_b',)),
            PityDef(name='soft_a', btype='soft_additive', scope='ssr',
                    soft_start=74, soft_increment=6.0, pools=('pool_a',)),
            PityDef(name='soft_b', btype='soft_additive', scope='ssr',
                    soft_start=63, soft_increment=6.0, pools=('pool_b',)),
        ]
        engine = _engine_with_pools(defs, ['pool_a', 'pool_b'])
        assert set(engine.behaviors) == {'rot_a', 'rot_b', 'soft_a', 'soft_b'}

    def test_genshin_flagship_shape_from_manual_loads(self):
        """⑤ 手册 §1.4 的原神旗舰示例形状（角色池 / 武器池各一 hard + 各一 soft，
        池集不相交）→ **可加载**。

        手册片段用裸池名（`pools = ["char_limited"]`，P61 之前的写法），现行口径是
        全限定键 `{banner_id}.{pool_id}` + fnmatch，故本用例按**等价构造**书写：
        `char_*` 组绑 `char_1.main` / `standard.main` / `beginner.main`，`weapon_*`
        组绑 `weapon_1.main`，两组池集不相交。同 scope 的 `char_rotating` 与
        `epitomized_weapon`（规则 3）、两条 `soft_additive`（规则 4）一并覆盖。
        """
        char_pools = ('char_1.main', 'standard.main', 'beginner.main')
        weapon_pools = ('weapon_1.main',)
        defs = [
            PityDef(name='char_soft', btype='soft_additive', scope='ssr',
                    soft_start=74, soft_increment=6.0, pools=char_pools),
            PityDef(name='char_rotating', btype='rotating', scope='ssr',
                    pools=('char_1.main',)),
            PityDef(name='char_hard', btype='hard', scope='ssr',
                    target_featured=True, threshold=90, pools=char_pools),
            PityDef(name='weapon_soft', btype='soft_additive', scope='ssr',
                    soft_start=63, soft_increment=6.0, pools=weapon_pools),
            PityDef(name='epitomized_weapon', btype='targeted', scope='ssr',
                    fate_threshold=1, switch_allowed=True,
                    switch_resets_progress=True, pools=weapon_pools),
            PityDef(name='weapon_hard', btype='hard', scope='ssr',
                    target_featured=True, threshold=80, pools=weapon_pools),
        ]
        engine = _engine_with_pools(
            defs, ['char_1.main', 'standard.main', 'beginner.main', 'weapon_1.main'])
        assert set(engine.behaviors) == {
            'char_soft', 'char_rotating', 'char_hard',
            'weapon_soft', 'epitomized_weapon', 'weapon_hard'}
        char_names = {n for n, _bh in engine.get_behaviors_for_pool('char_1.main')}
        weapon_names = {n for n, _bh in engine.get_behaviors_for_pool('weapon_1.main')}
        assert char_names == {'char_soft', 'char_rotating', 'char_hard'}
        assert weapon_names == {'weapon_soft', 'epitomized_weapon', 'weapon_hard'}

    def test_no_pool_info_falls_back_to_global_scope(self):
        """无池信息（`pool_specs` 缺省 / 空）时回退单一全局组，即既有语义不放松。"""
        with pytest.raises(ConfigError, match='两个硬保底'):
            _engine([
                PityDef(name='hard_a', btype='hard', scope='ssr', threshold=90),
                PityDef(name='hard_b', btype='hard', scope='ssr', threshold=80),
            ])
        with pytest.raises(ConfigError, match='两个硬保底'):
            PityEngine(pool_specs={}, pity_defs=[
                PityDef(name='hard_a', btype='hard', scope='ssr', threshold=90),
                PityDef(name='hard_b', btype='hard', scope='ssr', threshold=80),
            ], state=PityState(), rarity_rank=_RARITY)
