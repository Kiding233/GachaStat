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
        pool_draws = result.get('pool_draw_counts', {})
        # 锁真实行为：step1 抽满 30 触发 pool_draws 切换、step2 被抽（非仅 total_draws>0）
        assert pool_draws.get('step.step1', 0) >= 30, \
            f'step1 应抽满 30 触发 pool_draws 切换，实际 {pool_draws}'
        assert pool_draws.get('step.step2', 0) >= 1, \
            f'step2 应被抽（切换已发生），实际 {pool_draws}'

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
        pool_draws = result.get('pool_draw_counts', {})
        # 锁真实行为：main 抽满 max_draws=10 耗尽、pool_exhausted 切换后 next 被抽
        assert pool_draws.get('step.main', 0) >= 10, \
            f'main 应抽满 max_draws=10 耗尽，实际 {pool_draws}'
        assert pool_draws.get('step.next', 0) >= 1, \
            f'next 应被抽（pool_exhausted 切换），实际 {pool_draws}'

    def test_time_window_switch_no_draw(self):
        """无抽卡跨 time_window：等待分支触发 time_window 转换、目标池可达（ISSUE-003）。

        构造：main 无 draw_resource 可抽（smart 只能等待），free 含目标卡（ticket 成本），
        time_window 第 11 天 switch 到 free——验证等待期 time_window 转换触发、目标池可达不死锁。
        """
        b = BannerEntry(id='gift', name='送抽', enabled=True,
                        available_from=0.0, available_until=40 * DAY,
                        pools=[
                            _pool('main', rewards=[_reward('r1', 50.0, 'R'),
                                                   _reward('r2', 50.0, 'R')]),
                            _pool('free', cost='ticket:1', rewards=[_reward('ssr_a', 90.0, 'SSR', featured=True),
                                                                    _reward('r3', 10.0, 'R')]),
                        ],
                        lifecycle=[_lc('time_window', at=11 * DAY,
                                       action='switch_to', target='free')])
        store = _make_store(
            [b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)],
            initial={'draw_resource': 0, 'ticket': 100},
            gains=[GainRule(rule_type='every_n_days', param='1',
                            gains={'exchange_currency': 1})],  # 不产生 draw_resource → main 抽不起
        )
        result = _run(store, num=5, seed=42).results[0]
        pool_draws = result.get('pool_draw_counts', {})
        # 锁真实行为：等待期 time_window 转换触发 → free 池被抽、目标卡达成（不死锁）
        assert pool_draws.get('gift.free', 0) >= 1, \
            f'无抽卡跨 time_window 应经等待触发切换并抽 free，实际 {pool_draws}'
        assert pool_draws.get('gift.main', 0) == 0, \
            f'main 应不可抽（draw_resource 0），实际 {pool_draws}'
        assert result['card_counts'].get('ssr_a', 0) >= 1

    def test_card_obtained_rarity_newbie_close(self):
        """终末地新手池「出任意 SSR 即关闭」——card_obtained + match=rarity（ISSUE-306/007）。

        池含两张 SSR（目标 ssr_x + 非目标 ssr_other），目标 qty=2。若关闭生效，
        抽到任意 SSR（合计 5%）即 exhaust_banner，未达成 ssr_x×2 也停；若关闭失效
        会继续抽到 2 张 ssr_x（期望 ~400 抽）。锁「抽到 SSR 即关、未达目标也停」。
        """
        b = BannerEntry(id='newbie', name='新手', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', rewards=[
                            _reward('ssr_x', 0.5, 'SSR', featured=True),       # 目标卡（低概率）
                            _reward('ssr_other', 4.5, 'SSR', featured=True),   # 非目标 SSR
                            _reward('r_y', 95.0, 'R'),
                        ])],
                        lifecycle=[_lc('card_obtained', at=0.0, match='rarity',
                                       pool='ssr', action='exhaust_banner')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_x', quantity=2)])
        result = _run(store, num=10, seed=42).results[0]
        # 关闭生效：抽到任意 SSR 即 exhaust，ssr_x 未达成 ×2（<2）——区分「关闭失效时
        # 继续抽到 2 张 ssr_x」的回归（子代理 B1：原单 SSR 配置移除规则结果相同、空转）
        assert result['card_counts'].get('ssr_x', 0) < 2, \
            f'关闭应阻止达成 ssr_x×2 目标，实际 card_counts={result["card_counts"]}'
        assert result['total_draws'] < 100, \
            f'「抽到任意 SSR 即关闭」应限制抽数（~20 抽期望，非 400 达成抽数），实际 {result["total_draws"]}'

    def test_banner_draws_switch(self):
        """banner_draws 条件：Banner 总抽数达阈值 → 切换（补充 Ph9 缺失用例）。"""
        b = BannerEntry(id='bd', name='抽数', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[
                            _pool('main', rewards=[_reward('c1', 50.0, 'SSR', featured=True),
                                                   _reward('r1', 50.0, 'R')]),
                            _pool('alt', rewards=[_reward('c2', 50.0, 'SSR', featured=True),
                                                  _reward('r2', 50.0, 'R')]),
                        ],
                        lifecycle=[_lc('banner_draws', at=20,
                                       action='switch_to', target='alt')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='c2', quantity=1)])
        result = _run(store, num=10, seed=42).results[0]
        pool_draws = result.get('pool_draw_counts', {})
        assert pool_draws.get('bd.main', 0) >= 20, \
            f'main 应抽满 banner_draws=20 触发切换，实际 {pool_draws}'
        assert pool_draws.get('bd.alt', 0) >= 1, \
            f'alt 应被抽（banner_draws 切换），实际 {pool_draws}'


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

    def test_banner_max_draws_auto_exhaust(self):
        """新手池：Banner 级 max_draws 正数达到后自动 exhaust（ISSUE-303，补充缺失用例）。"""
        b = BannerEntry(id='newbie', name='新手', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        max_draws=20,
                        pools=[_pool('main', rewards=[_reward('ssr_a', 50.0, 'SSR', featured=True),
                                                      _reward('r1', 50.0, 'R')])])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=99)])
        result = _run(store, num=5, seed=42, strategy_key='fixed_count',
                      strategy_params={'count': 50}).results[0]
        assert result['total_draws'] == 20, \
            f'Banner max_draws=20 应自动 exhaust，总抽数恒 20，实际 {result["total_draws"]}'

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

    def test_all_permanent_raises_config_error(self):
        """全永久组合（无任何有结束时间的 Banner）解析报 ConfigError（2026-08-04 决策）。"""
        from gacha_simulator.core.config_store import ConfigError
        from gacha_simulator.core.config_toml import _normalize_permanent_banners
        store = _make_store([
            _ssr_only_banner('p1', available_from=0.0, available_until=None),
            _ssr_only_banner('p2', available_from=0.0, available_until=None),
        ])
        try:
            _normalize_permanent_banners(store.banner.banners)
            assert False, '全永久组合应抛 ConfigError'
        except ConfigError:
            pass

    def test_normalize_idempotent(self):
        """归一幂等：二次归一结果不变（load→save→load 后 hash 稳定）。"""
        from gacha_simulator.core.config_toml import _normalize_permanent_banners
        store = _make_store([
            _ssr_only_banner('perm', available_from=0.0, available_until=None),
            _ssr_only_banner('act', available_from=0.0, available_until=42 * DAY),
        ])
        _normalize_permanent_banners(store.banner.banners)
        first = store.banner.banners[0].available_until
        assert first == 42 * DAY
        _normalize_permanent_banners(store.banner.banners)  # 幂等
        assert store.banner.banners[0].available_until == first


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
        """banner_end_resources 键为 banner 级（ISSUE-323）。

        无论快照由结束路径（目标达成/窗口过期 on_banner_end）哪条写入，
        键语义必须是 banner 级——锁定 Ph2/Ph7 迁移后的键空间。
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


# ══════════════════════════════════════════════════════════════════
# Ph9 补充回归（对照 §3.12 Ph9 全量清单，补足 Ph8 首批遗漏项）
# ══════════════════════════════════════════════════════════════════

class TestGiftPoolInsertion:
    """送抽插入组合流程：main 30 抽 → switch free_10pull → pool_exhausted → 切回 main（§七 验收）。

    main 无目标卡（r1/r2），smart 因 banner.id 命中 target 而抽 main 30 发触发
    pool_draws 切换；free_10pull 为插入池（ticket 成本、90% 目标卡），抽到后达成。
    """

    def test_insertion_then_back(self):
        b = BannerEntry(id='gift', name='送抽', enabled=True,
                        available_from=0.0, available_until=40 * DAY,
                        pools=[
                            _pool('main', rewards=[_reward('r1', 50.0, 'R'),
                                                   _reward('r2', 50.0, 'R')]),
                            _pool('free_10pull', cost='ticket:1', max_draws=10,
                                  rewards=[_reward('ssr_a', 90.0, 'SSR', featured=True),
                                           _reward('r3', 10.0, 'R')]),
                        ],
                        lifecycle=[
                            _lc('pool_draws', pool='main', at=30,
                                action='switch_to', target='free_10pull'),
                            _lc('pool_exhausted', pool='free_10pull',
                                action='switch_to', target='main'),
                        ])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)],
                            initial={'draw_resource': 100000, 'ticket': 100})
        result = _run(store, num=5, seed=42).results[0]
        pool_draws = result.get('pool_draw_counts', {})
        # main 抽满 30 触发切换 → free_10pull 被抽（插入池生效）
        assert pool_draws.get('gift.main', 0) >= 30, \
            f'main 应抽满 30 触发 pool_draws 切换，实际 {pool_draws}'
        assert pool_draws.get('gift.free_10pull', 0) >= 1, \
            f'free_10pull 插入池应被抽（切换已触发），实际 {pool_draws}'


class TestMultiBannerSameNameQuota:
    """多 Banner 同名池配额不串池（ISSUE-327）。"""

    def test_quota_not_shared_across_banners(self):
        b1 = _ssr_only_banner('b1')
        b2 = _ssr_only_banner('b2')
        store = _make_store([b1, b2],
                            target_cards=[TargetCardEntry(card_id='ssr_a', quantity=99)])
        result = _run(store, num=5, seed=42, strategy_key='pool_quota',
                      strategy_params={'pool_quotas': {'b1.main': 5}}).results[0]
        pool_draws = result.get('pool_draw_counts', {})
        b1_draws = pool_draws.get('b1.main', 0)
        b2_draws = pool_draws.get('b2.main', 0)
        assert b1_draws <= 5, f'b1.main 配额 5，实际 {b1_draws}'
        assert b2_draws > 0, f'b2.main 不受 b1 配额约束（不串池），实际 {b2_draws}'


class TestExplicitPoolIdDispatch:
    """banner_id=None + 裸 pool_id 反查唯一 Banner 单池路径（ISSUE-316）。

    用自定义策略返回 DrawAction(banner_id=None, pool_id='b1.main') 跑真实模拟——
    验证 gacha_service 派发逻辑（:256-259 反查）真实命中 b1，而非重抄表达式。
    """

    def test_banner_id_none_pool_id_dispatch(self):
        import copy
        from gacha_simulator.service import GachaService
        from gacha_simulator.core.notifier import Notifier
        from gacha_simulator.core import GachaState
        from gacha_simulator.core.stop_condition import AllPoolsEndCondition
        from gacha_simulator.core.action import DrawAction, WaitAction
        from gacha_simulator.core.strategy import Strategy
        from gacha_simulator.service.batch_simulator import _build_target_set
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        env = SimulationEnvBuilder.from_config_store(store)

        class _OnlyPoolIdStrategy(Strategy):
            """只返回 banner_id=None + 裸 pool_id 的 DrawAction（3 次后 Wait 结束）。"""

            @classmethod
            def description(cls) -> str:
                return "测试策略：banner_id=None + 裸 pool_id 派发"

            def __init__(self, pool_id):
                self.pool_id = pool_id

            def select_action(self, ctx):
                if ctx.total_draws < 3:
                    return DrawAction(banner_id=None, pool_id=self.pool_id)
                return WaitAction(duration=1)

        service = GachaService(
            copy.deepcopy(env.pools), _OnlyPoolIdStrategy('b1.main'),
            AllPoolsEndCondition(env.end_time),
            _build_target_set(env.card_defs, {'ssr_a': 1}),
            notifier=Notifier(),
        )
        state = GachaState(resources=dict(env.initial_resources))
        result = service.run_simulation_compact(state)
        # banner_id=None + pool_id='b1.main' 应真实派发到 b1 并抽 3 次（不抛 ValueError）
        assert result.total_draws >= 3, \
            f'banner_id=None + pool_id 应成功反查 b1 并抽卡，实际 total_draws={result.total_draws}'


class TestMultiStrategyTargetHunting:
    """其余 3 策略目标追卡回归（ISSUE-303/315）——smart 已由
    TestStrategyBannerMode.test_pool_needs_target_hits_banner_id 覆盖。"""

    def test_other_strategies_hunt_target(self):
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        for key in ['pity_reserve', 'pool_quota', 'stop_on_target']:
            result = _run(store, num=8, seed=42, strategy_key=key).results[0]
            assert result['total_draws'] > 0, f'{key} 应抽卡追目标（banner.id 命中）'


class TestMultiStrategyExchange:
    """其余 3 策略兑换池定位回归（ISSUE-313）——smart 已由
    TestStrategyBannerMode.test_exchange_pool_location 覆盖。"""

    def test_other_strategies_locate_exchange(self):
        b = BannerEntry(id='ex', name='兑换', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', cost='exchange_currency:5',
                                     exchange_card_id='card_ex',
                                     rewards=[_reward('card_ex', 100.0, 'SSR')])])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='card_ex', quantity=1)],
                            initial={'draw_resource': 100000, 'exchange_currency': 1000})
        for key in ['pity_reserve', 'pool_quota', 'stop_on_target']:
            result = _run(store, num=5, seed=42, strategy_key=key).results[0]
            assert result['card_counts'].get('card_ex', 0) >= 1, \
                f'{key} 应经 exchange_card_id 命中兑换池'


class TestNoDrawBannerEnd:
    """no_draw + 多池 Banner 的 banner_end_resources 键（ISSUE-323）。"""

    def test_no_draw_banner_end_resources_banner_key(self):
        b = BannerEntry(id='b1', name='多池', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main'), _pool('free', cost='ticket:1')])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = _run(store, num=3, seed=42, strategy_key='no_draw').results[0]
        snap = result.get('banner_end_resources', {})
        assert 'b1' in snap, \
            f'no_draw banner_end_resources 键应为 banner 级，实际 {list(snap.keys())}'


class TestWorstImpactPityEngine:
    """最差影响分析保底触发（ISSUE-301）——pool_specs 键 {pid}.main 时 before_draw 不静默跳过。"""

    def test_pity_engine_qualified_key(self):
        from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
        b = _ssr_only_banner('b1')  # ssr_a featured
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)],
                            pity_enabled=True,
                            pity_defs=[PityDef(name='soft', btype='soft_interval', scope='ssr',
                                               target_featured=True, pools=('*',))])
        analyzer = WorstImpactAnalyzer([], {'ssr_a': 1}, store)
        analyzer._prepare_pool_info()
        engine = analyzer._build_pity_engine()
        assert engine is not None
        spec_keys = set(engine.pool_specs.keys())
        assert any(k.endswith('.main') for k in spec_keys), \
            f'pool_specs 键应为 {{pid}}.main，实际 {list(spec_keys)[:3]}'
        # 全限定键查询命中——before_draw 保底调整不静默跳过（裸键查询为 None 会退化）
        spec = engine.get_spec('_worst_impact_pool_0.main')
        assert spec is not None, '全限定键查询应命中（soft pity 不静默退化）'


class TestWorstImpactAnalyzeExpectedPools:
    """最差影响分析 analyze() 冒烟 + 99 池错峰窗口保留（ISSUE-302）。

    注：expected_pools ≈ MAX_POOLS 依赖 draw_target 目标感知（达成当前池目标后等待
    下一池窗口），而 draw_target 无该机制（P61 前后一致，resource_gain=None 时
    real_time 不推进、抽卡卡首池）——属既有行为而非 P61 退化。本测试锁定
    Ph1a 已落地的「99 池错峰窗口由 Banner 级 available_from/until 承载」+ analyze 可跑。
    """

    def test_staggered_windows_preserved(self):
        from gacha_simulator.core.worst_impact import WorstImpactAnalyzer, MAX_POOLS
        from gacha_simulator.core.banner import Banner
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        analyzer = WorstImpactAnalyzer([], {'ssr_a': 1}, store)
        cfg = analyzer.prepare_simulation_config(50000)
        assert len(cfg['pools']) == MAX_POOLS
        banners = [p for p in cfg['pools'] if isinstance(p, Banner)]
        assert len(banners) == MAX_POOLS, '99 池均为 Banner（窗口承载）'
        windows = [(p.id, p.available_from, p.available_until) for p in banners]
        assert all(w[1] is not None and w[2] is not None for w in windows), \
            '99 池均带 Banner 级 available_from/until（错峰窗口保留）'
        assert windows[0][1] < windows[1][1] < windows[-1][1], '错峰窗口依次递增'

    def test_analyze_smoke(self):
        """analyze() 冒烟：custom_resource 跳过条件分布，不崩、产出 expected_pools。"""
        from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
        b = _ssr_only_banner('b1')
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        analyzer = WorstImpactAnalyzer([], {'ssr_a': 1}, store)
        result = analyzer.analyze(num_simulations=2, custom_resource=50000)
        assert result.expected_pools >= 1
        assert result.worst_resource == 50000


class TestCliFallbackTarget:
    """CLI 无 [[targets]] 兜底目标取 banner 段（ISSUE-003）。"""

    def test_fallback_target_is_real_card(self):
        b = BannerEntry(id='b1', name='池', enabled=True,
                        available_from=0.0, available_until=21 * DAY,
                        pools=[_pool('main', rewards=[_reward('b1_ssr', 50.0, 'SSR', featured=True),
                                                      _reward('r1', 50.0, 'R')])])
        store = _make_store([b])  # 无 target_cards
        # P61（ISSUE-003）：调用 cli 真实兜底函数（非重抄表达式）——取 banner 段拼 _ssr
        from gacha_simulator.cli import _fallback_target_ids
        fallback_ids = _fallback_target_ids(store)
        assert fallback_ids == ['b1_ssr'], \
            f'兜底目标应取 banner 段（非全限定 banner.main_ssr），实际 {fallback_ids}'
        card_ids = {c.card_id for c in store.card_defs}
        assert fallback_ids[0] in card_ids, \
            f'兜底目标 {fallback_ids[0]} 应为真实卡，实际卡集 {card_ids}'


class TestCliMigrateDisposition:
    """CLI --migrate 处置（ISSUE-004）：空 banner 报错提示手工迁移；新格式提示已迁移。"""

    def test_migrate_new_format(self):
        import subprocess
        import sys
        import os
        cfg = os.path.join(os.path.dirname(__file__), '..', 'gacha_simulator', 'config', 'config.toml')
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        result = subprocess.run(
            [sys.executable, '-m', 'gacha_simulator.cli', '-c', cfg, '--migrate'],
            capture_output=True, text=True, timeout=120, env=env,
            encoding='utf-8', errors='replace',
        )
        assert '已为新格式' in result.stdout, f'新格式应提示已为新格式，输出: {result.stdout}'
        assert result.returncode == 0

    def test_migrate_empty_banner_errors(self, tmp_path):
        """旧格式（[[pools]] 无 [[banner]]）经 -c 传入 --migrate → 显式报错而非误导提示。"""
        import subprocess
        import sys
        import os
        old_toml = tmp_path / 'old_pools.toml'
        old_toml.write_text(
            '# 旧格式残留\n[[pools]]\npool_id = "p1"\nname = "旧池"\ncost = "draw_resource:160"\n',
            encoding='utf-8',
        )
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        result = subprocess.run(
            [sys.executable, '-m', 'gacha_simulator.cli', '-c', str(old_toml), '--migrate'],
            capture_output=True, text=True, timeout=120, env=env,
            encoding='utf-8', errors='replace',
        )
        combined = result.stdout + (result.stderr or '')
        assert '不含任何 Banner' in combined, f'空 banner 应显式报错，输出: {combined}'
        assert result.returncode == 1


class TestObtainablePermanentBanner:
    """永久 Banner（available_from=None）目标卡可达（B1 修复：None 归一 0.0 不误伤永久池）。"""

    def test_permanent_banner_obtainable(self):
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        b = BannerEntry(id='perm', name='永久', enabled=True,
                        available_from=None, available_until=None,
                        pools=[_pool('main', rewards=[_reward('ssr_a', 50.0, 'SSR', featured=True)])])
        store = _make_store([b], target_cards=[TargetCardEntry(card_id='ssr_a', quantity=1)])
        result = filter_target_specs_by_obtainable({'ssr_a': 1}, store, final_time=100.0)
        assert result == {'ssr_a': 1}, f'永久 Banner 目标卡应可达，实际 {result}'


def test_p72_mixed_draws_cross_banner_key_integrity():
    """P72 §4.3 首条：混合抽卡跨 banner 真实模拟——累积快照/脆弱性结果键均为 banner 级。

    确定性键修复（P72 §4.1）在真实模拟下生效：WorkerLocalExtractor 并行路径累积快照键
    （banner 级，经 merge 聚合）与 compute_vulnerability_analysis pool_results 键
    （banner 级）均不含 '.'；累积消费端 banner 段取数不崩溃。
    """
    from gacha_simulator.core.vulnerability import compute_vulnerability_analysis
    from gacha_simulator.gui.process_analysis_panel import ProcessAnalysisPanel

    store = _make_store(
        banners=[
            BannerEntry(id='b1', name='周年庆', available_from=0.0, available_until=10 * DAY,
                        pools=[
                            _pool('main', rewards=[
                                _reward('t1', 30.0, 'SSR', featured=True), _reward('r1', 70.0, 'R')]),
                            _pool('step1', rewards=[
                                _reward('t1', 30.0, 'SSR', featured=True), _reward('r1', 70.0, 'R')]),
                        ]),
            BannerEntry(id='b2', name='武器特选', available_from=10 * DAY, available_until=20 * DAY,
                        pools=[_pool('main', rewards=[
                            _reward('t2', 30.0, 'SSR', featured=True), _reward('r2', 70.0, 'R')])]),
        ],
        target_cards=[
            TargetCardEntry(card_id='t1', quantity=1),
            TargetCardEntry(card_id='t2', quantity=1),
        ],
        initial={'draw_resource': 5000},
    )
    batch = _run(store, num=8, seed=42)

    # 累积快照键 banner 级（并行路径 + merge）
    cum = (batch.extraction or {}).get('cumulative_snapshots', {}) if batch.extraction else {}
    assert cum, '混合抽卡应产出累积快照'
    for pid in cum:
        assert '.' not in pid, f'累积快照键应为 banner 级，got {pid}'

    # 累积消费端 banner 段取数不崩溃（真实模拟快照）
    panel = ProcessAnalysisPanel.__new__(ProcessAnalysisPanel)
    panel._cumulative_snapshots = cum
    first_pid = next(iter(cum))
    panel._compute_pool_gdr(
        'cumulative', None, f'{first_pid}.main', 0, {'t1': 1, 't2': 1}, 'all_targets',
        ssr_ids=set(), weapon_character_map=None, initial_resources={'draw_resource': 5000},
    )

    # 脆弱性结果键 banner 级
    analysis = compute_vulnerability_analysis(
        [r.to_dict() if hasattr(r, 'to_dict') else r for r in batch.results],
        {'t1': 1, 't2': 1}, gdr_key='all_targets', gdr_threshold=1.0, alpha=0.5)
    for pr in analysis.pool_results:
        assert '.' not in pr.pool_id, f'脆弱性 pool_id 应为 banner 级，got {pr.pool_id}'
