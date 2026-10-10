"""保底生命周期测试——P56 集成层 + P64 S3-1 统一骨架层。

覆盖目标：
  1. （P56）depends_on 激活传播——依赖方初始 inactive，被依赖方 did_fire() 后激活
  2. （P56）deactivate_on_early_hit=true 在提前命中后永久关闭
  3. （P64 S3-1）统一 `Pity` 骨架：构造期写入、相位顺序、rebind 委托、`_pools`
     注入与 S1d 结转的 `should_deactivate` 端到端断言（见文件下半段的 S3-1 段）

"""

import warnings

from gacha_simulator.core.pity import (
    AlwaysActive, DependentActive, DependentFiniteActive, DrawInfo,
    FiniteActive, HardPityBehavior,
    LifecycleConfig, Pity, PityContext, PityEngine, PityState, StateView, Tracker,
)
from gacha_simulator.core.pity_modifier import HardModifier, Modifier
from gacha_simulator.core.pity_tracker import (
    CounterTracker, FlagTracker, NamespaceTracker,
)


class TestDeactivateOnEarlyHit:
    """deactivate_on_early_hit——提前命中永久关闭。"""

    def test_hard_pity_early_hit_deactivates(self):
        """HardPityBehavior + deactivate_on_early_hit：提前命中 featured 后 _active 被清除。"""
        state = PityState()
        lifecycle = LifecycleConfig(
            deactivate_on_early_hit=True,
        )
        bh = HardPityBehavior('early_hard', state, 'ssr', threshold=120,
                               lifecycle=lifecycle,
                               target_featured=True)

        # 激活状态
        state.set('early_hard', '_active', True)

        # 模拟提前命中 featured（counter < threshold）
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured',)}, featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured'},
            base_probabilities={'ssr_featured': 0.01}, rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        # counter 低于 threshold
        state.set('early_hard', 'counter', 50)

        bh.after_draw(ctx)
        # deactivate_on_early_hit → _active 被清除
        assert state.get('early_hard', '_active', True) is False


# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# P64 S3-1：统一 `Pity` 骨架（§3.1.4）+ `StateView` 薄版（§3.10.3）
# ══════════════════════════════════════════════════════════════════
#
# 本段覆盖三块被测面：
#   1. **构造期**（ISSUE-001 / ISSUE-202 / ISSUE-407 / AUDIT-BREAK-3）——三元组
#      构造、btype 推导标志、`_active` 构造期写入、命名空间收集与两级 view、
#      `flags` / `counters` 的 truthy 消费、`_declared_keys` 汇总；
#   2. **相位顺序**（§3.1.1 N1 表）——`before_draw` = `is_active` 早退 → `advance`
#      → **`prepare`**（透传 `readonly`）→ Modifier 链；`after_draw` = 早退 →
#      `did_fire` → 退役判定（**四实参**）→ 退役 → `commit(skip_reset)`；
#   3. **rebind 委托**（P75 / ISSUE-004 / ISSUE-917）与 **`_pools` 注入**（ISSUE-019）。
#
# `rebind=True` 的说明：`Pity.__init__` **不**绑定零件的 Counter/Flag（§3.1.4 骨架
# 无该步骤，与 S1b/S1c 的「零件须先 rebind」契约一致）。真实流程由
# `PityEngine._rebind_state(per-call state)` 承担——每场模拟的状态由
# `PityState.from_dict(env.pity_state_init)` 重建为**新对象**，与引擎构造期的
# `_state` 不同，故引擎侧的重绑早退分支不生效。测试直构骨架时显式补这一步。

PITY_NAME = 'ssr_rotating'
PITY_SCOPE = 'ssr'
NS_SOFT = f'{PITY_NAME}_soft'


def _pity_ctx(rarity: str = 'ssr', is_featured: bool = False,
              state: PityState = None, current: dict = None):
    """构造一次抽卡的 `PityContext`（默认出 scope 内的非 featured 卡）。"""
    st = state if state is not None else PityState()
    draw = DrawInfo(
        pool_id='p', pool_instance_id='p_0',
        reward_id=f'{rarity}_card', reward_rarity=rarity, is_featured=is_featured,
    )
    return PityContext(draw=draw, current=dict(current or {}), state=st)


def _make_pity(state=None, *, name=PITY_NAME, btype='rotating', trackers=None,
               modifiers=None, lifecycle=None, rebind=False, **kwargs):
    """按骨架的关键字形参构造 `Pity`（`rebind=True` 时补一次 `_rebind_state`）。"""
    st = state if state is not None else PityState()
    args = dict(name=name, state=st, scope=PITY_SCOPE, btype=btype,
                trackers=list(trackers or []), modifiers=list(modifiers or []))
    if lifecycle is not None:
        args['lifecycle'] = lifecycle
    args.update(kwargs)
    pity = Pity(**args)
    if rebind:
        pity._rebind_state(st)
    return pity


class _ProbeTracker(Tracker):
    """相位探针——记录 `advance` / `prepare` / `commit` 的调用与实参。"""

    def __init__(self, log):
        self.log = log
        self.fired = False

    def advance(self, ctx, state, name, readonly):
        self.log.append(('advance', readonly))

    def prepare(self, ctx, state, name, readonly):
        self.log.append(('prepare', readonly))

    def commit(self, ctx, state, name, skip_reset=False):
        self.log.append(('commit', skip_reset))

    def did_reset(self, ctx, state, name):
        return self.fired


class _ProbeModifier(Modifier):
    """Modifier 探针——记录调用与收到的 view 命名空间。"""

    def __init__(self, log, namespace=None):
        self.log = log
        if namespace is not None:
            self.namespace = namespace

    def apply(self, ctx, view, dist, readonly):
        self.log.append(('modifier', readonly, view._name))
        return None


# ── 构造期 ──

class TestPityConstruction:
    """`Pity.__init__` 的构造期行为（§3.1.4 骨架）。"""

    def test_constructs_without_attribute_error_and_writes_active(self):
        """骨架可独立构造（无 `AttributeError`），且构造期已写 `_active`（ISSUE-202）。"""
        st = PityState()
        _make_pity(st)
        assert st.get(PITY_NAME, '_active') is True, \
            '非 depends_on 保底构造后 _active 必须为 True（否则首行早退、全线静默失效）'

    def test_btype_flags_derived_not_hardcoded(self):
        """`is_soft` / `is_hard` / `is_event_driven` 由 `btype` 推导（ISSUE-001）。

        写死 `is_event_driven` 会让 `_validate_behaviors` 的规则 2/3/4 全部落到
        事件驱动型分支，故三者必须逐 btype 各异。
        """
        cases = (('soft_step', True, False, False),
                 ('hard', False, True, False),
                 ('rotating_cr', False, False, True))
        for btype, soft, hard, event in cases:
            pity = _make_pity(PityState(), name=f'p_{btype}', btype=btype)
            assert (pity.is_soft, pity.is_hard, pity.is_event_driven) == \
                (soft, hard, event), f'btype={btype} 的分类标志推导错误'

    def test_flags_and_counters_written_only_when_truthy(self):
        """`flags` / `counters` 仅 truthy 才预建键（AUDIT-BREAK-3，对齐 `if cv:`）。"""
        st = PityState()
        _make_pity(st, flags={'guaranteed': True, 'lost_rotating': False},
                   counters={'counter': 5, 'fate_points': 0})
        assert st.get(PITY_NAME, 'guaranteed') is True
        assert st.get(PITY_NAME, 'counter') == 5
        assert st.get(PITY_NAME, 'lost_rotating') is None, 'falsy 值不得预建键'
        assert st.get(PITY_NAME, 'fate_points') is None, '0 不得预建键'

    def test_dependent_active_does_not_write_active(self):
        """`DependentActive` 构造期不写 `_active`（激活由引擎的 depends_on 传播置位）。"""
        st = PityState()
        _make_pity(st, lifecycle=DependentActive(LifecycleConfig(depends_on='src')))
        assert st.get(PITY_NAME, '_active') is None

    def test_namespaces_collected_and_active_written_to_each(self):
        """零件命名空间被收集，且 `initialize` 对 `name` 与每个命名空间各写 `_active`。

        这是 `X_soft: {_active: True}` 的唯一产出路径（ISSUE-407 / §3.10.3 配套 2）。
        """
        st = PityState()
        pity = _make_pity(st, btype='rotating_soft',
                          trackers=[NamespaceTracker(namespace=NS_SOFT)])
        assert pity._namespaces == (NS_SOFT,)
        assert st.get(NS_SOFT, '_active') is True
        assert st.get(PITY_NAME, '_active') is True

    def test_pools_stored_with_wildcard_default(self):
        """`_pools` 由构造形参注入，默认 `('*',)`（ISSUE-019）。"""
        assert _make_pity(PityState())._pools == ('*',)
        assert _make_pity(PityState(), pools=('b1.pool_a',))._pools == ('b1.pool_a',)

    def test_declared_keys_aggregated_from_three_families(self):
        """`_declared_keys` 汇总三族 `state_keys()`（ISSUE-501，S10-2 / S11 的输入）。"""
        pity = _make_pity(
            PityState(), btype='hard',
            trackers=[CounterTracker(scope=PITY_SCOPE, init=0)],
            modifiers=[HardModifier(PITY_SCOPE, threshold=90)],
            lifecycle=FiniteActive(LifecycleConfig(), max_triggers=2))
        assert pity._declared_keys == {
            'trackers': ('counter',),
            'modifiers': ('counter',),
            'lifecycle': ('triggers',),
        }

    def test_view_for_dispatches_by_namespace(self):
        """`_view_for`：声明 `namespace` 的零件拿自己的 view，其余拿默认 view。"""
        ns_tracker = NamespaceTracker(namespace=NS_SOFT)
        plain_tracker = _ProbeTracker([])
        ns_modifier = _ProbeModifier([], namespace=NS_SOFT)
        pity = _make_pity(PityState(), btype='rotating_soft',
                          trackers=[ns_tracker, plain_tracker],
                          modifiers=[ns_modifier])
        assert pity._view_for(ns_tracker)._name == NS_SOFT
        assert pity._view_for(ns_modifier)._name == NS_SOFT
        assert pity._view_for(plain_tracker)._name == PITY_NAME

    def test_stateview_does_not_cache_namespace_dict(self):
        """`StateView` 每次现取命名空间 dict（ISSUE-004）——命名空间后创建仍可读到。"""
        st = PityState()
        view = StateView(st, 'later')
        assert view.get('counter', 0) == 0
        st.set('later', 'counter', 7)
        assert view.get('counter', 0) == 7, \
            '构造期缓存 data.get(name, {}) 会拿到与 state 脱联的空 dict'


# ── `before_draw` 相位顺序 ──

class TestPityBeforeDrawPhase:
    """`before_draw` 的相位顺序与 `readonly` 透传（§3.1.1 N1 相位表）。"""

    def test_phase_order_is_advance_then_prepare_then_modifier(self):
        """相位顺序恒为 `advance` → `prepare` → Modifier 链。

        `prepare` 若被删掉或挪到 Modifier 链之后，本断言必红（裁决 6B′ 的
        `StreakTracker` 掷骰相位依赖它）。
        """
        st = PityState()
        log = []
        pity = _make_pity(st, btype='rotating_cr', rebind=True,
                          trackers=[_ProbeTracker(log)],
                          modifiers=[_ProbeModifier(log)])
        pity.before_draw(_pity_ctx(state=st))
        assert [entry[0] for entry in log] == ['advance', 'prepare', 'modifier']

    def test_readonly_propagated_to_all_three_phases(self):
        """`readonly` 透传至 `advance` / `prepare` / Modifier（`prepare` 漏透传即每次
        概率查询都掷骰，全局随机流整体错位）。"""
        st = PityState()
        log = []
        pity = _make_pity(st, btype='rotating_cr', rebind=True,
                          trackers=[_ProbeTracker(log)],
                          modifiers=[_ProbeModifier(log)])
        pity.before_draw(_pity_ctx(state=st), readonly=True)
        assert log == [('advance', True), ('prepare', True),
                       ('modifier', True, PITY_NAME)]

    def test_readonly_does_not_advance_counter(self):
        """只读查询不推进计数（`advance` 的 `readonly` 分支），且返回原分布副本。"""
        st = PityState()
        pity = _make_pity(st, btype='hard', rebind=True,
                          trackers=[CounterTracker(scope=PITY_SCOPE, init=0)])
        ctx = _pity_ctx(state=st, current={'ssr': 1.0})
        out = pity.before_draw(ctx, readonly=True)
        assert st.get(PITY_NAME, 'counter', 0) == 0, '只读查询不得推进计数'
        assert out == {'ssr': 1.0}
        assert out is not ctx.current, '返回副本，不得就地改写共享 ctx'

    def test_inactive_returns_current_copy_without_calling_parts(self):
        """未激活时首行早退：返回 `ctx.current` 副本，且不调用任何零件。"""
        st = PityState()
        log = []
        pity = _make_pity(st, btype='hard', rebind=True,
                          trackers=[_ProbeTracker(log)],
                          modifiers=[_ProbeModifier(log)],
                          lifecycle=DependentActive(LifecycleConfig(depends_on='src')))
        ctx = _pity_ctx(state=st, current={'ssr': 1.0})
        out = pity.before_draw(ctx)
        assert out == {'ssr': 1.0}
        assert log == [], '未激活不得调度任何零件'


# ── `after_draw` 退役与 `commit` ──

class TestPityAfterDrawPhase:
    """`after_draw` 的退役判定顺序与 `skip_reset`（ISSUE-018 / ISSUE-402）。"""

    def test_retire_before_commit_and_skip_reset_on_early_hit(self):
        """`deactivate_on_early_hit` 退役：清 `_active`，且 `commit` 收到 `skip_reset=True`。"""
        st = PityState()
        log = []
        probe = _ProbeTracker(log)
        probe.fired = True
        pity = _make_pity(
            st, rebind=True, trackers=[probe],
            lifecycle=AlwaysActive(LifecycleConfig(deactivate_on_early_hit=True)))
        pity.after_draw(_pity_ctx(state=st))
        assert log == [('commit', True)], '退役先于 commit，且跳过重置'
        assert st.get(PITY_NAME, '_active') is False

    def test_retire_by_max_triggers_does_not_skip_reset(self):
        """触发次数用尽导致的退役不改变 `commit` 语义——`skip_reset=False`。"""
        st = PityState()
        log = []
        probe = _ProbeTracker(log)
        probe.fired = True
        pity = _make_pity(st, rebind=True, trackers=[probe],
                          lifecycle=FiniteActive(LifecycleConfig(), max_triggers=1))
        pity.after_draw(_pity_ctx(state=st))
        assert log == [('commit', False)], '次数用尽退役仍须照常重置'
        assert st.get(PITY_NAME, '_active') is False

    def test_inactive_early_return_skips_commit(self):
        """未激活时首行早退：不调 `commit`、不写 `triggers`。"""
        st = PityState()
        log = []
        pity = _make_pity(
            st, rebind=True, trackers=[_ProbeTracker(log)],
            lifecycle=DependentFiniteActive(
                LifecycleConfig(depends_on='src'), max_triggers=2))
        pity.after_draw(_pity_ctx(state=st))
        assert log == []
        assert st.get(PITY_NAME, 'triggers', 0) == 0

    def test_did_fire_is_any_of_trackers_did_reset(self):
        """`did_fire` = `any(tr.did_reset(...))`（M4 统一语义，两族共用一处实现）。"""
        st = PityState()
        quiet, loud = _ProbeTracker([]), _ProbeTracker([])
        loud.fired = True
        pity = _make_pity(st, trackers=[quiet, loud])
        assert pity.did_fire(_pity_ctx(state=st)) is True
        loud.fired = False
        assert pity.did_fire(_pity_ctx(state=st)) is False


# ── S1d 结转第 ② 层：经 `Pity.after_draw` 的端到端断言 ──

class TestPityShouldDeactivateEndToEnd:
    """§3.1.3 / §六 ISSUE-402 的**第 ② 层**——端到端覆盖 `should_deactivate` 的
    四实参调用形态。

    S1d 只交付第 ① 层（直构 Lifecycle 并显式传 `fired`，见
    `tests/core/test_pity_tracker.py::TestLifecycleRetirement`）；第 ② 层因 `Pity`
    骨架当时不存在而顺延至 S3-1，断言必须真的走到 `Pity.after_draw` 的那一行调用，
    否则该调用行无验收面（三实参调用在两层验收里都不可见）。
    """

    def test_after_draw_end_to_end_fired_four_args(self):
        """`FiniteActive(max_triggers=2)`：命中两次后退役；连续未命中 ≥ 2 抽仍在役。

        `fired` 由 `Pity.did_fire` 算出并以**第四实参**传入 `should_deactivate`。
        若写成三实参：① Lifecycle 按四参协议实现 → 每次抽卡 `TypeError`；② 迁就三参
        → `triggers` 退化为「激活后的抽数」，第 2 抽即退役，本断言的「未命中不累加」
        一半必红。
        """
        st = PityState()
        pity = _make_pity(
            st, btype='rotating', rebind=True,
            trackers=[FlagTracker(scope=PITY_SCOPE, judge='featured',
                                  hit='clear', miss='set', flag='guaranteed')],
            lifecycle=FiniteActive(LifecycleConfig(), max_triggers=2))

        # 连续 3 抽未命中（出 scope 但非 featured）：did_fire 恒 False，triggers 不累加
        for _ in range(3):
            pity.after_draw(_pity_ctx(state=st, is_featured=False))
        assert st.get(PITY_NAME, 'triggers', 0) == 0, '未命中不得累加 triggers'
        assert pity._lifecycle.is_active(st, PITY_NAME) is True, \
            '连续未命中不得退役（三实参下 triggers 退化为抽数，此处必红）'

        # 命中两次 → 退役
        pity.after_draw(_pity_ctx(state=st, is_featured=True))
        assert st.get(PITY_NAME, 'triggers', 0) == 1
        assert pity._lifecycle.is_active(st, PITY_NAME) is True
        pity.after_draw(_pity_ctx(state=st, is_featured=True))
        assert st.get(PITY_NAME, 'triggers', 0) == 2
        assert pity._lifecycle.is_active(st, PITY_NAME) is False, '触发 N 次后退役'


# ── rebind 委托（P75 / ISSUE-004 / ISSUE-917） ──

class TestPityRebind:
    """`Pity._rebind_state` 的三族委托与 view 重建。"""

    def test_rebind_rebuilds_default_and_namespace_views(self):
        """`_rebind_state` 同批重建默认 view 与 `_ns_views`（ISSUE-004 / ISSUE-407）。"""
        a = PityState()
        pity = _make_pity(a, btype='rotating_soft', rebind=True,
                          trackers=[NamespaceTracker(namespace=NS_SOFT)])
        old_view, old_ns_view = pity._view, pity._ns_views[NS_SOFT]

        b = PityState()
        pity._rebind_state(b)
        assert pity._state is b
        assert pity._view is not old_view and pity._view._state is b
        assert pity._ns_views[NS_SOFT] is not old_ns_view
        assert pity._ns_views[NS_SOFT]._state is b, \
            '零件 view 须同批重建，否则第 2..N 场读旧账本'

    def test_rebind_lifecycle_namespaces_symmetric(self):
        """Lifecycle 的 `rebind` 收 `namespaces`（ISSUE-917）——命名空间的 `_active`
        Flag 须同批重定向；漏传即 `KeyError` / Flag 仍指上一场 state。"""
        ns = NS_SOFT
        a = PityState()
        pity = _make_pity(a, btype='rotating_soft', rebind=True,
                          trackers=[NamespaceTracker(namespace=ns)])
        assert a.get(ns, '_active') is True

        b = PityState()
        pity._rebind_state(b)
        assert pity._lifecycle._ns_active[ns]._state is b, \
            'ISSUE-917：命名空间的 _active Flag 须同批重定向'
        pity._lifecycle.deactivate(b, PITY_NAME)
        assert b.get(PITY_NAME, '_active') is False
        assert a.get(PITY_NAME, '_active') is True, '旧 state 不得再被触碰'

    def test_rebind_redirects_tracker_writes_to_new_state(self):
        """重绑后 Tracker 的写入落新账本、旧账本不再被写（P75 纯重定向）。

        第二场的 state 由第一场构造完成后的快照 `from_dict` 重建——与真实流程
        （`env.pity_state_init` 快照 → 每场模拟 `PityState.from_dict`）同形。
        """
        a = PityState()
        pity = _make_pity(a, btype='soft_step', rebind=True,
                          trackers=[CounterTracker(scope=PITY_SCOPE, init=0)])
        snapshot = a.to_dict()          # 阶段 3 快照（含构造期写入的 _active=True）
        pity.before_draw(_pity_ctx(state=a))
        assert a.get(PITY_NAME, 'counter') == 1

        b = PityState.from_dict(snapshot)
        pity._rebind_state(b)
        pity.before_draw(_pity_ctx(state=b))
        pity.before_draw(_pity_ctx(state=b))
        assert b.get(PITY_NAME, 'counter') == 2, '重绑后写入须落新账本'
        assert a.get(PITY_NAME, 'counter') == 1, '旧账本不得再被写'


# ── `_pools` 注入与池交集校验（ISSUE-019） ──

class TestPityPoolsActivationGraph:
    """`_pools` 注入后 `_build_activation_graph` 的池交集警告恢复语义（§3.12.2）。

    S1a 至 S2a-2 期间全库无任何 behavior 设置 `_pools`，`src_pools` / `dst_pools`
    恒为空集，警告对**每一条** `depends_on` 无条件触发——属已登记的过渡态。
    """

    @staticmethod
    def _pair(state, src_pools, dst_pools):
        src = _make_pity(state, name='src', btype='rotating', pools=src_pools)
        dst = _make_pity(state, name='dst', btype='hard', pools=dst_pools,
                         lifecycle=DependentActive(
                             LifecycleConfig(depends_on='src')))
        return src, dst

    @staticmethod
    def _graph(src, dst):
        engine = PityEngine({}, [])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            graph = engine._build_activation_graph([src, dst])
        return graph, [str(w.message) for w in caught]

    def test_same_pool_depends_on_does_not_warn(self):
        """同池 `depends_on` 不再触发池交集警告（ISSUE-019 的正例）。"""
        src, dst = self._pair(PityState(), ('b1.pool_a',), ('b1.pool_a',))
        graph, messages = self._graph(src, dst)
        assert graph == {'src': ['dst']}
        assert not [m for m in messages if 'pools' in m], \
            f'同池不得告警，实际：{messages}'

    def test_wildcard_pool_suppresses_warning(self):
        """任一方为 `'*'`（默认值）即抑制警告——`'*'` 表示不限定池。"""
        src, dst = self._pair(PityState(), ('*',), ('b1.pool_b',))
        _, messages = self._graph(src, dst)
        assert not [m for m in messages if 'pools' in m], \
            f'通配池不得告警，实际：{messages}'

    def test_disjoint_pool_depends_on_still_warns(self):
        """负例：双方池无交集时警告仍须触发（`_pools` 注入不得把该校验一并废掉）。"""
        src, dst = self._pair(PityState(), ('b1.pool_a',), ('b1.pool_b',))
        _, messages = self._graph(src, dst)
        assert [m for m in messages if 'pools' in m], \
            '池无交集须保留告警（这是全库唯一的跨池一致性检查）'
