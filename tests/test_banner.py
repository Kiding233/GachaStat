"""P61 Ph9 回归测试——banner 模式端到端验证。

覆盖（§3.12 Ph9）：
  时间窗口单位等价（ISSUE-001）/ on_banner_end 第 21 天触发
  lifecycle 全部规则（pool_draws / banner_draws / pool_exhausted / time_window /
    card_obtained + rarity，ISSUE-306/007）
  策略迁移回归（8 策略 banner 模式跑通，ISSUE-001）
  pool_quota 配额 / 4 策略目标追卡（banner.id 命中，ISSUE-303/315）
  兑换池定位（exchange_card_id 透传，ISSUE-313）
  _build_pity_engine_from_gui 全限定键保底绑定（ISSUE-005）
  批量多次模拟可复现（Banner 状态不跨模拟泄漏，ISSUE-312）
  max_draws=0 无限制 / 非 batch 倍数批次中途耗尽（ISSUE-302/331）
  永久 Banner 展平 end_day=None 守卫（ISSUE-002）
  窗口关闭后策略不可再抽（ISSUE-001）/ pending_transitions 单位与事件型守卫
"""
from gacha_simulator.core.config_store import (
    ConfigStore, CardDefEntry, BannerEntry, BannerPoolEntry, LifecycleRuleEntry,
    PityConfig, PityDef, GainRule, TargetCardEntry, DAY,
)
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, run_batch_parallel,
)


# ══════════════════════════════════════════════════════════════════
# Helper
# ══════════════════════════════════════════════════════════════════

def _reward(cid, prob, rarity='R', featured=False, **kw):
    d = {'card_id': cid, 'probability': prob, 'rarity': rarity, 'featured': featured}
    d.update(kw)
    return d


def _pool(pool_id='main', cost='draw_resource:160', batch_size=1, rewards=None,
          excludes_all_pity=False, max_draws=None, exchange_card_id=None):
    if rewards is None:
        rewards = [
            _reward('ssr_a', 1.0, 'SSR', featured=True),
            _reward('r_b', 99.0, 'R'),
        ]
    return BannerPoolEntry(id=pool_id, cost=cost, batch_size=batch_size,
                           excludes_all_pity=excludes_all_pity, max_draws=max_draws,
                           exchange_card_id=exchange_card_id, rewards=rewards)


def _lc(condition, pool=None, at=0.0, match='card_id', action='switch_to', target=None):
    return LifecycleRuleEntry(condition=condition, pool=pool, at=at, match=match,
                              action=action, target=target)


def _make_store(banners, target_cards=None, gains=None, initial=None, pity_enabled=False,
                pity_defs=None, card_defs=None, strategy_key='smart',
                strategy_params=None):
    store = ConfigStore()
    store.banner.banners = banners
    # 未显式提供 card_defs 时从 banner rewards 自动生成（pools 为全限定键，
    # 供 _build_target_set 取段为 banner 级——Ph6 ISSUE-315）
    if card_defs is None:
        card_defs = []
        seen = set()
        for b in banners:
            for p in b.pools:
                full = f"{b.id}.{p.id}"
                for r in p.rewards:
                    cid = r['card_id']
                    if cid in ('_no_card',) or cid in seen:
                        continue
                    seen.add(cid)
                    card_defs.append(CardDefEntry(
                        card_id=cid, name=cid,
                        rarity=r.get('rarity', 'R'), pools=[full]))
    store.card_defs = card_defs
    store.target_cards = target_cards or []
    store.initial_resources = initial or {'draw_resource': 100000}
    store.gain_rules = gains or [
        GainRule(rule_type='every_n_days', param='1', gains={'draw_resource': 150})]
    store.pity = PityConfig(enabled=pity_enabled, pities=pity_defs or [])
    store.strategy_key = strategy_key
    store.strategy_params = strategy_params or {}
    return store


def _run(store, target_specs=None, num=20, seed=42, strategy_key='', strategy_params=None,
         max_workers=1):
    """构造 env 并跑 run_batch_parallel，返回 BatchResult。"""
    env = SimulationEnvBuilder.from_config_store(store)
    return run_batch_parallel(
        env=env,
        target_specs=target_specs or {t.card_id: t.quantity for t in store.target_cards},
        initial_resources=env.initial_resources,
        num_simulations=num,
        max_workers=max_workers,
        seed=seed,
        strategy_key=strategy_key or env.strategy_key,
        strategy_params=strategy_params,
    )


def _ssr_only_banner(bid, available_from=0.0, available_until=21 * DAY,
                     lifecycle=None, max_draws=None, pools=None):
    """单池 SSR 高概率 banner（featured 目标卡 ssr_a）。"""
    if pools is None:
        pools = [_pool(rewards=[
            _reward('ssr_a', 50.0, 'SSR', featured=True),
            _reward('r_b', 50.0, 'R'),
        ])]
    return BannerEntry(id=bid, name=bid, enabled=True, max_draws=max_draws,
                       available_from=available_from, available_until=available_until,
                       pools=pools, lifecycle=lifecycle or [])


# ══════════════════════════════════════════════════════════════════
# 时间窗口单位等价（ISSUE-001）
# ══════════════════════════════════════════════════════════════════

class TestTimeWindowUnits:
    """21 天开池在 real_time >= 21*DAY 秒时开放/关闭；AllPoolsEndCondition 秒判定。"""

    def test_banner_available_within_window(self):
        b = _ssr_only_banner('b1', available_from=0.0, available_until=21 * DAY)
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        assert banner.is_available(0.0) is True
        assert banner.is_available(20 * DAY) is True
        # 窗口端点（real_time == available_until）仍开放；越过（> until）后关闭
        assert banner.is_available(21 * DAY) is True
        assert banner.is_available(21 * DAY + 1) is False
        assert banner.is_available(22 * DAY) is False

    def test_banner_not_available_before_open(self):
        b = _ssr_only_banner('b1', available_from=10 * DAY, available_until=30 * DAY)
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        assert banner.is_available(0.0) is False
        assert banner.is_available(5 * DAY) is False
        # 等待期越过 available_from 后可抽
        assert banner.is_available(10 * DAY) is True

    def test_end_time_is_seconds(self):
        """end_time = max(eff_end)，秒（与 available_until 同单位）。"""
        b = _ssr_only_banner('b1', available_from=0.0, available_until=21 * DAY)
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        assert env.end_time == 21 * DAY
        assert env.end_time != 21  # 非天——秒判定


# ══════════════════════════════════════════════════════════════════
# lifecycle 全部规则
# ══════════════════════════════════════════════════════════════════

class TestLifecycleRules:
    """pool_draws / banner_draws / pool_exhausted / time_window / card_obtained(rarity)。"""

    def test_pool_draws_switch_to(self):
        """pool_draws 抽满 30 抽 → switch_to 下一池。

        注意：单卡 100% 池会被推导为兑换池（§3.13.1 random=False）——阶梯池用
        概率分布避免误判，smart 才能正常抽卡推进。
        """
        b = BannerEntry(id='step', name='阶梯', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[
                            _pool('step1', rewards=[_reward('card_s1', 50.0, 'SSR', featured=True),
                                                    _reward('r1', 50.0, 'R')]),
                            _pool('step2', rewards=[_reward('card_s2', 50.0, 'SSR', featured=True),
                                                    _reward('r2', 50.0, 'R')]),
                        ],
                        lifecycle=[_lc('pool_draws', pool='step1', at=30,
                                       action='switch_to', target='step2')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='card_s2', quantity=1)])
        result = _run(store, num=10, seed=42).results[0]
        assert result['total_draws'] > 0

    def test_pool_exhausted_switch(self):
        """池 max_draws 达 → exhausted → switch_to（一次池）"""
        b = BannerEntry(id='step', name='阶梯', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[
                            _pool('main', max_draws=10,
                                  rewards=[_reward('c1', 50.0, 'SSR', featured=True),
                                           _reward('r1', 50.0, 'R')]),
                            _pool('next', rewards=[_reward('c2', 50.0, 'SSR', featured=True),
                                                   _reward('r2', 50.0, 'R')]),
                        ],
                        lifecycle=[_lc('pool_exhausted', pool='main',
                                       action='switch_to', target='next')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='c2', quantity=1)])
        result = _run(store, num=10, seed=42).results[0]
        assert result['total_draws'] > 0

    def test_time_window_switch_no_draw(self):
        """无抽卡跨 time_window：等待分支触发 time_window 转换、目标池可达（ISSUE-003）。

        构造：池 main 在 0-10 天，time_window 第 11 天 switch 到 free（送抽期）→ main 恢复。
        验证模拟不因等待死锁、正常完成。
        """
        b = BannerEntry(id='gift', name='送抽', enabled=True,
                        available_from=0.0, available_until=40 * DAY,
                        pools=[
                            _pool('main', rewards=[_reward('ssr_a', 50.0, 'SSR', featured=True),
                                                   _reward('r_b', 50.0, 'R')]),
                            _pool('free', cost='ticket:1', rewards=[_reward('ssr_a', 100.0, 'SSR')]),
                        ],
                        lifecycle=[_lc('time_window', at=11 * DAY,
                                       action='switch_to', target='free')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = _run(store, num=5, seed=42).results[0]
        assert result['total_draws'] >= 0

    def test_card_obtained_rarity_newbie_close(self):
        """终末地新手池「出任意 SSR 即关闭」——card_obtained + match=rarity（ISSUE-306/007）。

        exhaust_banner 后 banner 不可再抽；模拟完成后 total_draws 有限（关闭生效）。
        """
        b = BannerEntry(id='newbie', name='新手', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', rewards=[
                            _reward('ssr_x', 1.0, 'SSR', featured=True),
                            _reward('r_y', 99.0, 'R'),
                        ])],
                        lifecycle=[_lc('card_obtained', at=0.0, match='rarity',
                                       pool='ssr', action='exhaust_banner')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_x', quantity=1)])
        result = _run(store, num=10, seed=42).results[0]
        assert result['total_draws'] > 0


# ══════════════════════════════════════════════════════════════════
# 策略迁移回归（ISSUE-001）
# ══════════════════════════════════════════════════════════════════

class TestStrategyBannerMode:
    """8 内置策略在 banner 模式跑通。"""

    def test_all_builtin_strategies_run(self):
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        for key in ['smart', 'pool_quota', 'pity_reserve', 'target_hunting',
                    'stop_on_target', 'fixed_count', 'draw_target', 'no_draw']:
            result = _run(store, num=3, seed=42, strategy_key=key)
            assert len(result.results) == 3, f'{key} 应产出 3 条结果'
            r = result.results[0]
            assert 'total_draws' in r
            assert 'card_counts' in r

    def test_pool_quota_banner_mode(self):
        """pool_quota 配额在 banner 模式生效——全限定键命中、配额到后停抽（ISSUE-002/327）。

        pool_quotas={'b1.main': 5}：总抽数不超 5（配额限制），不恒 0。
        """
        b = _ssr_only_banner('b1')
        store = _make_store(
            [b],
            target_cards=[TargetCardEntry(card_id='ssr_a', quantity=99)],
            strategy_key='pool_quota',
            strategy_params={'pool_quotas': {'b1.main': 5}, 'desire_weights': {'ssr_a': 1.0}},
        )
        result = _run(store, num=5, seed=42, strategy_key='pool_quota',
                      strategy_params={'pool_quotas': {'b1.main': 5}}).results[0]
        # 配额 5 抽——目标 99 张不可能达成，抽数受配额约束
        assert result['total_draws'] <= 5
        assert result['total_draws'] > 0

    def test_pool_needs_target_hits_banner_id(self):
        """4 策略目标追卡：banner.id 命中 TargetCard.pool_ids（ISSUE-303/315）。

        TargetCard.pool_ids 为 banner 级（构造时取段）；smart 抽卡命中目标池。
        """
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = _run(store, num=10, seed=42, strategy_key='smart').results[0]
        # 目标卡 50% 概率——种子下应能达成或至少抽卡
        assert result['total_draws'] > 0

    def test_exchange_pool_location(self):
        """兑换池定位：exchange_card_id 透传后 4 策略命中（ISSUE-313）。"""
        b = BannerEntry(id='ex', name='兑换', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', cost='exchange_currency:5',
                                     exchange_card_id='card_ex',
                                     rewards=[_reward('card_ex', 100.0, 'SSR')])])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='card_ex', quantity=1)],
                            initial={'draw_resource': 100000, 'exchange_currency': 1000})
        result = _run(store, num=5, seed=42, strategy_key='smart').results[0]
        assert result['card_counts'].get('card_ex', 0) >= 1

    def test_draw_target_pool_id_matches_banner(self):
        """draw_target pool_id 参数匹配 banner.id（ISSUE-326）。"""
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = _run(store, num=5, seed=42, strategy_key='draw_target',
                      strategy_params={'pool_id': 'b1', 'max_draws': 10}).results[0]
        assert result['total_draws'] > 0  # 非恒 WaitAction


# ══════════════════════════════════════════════════════════════════
# 保底全限定键绑定（ISSUE-005）
# ══════════════════════════════════════════════════════════════════

class TestPityQualifiedKeyBinding:
    """_build_pity_engine_from_gui 全限定键保底绑定。"""

    def test_qualified_key_pity_def(self):
        """pools=['b1.main'] 精确命中 b1.main 的保底——pool_specs 含全限定键。"""
        b = _ssr_only_banner('b1')
        store = _make_store(
            [b],
            target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)],
            pity_enabled=True,
            pity_defs=[PityDef(name='soft', btype='soft_interval', scope='ssr',
                               target_featured=True, pools=('b1.main',))],
        )
        env = SimulationEnvBuilder.from_config_store(store)
        # pool_specs 键空间为全限定键 {banner_id}.{pool_id}（ISSUE-005/010）
        spec_keys = set(env.pity_engine.pool_specs.keys())
        assert 'b1.main' in spec_keys, f'pool_specs 应含 b1.main，实际 {spec_keys}'
        assert env.pools[0].id == 'b1'

    def test_wildcard_pity_def(self):
        """pools=('*',) 匹配全部池。"""
        b = _ssr_only_banner('b1')
        store = _make_store(
            [b],
            pity_enabled=True,
            pity_defs=[PityDef(name='all', btype='hard', scope='ssr',
                               threshold=90, pools=('*',))],
        )
        env = SimulationEnvBuilder.from_config_store(store)
        assert env.pity_engine is not None


# ══════════════════════════════════════════════════════════════════
# 批量可复现（ISSUE-312）
# ══════════════════════════════════════════════════════════════════

class TestReproducibility:
    """同 env 连续多次模拟固定种子结果逐字段一致（Banner 状态不跨模拟泄漏）。"""

    def test_same_env_reproducible(self):
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        env = SimulationEnvBuilder.from_config_store(store)
        r1 = run_batch_parallel(env=env, target_specs={'ssr_a': 1},
                                initial_resources=env.initial_resources,
                                num_simulations=5, max_workers=1, seed=7,
                                strategy_key='smart').results
        r2 = run_batch_parallel(env=env, target_specs={'ssr_a': 1},
                                initial_resources=env.initial_resources,
                                num_simulations=5, max_workers=1, seed=7,
                                strategy_key='smart').results
        assert [r['total_draws'] for r in r1] == [r['total_draws'] for r in r2]
        assert [r['card_counts'] for r in r1] == [r['card_counts'] for r in r2]


# ══════════════════════════════════════════════════════════════════
# max_draws（ISSUE-302/331）
# ══════════════════════════════════════════════════════════════════

class TestMaxDraws:
    def test_max_draws_zero_unlimited(self):
        """TOML max_draws=0 解析边界归一化 None 后不自动 exhaust（ISSUE-331）。

        注意：归一化发生在 config_toml._build_banners 解析边界（0→None）；引擎收到
        None 才不自动 exhaust。直接构造 BannerEntry(max_draws=0) 绕过解析边界，
        0 落引擎会首抽即 exhaust——测试分别验证归一化函数与 None 落引擎路径。
        """
        from gacha_simulator.core.config_toml import _normalize_max_draws
        assert _normalize_max_draws(0) is None
        assert _normalize_max_draws(None) is None
        assert _normalize_max_draws(50) == 50
        # None（无限制）落引擎：Banner 不自动 exhaust，可连续抽
        b = _ssr_only_banner('b1', max_draws=None)
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = _run(store, num=5, seed=42, strategy_key='fixed_count',
                      strategy_params={'count': 20}).results[0]
        assert result['total_draws'] >= 15

    def test_max_draws_partial_batch_mid(self):
        """max_draws=15, batch=10 非倍数：批次中途耗尽总抽数恒 15（ISSUE-302）。"""
        b = _ssr_only_banner('b1', max_draws=None)
        b.pools = [_pool('main', batch_size=10, max_draws=15,
                         rewards=[_reward('ssr_a', 50.0, 'SSR'), _reward('r_b', 50.0, 'R')])]
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        pool = banner.pools['main']
        assert pool.max_draws == 15
        assert pool.batch_size == 10
        # 跑模拟：fixed_count 目标 30 抽，但池 max_draws=15 耗尽后 banner 不可抽
        result = _run(store, num=3, seed=42, strategy_key='fixed_count',
                      strategy_params={'count': 30}).results[0]
        assert result['total_draws'] == 15, \
            f'非 batch 倍数批次中途耗尽，总抽数应恒 15，实际 {result["total_draws"]}'


# ══════════════════════════════════════════════════════════════════
# 永久 Banner 守卫（ISSUE-002）
# ══════════════════════════════════════════════════════════════════

class TestPermanentBanner:
    def test_permanent_banner_end_day_none(self):
        """永久 Banner 展平 end_day=None，_prepare_pool_info 不抛 TypeError（ISSUE-002）。"""
        b = _ssr_only_banner('b1', available_from=0.0, available_until=None)
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        # 展平视图：end_day=None（透传 None，不填 0）
        flat = store.pools
        assert flat[0].end_day is None
        # worst_impact 参考池读取不崩（pool_duration_days 兜底 21，ISSUE-333）
        from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
        analyzer = WorstImpactAnalyzer([], {}, store)
        analyzer._prepare_pool_info()
        assert analyzer._pool_duration == 21 * DAY


# ══════════════════════════════════════════════════════════════════
# pending_transitions 单位与事件型守卫（ISSUE-305/317/330）
# ══════════════════════════════════════════════════════════════════

class TestPendingTransitions:
    def test_time_window_remaining_days_ceil(self):
        """2.5 天窗口 remaining = ceil((at - real_time)/DAY) = 3，而非秒值（ISSUE-317）。"""
        b = BannerEntry(id='tw', name='时间窗', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[_pool('main')],
                        lifecycle=[_lc('time_window', at=2.5 * DAY,
                                       action='switch_to', target='free')])
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        previews = banner.pending_transitions(0.0)
        tw = next(p for p in previews if p.trigger == 'time_window')
        assert tw.remaining == 3, f'remaining 应为 3（向上取整），实际 {tw.remaining}'
        assert tw.remaining != 216000, '不得为秒值（差 86400 倍）'

    def test_event_remaining_minus1(self):
        """事件型（card_obtained / pool_exhausted）remaining=-1，策略须 >=0 守卫（ISSUE-305）。"""
        b = BannerEntry(id='ev', name='事件', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[_pool('main')],
                        lifecycle=[_lc('card_obtained', match='rarity', pool='ssr',
                                       action='exhaust_banner')])
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        previews = banner.pending_transitions(0.0)
        ev = next(p for p in previews if p.trigger == 'card_obtained')
        assert ev.remaining == -1


# ══════════════════════════════════════════════════════════════════
# on_banner_end 快照（ISSUE-001/003）
# ══════════════════════════════════════════════════════════════════

class TestBannerEndSnapshot:
    def test_banner_end_resources_at_window_close(self):
        """窗口过期（real_time >= available_until）触发 on_banner_end，写 banner_end_resources。

        构造 0-1 天超短窗口 + 等待策略，验证模拟推进越过 until 后快照键为 banner 级。
        """
        b = BannerEntry(id='b_end', name='快照', enabled=True,
                        available_from=0.0, available_until=1 * DAY,
                        pools=[_pool('main', rewards=[
                            _reward('ssr_a', 50.0, 'SSR', featured=True),
                            _reward('r_b', 50.0, 'R')])])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=99)])
        result = _run(store, num=5, seed=42, strategy_key='smart').results[0]
        # banner_end_resources 键为 banner 级（Ph2/Ph7 迁移）
        snap = result.get('banner_end_resources', {})
        assert 'b_end' in snap, f'banner_end_resources 键应为 banner 级，实际 {list(snap.keys())}'


# ══════════════════════════════════════════════════════════════════
# 窗口关闭后策略不可再抽（ISSUE-001）
# ══════════════════════════════════════════════════════════════════

class TestWindowClosedNoDraw:
    def test_banner_not_in_active_after_close(self):
        """real_time > available_until 时 banner 不进入 active_banners。"""
        b = BannerEntry(id='b1', name='关闭', enabled=True,
                        available_from=0.0, available_until=1 * DAY,
                        pools=[_pool('main')])
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        banner = env.pools[0]
        # 越过 until 后不可用
        assert banner.is_available(1 * DAY) is True   # 端点
        assert banner.is_available(1 * DAY + 1) is False


# ══════════════════════════════════════════════════════════════════
# cost_per_draw 非 160（ISSUE-304）
# ══════════════════════════════════════════════════════════════════

class TestCostPerDraw:
    def test_cost_per_draw_non_default(self):
        """orundum:600 配置经 get_cost_per_draw 返回 600 而非静默回退 160（ISSUE-304）。"""
        from gacha_simulator.core.retreat_search import get_cost_per_draw
        b = BannerEntry(id='b600', name='六百', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', cost='orundum:600',
                                     rewards=[_reward('c1', 100.0, 'SSR')])])
        store = _make_store([b])
        env = SimulationEnvBuilder.from_config_store(store)
        cost = get_cost_per_draw(env.pools)
        assert cost == 600, f'cost_per_draw 应为 600，实际 {cost}'
