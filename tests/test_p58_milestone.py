"""P58 里程碑奖励引擎（MilestoneEngine）测试——M8 阶段。

覆盖（§四附 M8 测试范围声明）：
  A. 单元测试
    UT1  MilestoneEngine._resolve_bonus()——cards+resources+random_cards 同时解析；
         随机卡同 seed 可复现；不修改 counters/_active/_triggered。
    UT2  _build_milestone() 解析器——正例（cards 引用有效卡加载成功）+ 负例
         （cards 引用不存在 / random_cards.count 非法 / weights 非数字 /
         resources 值非数值 / name 重复 → ConfigError）。注意 store.card_defs
         必须含被引用的卡（ISSUE-101）。
    UT3  TOML round-trip——构造 MilestoneConfig → save_toml → load_toml →
         逐字段相等。
    UT4  collector 序列化闭环——CompactCollector on_draw 制造 draw_resources_gained
         长度 ≥1 → on_bonus → to_dict → from_dict → bonus_events 字段完整 +
         result_version == 2。

  B. 集成测试（§1.1a 各场景期望输出表 + S1 + 空抽 + 溢出 + 流式 + 方案 A/B +
     run_batch_parallel 兜底）
"""
from gacha_simulator.core.collector import CompactCollector
from gacha_simulator.core.config_store import (
    ConfigStore, ConfigError, CardDefEntry, BannerEntry, BannerPoolEntry,
    MilestoneConfig, MilestoneDef, OverflowBand, DAY,
)
from gacha_simulator.core.config_toml import _build_milestone, load_toml, save_toml
from gacha_simulator.core.milestone import MilestoneEngine
from gacha_simulator.core.result_types import CompactResult
from gacha_simulator.core.stop_condition import FixedActionCountCondition
from gacha_simulator.core.streaming import extract_aggregate, WorkerLocalExtractor
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, run_batch_parallel,
)


# ══════════════════════════════════════════════════════════════════
# Helper（仿 tests/test_banner.py 的 _reward/_pool/_make_store/_run）
# ══════════════════════════════════════════════════════════════════

def _reward(cid, prob, rarity='R', featured=False, **kw):
    d = {'card_id': cid, 'probability': prob, 'rarity': rarity, 'featured': featured}
    d.update(kw)
    return d


def _pool(pool_id='main', cost='draw_resource:160', batch_size=1, rewards=None):
    if rewards is None:
        rewards = [
            _reward('ssr_a', 1.0, 'SSR', featured=True),
            _reward('r_b', 99.0, 'R'),
        ]
    return BannerPoolEntry(id=pool_id, cost=cost, batch_size=batch_size, rewards=rewards)


def _make_store(milestone_defs, card_extra=None, reward_overrides=None, banner_id='b1',
                available_until=30 * DAY):
    """构造 ConfigStore——含 milestone 配置与全部被引用卡。

    card_extra: 额外 CardDefEntry（赠卡候选，pools=[] 保证不在任何池 distribution，
      否则自然抽到会破坏 `card_counts[...] == N` 断言——REVIEW-R1-FIX: ISSUE-107）。
    reward_overrides: 覆盖池 rewards（如空抽交换池 _no_card）。
    """
    rewards = reward_overrides if reward_overrides is not None else None
    b = BannerEntry(id=banner_id, name=banner_id, enabled=True,
                    available_from=0.0, available_until=available_until,
                    pools=[_pool(rewards=rewards)])
    store = ConfigStore()
    store.banner.banners = [b]
    card_defs = []
    seen = set()
    for banner in store.banner.banners:
        for p in banner.pools:
            full = f"{banner.id}.{p.id}"
            for r in p.rewards:
                cid = r['card_id']
                if cid in ('_no_card',) or cid in seen:
                    continue
                seen.add(cid)
                card_defs.append(CardDefEntry(
                    card_id=cid, name=cid, rarity=r.get('rarity', 'R'), pools=[full]))
    store.card_defs = card_defs + list(card_extra or [])
    store.initial_resources = {'draw_resource': 1000000}
    store.milestone = MilestoneConfig(enabled=True, milestones=milestone_defs)
    store.strategy_key = 'smart'
    return store


def _run(store, count, seed=42, num=1, max_workers=1):
    """构造 env（固定抽数停止条件）并跑 run_batch_parallel，返回 CompactResult dict。"""
    env = SimulationEnvBuilder.from_config_store(store)
    env.stop_condition = FixedActionCountCondition(max_actions=count)
    batch = run_batch_parallel(
        env=env, target_specs={}, initial_resources=env.initial_resources,
        num_simulations=num, max_workers=max_workers, seed=seed,
        strategy_key='fixed_count', strategy_params={'count': count},
    )
    return batch.results[0] if num == 1 else batch.results


# ══════════════════════════════════════════════════════════════════
# A. 单元测试
# ══════════════════════════════════════════════════════════════════

class TestUT1ResolveBonus:
    """MilestoneEngine._resolve_bonus()——三字段并存 + 随机卡可复现 + 不改状态。"""

    def _def(self):
        return MilestoneDef(
            name='test', threshold=40,
            bonus_reward={
                'cards': ['a', 'b'],
                'resources': {'c': 5},
                'random_cards': [{'candidates': ['x', 'y'], 'weights': [1.0, 1.0], 'count': 1}],
            })

    def test_three_fields_resolved_and_reproducible(self):
        md = self._def()
        e1 = MilestoneEngine([md], seed=42)
        e2 = MilestoneEngine([md], seed=42)
        r1 = e1._resolve_bonus(md)
        r2 = e2._resolve_bonus(md)
        # cards + 1 张随机卡（固定 seed 下确定）
        assert r1['card_ids'][:2] == ['a', 'b']
        assert len(r1['card_ids']) == 3
        assert r1['card_ids'][2] in ('x', 'y')
        assert r1['resources'] == {'c': 5}
        # 同 seed 可复现
        assert r1 == r2

    def test_no_state_mutation(self):
        md = self._def()
        eng = MilestoneEngine([md], seed=42)
        eng.after_draw('', 'main')   # 先推进一次，确认 _resolve_bonus 不改已推进状态
        counters = dict(eng._counters)
        active = dict(eng._active)
        triggered = dict(eng._triggered)
        eng._resolve_bonus(md)
        assert eng._counters == counters
        assert eng._active == active
        assert eng._triggered == triggered


class TestUT2BuildMilestone:
    """_build_milestone() 解析器——正例 + 各负例 ConfigError（ISSUE-101/301/302/303）。"""

    def _store(self):
        return ConfigStore(card_defs=[
            CardDefEntry(card_id='a', name='a', rarity='R', pools=[]),
            CardDefEntry(card_id='x', name='x', rarity='R', pools=[]),
        ])

    def test_positive(self):
        store = self._store()
        _build_milestone({'milestone': [{
            'name': 'test', 'threshold': 10, 'repeat': True,
            'bonus_reward': {'cards': ['a'], 'resources': {}, 'random_cards': []},
        }]}, store)
        ms = store.milestone.milestones
        assert len(ms) == 1
        assert ms[0].name == 'test'
        assert ms[0].threshold == 10
        assert ms[0].repeat is True
        assert ms[0].banner == ''

    def _expect_config_error(self, milestone_entry):
        store = self._store()
        try:
            _build_milestone({'milestone': [milestone_entry]}, store)
        except ConfigError:
            return
        raise AssertionError(f"应抛 ConfigError：{milestone_entry}")

    def test_cards_ghost_id(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {'cards': ['ghost_id']}})

    def test_random_cards_candidates_ghost(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['ghost2']}]}})

    def test_random_cards_count_zero(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a'], 'count': 0}]}})

    def test_random_cards_count_negative(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a'], 'count': -1}]}})

    def test_random_cards_count_non_numeric_string(self):
        # 'abc' 非数字 → ConfigError（ISSUE-301）
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a'], 'count': 'abc'}]}})

    def test_random_cards_count_numeric_string_normalized(self):
        # '2' 数字字符串——校验通过并被规范化写回为 int（ISSUE-301 写回逻辑）
        store = self._store()
        _build_milestone({'milestone': [{'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a'], 'count': '2'}]}}]}, store)
        rc = store.milestone.milestones[0].bonus_reward['random_cards'][0]
        assert rc['count'] == 2 and isinstance(rc['count'], int)

    def test_weights_non_numeric(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a'], 'weights': ['high']}]}})

    def test_weights_all_zero(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a', 'x'], 'weights': [0.0, 0.0]}]}})

    def test_weights_len_mismatch(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'random_cards': [{'candidates': ['a', 'x'], 'weights': [1.0]}]}})

    def test_resources_non_numeric_value(self):
        self._expect_config_error({'name': 'm', 'bonus_reward': {
            'resources': {'coin': 'abc'}}})

    def test_duplicate_name(self):
        # 两条同名（seen_names 跨条目）→ ConfigError
        store = self._store()
        try:
            _build_milestone({'milestone': [{'name': 'm'}, {'name': 'm'}]}, store)
        except ConfigError:
            return
        raise AssertionError('应抛 ConfigError：name 重复')

    # ── 代码审查 F1/F2/F3（2026-08-05）防御性校验缺口 ──

    def test_milestone_entry_not_dict(self):
        # F1：milestone 列表项非 dict → ConfigError 而非裸 AttributeError
        self._expect_config_error(5)

    def test_name_not_string(self):
        # F1：name 非字符串 → ConfigError 而非裸 AttributeError
        self._expect_config_error({'name': 123})

    def test_bonus_reward_not_dict(self):
        # F1：bonus_reward 非表 → ConfigError 而非裸 AttributeError
        self._expect_config_error({'name': 'm', 'bonus_reward': 5})

    def test_max_triggers_negative(self):
        # F2：max_triggers 负数 → ConfigError（否则静默变成「触发一次即停用」）
        self._expect_config_error({'name': 'm', 'max_triggers': -1})

    def test_threshold_float(self):
        # F3：threshold float → ConfigError（拒绝 int() 静默截断）
        self._expect_config_error({'name': 'm', 'threshold': 10.9})

    def test_threshold_bool(self):
        # F3：threshold bool → ConfigError（bool 是 int 子类的陷阱）
        self._expect_config_error({'name': 'm', 'threshold': True})

    def test_repeat_string(self):
        # F3：repeat 字符串 → ConfigError（'false' 字符串 truthy 被当 True）
        self._expect_config_error({'name': 'm', 'repeat': 'false'})


class TestUT3TomlRoundTrip:
    """MilestoneConfig → save_toml → load_toml → 逐字段相等。"""

    def test_round_trip(self, tmp_path):
        store = ConfigStore(card_defs=[
            CardDefEntry(card_id='a', name='a', rarity='R', pools=[]),
            CardDefEntry(card_id='x', name='x', rarity='R', pools=[]),
            CardDefEntry(card_id='y', name='y', rarity='R', pools=[]),
        ])
        store.milestone = MilestoneConfig(enabled=True, milestones=[MilestoneDef(
            name='m1', threshold=40, repeat=False, max_triggers=1, banner='b1',
            bonus_reward={
                'cards': ['a'], 'resources': {'coin': 500},
                'random_cards': [{'candidates': ['x', 'y'], 'weights': [1.0, 2.0], 'count': 2}],
            })])
        path = str(tmp_path / 'cfg.toml')
        save_toml(store, path)
        loaded = load_toml(path)
        m1 = store.milestone.milestones[0]
        m2 = loaded.milestone.milestones[0]
        assert m2.name == m1.name
        assert m2.threshold == m1.threshold
        assert m2.repeat == m1.repeat
        assert m2.max_triggers == m1.max_triggers
        assert m2.banner == m1.banner
        assert m2.bonus_reward == m1.bonus_reward
        # random_cards 内嵌列表/数字完整保真（无字符串化退化）
        assert m2.bonus_reward['random_cards'][0]['weights'] == [1.0, 2.0]
        assert m2.bonus_reward['random_cards'][0]['count'] == 2


class TestUT4CollectorSerialization:
    """collector on_bonus → to_dict → from_dict 闭环（result_version == 2）。"""

    def test_bonus_events_round_trip(self):
        class FakePool:
            id = 'pool_1'

        c = CompactCollector()
        c.on_draw(card_id='ssr_a', pool=FakePool(), spent={'draw_resource': 160},
                  resources_gained={'coin': 10}, pity_triggered=False,
                  triggered_pity_name=None, pity_counter_max=0, real_time=10.0,
                  pity_state=None, combined_gained={'coin': 10}, pool_key='pool_1')
        c.on_bonus(milestone_name='m1', card_ids=['a', 'b'], resources={'coin': 500},
                   pool_id='pool_1', real_time=10.0, draw_index=0)
        result = CompactResult.from_dict(c.get_result().to_dict())
        assert len(result.bonus_events) == 1
        ev = result.bonus_events[0]
        assert ev['milestone_name'] == 'm1'
        assert ev['card_ids'] == ['a', 'b']
        assert ev['resources'] == {'coin': 500}
        assert ev['pool_id'] == 'pool_1'
        assert ev['real_time'] == 10.0
        assert ev['draw_index'] == 0
        # 方案 C 源头合并：milestone 资源并入触发抽产出与 total_gained
        assert result.draw_resources_gained[0]['coin'] == 510
        assert result.total_gained['coin'] == 500
        # 方案 A 源头合并：milestone 卡并入 card_counts / pool_card_counts
        assert result.card_counts['a'] == 1 and result.card_counts['b'] == 1
        assert result.pool_card_counts['pool_1']['a'] == 1
        # 序列化版本号反映格式演进（ISSUE-106）
        assert result.result_version == 2


# ══════════════════════════════════════════════════════════════════
# B. 集成测试（§1.1a 7 个场景 + S1 + 空抽 + 溢出 + 流式 + 方案 A/B + 单进程兜底）
# ══════════════════════════════════════════════════════════════════

class TestScenarioNaruto:
    """场景 1/2——火影每 10 抽碎片 + 50 抽大保底碎片（资源型 milestone，repeat=true）。"""

    def test_scenario1_every_10(self):
        store = _make_store([MilestoneDef(
            name='naruto_fragment', threshold=10, repeat=True,
            bonus_reward={'resources': {'fragment_s': 1}})])
        result = _run(store, count=25)
        assert len(result['bonus_events']) == 2
        assert result['final_resources'].get('fragment_s', 0) == 2

    def test_scenario2_every_50(self):
        store = _make_store([MilestoneDef(
            name='naruto_s_fragment', threshold=50, repeat=True,
            bonus_reward={'resources': {'fragment_s': 5}})])
        result = _run(store, count=120)
        assert len(result['bonus_events']) == 2
        assert result['final_resources'].get('fragment_s', 0) == 10
        assert [ev['draw_index'] for ev in result['bonus_events']] == [49, 99]


class TestScenarioFirstPayback:
    """场景 3——火影首付返利（repeat=false，cards+resources 同时交付）。"""

    def test_scenario3(self):
        store = _make_store(
            [MilestoneDef(name='naruto_first_payback_s', threshold=100, repeat=False,
                          bonus_reward={'cards': ['limited_ssr_1'], 'resources': {'coin': 500}})],
            card_extra=[CardDefEntry(card_id='limited_ssr_1', name='limited_ssr_1',
                                     rarity='SSR', pools=[])])
        result = _run(store, count=150)
        assert len(result['bonus_events']) == 1
        # 赠卡不在池 distribution——150 抽自然抽到 ≥1 张会破坏 `== 1` 断言（ISSUE-107）
        assert result['card_counts'].get('limited_ssr_1', 0) == 1
        assert result['final_resources'].get('coin', 0) == 500


class TestScenarioRandomSsr:
    """场景 4——阴阳师 40 抽随机 SSR（固定 seed 可复现，候选不在池 distribution）。"""

    SSR_CANDIDATES = ['ssr_ibaraki', 'ssr_shuten', 'ssr_oomoji', 'ssr_kaguya']

    def _store(self):
        return _make_store(
            [MilestoneDef(name='onmyoji_40_gift', threshold=40, repeat=False,
                          bonus_reward={'random_cards': [{
                              'candidates': self.SSR_CANDIDATES,
                              'weights': [1.0, 1.0, 1.0, 1.0], 'count': 1}]})],
            card_extra=[CardDefEntry(card_id=c, name=c, rarity='SSR', pools=[])
                        for c in self.SSR_CANDIDATES])

    def test_scenario4(self):
        result = _run(self._store(), count=80, seed=9)
        assert len(result['bonus_events']) == 1
        gift = result['bonus_events'][0]['card_ids']
        assert len(gift) == 1
        assert gift[0] in self.SSR_CANDIDATES
        # 候选不在池 distribution——80 抽自然抽到任一张会破坏 sum == 1 断言（ISSUE-307）
        assert sum(result['card_counts'].get(c, 0) for c in self.SSR_CANDIDATES) == 1

    def test_reproducible_same_seed(self):
        assert _run(self._store(), count=80, seed=9)['bonus_events'][0]['card_ids'] == \
            _run(self._store(), count=80, seed=9)['bonus_events'][0]['card_ids']


class TestScenarioArknight:
    """场景 5——明日方舟 300 抽当期限定（cards+resources 同时交付）。"""

    def test_scenario5(self):
        store = _make_store(
            [MilestoneDef(name='ak_300_gift', threshold=300, repeat=False,
                          bonus_reward={'cards': ['limited_operator'],
                                        'resources': {'exchange_currency': 300}})],
            card_extra=[CardDefEntry(card_id='limited_operator', name='limited_operator',
                                     rarity='SSR', pools=[])])
        result = _run(store, count=300)
        assert len(result['bonus_events']) == 1
        # 赠卡不在池 distribution——仅作赠卡（ISSUE-107）
        assert result['card_counts'].get('limited_operator', 0) == 1
        assert result['final_resources'].get('exchange_currency', 0) >= 300
        assert result['total_gained'].get('exchange_currency', 0) >= 300


class TestScenarioEndfield:
    """场景 6/7——终末地 30 抽取送十连 + 60 抽寻访档案。"""

    def test_scenario6_7(self):
        store = _make_store([
            MilestoneDef(name='endfield_30', threshold=30, repeat=False,
                         bonus_reward={'resources': {'endfield_next_voucher': 1}}),
            MilestoneDef(name='endfield_archive', threshold=60, repeat=False,
                         bonus_reward={'resources': {'endfield_next_voucher': 10}}),
        ])
        result = _run(store, count=60)
        assert len(result['bonus_events']) == 2
        assert result['final_resources'].get('endfield_next_voucher', 0) == 11


class TestScenarioSimultaneous:
    """S1——同抽多触发：第 50 抽同时触发 threshold=10 与 threshold=50。"""

    def test_s1_order_by_toml_definition(self):
        store = _make_store([
            MilestoneDef(name='naruto_fragment', threshold=10, repeat=True,
                         bonus_reward={'resources': {'fragment_s': 1}}),
            MilestoneDef(name='naruto_s_fragment', threshold=50, repeat=True,
                         bonus_reward={'resources': {'fragment_s': 5}}),
        ])
        result = _run(store, count=50)
        # bonus_events 顺序 = TOML [[milestone]] 定义顺序（dict 插入顺序）
        assert [ev['milestone_name'] for ev in result['bonus_events']] == \
            ['naruto_fragment'] * 5 + ['naruto_s_fragment']
        assert result['final_resources'].get('fragment_s', 0) == 10


class TestEmptyDraw:
    """空抽（_NO_CARD_ID）计数推进——交换池 reward 全 _no_card。"""

    def test_empty_draw_counts(self):
        store = _make_store(
            [MilestoneDef(name='m1', threshold=5, repeat=True,
                          bonus_reward={'resources': {'frag': 1}})],
            reward_overrides=[_reward('_no_card', 100.0, 'R')])
        result = _run(store, count=12)
        assert result['total_draws'] == 12
        assert len(result['bonus_events']) == 2
        assert result['final_resources'].get('frag', 0) == 2


class TestMilestoneOverflow:
    """里程碑卡溢出——满突后赠送触发 match_overflow_bands，溢出资源入账。"""

    def test_overflow_resources(self):
        store = _make_store(
            [MilestoneDef(name='m1', threshold=3, repeat=True,
                          bonus_reward={'cards': ['limited_ssr_1']})],
            card_extra=[CardDefEntry(card_id='limited_ssr_1', name='limited_ssr_1',
                                     rarity='SSR', pools=[])])
        store.card_overflow_map = {
            'limited_ssr_1': [OverflowBand(min=1, max=None, resources={'stardust': 10})],
        }
        result = _run(store, count=7)
        assert len(result['bonus_events']) == 2
        # 每次赠送即溢出 10 星辉（min=1 满突即溢）
        assert result['final_resources'].get('stardust', 0) == 20
        assert all(ev['resources'].get('stardust', 0) == 10
                   for ev in result['bonus_events'])
        # 方案 C：溢出资源归因到触发抽 draw_resources_gained[draw_index]
        assert result['draw_resources_gained'][2].get('stardust', 0) == 10


class TestStreamingPaths:
    """流式六路径（方案 B）——kept_sequences 含赠卡行 + extract_aggregate 含 bonus_events。"""

    def test_streaming_six_paths(self):
        store = _make_store(
            [MilestoneDef(name='m1', threshold=4, repeat=True,
                          bonus_reward={'cards': ['limited_ssr_1']})],
            card_extra=[CardDefEntry(card_id='limited_ssr_1', name='limited_ssr_1',
                                     rarity='SSR', pools=[])])
        env = SimulationEnvBuilder.from_config_store(store)
        env.stop_condition = FixedActionCountCondition(max_actions=8)
        batch = run_batch_parallel(
            env=env, target_specs={}, initial_resources=env.initial_resources,
            num_simulations=1, max_workers=1, seed=42,
            strategy_key='fixed_count', strategy_params={'count': 8})
        result = batch.results[0]

        # extract_aggregate 输出含 bonus_events 键（ISSUE-315/316 数据通道）
        agg = extract_aggregate(result.to_dict())
        assert agg['bonus_events'] == result['bonus_events']

        # WorkerLocalExtractor.process：kept_sequences 含赠卡行、平行数组长度一致
        ext = WorkerLocalExtractor(
            pool_end_times=env.pool_end_times, target_ids=env.target_ids,
            ssr_ids=env.ssr_ids, target_specs={},
            initial_resources=env.initial_resources, n_heatmap_bins=50, max_keep=200)
        pkt = ext.process(result.to_dict())
        kept = pkt['kept']
        assert 'limited_ssr_1' in kept['draw_card_ids']
        assert len(kept['draw_card_ids']) == len(kept['draw_times']) == \
            len(kept['draw_resources_gained']) == len(kept['draw_pool_ids']) == \
            len(kept['draw_pity']) == len(kept['draw_resources_consumed'])
        # 赠卡行不计入 cum_draws 分母（ISSUE-306）——8 抽 2 赠卡 → cumulative_draws == 8
        assert pkt['cumulative_snapshots']
        assert pkt['cumulative_snapshots'][-1]['cumulative_draws'] == 8
        # 赠卡贡献入累积快照卡计数
        assert pkt['cumulative_snapshots'][-1]['cumulative_card_counts']['limited_ssr_1'] == 2
        assert len(pkt['heatmap_ach_bins']) == len(kept['draw_card_ids'])
        assert len(pkt['transition_flags']) == len(pkt['cumulative_snapshots'])


class TestPlanABExclusivity:
    """方案 A/B 互斥——on_bonus 源头合并后 card_counts 不双重计入。"""

    def test_no_double_count(self):
        store = _make_store(
            [MilestoneDef(name='m1', threshold=5, repeat=True,
                          bonus_reward={'cards': ['limited_ssr_1']})],
            card_extra=[CardDefEntry(card_id='limited_ssr_1', name='limited_ssr_1',
                                     rarity='SSR', pools=[])])
        result = _run(store, count=12)
        occ = sum(1 for ev in result['bonus_events']
                  for cid in ev['card_ids'] if cid == 'limited_ssr_1')
        assert result['card_counts'].get('limited_ssr_1', 0) == occ


class TestSingleProcessFallback:
    """run_batch_parallel 单进程兜底（max_workers=1）——不崩溃、bonus_events 正确。"""

    def test_max_workers_1(self):
        store = _make_store(
            [MilestoneDef(name='m1', threshold=10, repeat=True,
                          bonus_reward={'resources': {'frag': 1}})],
            reward_overrides=[_reward('_no_card', 100.0, 'R')])
        results = _run(store, count=25, num=3, max_workers=1)
        assert len(results) == 3
        for r in results:
            assert r['total_draws'] == 25
            assert len(r['bonus_events']) == 2
            assert r['final_resources'].get('frag', 0) == 2


class TestMaxTriggers:
    """max_triggers 生命周期——触发上限后 is_active=False。"""

    def test_max_triggers_engine_level(self):
        md = MilestoneDef(name='mt', threshold=3, repeat=True, max_triggers=2,
                          bonus_reward={'resources': {'frag': 1}})
        eng = MilestoneEngine([md], seed=42)
        hits = []
        for _ in range(12):
            hits.extend(eng.after_draw('', 'main'))
        assert len(hits) == 2
        assert eng.is_active('mt') is False


# ══════════════════════════════════════════════════════════════════
# C. 独立审查补齐用例（2026-08-05）
# ══════════════════════════════════════════════════════════════════

class TestBannerFiltering:
    """M9 验收——banner 限定里程碑仅目标 banner 内触发（独立审查补齐）。"""

    def test_banner_filtered_integration(self):
        b = BannerEntry(id='banner_a', name='A', enabled=True,
                        available_from=0.0, available_until=30 * DAY,
                        pools=[_pool()], lifecycle=[])
        b2 = BannerEntry(id='banner_b', name='B', enabled=True,
                         available_from=0.0, available_until=30 * DAY,
                         pools=[_pool()], lifecycle=[])
        store = ConfigStore()
        store.banner.banners = [b, b2]
        seen = set()
        card_defs = []
        for banner in store.banner.banners:
            for p in banner.pools:
                full = f"{banner.id}.{p.id}"
                for r in p.rewards:
                    cid = r['card_id']
                    if cid in seen:
                        continue
                    seen.add(cid)
                    card_defs.append(CardDefEntry(
                        card_id=cid, name=cid, rarity=r.get('rarity', 'R'), pools=[full]))
        store.card_defs = card_defs
        store.initial_resources = {'draw_resource': 1000000}
        store.strategy_key = 'smart'
        # banner 限定里程碑：仅 banner_a 内每 5 抽触发
        store.milestone = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='only_a', threshold=5, repeat=True, max_triggers=0,
                         banner='banner_a', bonus_reward={'resources': {'fragment_x': 1}}),
        ])
        env = SimulationEnvBuilder.from_config_store(store)
        assert env.milestone_defs, 'milestone_defs 应被提取'
        assert env.milestone_engine is None, 'milestone_engine 应保持 None 兜底（P61 落点 #1）'
        env.stop_condition = FixedActionCountCondition(max_actions=40)
        batch = run_batch_parallel(
            env=env, target_specs={}, initial_resources=env.initial_resources,
            num_simulations=1, max_workers=1, seed=42,
            strategy_key='fixed_count', strategy_params={'count': 40},
        )
        res = batch.results[0]
        bonus = res['bonus_events']
        # 固定 40 抽轮换两 banner → 至少触发若干次；全部 pool_id 必须以 banner_a 开头
        assert len(bonus) >= 1, f'应触发里程碑，实际 {len(bonus)}'
        for ev in bonus:
            assert ev['pool_id'].startswith('banner_a'), f'banner 过滤失效: {ev}'

    def test_banner_empty_matches_all(self):
        md = MilestoneDef(name='all', threshold=2, repeat=True,
                          bonus_reward={'resources': {'frag': 1}})
        eng = MilestoneEngine([md], seed=42)
        hits = eng.after_draw('any_banner', 'p1')
        hits += eng.after_draw('any_banner', 'p1')
        assert len(hits) == 1  # banner='' 匹配全部


class TestShippedConfigLoads:
    """M8 验收（ISSUE-002）——shipped config.toml 含 [[milestone]] 示例段可加载。"""

    def test_shipped_config_loads_with_milestone(self):
        from gacha_simulator.core.config_toml import load_toml
        store = load_toml('gacha_simulator/config/config.toml')
        assert store.milestone.milestones, 'config.toml 应含 [[milestone]] 示例段'
        # 示例段空 banner = 全部（P78 示例已从默认配置移除，保持基线行为不变）
        for m in store.milestone.milestones:
            assert m.banner == '', f"示例里程碑 banner 异常: {m.name} → {m.banner}"
        # round-trip：加载 → 保存 → 再加载
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False, mode='w') as f:
            p = f.name
        try:
            save_toml(store, p)
            store2 = load_toml(p)
            assert len(store2.milestone.milestones) == len(store.milestone.milestones)
        finally:
            os.unlink(p)


class TestClearedNameRoundtrip:
    """M8 验收（ISSUE-314）——清空名称后保存→加载成功（无重复 ConfigError）。

    注：名称清空回退（_flush_milestone_current_detail 查重）是 UI 层逻辑（pytest-qt 覆盖），
    本用例验证 TOML 层——两个合法不同名 milestone round-trip 不产生重复名。
    """

    def test_distinct_names_roundtrip(self):
        store = ConfigStore()
        store.card_defs = [CardDefEntry(card_id='a', name='A', rarity='r')]
        store.resource_defs = {'coin': '金币'}
        store.milestone = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='milestone_1', threshold=10, bonus_reward={'resources': {'coin': 1}}),
            MilestoneDef(name='milestone_2', threshold=20, bonus_reward={'resources': {'coin': 2}}),
        ])
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False, mode='w') as f:
            p = f.name
        try:
            save_toml(store, p)
            store2 = load_toml(p)
            names = [m.name for m in store2.milestone.milestones]
            assert names == ['milestone_1', 'milestone_2']
            assert len(names) == len(set(names))  # 无重复名
        finally:
            os.unlink(p)


class TestStrategyContextQueries:
    """验收项——StrategyContext 里程碑查询 + 安全默认值 + 只读。"""

    def test_queries_via_engine(self):
        from gacha_simulator.core.strategy import StrategyContext
        from gacha_simulator.core.state import GachaState
        md = MilestoneDef(name='q1', threshold=5, repeat=False,
                          bonus_reward={'resources': {'x': 1}})
        eng = MilestoneEngine([md], seed=42)
        ctx = StrategyContext(
            state=GachaState(), current_pools=[], all_pools=[], future_schedules=[],
            target_cards=object(), stop_condition=object(),
            _milestone_engine=eng,
        )
        assert ctx.get_milestone_counter('q1') == 0
        assert ctx.is_milestone_active('q1') is True
        defs = ctx.get_milestone_defs()
        assert defs['q1'].threshold == 5
        eng.after_draw('', 'p1')  # 第 1 抽
        assert ctx.get_milestone_counter('q1') == 1

    def test_safe_defaults_when_none(self):
        from gacha_simulator.core.strategy import StrategyContext
        from gacha_simulator.core.state import GachaState
        ctx = StrategyContext(
            state=GachaState(), current_pools=[], all_pools=[], future_schedules=[],
            target_cards=object(), stop_condition=object(),
        )
        assert ctx.get_milestone_counter('q1') == 0
        assert ctx.is_milestone_active('q1') is False
        assert ctx.get_milestone_defs() == {}


class TestConfigStoreIntegration:
    """验收项——ConfigStore.clear() 重置 + get_config 含 milestone 键。"""

    def test_clear_resets_milestone(self):
        store = ConfigStore()
        store.milestone = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='m', threshold=1)])
        store.clear()
        assert store.milestone == MilestoneConfig()
        assert store.milestone.milestones == []

    def test_get_config_has_milestone_key(self):
        # get_config 是 GUI ConfigPanel 方法；此处验证 config 字典结构契约——
        # 通过 save_toml/load_toml round-trip 保证 'milestone' 段键存在
        store = ConfigStore()
        store.card_defs = [CardDefEntry(card_id='a', name='A', rarity='r')]
        store.milestone = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='m1', threshold=10, bonus_reward={'resources': {}}),
        ])
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False, mode='w') as f:
            p = f.name
        try:
            save_toml(store, p)
            with open(p, 'rb') as fh:
                data = __import__('tomllib').load(fh)
            assert 'milestone' in data
            assert data['milestone'][0]['name'] == 'm1'
        finally:
            os.unlink(p)


class TestTransitionDrawOnly:
    """独立审查缺陷 1 回归——转变标记 draw-only 口径（键空间修正）。"""

    def _run_extractor(self, compact, target_specs):
        from gacha_simulator.core.streaming import WorkerLocalExtractor
        ex = WorkerLocalExtractor(
            pool_end_times={'b1': 30 * DAY}, target_ids={'target_x'},
            target_specs=target_specs, initial_resources={'draw_resource': 1000000},
        )
        return ex.process(compact)

    def test_transition_flag_draw_only_with_gift_target(self):
        # 目标卡仅作为赠卡（不在池 distribution）：8 抽 2 赠卡后 transition_flags 应为 False（draw-only）
        compact = {
            'draw_card_ids': ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8'],
            'draw_pool_ids': ['b1.main'] * 8,
            'draw_times': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            'draw_pity': [False] * 8,
            'draw_resources_consumed': [{'draw_resource': 160}] * 8,
            'draw_resources_gained': [{}] * 8,
            'draw_pity_names': [None] * 8,
            'draw_pity_counter_max': [0] * 8,
            'pool_card_counts': {'b1.main': {'r1': 8, 'target_x': 2}},
            'card_counts': {'r1': 8, 'target_x': 2},
            'banner_end_resources': {'b1': {'draw_resource': 1000000}},
            'bonus_events': [
                {'pool_id': 'b1.main', 'draw_index': 3, 'card_ids': ['target_x'],
                 'resources': {}},
                {'pool_id': 'b1.main', 'draw_index': 7, 'card_ids': ['target_x'],
                 'resources': {}},
            ],
        }
        result = self._run_extractor(compact, {'target_x': 1})
        # 赠卡累加后 cum_cards 含 target_x=2，但 draw-only 口径应减掉赠卡 → 池未自然抽到 → False
        assert result['transition_flags'] == [False], result['transition_flags']
        # kept_sequences 应含赠卡行
        kept = result['kept']
        assert kept is not None
        assert kept['draw_card_ids'].count('target_x') == 2
        assert len(kept['draw_card_ids']) == len(kept['draw_pool_ids']) == len(kept['draw_times']) \
            == len(kept['draw_pity']) == len(kept['draw_resources_consumed']) == len(kept['draw_resources_gained'])
        # cumulative_draws 不计赠卡（ISSUE-306）：8 抽 + 2 赠卡 → cumulative_draws=8
        snaps = result['cumulative_snapshots']
        assert snaps and snaps[0]['cumulative_draws'] == 8
        # cumulative_card_counts 含赠卡贡献
        assert snaps[0]['cumulative_card_counts']['target_x'] == 2


# ══════════════════════════════════════════════════════════════════
# D. 独立核查缺口补齐（2026-08-05 第 2 轮）
# ══════════════════════════════════════════════════════════════════

class TestTransitionFlagsFromGdrDrawOnly:
    """ISSUE-312——compute_transition_flags_from_gdr 回退路径 draw-only 口径。"""

    def _snap(self, counts):
        return {'b1': [{'cumulative_card_counts': dict(counts), 'cumulative_draws': 5,
                        'cumulative_pity_draws': 0, 'cumulative_consumed': {},
                        'cumulative_gained': {}}]}

    def test_draw_only_subtracts_gift(self):
        from gacha_simulator.core.per_pool_analysis import compute_transition_flags_from_gdr
        snaps = self._snap({'r1': 5, 'target_x': 1})
        bonus = [[{'pool_id': 'b1.main', 'card_ids': ['target_x']}]]
        flags = compute_transition_flags_from_gdr(
            snaps, ['b1'], {'target_x': 1}, gdr_key='all_targets',
            threshold=1.0, scope='cumulative', bonus_events=bonus)
        assert flags == [[False]], f'draw-only 应判 False（赠卡不计），实际 {flags}'

    def test_none_bonus_falls_back_to_full(self):
        from gacha_simulator.core.per_pool_analysis import compute_transition_flags_from_gdr
        snaps = self._snap({'r1': 5, 'target_x': 1})
        flags = compute_transition_flags_from_gdr(
            snaps, ['b1'], {'target_x': 1}, gdr_key='all_targets',
            threshold=1.0, scope='cumulative', bonus_events=None)
        assert flags == [[True]], f'None 保守回退应含赠卡判 True，实际 {flags}'

    def test_multi_gift_events(self):
        from gacha_simulator.core.per_pool_analysis import compute_transition_flags_from_gdr
        snaps = self._snap({'r1': 5, 'target_x': 2})
        bonus = [[{'pool_id': 'b1.main', 'card_ids': ['target_x']},
                  {'pool_id': 'b1.main', 'card_ids': ['target_x']}]]
        flags = compute_transition_flags_from_gdr(
            snaps, ['b1'], {'target_x': 1}, gdr_key='all_targets',
            threshold=1.0, scope='cumulative', bonus_events=bonus)
        assert flags == [[False]], f'多赠卡事件应全减，实际 {flags}'


class TestRetreatConfigMilestonePassthrough:
    """ISSUE-005/306——RetreatConfigBuilder.build 透传 milestone + 溢出数据。"""

    def test_passthrough_milestone_and_overflow(self):
        from gacha_simulator.core.retreat_config import RetreatConfigBuilder
        store = ConfigStore()
        store.banner.banners = [
            BannerEntry(id='b1', name='B1', enabled=True, available_from=0.0,
                        available_until=30 * DAY,
                        pools=[BannerPoolEntry(id='main', cost='draw_resource:160', batch_size=1,
                                               rewards=[_reward('ssr_a', 1.0, 'SSR'),
                                                        _reward('r_b', 99.0)])],
                        lifecycle=[]),
        ]
        store.card_defs = [CardDefEntry(
            card_id='ssr_a', name='a', rarity='ssr', pools=['b1.main'],
            overflow_bands=[OverflowBand(1, None, {'star': 5})])]
        store.milestone = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='m1', threshold=10, bonus_reward={'resources': {'coin': 5}}),
        ])
        store.card_overflow_map = {'ssr_a': [OverflowBand(1, None, {'star': 5})]}
        store.rarity_defaults = {'ssr': {'overflow_bands': []}}
        truncated = RetreatConfigBuilder.build(store, 'b1', {'draw_resource': 1000}, {})
        assert truncated.milestone.milestones[0].name == 'm1'
        assert truncated.milestone.enabled is True
        assert truncated.card_overflow_map.get('ssr_a')
        assert truncated.rarity_defaults == {'ssr': {'overflow_bands': []}}
        assert truncated.card_defs[0].overflow_bands is not None


class TestConfigHashIncludesMilestone:
    """ISSUE-008——compute_config_hash 纳入 milestone（可比性指纹）。"""

    def test_milestone_changes_hash(self):
        from gacha_simulator.core.result_store import compute_config_hash
        store = ConfigStore()
        store.banner.banners = [
            BannerEntry(id='b1', name='B1', enabled=True, available_from=0.0,
                        available_until=30 * DAY, pools=[], lifecycle=[]),
        ]
        m1 = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='m1', threshold=10, bonus_reward={'resources': {'coin': 5}}),
        ])
        m2 = MilestoneConfig(enabled=True, milestones=[
            MilestoneDef(name='m2', threshold=99, bonus_reward={'resources': {'coin': 99}}),
        ])
        h_none = compute_config_hash(store.banner.banners, None, [])
        h_m1 = compute_config_hash(store.banner.banners, None, [], milestone_config=m1)
        h_m2 = compute_config_hash(store.banner.banners, None, [], milestone_config=m2)
        assert h_none != h_m1, '无 milestone 与含 milestone 应不同 hash'
        assert h_m1 != h_m2, 'milestone 内容不同应不同 hash'
