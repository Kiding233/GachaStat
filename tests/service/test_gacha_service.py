"""GachaService 初始持有数量测试

规则：card_counts / acquired_counts 只记录新抽到的卡（从0开始），
不预填入 initial_count。initial_count 单独保留，用于 bonus 计算时
确定总持有量（= initial_count + newly_acquired）。
"""
import copy
import os
import tempfile

from gacha_simulator.core import (
    Pool, Reward, GachaState, TargetCard, TargetCardSet,
    SmartStrategy, AllPoolsEndCondition,
)
from gacha_simulator.core.action import NonDrawAction, WaitAction
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.core.pity import PityState
from gacha_simulator.core.strategy import Strategy
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, run_batch_parallel,
)
from gacha_simulator.service.gacha_service import (
    GachaService, SimulationStats, _progress_signature,
)


def _make_pool(pool_id="test_pool"):
    # P61（Ph1a）：Pool 已删除 available_from/available_until——时间窗口移至 Banner。
    # 裸 Pool 经构造桥包装为 Banner 后无窗口（永不关闭），停止由 AllPoolsEndCondition 决定。
    # P61（Ph1a/ISSUE-319）：100% 单卡池被推导属性判定为兑换池（random=False），
    # exchange_card_id 对齐目标卡，SmartStrategy 走兑换分支完成抽卡。
    return Pool(
        id=pool_id,
        name="Test Pool",
        cost=[{"draw_resource": 160}],
        rewards=[(Reward(id="card_A", name="Card A"), 1.0)],
        exchange_card_id="card_A",
    )


def test_initial_count_not_prepopulated():
    """initial_count > 0 不预填入 card_counts——只记录新抽到的"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=2)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 1}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    # 概率 100%，每抽必出 card_A → quantity_needed=2，抽2次后满足
    # card_counts 只记新抽到的，应为 2（不含 initial_count）
    assert result.card_counts.get("card_A", 0) == 2


def test_initial_count_zero_no_effect():
    """initial_count=0 时不影响任何行为"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 0}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    assert result.card_counts.get("card_A", 0) == 1


def test_initial_count_multiple_cards():
    """多张卡有不同 initial_count——card_counts 只记新抽到"""
    pool = Pool(
        id="multi_pool",
        name="Multi",
        cost=[{"draw_resource": 160}],
        rewards=[(Reward(id="card_A", name="A"), 0.5), (Reward(id="card_B", name="B"), 0.5)],
    )
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([
        TargetCard(card_id="card_A", pool_ids=["multi_pool"], quantity_needed=2),
        TargetCard(card_id="card_B", pool_ids=["multi_pool"], quantity_needed=1),
    ])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[
            {"card_id": "card_A", "initial_count": 3},
            {"card_id": "card_B", "initial_count": 0},
        ],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=300)

    # card_A: initial=3, quantity=2 — 还需抽2张，card_counts只记新抽到
    assert result.card_counts.get("card_A", 0) >= 2
    # card_B: 无初始持有
    assert result.card_counts.get("card_B", 0) >= 1


def test_initial_count_does_not_satisfy_target():
    """初始持有再高也不满足需求——必须从gacha中新抽到"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 5}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    # 100%出A，抽1次满足 quantity_needed=1
    # card_counts 只记新抽到，不含初始持有
    assert result.card_counts.get("card_A", 0) == 1
    assert result.total_draws == 1


def test_card_defs_none_handled():
    """不传 card_defs 时应正常运行"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService([pool], strategy, stop_cond, target)
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    assert result.card_counts.get("card_A", 0) >= 1


def test_env_builder_from_config_store_smoke():
    """SimulationEnvBuilder.from_config_store() 冒烟测试——模拟 GUI→引擎 实际路径"""
    from gacha_simulator.core.config_store import (
        ConfigStore, CardDefEntry, BannerEntry, BannerPoolEntry, DAY,
        PityConfig, GainRule, TargetCardEntry,
    )
    from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

    store = ConfigStore()
    # P61（§3.9）：写入侧为 store.banner.banners
    store.banner.banners = [
        BannerEntry(
            enabled=True,
            id='pool_draw',
            name='测试抽卡池',
            available_from=0 * DAY,
            available_until=21 * DAY,
            pools=[BannerPoolEntry(
                id='main',
                cost='draw_resource:160',
                rewards=[
                    {'card_id': 'card_A', 'probability': 50.0, 'rarity': 'SSR', 'featured': True},
                    {'card_id': '_no_card', 'probability': 50.0, 'rarity': 'R'},
                ],
            )],
        ),
    ]
    store.card_defs = [
        CardDefEntry(card_id='card_A', name='角色A', rarity='SSR', pools=['pool_draw']),
    ]
    store.target_cards = [TargetCardEntry(card_id='card_A', quantity=2)]
    store.initial_resources = {'draw_resource': 100000}
    store.gain_rules = [GainRule(rule_type='every_n_days', param='1', gains={'draw_resource': 150})]
    store.pity = PityConfig(enabled=False)

    env = SimulationEnvBuilder.from_config_store(store)
    assert env is not None
    assert len(env.pools) == 1
    # P61（Ph6）：from_config_store 改读 store.banner，env.pools 承载 List[Banner]
    assert env.pools[0].id == 'pool_draw'
    assert env.pools[0].name == '测试抽卡池'
    # Pool.pool_type 已删除——推导属性 is_exchange（output='card' and not random）
    assert env.pools[0].active_pool.is_exchange is False
    # P61（Ph6 / ISSUE-001）：Banner 级时间窗口透传（TOML 解析边界已 *DAY 为秒）
    assert env.pools[0].available_from == 0 * DAY
    assert env.pools[0].available_until == 21 * DAY
    # P61（Ph6 / ISSUE-011）：banner_defs 与 pools 同源（_run_single 深拷贝隔离用）
    assert env.banner_defs is not None and len(env.banner_defs) == 1
    assert env.end_time == 21 * DAY


# ══════════════════════════════════════════════════════════════════
# P79（阶段 3）：零进度兜底
#
# 回传断言的并行度纪律：直接断言 result.warnings / result.iterations 的用例
# 统一以 max_workers=1 运行（走进程内路径，规避子进程回传不确定性）；
# return_compact=False 且 max_workers>1 的生产形态另立一条回归（3e）。
# ══════════════════════════════════════════════════════════════════

_MAIN_CONFIG = 'gacha_simulator/config/config.toml'

# 带 targeted 保底的池——供 NonDrawAction 改写保底状态（防误杀用例）
_TARGETED_TOML = """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["SR"],
    ["R"],
]

[[banner]]
id = "test_pool"
name = "测试池"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 0.5
rarity = "SSR"
featured = true

[[banner.pool.reward]]
card_id = "c2"
probability = 0.5
rarity = "SSR"
featured = false

[[pity]]
name = "epi"
type = "targeted"
scope = "ssr"
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true
"""


class _ZeroWaitStrategy(Strategy):
    """类型 1 复现：恒返回零等待，real_time 永久冻结。"""

    @classmethod
    def description(cls) -> str:
        return '始终零等待（类型 1 复现）'

    def select_action(self, ctx):
        return WaitAction(duration=0)


class _NonDrawSpinStrategy(Strategy):
    """防误杀：前 N 轮只发 NonDrawAction——不抽卡、不推进时间，但改写保底状态。

    在 c1 / c2 之间交替切换定轨目标，使「保底状态」这一维度逐轮变化。
    """

    def __init__(self, rounds: int = 4):
        self.rounds = rounds
        self.n = 0

    @classmethod
    def description(cls) -> str:
        return '前 N 轮交替切换定轨目标（合法多轮 NonDrawAction）'

    def select_action(self, ctx):
        if self.n < self.rounds:
            self.n += 1
            card = 'c1' if self.n % 2 else 'c2'
            # Banner 型 service 须用全限定键 {banner}.{pool}——_pool_id_to_banner
            # 只在裸 Pool 输入路径下填充，裸 id 会抛「引用了不存在的池子」
            return NonDrawAction(action_id='switch_epitomized_target',
                                 params={'pool_id': 'test_pool.main', 'card_id': card})
        return WaitAction(duration=86400)


def _run_with(strategy, stop_cond, max_iterations=1000):
    """以自建 service 跑一次（自建池为 100% 单卡池，不依赖外部配置）。"""
    pool = _make_pool()
    target = TargetCardSet(
        [TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])
    svc = GachaService([pool], strategy, stop_cond, target,
                       card_defs=[{"card_id": "card_A", "initial_count": 0}])
    state = GachaState(resources={"draw_resource": 100000})
    return svc.run_simulation_compact(state, max_iterations=max_iterations)


def _write_targeted_config():
    fd, path = tempfile.mkstemp(suffix='.toml')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_TARGETED_TOML)
    return path


def test_zero_progress_dead_loop_is_caught():
    """四例之一：真死循环（恒返回 WaitAction(0)）被兜住并打 warning。"""
    r = _run_with(_ZeroWaitStrategy(), AllPoolsEndCondition(1000.0))
    assert r.warnings, '零等待死循环未被兜住'
    assert '零进度兜底' in r.warnings[0]
    # 连续 3 轮签名相同即 break（首轮只记录），故远小于迭代预算
    assert 3 <= r.iterations <= 6
    assert r.total_draws == 0


def test_zero_progress_affordability_spin_is_caught():
    """四例之二：affordability 空转（fixed_count count=50000 资源耗尽后抽不动）。

    该空转轮返回的正是 DrawAction（动作已产出后才被 affordability 拦下），
    是「判据不得取动作类型」的直接验证；空转走 continue 跳过循环体尾部，
    是「检测必须落循环体顶部」的直接验证。
    """
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}

    r = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=1, max_workers=1, seed=42).results[0]

    assert r.warnings and '零进度兜底' in r.warnings[0]
    assert r.iterations < 1000          # 现状为 100000
    assert r.total_draws > 0            # 空转前确实抽过卡


def test_zero_progress_does_not_kill_legit_non_draw_rounds():
    """四例之三：防误杀——合法多轮 NonDrawAction（改写保底状态）不被终止。"""
    path = _write_targeted_config()
    try:
        store = load_toml(path)
        env = SimulationEnvBuilder.from_config_store(store)
        env.strategy_key = 'no_draw'
        env.strategy_params = {}

        rounds = 4
        strategy = _NonDrawSpinStrategy(rounds=rounds)
        import gacha_simulator.service.batch_simulator as _bs
        orig = _bs.create_strategy
        _bs.create_strategy = lambda key, params=None: strategy
        try:
            batch = run_batch_parallel(
                env=env, target_specs={}, initial_resources=env.initial_resources,
                num_simulations=1, max_workers=1, seed=42)
            r = batch.results[0]
        finally:
            _bs.create_strategy = orig

        assert r.warnings == [], f'合法 NonDrawAction 被误杀: {r.warnings}'
        assert r.iterations > rounds, '未越过 NonDrawAction 阶段即结束'
        assert r.total_draws == 0
    finally:
        os.unlink(path)


def test_progress_signature_covers_all_dimensions():
    """四例之四：进度信号完备性——逐项构造单一维度变化，签名均须随之变化。"""
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    banners = {b.id: b for b in env.pools}
    pity = PityState()

    def sig(state=None, stats=None, bs=None, real_time=0.0, ps=None):
        return _progress_signature(
            state if state is not None
            else GachaState(resources={'draw_resource': 100}, acquired={'c1': 1}),
            stats if stats is not None else SimulationStats(),
            bs if bs is not None else banners,
            real_time,
            ps if ps is not None else pity)

    base = sig()
    # 同态深拷贝必须产出同一签名（否则检测会持续误判为「有进度」）
    assert sig(bs=copy.deepcopy(banners)) == base

    variants = {}
    variants['资源余额'] = sig(
        state=GachaState(resources={'draw_resource': 101}, acquired={'c1': 1}))
    variants['持卡数量'] = sig(
        state=GachaState(resources={'draw_resource': 100}, acquired={'c1': 2}))
    variants['时间'] = sig(real_time=1.0)

    ss_draws = SimulationStats()
    ss_draws.total_draws = 1
    variants['抽数'] = sig(stats=ss_draws)
    ss_pool = SimulationStats()
    ss_pool.pool_draw_counts = {'pool_c1.main': 1}
    variants['池抽数'] = sig(stats=ss_pool)
    ss_pity = SimulationStats()
    ss_pity.last_draw_pity_triggered = True
    variants['上次抽卡触发保底'] = sig(stats=ss_pity)

    ps2 = PityState()
    ps2.set('p1', 'counter', 5)
    variants['保底状态'] = sig(ps=ps2)

    deep = copy.deepcopy(banners)
    deep[next(iter(banners))]._exhaust()
    variants['banner 耗尽标记'] = sig(bs=deep)

    assert len(variants) == 8
    unchanged = [name for name, v in variants.items() if v == base]
    assert not unchanged, f'以下维度未被签名覆盖: {unchanged}'

def test_zero_iteration_boundary():
    """3e：max_iterations=0 不抛 NameError，iterations==0 且耗尽告警正常写入。"""
    pool = _make_pool()
    target = TargetCardSet(
        [TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])
    svc = GachaService([pool], SmartStrategy(), AllPoolsEndCondition(1000.0), target,
                       card_defs=[{"card_id": "card_A", "initial_count": 0}])
    state = GachaState(resources={"draw_resource": 100000})

    r = svc.run_simulation_compact(state, max_iterations=0)
    assert r.iterations == 0
    assert r.total_draws == 0
    assert any('迭代预算耗尽' in w for w in r.warnings), r.warnings
    # 文案不得引用未绑定的 iteration
    assert all('iteration' not in w for w in r.warnings)

    # 充足预算下不应出现该告警
    r2 = svc.run_simulation_compact(GachaState(resources={"draw_resource": 100000}),
                                    max_iterations=200)
    assert not any('迭代预算耗尽' in w for w in r2.warnings), r2.warnings


def test_return_compact_false_with_parallel_workers_propagates_warnings():
    """3e：生产形态回归——return_compact=False 且 max_workers>1 时告警仍到达调用方。

    GUI 抽卡面板与 WebUI 在跑主模拟前都置 env.return_compact = False 且默认
    max_workers=4；只覆盖 max_workers=1 会让闸门对这两条主要入口失明。
    """
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    env.return_compact = False
    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}

    batch = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=2, max_workers=2, seed=42)

    assert batch.results == []          # return_compact=False → compact 不回传
    assert batch.warnings, '告警未经 BatchResult.warnings 到达调用方'
    assert all('零进度兜底' in w for w in batch.warnings)
