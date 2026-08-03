"""GachaService 初始持有数量测试

规则：card_counts / acquired_counts 只记录新抽到的卡（从0开始），
不预填入 initial_count。initial_count 单独保留，用于 bonus 计算时
确定总持有量（= initial_count + newly_acquired）。
"""
from gacha_simulator.core import (
    Pool, Reward, GachaState, TargetCard, TargetCardSet,
    SmartStrategy, AllPoolsEndCondition,
)
from gacha_simulator.service.gacha_service import GachaService


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
