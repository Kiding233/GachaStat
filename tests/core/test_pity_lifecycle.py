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
    FiniteActive, create_behavior,
    LifecycleConfig, Pity, PityContext, PityEngine, PityState, StateView, Tracker,
)
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pity_modifier import HardModifier, Modifier
from gacha_simulator.core.pity_tracker import (
    CounterTracker, FlagTracker, NamespaceTracker,
)


class TestDeactivateOnEarlyHit:
    """deactivate_on_early_hit——提前命中永久关闭。"""

    def test_hard_pity_early_hit_deactivates(self):
        """hard 保底 + deactivate_on_early_hit：提前命中 featured 后 `_active` 被清除。

        **P64 S7d 改造**：原以旧 hard 行为类直构并传 `LifecycleConfig`；改造后经
        `create_behavior(PityDef(...))` 取统一骨架 `Pity`，生命周期由
        `build_lifecycle(pdef)` 从 `deactivate_on_early_hit` 字段转换（唯一转换点），
        退役判定走 `Pity._lifecycle.should_deactivate` 的四实参形态。
        """
        state = PityState()
        pity = create_behavior(
            PityDef(name='early_hard', btype='hard', scope='ssr', threshold=120,
                    target_featured=True, deactivate_on_early_hit=True), state)
        # 骨架不在构造期绑定零件，直驱前须自行补一次重绑
        pity._rebind_state(state)

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

        pity.after_draw(ctx)
        # deactivate_on_early_hit → _active 被清除
        assert state.get('early_hard', '_active', True) is False
        # 退役先于 commit，且该退役形态跳过重置（counter 保持）
        assert state.get('early_hard', 'counter', 0) == 50


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
    """Modifier 探针——记录调用与收到的 view 命名空间。

    **S8-1 起探针挂在 `compute_delta` 上**（骨架改调该方法；`apply` 收敛为基类默认
    实现、在生产路径上无消费者），`readonly` 不再是本方法的形参，改经
    `ctx.readonly`（查询标记字段，§3.9.6 的「处置（两期）②」）读取——故本探针顺带
    把「只读标记透传至 Modifier 相位」钉在同一处。
    """

    def __init__(self, log, namespace=None):
        self.log = log
        if namespace is not None:
            self.namespace = namespace

    def compute_delta(self, view, dist, ctx):
        self.log.append(('modifier', ctx.readonly, view._name))
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


# ══════════════════════════════════════════════════════════════════
# P64 S3-2：生命周期顺序与视图接线（§3.1.4 行内注释 / §3.10.3 配套 2、3）
# ══════════════════════════════════════════════════════════════════
#
# 本段的每一条都对应 S3-2 块条目里的一项，且**都不被 S3-1 的既有断言覆盖**：
#   1. 构造期写入**次序**——`Lifecycle.initialize` 先于 `flags` / `counters` 消费
#      （§3.1.4 行内注释：「写入点必须在 `_lifecycle.initialize` 之后」）；
#   2. `initialize` 与 **view 创建**的相对次序：两条 view 的构造本身不写 state，
#      故第 1 条的写入序列观测不到它，须以 `StateView` 构造探针钉住；
#   3. `_namespaces` 的**收集面是三族**（`trackers` / `modifiers` / `lifecycle`）、
#      去重排序，且 `_ns_views` 的键集与之逐项相同：S3-1 的
#      `test_namespaces_collected_and_active_written_to_each` 只喂了 Tracker；
#   4. `_namespaces` / `_ns_views` **去 `None`**：单列一条用例，因为该缺陷若混入
#      真命名空间会先在 `sorted` 处 `TypeError`，断言反被掩盖；
#   5. `FiniteActive`（非 `depends_on` 维）的构造期写入——S3-1 只断言了 `AlwaysActive`
#      与 `DependentActive`，而 §六 ISSUE-202 的口径是「**非 `depends_on`** 保底」；
#   6. `_view_for` 的**调用点**——S3-1 的 `test_view_for_dispatches_by_namespace` 直调
#      helper，**不经过 `before_draw`**，故把调用行写死成 `self._view` 时它不红；
#   7. N 场隔离下 view 的落点：S3-1 只覆盖 2 场且只查 `_view` / `_ns_views` 的
#      `_state` 身份，不查「Modifier 经调用点拿到的 view 是否绑当场 state」。


class _RecordingState(PityState):
    """记录 `set` 调用序列的 `PityState`——用于断言构造期的写入**次序**。"""

    def __init__(self):
        super().__init__()
        self.writes = []

    def set(self, name, key, value):
        self.writes.append((name, key, value))
        super().set(name, key, value)


class _NsProbeModifier(Modifier):
    """命名空间 Modifier 探针——记录每次 `compute_delta` 收到的 view 的命名空间与所绑 state。

    **S8-1 起探针挂在 `compute_delta` 上**（同 `_ProbeModifier` 的理由：骨架改调该
    方法，挂 `apply` 的探针永不触发、断言退化为恒真）。
    """

    def __init__(self, log, namespace):
        self.log = log
        self.namespace = namespace

    def compute_delta(self, view, dist, ctx):
        self.log.append((view._name, view._state))
        return None


class TestPityLifecycleOrderAndViewWiring:
    """S3-2——构造期写入次序、命名空间收集面、`_view_for` 的调用点、N 场 view 落点。"""

    def test_initialize_precedes_flags_and_counters_consumption(self):
        """`Lifecycle.initialize` 先于 `flags` / `counters` 消费（§3.1.4 行内注释）。

        `_active` 归 Lifecycle 负责、不属 `flags` 键集，故两条写入路径的相对次序
        是「先 `_active` 后 `flags` / `counters`」；把两段 `for` 循环挪到
        `initialize` 之前即本断言必红。
        """
        st = _RecordingState()
        _make_pity(st, flags={'guaranteed': True}, counters={'counter': 5})
        keys = [(name, key) for name, key, _ in st.writes]
        assert (PITY_NAME, '_active') in keys, \
            'initialize 的 _active 写入须落在 state 上（ISSUE-202）'
        assert keys.index((PITY_NAME, '_active')) < \
            keys.index((PITY_NAME, 'guaranteed')), \
            'flags 消费必须在 initialize 之后（§3.1.4：写入点须在 initialize 之后）'
        assert keys.index((PITY_NAME, '_active')) < \
            keys.index((PITY_NAME, 'counter')), \
            'counters 消费必须在 initialize 之后'

    def test_initialize_precedes_view_creation(self, monkeypatch):
        """`Lifecycle.initialize` 须先于 `_view` / `_ns_views` 创建（§3.1.4 行内注释）。

        块条目原文：「`Pity.__init__` 在创建 `_view` **之前**调用
        `Lifecycle.initialize(state, name, namespaces)` 写初始 `_active`」。
        两条 view 的构造本身不写 state，故该次序**无法**由 state 写入序列观测
        （上一条用例只钉住「先于 `flags` / `counters` 消费」），须以 `StateView`
        构造探针记录它与 `initialize` 的相对位置。把 `_view` / `_ns_views` 两行
        挪到 `initialize` 之前即本断言必红。
        """
        import gacha_simulator.core.pity as pity_module

        events = []

        class _OrderLifecycle(AlwaysActive):
            def initialize(self, state, name, namespaces=()):
                events.append(('initialize', name))
                super().initialize(state, name, namespaces)

        real_view = pity_module.StateView

        def _spy_view(state, name):
            events.append(('view', name))
            return real_view(state, name)

        monkeypatch.setattr(pity_module, 'StateView', _spy_view)
        _make_pity(PityState(), btype='rotating_soft',
                   trackers=[NamespaceTracker(namespace=NS_SOFT)],
                   lifecycle=_OrderLifecycle(LifecycleConfig()))
        assert events[0] == ('initialize', PITY_NAME), \
            'initialize 须先于 _view / _ns_views 创建（§3.1.4 的 ISSUE-202 行）'
        assert events[1:] == [('view', PITY_NAME), ('view', NS_SOFT)], \
            '默认 view 与零件 view 须在 initialize 之后创建，且默认 view 在先'

    def test_namespaces_collected_from_all_three_families(self):
        """`_namespaces` 的收集面是 **三族**（`trackers` / `modifiers` / `lifecycle`）。

        块条目原文：「`namespaces` 由 `Pity` 从 `trackers` / `modifiers` /
        `lifecycle` 的 `namespace` 属性收集（去 `None`）」。漏掉任一族的后果是
        该族的命名空间收不到 `_active`，而骨架**不报错**（读取侧静默返回 default）。
        重复项去重、结果排序亦在此一并钉住（「去 `None`」见下一条用例）。

        `_ns_views` 的键集断言另封住「收集了命名空间却没建对应 view」：该形态下
        `_view_for` 静默回落默认 view（`X_soft` 的读取全落 `X`），且**不报错**。
        """
        ns_tr, ns_md, ns_lc = 'x_tr', 'x_md', 'x_lc'

        class _NsLifecycle(AlwaysActive):
            pass

        _NsLifecycle.namespace = ns_lc

        st = PityState()
        pity = _make_pity(
            st, btype='rotating_soft',
            trackers=[NamespaceTracker(namespace=ns_tr),
                      NamespaceTracker(namespace=ns_tr)],   # 重复项须去重
            modifiers=[_NsProbeModifier([], ns_md)],
            lifecycle=_NsLifecycle(LifecycleConfig()))
        assert pity._namespaces == tuple(sorted({ns_tr, ns_md, ns_lc})), \
            '三族命名空间须全部收集（含 modifiers / lifecycle 两族）'
        assert set(pity._ns_views) == set(pity._namespaces), \
            '零件 view 的键集须与收集到的命名空间一致（缺一即静默回落默认 view）'
        for ns in (ns_tr, ns_md, ns_lc):
            assert st.get(ns, '_active') is True, \
                f'命名空间 {ns} 的 _active 须由 initialize 写入'
        assert st.get(PITY_NAME, '_active') is True

    def test_namespaces_excludes_none(self):
        """`_namespaces` / `_ns_views` **去 `None`**（块条目原文：「（去 `None`）」）。

        收集面按 `getattr(part, 'namespace', None)` 取值，而 `Tracker` / `Modifier` /
        `Lifecycle` 三族基类都把 `namespace` 声明为默认 `None`，故「不声明命名空间的
        零件」在此一律返回 `None`（**不是** `AttributeError`）。漏去 `None` 时：
        `None` 成为 `_namespaces` 成员与 `_ns_views` 键，`initialize` 随即
        `state.set(None, '_active', True)`，状态快照里多出一个非法命名空间；
        而 `_view_for` 对这类零件仍经 `or self._view` 回落默认 view，**全程不报错**。

        判别力为何单列一条用例：本用例只喂无 `namespace` 的零件，故漏去 `None` 时
        `sorted({None})` 是单元素排序、不触发 `None < str` 的 `TypeError`，缺陷得以
        走到断言；若混入真命名空间（上一条用例的形态），同一缺陷会先在 `sorted`
        处抛 `TypeError`，断言反被掩盖。
        """
        st = PityState()
        pity = _make_pity(st, trackers=[_ProbeTracker([])],
                          modifiers=[_ProbeModifier([])])
        assert pity._namespaces == (), '无 namespace 的零件不得产出 None 项'
        assert pity._ns_views == {}, '无 namespace 的零件不得产出 None 键'
        assert None not in st.to_dict()['data'], \
            'None 不得成为命名空间（initialize 会写 _active 进该非法空间）'
        assert st.get(PITY_NAME, '_active') is True, '默认命名空间仍须写入'

    def test_finite_active_writes_active_to_name_and_namespaces(self):
        """`FiniteActive`（非 `depends_on` 维）构造期写 `_active = True`。

        §六 ISSUE-202 的口径是「**非 `depends_on` 保底**在构造后
        `state.get(name, "_active")` 为 `True`」——`FiniteActive` 的激活维是
        `Always`，故与 `AlwaysActive` 同属写入面；S3-1 只断言了 `AlwaysActive`。
        命名空间侧须一并写入（`X_soft: {_active: True}` 的唯一产出路径）。
        """
        st = PityState()
        pity = _make_pity(
            st, btype='rotating_soft',
            trackers=[NamespaceTracker(namespace=NS_SOFT)],
            lifecycle=FiniteActive(LifecycleConfig(), max_triggers=2))
        assert st.get(PITY_NAME, '_active') is True
        assert st.get(NS_SOFT, '_active') is True, \
            'FiniteActive 亦须对零件命名空间写 _active'
        assert pity._lifecycle.is_active(st, PITY_NAME) is True

    def test_before_draw_dispatches_namespace_view_to_modifier(self):
        """`before_draw` 的 Modifier 链**经 `_view_for(mod)` 取 view**（§3.10.3 配套 3）。

        块条目原文：「遍历 `trackers` / `modifiers` 时经 `self._ns_views.get(...)
        or self._view` 取值，**不得写死 `self._view`**」。本断言走**调用点**而非
        helper——命名空间 Modifier 必须收到 `StateView(state, mod.namespace)`，
        否则 `X_soft` 的读取全落默认命名空间且**不报错**。
        """
        st = PityState()
        log = []
        pity = _make_pity(st, btype='rotating_soft', rebind=True,
                          trackers=[NamespaceTracker(namespace=NS_SOFT)],
                          modifiers=[_NsProbeModifier(log, NS_SOFT)])
        st.set(NS_SOFT, 'probe_key', 41)
        pity.before_draw(_pity_ctx(state=st))
        assert len(log) == 1
        view_name, view_state = log[0]
        assert view_name == NS_SOFT, \
            '调用点写死 self._view 会让此处变成默认命名空间（本断言即红）'
        assert view_state is st
        assert pity._view_for(pity._modifiers[0]).get('probe_key') == 41
        assert pity._view.get('probe_key') is None, \
            '默认 view 不得看见 X_soft 命名空间的键'

    def test_n_fields_isolation_views_track_current_state(self):
        """P75 跨模拟隔离（worker 内连跑 N 场）——view 与 Modifier 收到的 view 逐场跟随。

        每场 state 由上一场构造完成后的快照 `from_dict` 重建（与真实流程
        `env.pity_state_init` → 每场 `PityState.from_dict` 同形），逐场 `_rebind_state`。
        `_rebind_state` 漏建 `_ns_views`、或调用点写死 `self._view`，本断言必红。
        """
        st = PityState()
        log = []
        pity = _make_pity(st, btype='rotating_soft', rebind=True,
                          trackers=[NamespaceTracker(namespace=NS_SOFT),
                                    CounterTracker(scope=PITY_SCOPE, init=0)],
                          modifiers=[_NsProbeModifier(log, NS_SOFT)])
        snapshot = st.to_dict()
        fields = [PityState.from_dict(snapshot) for _ in range(5)]
        for i, fld in enumerate(fields):
            pity._rebind_state(fld)
            pity.before_draw(_pity_ctx(state=fld))
            assert pity._state is fld
            assert pity._view._state is fld
            assert pity._ns_views[NS_SOFT]._state is fld, \
                f'第 {i} 场：零件 view 须同批重建（否则读第 1 场账本）'
            assert log[-1][1] is fld, \
                f'第 {i} 场：Modifier 经调用点拿到的 view 须绑当场 state'
            assert log[-1][0] == NS_SOFT
            assert fld.get(PITY_NAME, 'counter') == 1, '每场计数各自独立'
        assert st.get(PITY_NAME, 'counter') is None, \
            '构造期 state 不得被后续场次写入（跨场隔离）'
