"""P56 集成测试——多 behavior 协同 + depends_on 激活传播 + card_to_slot。

覆盖目标：
  1. _resolve_selected_slots O(1) card_to_slot 路径
  2. depends_on：被依赖方 did_fire → 依赖方 _active 从 False → True
  3. 多保底协同：rotating + hard 同时作用于一个池子
"""

import pytest
from gacha_simulator.core.pity import (
    PityState, PityEngine, DrawInfo, PityContext,
    TargetedBehavior, RotatingBehavior, HardPityBehavior,
    compute_scope_mappings,
    PoolPitySpec,
)
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pool import Pool, Reward


# ══════════════════════════════════════════════════════════════════
# _resolve_selected_slots O(1) 路径
# ══════════════════════════════════════════════════════════════════

class TestResolveSelectedSlots:
    """TargetedBehavior._resolve_selected_slots 的 card_to_slot 主路径。"""

    def test_o1_lookup_via_card_to_slot(self):
        """selected 在 card_to_slot 中 → O(1) 返回对应槽位。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        state.set('tgt', 'selected_card', 'f1')

        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1', 'f2')},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured', 's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)

        result = bh._resolve_selected_slots('f1', ('ssr_featured',), ctx)
        assert result == ('ssr_featured',)

    def test_fallback_when_not_in_card_to_slot(self):
        """selected 不在 card_to_slot → 降级遍历 featured_slots → scope_cards。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)

        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1',)},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={},  # 空——走降级路径
            base_probabilities={},
            rarity_rank={'ssr': 3},
        )
        ctx = PityContext(draw=draw, current={}, state=state)

        result = bh._resolve_selected_slots('f1', ('ssr_featured',), ctx)
        assert result == ('ssr_featured',)

    def test_selected_none_returns_all_featured(self):
        """selected=None → 返回全部 featured_slots。"""
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={}, featured_cards={}, scope_slots={},
            featured_slots={'ssr': ('ssr_featured', 'ssr_featured2')},
            card_to_slot={}, base_probabilities={}, rarity_rank={},
        )
        ctx = PityContext(draw=draw, current={}, state=state)
        result = bh._resolve_selected_slots(None, ('ssr_featured', 'ssr_featured2'), ctx)
        assert result == ('ssr_featured', 'ssr_featured2')


# ══════════════════════════════════════════════════════════════════
# depends_on 激活传播
# ══════════════════════════════════════════════════════════════════

class TestDependsOnIntegration:
    """PityEngine + depends_on 端到端——did_fire 激活依赖方。"""

    def test_dependent_activated_after_source_fires(self):
        """被依赖方 did_fire → 依赖方 _active 变为 True。"""
        state = PityState()

        pool = Pool(
            id='test_pool', name='测试池',
            cost={'gem': 1},
            rewards=[
                (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.005),
                (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.005),
            ],
        )

        scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = \
            compute_scope_mappings(pool)

        source_def = PityDef(name='source', btype='rotating', scope='ssr')
        dep_def = PityDef(name='dependent', btype='hard', scope='ssr',
                           threshold=100, depends_on='source')

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            scope_slots=scope_slots, featured_slots=featured_slots,
            pity_names=('source', 'dependent'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
            card_to_slot=card_to_slot,
        )

        engine = PityEngine(
            pool_specs={'test_pool': pool_spec},
            pity_defs=[source_def, dep_def],
            state=state,
            rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
        )

        # 依赖方初始 inactive（depends_on → _active 未 set → Flag 默认 False）
        assert state.get('dependent', '_active', False) is False

        # 模拟抽中 featured SSR —— source.did_fire → True
        engine.before_draw('test_pool', state, {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        engine.after_draw('test_pool', state, 'f1')

        # 依赖方被激活
        assert state.get('dependent', '_active', False) is True


# ══════════════════════════════════════════════════════════════════
# 多保底协同
# ══════════════════════════════════════════════════════════════════

class TestMultiPityCoordination:
    """rotating + hard 同时作用——概率叠加 + 状态独立。"""

    def test_rotating_and_hard_on_same_pool(self):
        """rotating 和 hard 概率叠加：先 rotating 调整比例，再 hard 100% featured。"""
        state = PityState()

        pool = Pool(
            id='test_pool', name='测试池',
            cost={'gem': 1},
            rewards=[
                (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.005),
                (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.005),
            ],
        )

        scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = \
            compute_scope_mappings(pool)

        rot_def = PityDef(name='rot', btype='rotating', scope='ssr')
        hard_def = PityDef(name='hard90', btype='hard', scope='ssr', threshold=90)

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            scope_slots=scope_slots, featured_slots=featured_slots,
            pity_names=('rot', 'hard90'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
            card_to_slot=card_to_slot,
        )

        engine = PityEngine(
            pool_specs={'test_pool': pool_spec},
            pity_defs=[rot_def, hard_def],
            state=state,
            rarity_rank={'ssr': 3, 'sr': 2, 'r': 1},
        )

        # 初始——小保底，未到硬保底阈值
        probs = engine.before_draw('test_pool', state,
                                    {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        # rotating 小保底维持基础比例
        assert probs['ssr_featured'] == pytest.approx(0.005)
        assert probs['ssr_standard'] == pytest.approx(0.005)

        # 设 counter 到 90——hard 保底触发 + rotating 大保底
        state.set('hard90', 'counter', 89)
        state.set('rot', 'guaranteed', True)
        probs2 = engine.before_draw('test_pool', state,
                                     {'ssr_featured': 0.005, 'ssr_standard': 0.005})
        # 两条保底叠加后 standard 槽位归零（全部导向 featured）
        assert probs2['ssr_standard'] == pytest.approx(0.0)
        assert probs2['ssr_featured'] >= 0.005  # featured 至少保持基础概率


# ══════════════════════════════════════════════════════════════════
# M4：did_fire 统一语义（2026-09-16）
# ══════════════════════════════════════════════════════════════════

def _mk_draw(reward_id, rarity, is_featured):
    """构造一次抽卡的 DrawInfo——ssr 与 sr 两个稀有度都有 featured 卡。"""
    return DrawInfo(
        pool_id='p1', pool_instance_id='p1_0',
        reward_id=reward_id, reward_rarity=rarity, is_featured=is_featured,
        scope_cards={'ssr': ('f1',), 'sr': ('sf1',)},
        featured_cards={'ssr': ('f1',), 'sr': ('sf1',)},
        scope_slots={'ssr': ('ssr_featured',), 'sr': ('sr_featured',)},
        featured_slots={'ssr': ('ssr_featured',), 'sr': ('sr_featured',)},
        card_to_slot={'f1': 'ssr_featured', 'sf1': 'sr_featured'},
        base_probabilities={},
        rarity_rank={'ssr': 0, 'sr': 1},
    )


class TestDidFireUnified:
    """did_fire ≡ 本次抽卡是否让本保底回到初始状态。

    统一前 rotating / targeted 只判 judge、不含 scope 门控，会在「出非 scope 稀有度的
    UP」时为真而状态并未翻转，`depends_on` 依赖方被提前激活。
    """

    def test_rotating_requires_scope(self):
        state = PityState()
        bh = RotatingBehavior('rot', state, scope='ssr')

        out_of_scope = PityContext(draw=_mk_draw('sf1', 'sr', True),
                                   current={}, state=state)
        assert bh._is_hit(out_of_scope) is True      # judge 命中（is_featured）
        assert bh.did_fire(out_of_scope) is False    # 但 scope 门控挡住

        in_scope = PityContext(draw=_mk_draw('f1', 'ssr', True),
                               current={}, state=state)
        assert bh.did_fire(in_scope) is True

    def test_rotating_matches_after_draw_reset(self):
        """did_fire 与 after_draw 的重置分支严格同条件。"""
        state = PityState()
        bh = RotatingBehavior('rot', state, scope='ssr')
        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state)
        bh.after_draw(ctx)
        assert state.get('rot', 'guaranteed', False) is False   # 状态未翻转
        assert bh.did_fire(ctx) is False                        # did_fire 亦为假

    def test_targeted_requires_scope(self):
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        state.set('tgt', 'selected_card', 'sf1')     # 定轨卡指向非 scope 稀有度

        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state)
        assert bh._is_hit(ctx) is True               # judge 命中
        assert bh.did_fire(ctx) is False             # 但 scope 门控挡住

    def test_targeted_in_scope_fires(self):
        state = PityState()
        bh = TargetedBehavior('tgt', state, scope='ssr', fate_threshold=1)
        state.set('tgt', 'selected_card', 'f1')
        ctx = PityContext(draw=_mk_draw('f1', 'ssr', True), current={}, state=state)
        assert bh.did_fire(ctx) is True

    def test_counter_family_unchanged(self):
        """counter 驱动型仍为 _should_reset——出 scope 即真，不看 featured。"""
        state = PityState()
        bh = HardPityBehavior('h', state, scope='ssr', threshold=90)

        not_featured = PityContext(draw=_mk_draw('s1', 'ssr', False),
                                   current={}, state=state)
        assert bh.did_fire(not_featured) is True

        other_rarity = PityContext(draw=_mk_draw('sf1', 'sr', True),
                                   current={}, state=state)
        assert bh.did_fire(other_rarity) is False


# ════════════════════════════════════════════════════════
# 两份「卡 id → 稀有度」实现的一致性（缺陷 12 的守卫）
# ════════════════════════════════════════════════════════

class TestRarityInferenceConsistency:
    """A 与 B 必须对同一 spec 给出同一答案。

    - **A** = `pool.infer_rarity_from_spec`——喂**概率**路径（`scale_factors` 还原段、
      `aggregate_probs_by_rarity`）
    - **B** = `PityEngine._infer_rarity`——喂**状态**路径（`DrawInfo.reward_rarity`
      → `_should_reset` / `_is_trigger_rarity` / `did_fire`）

    两者是同一条规则的两处实现，**已经漂移过一次**：缺陷 12 只存在于 A（SR / R 返回
    `None`），B 从来没有（它一直遍历 `scope_cards`）。分歧的后果是「同一张卡在概率里
    是 SR、在状态里是 SSR」，不报错、不崩溃。本测试把这种静默漂移变成响亮失败。

    `None`（A 的「不属于任何槽位」）与 `''`（B 的「无稀有度」）是两种哨兵，语义等价，
    比较时归一。
    """

    @staticmethod
    def _both(cid, spec, engine):
        from gacha_simulator.core.pool import infer_rarity_from_spec
        return ((infer_rarity_from_spec(cid, spec) or None),
                (engine._infer_rarity(cid, spec) or None))

    def test_agree_on_multi_rarity_spec(self):
        """不依赖真配置的最小构造：三种稀有度各给一张卡。"""
        spec = PoolPitySpec(
            pity_names=['p'],
            scope_cards={'ssr': ('ssr_a',), 'sr': ('sr_a',), 'r': ('r_a',)},
            featured_cards={'ssr': ('ssr_a',)},
            ssr_ids={'ssr_a'},
            featured_ids={'ssr_a'},
        )
        engine = PityEngine({'k': spec}, [])
        for cid in ('ssr_a', 'sr_a', 'r_a', 'not_in_spec'):
            a, b = self._both(cid, spec, engine)
            assert a == b, f'{cid}: A={a!r} B={b!r}（两份实现分歧）'

    def test_agree_on_real_config_and_invariants_hold(self):
        """真实配置全量扫一遍，并断言两条支撑「必然一致」的不变量。

        不变量成立时 A 与 B 必然给出同一答案，故同时断言它们——任一条破掉，
        本测试即红（这是比「逐卡比对」更早的预警）。
        """
        from pathlib import Path
        from gacha_simulator.core.config_toml import load_toml
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

        cfg = Path(__file__).resolve().parents[2] / 'gacha_simulator' / 'config' / 'config.toml'
        env = SimulationEnvBuilder.from_config_store(load_toml(str(cfg)))

        checked = 0
        for banner in env.pools:
            for pid, pool in banner.pools.items():
                spec = env.pity_engine.get_spec(f'{banner.id}.{pid}')
                if spec is None:
                    continue
                # 不变量①：ssr_ids ⊆ scope_cards['ssr']（需要的是「查得到」，不是「相等」
                #   ——`batch_simulator` 建 ssr_ids 时排除 `_no_card`，等号会在合法配置上误红）
                sc_ssr = {c.lower() for c in spec.scope_cards.get('ssr', ())}
                assert {c.lower() for c in spec.ssr_ids} <= sc_ssr, \
                    f'{banner.id}.{pid}: ssr_ids 未被 scope_cards["ssr"] 覆盖'
                # 不变量②：featured_ids ⊆ scope_cards
                all_sc = {c.lower() for cs in spec.scope_cards.values() for c in cs}
                assert {c.lower() for c in spec.featured_ids} <= all_sc, \
                    f'{banner.id}.{pid}: featured_ids 不在 scope_cards 内'

                for rwd, _ in pool.rewards:
                    a, b = self._both(rwd.id, spec, env.pity_engine)
                    assert a == b, f'{rwd.id} @ {banner.id}.{pid}: A={a!r} B={b!r}'
                    # A 的答案还必须与该卡在池里的真实稀有度一致
                    real = (rwd.extra_info.get('rarity') or '').lower() or None
                    assert a == real, f'{rwd.id} @ {banner.id}.{pid}: A={a!r} 真实={real!r}'
                    checked += 1
        assert checked > 0, '未扫到任何卡——本测试无验收面'
# ══════════════════════════════════════════════════════════════════
# G16（P64 独立先行）：reset="never"：hard 出金不重置 counter
# ══════════════════════════════════════════════════════════════════

class TestNeverResetHardPity:
    """幻塔「提前出金不重置 80 抽保底」（G16，手册 §5.3 / 计划 §3.8）。

    判据取 §六 G16 断言行：**hard 保底出金不重置 counter，每 N 抽白送保底金；
    `reset="featured"` / 默认行为不受影响**。实现面是 `_should_reset` 的 `never`
    分支（恒 False），故出金不再把 counter 打回 0，第 79 抽出金后第 80 抽照常
    触发保底（白送）。默认（`reset` 缺省 → 落回 scope）与 `featured` 的语义由
    本类的对照用例钉住，本块不得改动它们。
    """

    NAME = 'tof_hard'
    THRESHOLD = 80
    CUR = {'ssr_featured': 0.6, 'sr_featured': 0.4}

    @classmethod
    def _ctx(cls, state, rarity='r', featured=False):
        """一次抽卡的上下文：current 含两个槽位，便于断言「被强制为 100%」。"""
        return PityContext(
            draw=_mk_draw('f1' if featured else 's1', rarity, featured),
            current=dict(cls.CUR),
            state=state,
        )

    @classmethod
    def _draw(cls, bh, state, rarity='r', featured=False):
        """一次「取概率 → 结算」往返，返回 before_draw 的概率分布。"""
        ctx = cls._ctx(state, rarity=rarity, featured=featured)
        probs = bh.before_draw(ctx)
        bh.after_draw(ctx)
        return probs

    @classmethod
    def _counter(cls, state):
        return state.get(cls.NAME, 'counter', 0)

    def test_never_reset_gold_at_79_keeps_80th_guaranteed(self):
        """第 79 抽提前出金不清零 counter → 第 80 抽仍必出（白送保底金）。"""
        state = PityState()
        bh = HardPityBehavior(self.NAME, state, scope='ssr',
                              threshold=self.THRESHOLD, reset='never')

        for _ in range(self.THRESHOLD - 2):          # 抽 1..78：不出金
            assert self._draw(bh, state, rarity='r') == self.CUR
        assert self._counter(state) == self.THRESHOLD - 2

        # 第 79 抽：提前出金（SSR，且为 featured）；未达阈值，概率未被改动
        assert self._draw(bh, state, rarity='ssr', featured=True) == self.CUR
        assert self._counter(state) == self.THRESHOLD - 1, \
            'reset="never" 下出金不得清零 counter'

        # 第 80 抽：counter 未被出金清零 → 保底照常触发，scope 槽位强制 100%
        assert self._draw(bh, state, rarity='ssr') == {
            'ssr_featured': 1.0, 'sr_featured': 0.0}
        assert self._counter(state) == self.THRESHOLD

        # 本次出金（保底金）之后 counter 同样不归零
        assert self._counter(state) == self.THRESHOLD, \
            'reset="never" 下保底金出金不得清零 counter'

    def test_never_reset_default_and_featured_unaffected(self):
        """对照：默认（落回 scope）出金即清零、下一抽不再强制；`featured` 语义不变。"""
        # ── 默认：reset 缺省 → CounterBasedBehavior 落回 scope('ssr') ──
        s_scope = PityState()
        default = HardPityBehavior(self.NAME, s_scope, scope='ssr',
                                   threshold=self.THRESHOLD)
        for _ in range(self.THRESHOLD - 2):
            self._draw(default, s_scope, rarity='r')
        self._draw(default, s_scope, rarity='ssr', featured=True)   # 第 79 抽出金
        assert self._counter(s_scope) == 0, '默认语义：出 SSR 即清零'
        assert self._draw(default, s_scope, rarity='r') == self.CUR, \
            '默认语义：清零后第 80 抽不应再被强制'

        # ── featured：仅 featured 出金清零 ──
        s_feat = PityState()
        feat = HardPityBehavior(self.NAME, s_feat, scope='ssr',
                                threshold=self.THRESHOLD, reset='featured')
        for _ in range(self.THRESHOLD - 2):
            self._draw(feat, s_feat, rarity='r')
        self._draw(feat, s_feat, rarity='ssr', featured=False)      # 非 featured 出金
        assert self._counter(s_feat) == self.THRESHOLD - 1, \
            'featured 语义：非 featured 出金不清零'
        assert self._draw(feat, s_feat, rarity='r') == {
            'ssr_featured': 1.0, 'sr_featured': 0.0}

    def test_never_reset_reaches_behavior_via_create_behavior(self):
        """`reset='never'` 经 `create_behavior(PityDef(...))` 透传（配置 → 行为接线面）。"""
        from gacha_simulator.core.pity import create_behavior

        state = PityState()
        pdef = PityDef(name=self.NAME, btype='hard', scope='ssr',
                       threshold=self.THRESHOLD, reset='never')
        bh = create_behavior(pdef, state)
        assert isinstance(bh, HardPityBehavior)

        for _ in range(self.THRESHOLD - 2):
            self._draw(bh, state, rarity='r')
        self._draw(bh, state, rarity='ssr', featured=True)
        assert self._counter(state) == self.THRESHOLD - 1
        assert self._draw(bh, state, rarity='ssr') == {
            'ssr_featured': 1.0, 'sr_featured': 0.0}
