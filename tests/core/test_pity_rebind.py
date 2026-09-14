"""P75 回归：_rebind_state 纯重定向 + 保底快照非空 + 跨模拟隔离语义。

覆盖：
- 各 behavior 的 _rebind_state 纯重定向（计数写新 state、旧 state 不变）
- engine is_active 默认值 False（ISSUE-120）
- 带保底模拟后 banner_end_pity_states 含 counter（P75 核心目标，修复前恒空）
"""
import os

from gacha_simulator.core.pity import (
    PityState, PityEngine,
    SoftStepBehavior, HardPityBehavior, RotatingBehavior, TargetedBehavior,
)
from gacha_simulator.core.config_store import PityDef

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CFG = os.path.join(_ROOT, 'gacha_simulator', 'config', 'config.toml')


def _soft(a, name='t'):
    return SoftStepBehavior(name=name, state=a, scope='ssr', btype='soft_interval',
                            deltas=((73, 0.0), (17, 5.88)), reset='ssr')


def _hard(a, name='h'):
    return HardPityBehavior(name=name, state=a, scope='ssr', btype='hard', threshold=90)


def _rot(a, name='r'):
    return RotatingBehavior(name=name, state=a, scope='ssr')


def _tgt(a, name='tgt'):
    return TargetedBehavior(name=name, state=a, scope='ssr', fate_threshold=2)


class TestRebindPureRedirect:
    """P75 阶段 2：_rebind_state 纯重定向——计数写新 state、旧 state 不变。

    纯重定向（不复制旧值）是跨模拟隔离的根基：sim2 rebind 到新 B 后从初始态开始，
    不继承 sim1 的残留计数。
    """

    def test_softstep_counter_to_new_state(self):
        a, b = PityState(), PityState()
        bh = _soft(a)
        a.set('t', 'counter', 5)  # 预置旧账本非零值——纯重定向不得复制到新账本
        bh._rebind_state(b)
        assert b.get('t', 'counter', 0) == 0  # 新账本初始为 0（若复制旧值此处会失败）
        bh._counter().incr()
        assert b.get('t', 'counter') == 1
        assert a.get('t', 'counter', 0) == 5  # 旧账本保持非零

    def test_hard_counter_to_new_state(self):
        a, b = PityState(), PityState()
        bh = _hard(a)
        a.set('h', 'counter', 7)
        bh._rebind_state(b)
        assert b.get('h', 'counter', 0) == 0
        bh._counter().incr()
        assert b.get('h', 'counter') == 1
        assert a.get('h', 'counter', 0) == 7

    def test_rotating_guaranteed_to_new_state(self):
        a, b = PityState(), PityState()
        bh = _rot(a)
        a.set('r', 'guaranteed', True)  # 预置大保底态——不得复制到新账本
        bh._rebind_state(b)
        assert b.get('r', 'guaranteed', False) is False  # 新账本初始无 guaranteed
        bh._guaranteed.set()
        assert b.get('r', 'guaranteed') is True
        assert a.get('r', 'guaranteed', False) is True

    def test_targeted_fate_points_to_new_state(self):
        a, b = PityState(), PityState()
        bh = _tgt(a)
        a.set('tgt', 'fate_points', 3)
        bh._rebind_state(b)
        assert b.get('tgt', 'fate_points', 0) == 0
        bh._fate_points.incr()
        assert b.get('tgt', 'fate_points') == 1
        assert a.get('tgt', 'fate_points', 0) == 3


class TestEngineRebind:
    """engine 级 _rebind_state：同 state 短路 + legacy 守卫。"""

    def test_is_active_default_false(self):
        """ISSUE-120：is_active 默认值 False——depends_on 依赖方初始 inactive。"""
        engine = PityEngine(pool_specs={}, pity_defs=[], state=PityState(), rarity_rank={})
        assert engine.is_active('nonexistent') is False

    def test_rebind_same_state_short_circuit(self):
        """同 state 短路：rebind(same) 跳过 behaviors 重绑（Flag 实例不重建）。

        若删除短路逻辑，behaviors 的 Counter/Flag 会被重建（新实例），此断言失败。
        """
        a = PityState()
        engine = PityEngine(pool_specs={}, pity_defs=[
            PityDef(name='t', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
        ], state=a, rarity_rank={'ssr': 0})
        bh = engine._behavior_list[0]
        active_before = bh._active
        engine._rebind_state(a)  # 同一对象——短路
        assert engine._state is a
        assert bh._active is active_before  # 短路后 Flag 未被重建


class TestPitySnapshot:
    """P75 核心目标：带保底模拟后 banner_end_pity_states 含 counter（修复前恒空）。"""

    def test_banner_end_pity_states_nonempty(self):
        from gacha_simulator.core.config_store import ConfigStore, PityConfig
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        store = ConfigStore()
        load_toml(_CFG, store)
        store.pity = PityConfig(enabled=True, pities=[
            PityDef(name='ssr_hard', btype='hard', scope='ssr', threshold=90, pools=('*',)),
        ])
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        env = SimulationEnvBuilder.from_config_store(store)
        env.return_compact = False
        batch = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=5, max_workers=1, seed=42,
            strategy_key=store.strategy_key, strategy_params=store.strategy_params,
        )
        results = list(batch)

        any_counter = False
        for r in results:
            for bid, payload in r.get('banner_end_pity_states', {}).items():
                data = payload.get('data', {}) if isinstance(payload, dict) else {}
                if any('counter' in (ns or {}) for ns in data.values()):
                    any_counter = True
        assert any_counter, "banner_end_pity_states 应含 counter 键（保底快照恢复，P75 核心目标）"

    def test_draw_pity_counter_max_nonzero(self):
        """ISSUE-100/108：draw_pity_counter_max 修复后非零（修复前 get_counter 读账本 B 恒 0）。"""
        from gacha_simulator.core.config_store import ConfigStore, PityConfig
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        store = ConfigStore()
        load_toml(_CFG, store)
        store.pity = PityConfig(enabled=True, pities=[
            PityDef(name='ssr_soft', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90, pools=('*',)),
        ])
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        env = SimulationEnvBuilder.from_config_store(store)
        # compact 模式（默认 return_compact=True）收集 draw_pity_counter_max
        batch = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=1, max_workers=1, seed=42,
            strategy_key=store.strategy_key, strategy_params=store.strategy_params,
        )
        r = list(batch)[0]
        dcm = r.get('draw_pity_counter_max', [])
        assert any(v > 0 for v in dcm), "draw_pity_counter_max 应含非零值（ISSUE-100/108）"

    def test_draw_pity_counter_max_hard_peak(self):
        """ISSUE-108：hard 保底触发抽的 draw_pity_counter_max 记录阈值峰值（非抽后 0）。

        修复前采集点在 after_draw 之后，触发抽的 counter 已被 reset → 记录 0；
        修复后（banner.draw 在 after_draw 前采集）应记录 threshold 峰值。
        """
        from gacha_simulator.core.config_store import ConfigStore, PityConfig
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        store = ConfigStore()
        load_toml(_CFG, store)
        store.pity = PityConfig(enabled=True, pities=[
            PityDef(name='ssr_hard', btype='hard', scope='ssr', threshold=30, pools=('*',)),
        ])
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        env = SimulationEnvBuilder.from_config_store(store)
        batch = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=3, max_workers=1, seed=42,
            strategy_key=store.strategy_key, strategy_params=store.strategy_params,
        )
        results = list(batch)
        found = any(30 in r.get('draw_pity_counter_max', []) for r in results)
        assert found, "hard-30 触发抽应记录峰值 30（采集点在 after_draw 前，ISSUE-108）"


class TestEngineRebindExtended:
    """ISSUE-109/123/116：引擎级 rebind 后只读查询读 B、无效池早退先 rebind、交错时序自愈。"""

    def _engine(self):
        return PityEngine(pool_specs={}, pity_defs=[
            PityDef(name='t', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
        ], state=PityState(), rarity_rank={'ssr': 0})

    def test_get_counter_reads_b_after_rebind(self):
        """ISSUE-109/130：rebind 后 get_counter/get_state_summary 立即读 per-call state。"""
        engine = self._engine()
        b = PityState()
        engine._rebind_state(b)
        b.set('t', 'counter', 42)
        assert engine.get_counter('t') == 42
        assert engine.get_state_summary().get('t', {}).get('counter') == 42

    def test_invalid_pool_id_binds_before_early_return(self):
        """ISSUE-123：无效 pool_id 早退前已 rebind——engine._state 指向传入 state。"""
        engine = self._engine()
        b = PityState()
        engine.get_probabilities('invalid_pool', b, {})  # spec=None 早退，但 rebind 先执行
        assert engine._state is b

    def test_interleaved_state_self_heal(self):
        """ISSUE-116：独立 state 调 get_probabilities 重绑到它，再 before_draw 重绑回当前。"""
        engine = self._engine()
        bh = engine._behavior_list[0]
        other, cur = PityState(), PityState()
        engine.get_probabilities('any', other, {})
        assert bh._state is other
        engine.before_draw('any', cur, {})
        assert bh._state is cur


class TestLegacyRebind:
    """ISSUE-102：legacy 签名（state=None）behavior 在 engine rebind 时跳过不崩溃。"""

    def test_legacy_behavior_rebind_no_crash(self):
        legacy = HardPityBehavior(name='legacy', state=None, scope='ssr',
                                  btype='hard', threshold=90)
        assert getattr(legacy, '_legacy_mode', False) is True
        engine = PityEngine(pool_specs={}, pity_defs=[], state=PityState(), rarity_rank={})
        engine._behavior_list.append(legacy)
        b = PityState()
        engine._rebind_state(b)  # 不应 AttributeError
        assert engine._state is b


class TestDependsOnIsActive:
    """ISSUE-120/133：counter 型依赖方激活链——未激活 False、源 did_fire 后 True。"""

    def test_depends_on_is_active_activation_chain(self):
        engine = PityEngine(pool_specs={}, pity_defs=[
            PityDef(name='src', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
            PityDef(name='dep', btype='hard', scope='ssr', threshold=90, depends_on='src'),
        ], state=PityState(), rarity_rank={'ssr': 0})
        b = PityState()
        # 触发 rebind 到 B（get_probabilities 首行 rebind，即使 pool_specs 空早退）
        engine.get_probabilities('any', b, {})
        # 依赖方未激活（B 无 _active 键 → is_active 默认 False）
        assert engine.is_active('dep') is False
        # 模拟源 did_fire 激活传播（after_draw 写 B）
        b.set('dep', '_active', True)
        assert engine.is_active('dep') is True


class TestCrossSimulationIsolation:
    """ISSUE-121：sim1 跑完 → sim2 从初始态开始（纯重定向不残留计数）。"""

    def test_sim2_starts_fresh(self):
        engine = PityEngine(pool_specs={}, pity_defs=[
            PityDef(name='t', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
        ], state=PityState(), rarity_rank={'ssr': 0})
        bh = engine._behavior_list[0]
        b1, b2 = PityState(), PityState()
        engine._rebind_state(b1)          # sim1 开始
        bh._counter().incr()
        bh._counter().incr()
        assert b1.get('t', 'counter') == 2
        engine._rebind_state(b2)          # sim2 开始——从初始态
        assert b2.get('t', 'counter', 0) == 0
        assert engine.get_counter('t') == 0


class TestCounterInitZeroTriggers:
    """ISSUE-106：counter_init=0 且无 guaranteed 初始态下计数型保底仍触发。"""

    def test_soft_triggers_with_zero_init(self):
        from gacha_simulator.core.config_store import ConfigStore, PityConfig
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        store = ConfigStore()
        load_toml(_CFG, store)
        store.pity = PityConfig(enabled=True, pities=[
            PityDef(name='ssr_soft', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90, pools=('*',)),
        ])
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        env = SimulationEnvBuilder.from_config_store(store)
        batch = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=3, max_workers=1, seed=42,
            strategy_key=store.strategy_key, strategy_params=store.strategy_params,
        )
        results = list(batch)
        assert any(r.get('pity_triggers', 0) > 0 for r in results), \
            "counter_init=0 下 soft 计数型保底应触发（阶段 3 快照含 _active，ISSUE-106）"


class TestVulnerabilityFlagOnly:
    """ISSUE-117：含 _active/guaranteed Flag-only 命名空间的快照不进 pity_stats_at_pool_end。"""

    def test_flag_only_namespace_skipped(self):
        from gacha_simulator.core.vulnerability import compute_vulnerability_analysis

        results = [
            {
                'banner_end_resources': {'pool_A': {'draw_resource': 8000.0}},
                'banner_end_pity_states': {'pool_A': {
                    'data': {
                        'ssr_hard': {'counter': 40, '_active': True},
                        'rot': {'guaranteed': True},   # Flag-only，无 counter 键
                    }
                }},
                'card_counts': {},   # 目标未达成 → 失败，进入保底水位统计
                'total_draws': 100,
                'pity_triggers': 1,
            }
            for _ in range(15)
        ]
        analysis = compute_vulnerability_analysis(
            results, {'limited_ssr_1': 1},
            gdr_key='all_targets', gdr_threshold=1.0, alpha=0.5,
        )
        assert analysis.pool_results, "应产出池结果"
        pr = analysis.pool_results[0]
        assert 'ssr_hard' in pr.pity_stats_at_pool_end  # counter 命名空间进水位表
        assert 'rot' not in pr.pity_stats_at_pool_end    # Flag-only 命名空间跳过


class TestNonSnapshotState:
    """ISSUE-128：非快照 state（未含构造期 _active 键）为不支持用法——counter 型保底静默失效。

    生产路径（batch_simulator/worst_impact/profile 脚本）均从 env.pity_state_init 传阶段 3
    快照，故无实际风险。此用例显式声明该用法不受支持，并锁定边界：非快照 state 下
    CounterBasedBehavior 的 _active 读默认 False → before_draw 提前返回（概率调整不生效）。
    """

    def test_non_snapshot_state_silent_degradation(self):
        a = PityState()
        bh = _soft(a)                 # 构造期写 _active=True 到 a
        non_snapshot = PityState()    # 独立空 state，非阶段 3 快照来源
        bh._rebind_state(non_snapshot)
        assert bh._active.is_set() is False  # 非快照缺 _active → 默认 False → 早退
        # 阶段 3 快照（含构造期 _active=True）恢复后生效
        snap = PityState()
        snap.set('t', '_active', True)
        bh._rebind_state(snap)
        assert bh._active.is_set() is True


class TestHard90Peak:
    """ISSUE-108 验收：hard-90 强制保底池的 draw_pity_counter_max 精确 == 90（非 89/0）。"""

    def test_draw_pity_counter_max_hard_90(self):
        from gacha_simulator.core.config_store import ConfigStore, PityConfig
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        store = ConfigStore()
        load_toml(_CFG, store)
        store.pity = PityConfig(enabled=True, pities=[
            PityDef(name='ssr_hard', btype='hard', scope='ssr', threshold=90,
                    counter_init=85, pools=('*',)),   # counter 从 85 起，5 抽后触发 → 峰值 90
        ])
        target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
        env = SimulationEnvBuilder.from_config_store(store)
        batch = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=env.initial_resources,
            num_simulations=3, max_workers=1, seed=42,
            strategy_key=store.strategy_key, strategy_params=store.strategy_params,
        )
        results = list(batch)
        found = any(90 in r.get('draw_pity_counter_max', []) for r in results)
        assert found, "hard-90 触发抽应记录峰值 90（采集点在 after_draw 前，ISSUE-108 验收）"
        # 阶段 5：process_trace 派生 counter_max 抽样验证——随 draw_pity_counter_max 为真实值
        from gacha_simulator.core.process_trace import infer_events
        derived_ok = any(
            90 in (e.counter_max for e in infer_events(r, set(target_specs.keys())).values())
            for r in results
        )
        assert derived_ok, "process_trace 派生 counter_max 应含 hard-90 峰值"
