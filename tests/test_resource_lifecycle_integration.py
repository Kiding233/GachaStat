"""P77 资源生命周期：服务层集成测试（§3.8 6c）。

覆盖：等额转换 / 非等额零头作废 / 小数余额 floor / 清零 / 对账恒等式 /
GDR 分母隔离 / 结算幂等 / 零余额跳过 / 同到期原子结算 / banner 快照时序 /
并行透传一致性。

触发前提：到期检查依赖 real_time 推进，用例策略必须含 WaitAction（_WaitStrategy），
否则时间轴不越到期点、转换永不触发（P77 §3.3 触发时机边界）。
"""

import pytest

from gacha_simulator.core.action import WaitAction
from gacha_simulator.core.banner import Banner
from gacha_simulator.core.pool import Pool, Reward
from gacha_simulator.core.resource_lifecycle import ResourceLifecycle
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import AllPoolsEndCondition
from gacha_simulator.core.strategy import Strategy
from gacha_simulator.core.target_card import TargetCardSet
from gacha_simulator.service.gacha_service import GachaService

DAY = 86400
_BASE = {'draw_resource': 1000.0}


class _WaitStrategy(Strategy):
    """始终等待一天，推进 real_time 越过到期点。"""

    lookahead = None

    @classmethod
    def description(cls):
        return '等待'

    def select_action(self, ctx):
        return WaitAction(duration=DAY)


def _make_banner(until=10 * DAY, bid='b_lim'):
    pool = Pool(id='main', name='main', cost=[{'draw_resource': 160}],
                rewards=[(Reward(id='c1', name='c1'), 1.0)])
    return Banner(id=bid, name='限时池', pools={'main': pool},
                  available_from=0, available_until=until)


def _run(rules, resources, until=10 * DAY, iters=20, banners=None):
    svc = GachaService(banners or [_make_banner(until=until)], _WaitStrategy(),
                       AllPoolsEndCondition(until), TargetCardSet([]),
                       resource_lifecycle_rules=rules)
    return svc.run_simulation_compact(GachaState(resources=dict(resources)),
                                      max_iterations=iters)


def _convert(res_id, target, f=1, t=1, expire_at=10 * DAY):
    return ResourceLifecycle(res_id, expire_at=expire_at,
                             on_expire={'convert_to': target, 'from': f, 'to': t})


# ══════════════════════════════════════════════════════════════════
# 转换与清零语义
# ══════════════════════════════════════════════════════════════════

class TestConvert:
    def test_convert_equal(self):
        """等额转换 from=1,to=1：源清零、目标全额入账，两侧记账对称。"""
        r = _run([_convert('a', 'b')], {**_BASE, 'a': 100.0, 'b': 0.0})
        assert r.final_resources['a'] == 0
        assert r.final_resources['b'] == 100
        assert r.total_consumed.get('a') == 100.0
        assert r.total_gained.get('b') == 100

    def test_convert_ratio_3_2(self):
        """非等额 3:2：目标仅得完整兑换对之积，零头随源作废。"""
        r = _run([_convert('a', 'b', f=3, t=2)], {**_BASE, 'a': 10.0, 'b': 0.0})
        assert r.final_resources['a'] == 0            # 源全额扣减（含零头 1）
        assert r.final_resources['b'] == 6            # (10 // 3) * 2
        assert r.total_consumed.get('a') == 10.0
        assert r.total_gained.get('b') == 6           # 零头不折算

    def test_convert_float_balance(self):
        """小数余额按 floor 取整数量纲换算，源仍全额扣减。"""
        r = _run([_convert('a', 'b', f=3, t=2)], {**_BASE, 'a': 10.6, 'b': 0.0})
        assert r.final_resources['a'] == 0
        assert r.final_resources['b'] == 6            # floor(10.6)=10 → (10//3)*2
        assert r.total_consumed.get('a') == 10.6

    def test_balance_less_than_from(self):
        """余额不足一个兑换对：源全额扣减、目标零入账，不产生负余额。"""
        r = _run([_convert('a', 'b', f=3, t=2)], {**_BASE, 'a': 2.0, 'b': 0.0})
        assert r.final_resources['a'] == 0
        assert r.final_resources.get('b', 0) == 0
        assert r.total_consumed.get('a') == 2.0
        assert 'b' not in r.total_gained

    def test_clear(self):
        """清零：源全额扣减、无目标入账。"""
        r = _run([ResourceLifecycle('fgo', expire_at=10 * DAY,
                                    on_expire={'clear': True})],
                 {**_BASE, 'fgo': 50.0})
        assert r.final_resources['fgo'] == 0
        assert r.total_consumed.get('fgo') == 50.0
        assert r.total_gained == {}

    def test_zero_balance_skip(self):
        """余额为 0 时不触发任何操作（空转跳过）。"""
        r = _run([_convert('a', 'b')], {**_BASE, 'a': 0.0})
        assert r.total_consumed == {}
        assert r.total_gained == {}


# ══════════════════════════════════════════════════════════════════
# 记账与对账
# ══════════════════════════════════════════════════════════════════

class TestAccounting:
    def test_ledger_balance(self):
        """对账恒等式 final = initial + gained - consumed 逐资源成立。"""
        initial = {**_BASE, 'a': 10.0, 'b': 3.0}
        r = _run([_convert('a', 'b', f=3, t=2)], initial)
        for rid, iv in initial.items():
            expected = iv + r.total_gained.get(rid, 0) - r.total_consumed.get(rid, 0)
            assert r.final_resources.get(rid, 0) == expected, f"{rid} 对账不平"

    def test_gdr_denominator_isolated(self):
        """GDR 分母（draw_resource）不受转换影响：分母值与转化效率指标均不变。"""
        from gacha_simulator.core.gdr import GDRCalculator

        initial = {**_BASE, 'a': 100.0}
        r_without = _run([], initial)
        r_with = _run([_convert('a', 'b')], {**initial, 'b': 0.0})

        assert r_with.total_consumed.get('draw_resource', 0) == \
            r_without.total_consumed.get('draw_resource', 0)

        calc = GDRCalculator(target_specs={}, gdr_key='draw_conversion_efficiency')
        assert calc.compute_gdr(r_with) == calc.compute_gdr(r_without)

    def test_idempotent(self):
        """越过到期点后继续推进不重复转换。"""
        r_short = _run([_convert('a', 'b')], {**_BASE, 'a': 100.0}, iters=12)
        r_long = _run([_convert('a', 'b')], {**_BASE, 'a': 100.0}, iters=40)
        assert r_long.total_consumed.get('a') == r_short.total_consumed.get('a') == 100.0
        assert r_long.final_resources['b'] == 100


# ══════════════════════════════════════════════════════════════════
# 触发与快照时序
# ══════════════════════════════════════════════════════════════════

class TestTiming:
    def test_expire_with_banner_alignment(self):
        """expire_with_banner 对齐 banner 下架时刻触发转换。"""
        rule = ResourceLifecycle('a', expire_with_banner='b_lim',
                                 on_expire={'convert_to': 'b', 'from': 1, 'to': 1})
        r = _run([rule], {**_BASE, 'a': 100.0, 'b': 0.0})
        assert r.final_resources['a'] == 0
        assert r.final_resources['b'] == 100

    def test_cascade_same_expire_atomic(self):
        """同到期时刻多资源按快照原子结算，不产生同 tick 链式重复转换。

        A→B (bal=6) 与 B→C (pre_B=2) 同时到期：B 转 C 只按快照 2 结算，
        终态 B=6（2 原余额 + 6 转入 - 2 转出）、C=2；若按实时余额级联则为 B=0、C=8。
        """
        rules = [_convert('a', 'b'), _convert('b', 'c')]
        r = _run(rules, {**_BASE, 'a': 6.0, 'b': 2.0, 'c': 0.0})
        assert r.final_resources['a'] == 0
        assert r.final_resources['b'] == 6
        assert r.final_resources['c'] == 2

    def test_banner_snapshot_after_expiry(self):
        """banner 结束快照采集于资源结算之后（快照含转换收尾结果）。"""
        rule = ResourceLifecycle('a', expire_with_banner='b_lim',
                                 on_expire={'convert_to': 'b', 'from': 1, 'to': 1})
        r = _run([rule], {**_BASE, 'a': 100.0, 'b': 0.0})
        snap = r.banner_end_resources['b_lim']
        assert snap['a'] == 0
        assert snap['b'] == 100

    def test_unmappable_rule_warns_and_skips(self):
        """无法映射的 expire_with_banner 规则发 warning 并跳过，不阻断模拟。"""
        rule = ResourceLifecycle('a', expire_with_banner='not_exist',
                                 on_expire={'clear': True})
        with pytest.warns(UserWarning, match='无法映射'):
            svc = GachaService([_make_banner()], _WaitStrategy(),
                               AllPoolsEndCondition(10 * DAY), TargetCardSet([]),
                               resource_lifecycle_rules=[rule])
        assert svc.resource_expiry_times_sorted == []

    def test_disabled_rule_absent_when_empty(self):
        """未传规则时不建到期索引，模拟正常跑完。"""
        svc = GachaService([_make_banner()], _WaitStrategy(),
                           AllPoolsEndCondition(10 * DAY), TargetCardSet([]))
        assert svc.resource_expiry_times_sorted == []
        r = svc.run_simulation_compact(GachaState(resources={**_BASE, 'a': 5.0}),
                                       max_iterations=12)
        assert r.final_resources['a'] == 5.0


# ══════════════════════════════════════════════════════════════════
# 装配链路与并行透传
# ══════════════════════════════════════════════════════════════════

def _make_store():
    """构造含资源生命周期的 ConfigStore（banner 下架时转换限时币）。"""
    from gacha_simulator.core.config_store import (
        BannerEntry, BannerPoolEntry, CardDefEntry, ConfigStore,
    )
    from gacha_simulator.core.resource_lifecycle import ResourceLifecycleConfig

    store = ConfigStore()
    store.resource_defs = {'draw_resource': '抽卡资源', 'a': '限时币', 'b': '常驻币'}
    store.initial_resources = {'draw_resource': 100000, 'a': 100}
    store.card_defs = [CardDefEntry(card_id='c1', name='卡1', rarity='ssr')]
    store.banner.banners = [BannerEntry(
        id='b_lim', name='限时池', enabled=True,
        available_from=0.0, available_until=10 * DAY,
        pools=[BannerPoolEntry(
            id='main', cost='draw_resource:160',
            rewards=[{'card_id': 'c1', 'probability': 100, 'rarity': 'ssr'}])])]
    store.resource_lifecycle = ResourceLifecycleConfig(enabled=True, rules=[
        ResourceLifecycle('a', expire_with_banner='b_lim',
                          on_expire={'convert_to': 'b', 'from': 1, 'to': 1})])
    store.strategy_key = 'no_draw'
    return store


class TestAssembly:
    def test_env_transmits_rules(self):
        """from_config_store 按 enabled 门控透传规则至 SimulationEnv。"""
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

        env = SimulationEnvBuilder.from_config_store(_make_store())
        assert len(env.resource_lifecycle_rules) == 1
        assert env.resource_lifecycle_rules[0].resource_id == 'a'

    def test_env_disabled_transmits_empty(self):
        """enabled=False 时透传空列表（GachaService 不建到期索引）。"""
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

        store = _make_store()
        store.resource_lifecycle.enabled = False
        env = SimulationEnvBuilder.from_config_store(store)
        assert env.resource_lifecycle_rules == []

    def test_parallel_consistency(self):
        """并行（max_workers=2）与单进程（max_workers=1）同种子结果一致。"""
        from gacha_simulator.service.batch_simulator import (
            SimulationEnvBuilder, run_batch_parallel,
        )

        env = SimulationEnvBuilder.from_config_store(_make_store())
        outs = []
        for workers in (1, 2):
            batch = run_batch_parallel(
                env=env, target_specs={}, initial_resources=env.initial_resources,
                num_simulations=2, max_workers=workers, seed=42,
                strategy_key='no_draw', strategy_params={})
            outs.append(batch.results[0])

        assert outs[0].final_resources == outs[1].final_resources
        assert outs[0].final_resources['a'] == 0
        assert outs[0].final_resources['b'] == 100
        assert outs[0].total_gained.get('b') == 100

    def test_from_dict_rejects_non_list(self):
        """from_dict 对非列表的 resource_lifecycle_rules 抛 ConfigError（不静默接受）。"""
        from gacha_simulator.core.config_store import ConfigError
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

        with pytest.raises(ConfigError):
            SimulationEnvBuilder.from_dict({
                'pools': [], 'schedule_mgr': None, 'end_time': 0,
                'pity_engine': None, 'card_defs': [],
                'resource_lifecycle_rules': 'not_a_list',
            })

    def test_from_dict_accepts_missing_key(self):
        """from_dict 缺省键回退空列表（非 ConfigStore 调用方向后兼容）。"""
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

        env = SimulationEnvBuilder.from_dict({
            'pools': [], 'schedule_mgr': None, 'end_time': 0,
            'pity_engine': None, 'card_defs': [],
        })
        assert env.resource_lifecycle_rules == []


# ══════════════════════════════════════════════════════════════════
# 非紧凑（InfoVector）路径
# ══════════════════════════════════════════════════════════════════

class TestNonCompactPath:
    def test_non_compact_triggers_without_accounting(self, monkeypatch):
        """InfoVector 路径同样触发到期（ISSUE-203），且该路径不记账（total 为 None）。

        非紧凑路径的余额变更落在内部 clone 的 state 上（外部不可观察），
        故以 spy 捕获结算调用与传入的记账账本。
        """
        from gacha_simulator.core.collector import InfoVectorCollector

        calls = []
        original = GachaService._settle_resource_expiry

        def _spy(self, rule, balance, state, total_consumed, total_gained):
            calls.append((rule.resource_id, balance, total_consumed is None))
            return original(self, rule, balance, state, total_consumed, total_gained)

        monkeypatch.setattr(GachaService, '_settle_resource_expiry', _spy)

        svc = GachaService([_make_banner()], _WaitStrategy(),
                           AllPoolsEndCondition(10 * DAY), TargetCardSet([]),
                           resource_lifecycle_rules=[_convert('a', 'b')])
        history = svc.run_simulation(
            GachaState(resources={**_BASE, 'a': 100.0}),
            max_iterations=20, collector=InfoVectorCollector(),
        )

        assert isinstance(history, list)
        assert len(calls) == 1, "非紧凑路径应触发一次到期结算"
        assert calls[0][0] == 'a'
        assert calls[0][1] == 100.0
        assert calls[0][2] is True, "非紧凑路径无汇总账（total_consumed 为 None）"


# ══════════════════════════════════════════════════════════════════
# TOML 驱动的端到端（G6：幻塔等额转换）
# ══════════════════════════════════════════════════════════════════

_G6_TOML = '''
[resources.defs]
draw_resource = "抽卡资源"
tof_token_a = "回火铸金"
tof_token_black = "黑市铸金"

[resources.initial]
draw_resource = 100000
tof_token_a = 100

[[card]]
card_id = "c1"
name = "卡1"
rarity = "ssr"

[[banner]]
id = "banner_tof_weapon_a"
name = "武器池"
start_day = 0
end_day = 10

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 100
rarity = "ssr"

[resources.lifecycle]
enabled = true

[[resources.lifecycle.rules]]
resource_id = "tof_token_a"
expire_with_banner = "banner_tof_weapon_a"

[resources.lifecycle.rules.on_expire]
convert_to = "tof_token_black"
from = 1
to = 1
'''


class TestTomlEndToEnd:
    def test_g6_toml_full_chain(self, tmp_path):
        """TOML 文本 → load_toml → from_config_store → 含等待模拟 → 转换生效。"""
        import os

        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import (
            SimulationEnvBuilder, run_batch_parallel,
        )

        path = os.path.join(str(tmp_path), 'g6.toml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(_G6_TOML)

        store = load_toml(path)
        assert len(store.resource_lifecycle.rules) == 1

        env = SimulationEnvBuilder.from_config_store(store)
        assert len(env.resource_lifecycle_rules) == 1

        batch = run_batch_parallel(
            env=env, target_specs={}, initial_resources=env.initial_resources,
            num_simulations=1, max_workers=1, seed=42,
            strategy_key='no_draw', strategy_params={})
        result = batch.results[0]

        # 卡池下架时刻触发等额转换
        assert result.final_resources['tof_token_a'] == 0
        assert result.final_resources['tof_token_black'] == 100
        assert result.total_consumed.get('tof_token_a') == 100.0
        assert result.total_gained.get('tof_token_black') == 100

        # 对账恒等式
        assert (store.initial_resources['tof_token_a']
                + result.total_gained.get('tof_token_a', 0)
                - result.total_consumed.get('tof_token_a', 0)) == 0.0

    def test_g6_toml_no_wait_strategy_never_triggers(self, tmp_path):
        """无等待动作的策略不推进 real_time，到期永不触发（模拟边界，非缺陷）。"""
        import os

        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import (
            SimulationEnvBuilder, run_batch_parallel,
        )

        path = os.path.join(str(tmp_path), 'g6.toml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(_G6_TOML)

        env = SimulationEnvBuilder.from_config_store(load_toml(path))
        batch = run_batch_parallel(
            env=env, target_specs={}, initial_resources=env.initial_resources,
            num_simulations=1, max_workers=1, seed=42,
            strategy_key='fixed_count', strategy_params={'count': 5})
        result = batch.results[0]

        # 抽 5 次即停（real_time 未推进到 banner 下架时刻），限时币原样保留
        assert result.final_resources['tof_token_a'] == 100
        assert result.final_resources.get('tof_token_black', 0) == 0
