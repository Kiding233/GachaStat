"""P56 集成测试——多 behavior 协同 + depends_on 激活传播 + card_to_slot。

覆盖目标：
  1. 定轨目标集的定位（`card_to_slot` 投影主路径 + 落空回退）
  2. depends_on：被依赖方 did_fire → 依赖方 _active 从 False → True
  3. 多保底协同：rotating + hard 同时作用于一个池子

**P64 S7d 改造（旧类直构 → 新架构）**：本文件原直构三个旧行为类；改造后一律经
`create_behavior(PityDef(...), state)` 取统一骨架 `Pity`。旧类独有的私有方法
（`_resolve_selected_slots` / `_is_hit`）在新架构下**没有同名对应物**，其语义由
`SelectedModifier` 的 A 列解析与各 Tracker 内联的判据承载，断言面随之改为
「`before_draw` 的产出分布」与「`did_fire` / 状态键」两类可观测事实。
"""

import subprocess
import sys
from pathlib import Path

import pytest
from gacha_simulator.core.pity import (
    PityState, PityEngine, DrawInfo, PityContext,
    compute_scope_mappings,
    PoolPitySpec,
    # P64 S6b（G5）：排序键的直测面
    _BTYPE_ORDER, _resolve_order, create_behavior,
)
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pool import Pool, Reward

ROOT = Path(__file__).resolve().parents[2]
# 与 scripts/p82_baseline.py 的 BUILTIN_KEYS / PLUGIN_KEYS 同源（9 组）
P82_BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
P82_PLUGIN_KEYS = ['plugin/example_phased']


def _make_pity(state, btype, name, **pdef_kwargs):
    """经 `create_behavior` 构造骨架并补一次重绑（骨架不在构造期绑定零件）。"""
    pity = create_behavior(
        PityDef(name=name, btype=btype, scope='ssr', **pdef_kwargs), state)
    pity._rebind_state(state)
    return pity


# ══════════════════════════════════════════════════════════════════
# 定轨目标集的定位
# ══════════════════════════════════════════════════════════════════

class TestSelectedTargetResolution:
    """`SelectedModifier` 的 A 列解析：旧 `_resolve_selected_slots` 的替代断言面。

    旧类有一个私有方法 `_resolve_selected_slots(selected, featured_slots, ctx)`，
    按「`card_to_slot` 直查 → 按槽位名反查 featured 槽 → 遍历 `scope_cards`」三级
    回退定位定轨槽。新架构**不再复刻**该方法（见 `SelectedModifier` 的 docstring）：
    `card_to_slot` 是唯一投影通道（`_to_dist_keys`），A 列落空时回退**全部 featured 槽**
    （`selected_keys or featured`）。故本类断言的对象由「私有方法的返回值」改为
    「`before_draw` 产出分布的目标集落点」；目标集取错时 scope 总量会落在错误的槽位
    或整条保底恒等，两种形态都可判。

    `tau=0` 是「定轨后必出」形态（G19 尘白禁区不歪池），用于让 `sel is not None` 的
    分支可达；`selected_card=None` 的一档改由 `guaranteed` 分支触发（与旧实现的
    析取项同形）。
    """

    @staticmethod
    def _ctx(state, current=None):
        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1', 'f2')},
            scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
            featured_slots={'ssr': ('ssr_featured',)},
            card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured',
                          's1': 'ssr_standard'},
            base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
            rarity_rank={'ssr': 3},
        )
        return PityContext(
            draw=draw,
            current=dict(current or {'ssr_featured': 0.005, 'ssr_standard': 0.005}),
            state=state,
        )

    def test_selected_card_located_via_card_to_slot(self):
        """selected 在 card_to_slot 中 → A 列落在其投影槽位（scope 总量全给该槽）。"""
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=0)
        state.set('tgt', 'selected_card', 'f1')

        out = pity.before_draw(self._ctx(state))
        assert out['ssr_featured'] == pytest.approx(0.01)
        assert out['ssr_standard'] == pytest.approx(0.0)

    def test_unresolvable_selection_falls_back_to_all_featured(self):
        """selected 的投影不在 featured 投影内 → A 列回退全部 featured 槽。

        旧用例的触发条件是「selected 不在 `card_to_slot` 里」（走槽位名反查回退）；
        新架构以 `card_to_slot` 为唯一通道，该回退不复刻，**等价语义**由「A 列落空 →
        回退全部 featured」承担（`selected_keys or featured`）。本用例把触发条件
        换成「selected 投影与 featured 投影不相交」，效果同档（目标集 = 全部 featured），
        且断言可判：A 若真的为空，`SelectedModifier` 直接返 `None`、分布保持原值。
        """
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=0)
        state.set('tgt', 'selected_card', 's1')   # 非 featured 卡

        out = pity.before_draw(self._ctx(state))
        assert out['ssr_featured'] == pytest.approx(0.01)
        assert out['ssr_standard'] == pytest.approx(0.0)

    def test_selected_none_returns_all_featured(self):
        """selected=None → A 列 = 全部 featured 槽（经 `guaranteed` 分支触发）。"""
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'guaranteed', True)      # selected_card 保持未设置

        out = pity.before_draw(self._ctx(state))
        assert out['ssr_featured'] == pytest.approx(0.01)
        assert out['ssr_standard'] == pytest.approx(0.0)


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

        # P82-2 观察点（P64 §1.5）：本类的 `pity_names` 书写顺序是
        # ('source', 'dependent')，接线后池内**执行**顺序按排序键反转为
        # (dependent, source)——同 scope 下 type 序决定先后（source 是 rotating、
        # dependent 是 hard）。上面的激活断言在两种顺序下都成立（实测反转后仍为
        # True），故此处单独钉住反转事实，把「接线被静默回退」与「接线生效但本类
        # 无差异」区分开。`pity_names` 本身保持 TOML 顺序不动。
        assert [n for n, _ in engine.get_behaviors_for_pool('test_pool')] == [
            'dependent', 'source']
        assert tuple(engine.pool_specs['test_pool'].pity_names) == ('source', 'dependent')


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

        # P82-2 观察点（P64 §1.5）：书写顺序 ('rot', 'hard90') 接线后反转为
        # (hard90, rot)；上面的概率断言在两种顺序下都成立（本组合属 §1.5
        # 「其余组合数学可交换」一档），故反转事实须单独钉住。
        assert [n for n, _ in engine.get_behaviors_for_pool('test_pool')] == [
            'hard90', 'rot']
        assert tuple(engine.pool_specs['test_pool'].pity_names) == ('rot', 'hard90')


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

    **P64 S7d 改造**：旧类各有一个私有 `_is_hit()` 表达「judge 命中」（不含 scope
    门控），新架构把它内联进各 Tracker 的判据（`_judge_hit`）里、**不再有同名可观测
    面**。故「judge 命中但被 scope 门控挡住」这一形态改写为**状态侧的可观测事实**：
    `did_fire` 为假 **且** `after_draw` 后标志 / 计数未被触碰。
    """

    def test_rotating_requires_scope(self):
        state = PityState()
        pity = _make_pity(state, 'rotating', 'rot')

        out_of_scope = PityContext(draw=_mk_draw('sf1', 'sr', True),
                                   current={}, state=state)
        assert pity.did_fire(out_of_scope) is False    # scope 门控挡住
        pity.after_draw(out_of_scope)
        assert state.get('rot', 'guaranteed', False) is False  # 状态未翻转

        in_scope = PityContext(draw=_mk_draw('f1', 'ssr', True),
                               current={}, state=state)
        assert pity.did_fire(in_scope) is True

    def test_rotating_matches_after_draw_reset(self):
        """did_fire 与 after_draw 的重置分支严格同条件。"""
        state = PityState()
        pity = _make_pity(state, 'rotating', 'rot')
        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state)
        pity.after_draw(ctx)
        assert state.get('rot', 'guaranteed', False) is False   # 状态未翻转
        assert pity.did_fire(ctx) is False                      # did_fire 亦为假

    def test_targeted_requires_scope(self):
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'selected_card', 'sf1')     # 定轨卡指向非 scope 稀有度

        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state)
        assert pity.did_fire(ctx) is False           # scope 门控挡住
        pity.after_draw(ctx)
        assert state.get('tgt', 'fate_points', 0) == 0   # 命中判据为真但状态未累积

    def test_targeted_in_scope_fires(self):
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'selected_card', 'f1')
        ctx = PityContext(draw=_mk_draw('f1', 'ssr', True), current={}, state=state)
        assert pity.did_fire(ctx) is True

    def test_counter_family_unchanged(self):
        """counter 驱动型仍为「出 scope 即真」，不看 featured。"""
        state = PityState()
        pity = _make_pity(state, 'hard', 'h', threshold=90)

        not_featured = PityContext(draw=_mk_draw('s1', 'ssr', False),
                                   current={}, state=state)
        assert pity.did_fire(not_featured) is True

        other_rarity = PityContext(draw=_mk_draw('sf1', 'sr', True),
                                   current={}, state=state)
        assert pity.did_fire(other_rarity) is False


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

    判据只取 §六 G16 断言行的**已钉住两条**：**hard 保底出金不重置 counter**
    与 **counter 达阈值当抽被强制为 scope 100%**（外加 `reset="featured"` /
    默认行为不受影响）。实现面是 `CounterTracker` 的 `reset_on='never'` 分支
    （`_reset_condition` 恒 False），故出金不再把 counter 打回 0，第 79 抽出金后
    第 80 抽照常触发保底。

    **本类不钉该断言行的另一半「每 N 抽白送保底金」**：`never` 下 counter 从不
    归零，第 80 抽起**每一抽**都被强制（本机复跑 90 抽，forced = 第 80..90 抽），
    而「每 N 抽一个白送金」要求**保底触发时归零**——现有 `reset` 取值集合
    （`scope` / `featured` / `never`）无此项。该半已登记为残余缺口 · 待裁决
    （手册 §5.4 幻塔缺口表 / §21 G16 行 / 计划 §六 G16 / 模块状态矩阵 P64 行），
    故第 80 抽之后的 counter 终值也不在此钉住：`never` 下为 80、而「保底触发时
    归零」这一候选语义下为 0，钉死任一值都会让另一种候选语义的裁决必红。

    默认（`reset` 缺省 → 落回 scope）与 `featured` 的语义由本类的对照用例钉住，
    本块不得改动它们。
    """

    NAME = 'tof_hard'
    THRESHOLD = 80
    CUR = {'ssr_featured': 0.6, 'sr_featured': 0.4}

    @classmethod
    def _make(cls, state, **pdef_kwargs):
        """经 `create_behavior` 构造 hard 骨架并补一次重绑。"""
        return _make_pity(state, 'hard', cls.NAME, threshold=cls.THRESHOLD,
                          **pdef_kwargs)

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
        bh = self._make(state, reset='never')

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
        # 第 80 抽之后的 counter 终值**有意不在此断言**（原为 `== THRESHOLD` 的
        # 两条重复断言，仅报错文案不同）：`never` 下为 80，而「保底触发时归零」
        # 这一候选语义（能产生「每 N 抽一个白送金」的周期性）下为 0——两者都是
        # 待裁决的候选，钉住其一即让另一种候选语义的裁决必红。缺口登记见类 docstring。

    def test_never_reset_default_and_featured_unaffected(self):
        """对照：默认（落回 scope）出金即清零、下一抽不再强制；`featured` 语义不变。"""
        # ── 默认：reset 缺省 → CounterTracker 落回 scope('ssr') ──
        s_scope = PityState()
        default = self._make(s_scope)
        for _ in range(self.THRESHOLD - 2):
            self._draw(default, s_scope, rarity='r')
        self._draw(default, s_scope, rarity='ssr', featured=True)   # 第 79 抽出金
        assert self._counter(s_scope) == 0, '默认语义：出 SSR 即清零'
        assert self._draw(default, s_scope, rarity='r') == self.CUR, \
            '默认语义：清零后第 80 抽不应再被强制'

        # ── featured：仅 featured 出金清零 ──
        s_feat = PityState()
        feat = self._make(s_feat, reset='featured')
        for _ in range(self.THRESHOLD - 2):
            self._draw(feat, s_feat, rarity='r')
        self._draw(feat, s_feat, rarity='ssr', featured=False)      # 非 featured 出金
        assert self._counter(s_feat) == self.THRESHOLD - 1, \
            'featured 语义：非 featured 出金不清零'
        assert self._draw(feat, s_feat, rarity='r') == {
            'ssr_featured': 1.0, 'sr_featured': 0.0}

    def test_never_reset_reaches_behavior_via_create_behavior(self):
        """`reset='never'` 经 `create_behavior(PityDef(...))` 透传（配置 → 行为接线面）。

        S4-2 起 `hard` 已 preset 化：本用例断言的对象由旧行为类改为统一骨架 `Pity`
        + 「`reset` 落进 `CounterTracker.reset_on`」这一接线点（旧类的 `_reset`
        属性在骨架上不存在）。
        """
        from gacha_simulator.core.pity import create_behavior, Pity

        state = PityState()
        pdef = PityDef(name=self.NAME, btype='hard', scope='ssr',
                       threshold=self.THRESHOLD, reset='never')
        bh = create_behavior(pdef, state)
        assert isinstance(bh, Pity), 'hard 已 preset 化，须返回统一骨架'
        assert bh._trackers[0]._reset_on == 'never', \
            'reset="never" 未透传到 CounterTracker.reset_on'
        # 骨架**不在构造期绑定**零件 Counter/Flag（§3.1.4；绑定只发生在
        # `Pity._rebind_state`），本用例不经引擎直驱，故须自行完成一次重绑
        # 引擎的三条派发入口（before_draw / after_draw / get_probabilities）
        # 首行都会做这件事。
        bh._rebind_state(state)

        for _ in range(self.THRESHOLD - 2):
            self._draw(bh, state, rarity='r')
        self._draw(bh, state, rarity='ssr', featured=True)
        assert self._counter(state) == self.THRESHOLD - 1
        assert self._draw(bh, state, rarity='ssr') == {
            'ssr_featured': 1.0, 'sr_featured': 0.0}


# ══════════════════════════════════════════════════════════════════
# P82-1：池内保底执行顺序——独立排序视图
# ══════════════════════════════════════════════════════════════════

class TestPoolOrderView:
    """`get_behaviors_for_pool` 消费 `PityEngine._pool_order`（独立排序视图）。

    接线口径（§1.5 裁决 1）：池内保底的**执行顺序**由排序键
    `(稀有度 rank, -priority, _BTYPE_ORDER, name)` 决定（priority 一位由 S6b 接入，
    见下方 `TestPoolOrderPriority`），与 `PoolPitySpec.pity_names` 的 TOML
    书写顺序解耦；后者保持 TOML 顺序不动（`banner.draw_pity_names`
    的输出串依赖它）。本组用例直接钉住接线本身——若排序视图
    被回退为不生效（空集合 / 未被消费），此处即红，而基线快照对照
    只会全绿。
    """

    @staticmethod
    def _make_engine(pity_names, pity_defs, rarity_rank):
        spec = PoolPitySpec(pity_names=list(pity_names))
        return PityEngine(
            pool_specs={'p': spec}, pity_defs=list(pity_defs),
            state=PityState(), rarity_rank=rarity_rank,
        )

    def test_type_order_overrides_toml_order(self):
        """同 scope：hard（_BTYPE_ORDER=1）先于 rotating（=3），与 TOML 书写顺序相反。"""
        defs = [
            PityDef(name='zz_rot', btype='rotating', scope='ssr'),
            PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90),
        ]
        engine = self._make_engine(['zz_rot', 'aa_hard'], defs, {'ssr': 0, 'sr': 1})

        assert [n for n, _ in engine.get_behaviors_for_pool('p')] == ['aa_hard', 'zz_rot']
        # 同一池的 pity_names 保持 TOML 顺序不动
        assert engine.pool_specs['p'].pity_names == ['zz_rot', 'aa_hard']

    def test_rarity_rank_is_first_sort_key(self):
        """跨 scope：稀有度 rank 小者先执行，与 TOML 书写顺序相反。"""
        defs = [
            PityDef(name='aa_sr', btype='hard', scope='sr', threshold=10),
            PityDef(name='zz_ssr', btype='hard', scope='ssr', threshold=90),
        ]
        engine = self._make_engine(['aa_sr', 'zz_ssr'], defs, {'ssr': 0, 'sr': 1})

        assert [n for n, _ in engine.get_behaviors_for_pool('p')] == ['zz_ssr', 'aa_sr']

    def test_order_view_covers_specs_and_unknown_pool_returns_empty(self):
        """视图覆盖全部池；未知池 id 仍返回空（与旧「spec 为 None」早退同义）。"""
        defs = [PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90)]
        engine = self._make_engine(['aa_hard'], defs, {'ssr': 0})

        assert set(engine._pool_order) == set(engine.pool_specs)
        assert engine._pool_order['p'] == ['aa_hard']
        assert engine.get_behaviors_for_pool('no_such_pool') == []

    def test_behavior_not_in_specs_is_excluded(self):
        """`pity_names` 里的未知名不进视图、也不进调度列表。"""
        defs = [PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90)]
        engine = self._make_engine(['aa_hard', 'ghost'], defs, {'ssr': 0})

        assert engine._pool_order['p'] == ['aa_hard']
        assert [n for n, _ in engine.get_behaviors_for_pool('p')] == ['aa_hard']


# ══════════════════════════════════════════════════════════════════
# P64 S6b（G5）：`priority` 参与排序键（§1.5 排序键规格 / §3.6 M3）
# ══════════════════════════════════════════════════════════════════

class TestPoolOrderPriority:
    """`priority` 插在排序键的稀有度 rank 之后、`_BTYPE_ORDER` 之前。

    方向**数值大者先执行**（排序键取 `-priority`），0 = 不覆盖 type 顺序。
    本组用例钉住 §六 G5 priority 的两条断言：
      ① 显式 priority 覆盖 type 顺序（`test_explicit_priority_overrides_type_order`）；
      ② 全 0 时排序结果与「只按 `(rank, _BTYPE_ORDER, name)` 排」逐位相同
         （`test_all_zero_priority_matches_default_order`）。
    两条断言的载体都是 `_resolve_order` 的**产出顺序**；消费链路另由
    `test_priority_reaches_pool_order_view` 覆盖（`_resolve_order` → `_pool_order`
    → `get_behaviors_for_pool` → 三个调度入口）。
    """

    @staticmethod
    def _behaviors(pity_defs):
        """按 PityDef 造 behavior 实例（直测 `_resolve_order` 用，不经引擎）。"""
        state = PityState()
        return [create_behavior(pd, state) for pd in pity_defs]

    @staticmethod
    def _make_engine(pity_names, pity_defs, rarity_rank):
        spec = PoolPitySpec(pity_names=list(pity_names))
        return PityEngine(
            pool_specs={'p': spec}, pity_defs=list(pity_defs),
            state=PityState(), rarity_rank=rarity_rank,
        )

    def test_explicit_priority_overrides_type_order(self):
        """断言 ①：priority 大者先执行，与 type 默认序相反时同样生效。

        取 `hard`（`_BTYPE_ORDER`=1）与 `rotating`（=3）：默认序是 hard 先。
        给 `rotating` 显式 `priority=5` 后它必须排到 hard 之前。
        **去掉排序键里的负号，或把 priority 一位从排序键里删掉，本用例即红**
        （两种退化下 hard 都会回到首位）。
        """
        defs = [
            PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90),
            PityDef(name='zz_rot', btype='rotating', scope='ssr', priority=5),
        ]
        ordered = self._behaviors(defs)
        assert [b._name for b in _resolve_order(ordered, {'ssr': 0})] == [
            'zz_rot', 'aa_hard'], (
            'priority=5 的 rotating 未覆盖 _BTYPE_ORDER（默认序 hard=1 先于 rotating=3）')
        # 前置条件：默认序确与期望相反（否则本用例无判别力）
        assert _BTYPE_ORDER['hard'] < _BTYPE_ORDER['rotating']
        assert [b._name for b in sorted(
            ordered,
            key=lambda b: (0, _BTYPE_ORDER[b._btype], b._name))] == ['aa_hard', 'zz_rot']

    def test_negative_priority_runs_after_type_order(self):
        """方向的下半段：负 priority 排在默认序**之后**（GUI 量程含负值即为此）。"""
        defs = [
            PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90,
                    priority=-1),
            PityDef(name='zz_rot', btype='rotating', scope='ssr'),
        ]
        assert [b._name for b in _resolve_order(self._behaviors(defs), {'ssr': 0})] == [
            'zz_rot', 'aa_hard']

    def test_all_zero_priority_matches_default_order(self):
        """断言 ②：全 0 时排序结果与「只按 `(rank, _BTYPE_ORDER, name)` 排」逐位相同。

        样本刻意混合两个 scope、四种 btype，且传入顺序与两种排序都不一致，
        逐位比较（不是集合比较）。
        """
        defs = [
            PityDef(name='zz_rot', btype='rotating', scope='ssr'),
            PityDef(name='bb_hard', btype='hard', scope='ssr', threshold=90),
            PityDef(name='aa_sr_hard', btype='hard', scope='sr', threshold=10),
            PityDef(name='cc_soft', btype='soft_interval', scope='ssr',
                    soft_start=73, soft_end=90),
        ]
        rank = {'ssr': 0, 'sr': 1}
        behaviors = self._behaviors(defs)
        assert all(b._priority == 0 for b in behaviors), '样本须全部 priority=0'
        got = [b._name for b in _resolve_order(behaviors, rank)]
        want = [b._name for b in sorted(
            behaviors, key=lambda b: (rank[b._scope], _BTYPE_ORDER[b._btype], b._name))]
        assert got == want
        # 期望序本身须含跨 scope 与同 scope 两类比较，否则退化为常数断言
        assert got == ['cc_soft', 'bb_hard', 'zz_rot', 'aa_sr_hard']

    def test_missing_priority_attribute_falls_back_to_zero(self):
        """旧类实例（无 `_priority` 属性）按 0 参与排序，不抛 `AttributeError`。

        `create_behavior` 保留着旧类兼容分支（GATE-5，保留到发布前），
        故 `_resolve_order` 的取值必须走 `getattr(bh, '_priority', 0)` 兜底。
        桩对象即旧类形态的代理（只有 `_name` / `_btype` / `_scope` 三个属性）。
        """
        class _LegacyStub:
            def __init__(self, name, btype, scope):
                self._name, self._btype, self._scope = name, btype, scope

        stubs = [_LegacyStub('zz_rot', 'rotating', 'ssr'),
                 _LegacyStub('aa_hard', 'hard', 'ssr')]
        assert [s._name for s in _resolve_order(stubs, {'ssr': 0})] == ['aa_hard', 'zz_rot']

    def test_priority_reaches_pool_order_view(self):
        """消费链路：`_resolve_order` → `_pool_order` → `get_behaviors_for_pool`。

        池内执行顺序取自独立排序视图，故 priority 经该链路生效；
        `PoolPitySpec.pity_names` 保持 TOML 书写顺序不动。
        """
        defs = [
            PityDef(name='aa_hard', btype='hard', scope='ssr', threshold=90),
            PityDef(name='zz_rot', btype='rotating', scope='ssr', priority=5),
        ]
        engine = self._make_engine(['aa_hard', 'zz_rot'], defs, {'ssr': 0})

        assert engine._pool_order['p'] == ['zz_rot', 'aa_hard']
        assert [n for n, _ in engine.get_behaviors_for_pool('p')] == ['zz_rot', 'aa_hard']
        assert engine.pool_specs['p'].pity_names == ['aa_hard', 'zz_rot']

# ══════════════════════════════════════════════════════════════════
# P82-2：接线基线固化 + 等价对照（P64 §1.5 / §七 P82-2）
# ══════════════════════════════════════════════════════════════════

class TestP82OrderWiringBaseline:
    """`scripts/p82_baseline.py` 的活守卫（分工同 P79：脚本跑对照，本类断言其结论）。

    快照是**接线前**（`a41de1b^`）在固定种子与固定 `sim_start_date` 下固化的
    `CompactResult`；本类在**接线后**的代码上以子进程重跑 `--verify`，逐字段对比。
    `config.toml` 仅一条保底定义，P64 §1.5 的五类敏感集合均不受影响，故差异数
    必须为 0——任何差异都意味着接线改变了管道输出（回归），而不是「无差异」。
    """

    BASELINE_DIR = ROOT / 'tests' / 'fixtures' / 'p82_baseline'

    def test_baseline_snapshots_present(self):
        """9 组快照齐备（缺任一即对照退化为部分覆盖）。"""
        keys = P82_BUILTIN_KEYS + P82_PLUGIN_KEYS
        missing = [
            k for k in keys
            if not (self.BASELINE_DIR / (k.replace('/', '__') + '.json')).exists()
        ]
        assert not missing, f'P82 基线快照缺失: {missing}'

    def test_equivalence_verify_script_passes(self):
        """对照脚本退出码 0 且输出 PASS = 逐字段等价、`draw_pity_names` 不变。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts' / 'p82_baseline.py'), '--verify'],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding='utf-8', errors='replace',
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '等价对照结果：PASS' in result.stdout
        assert result.stdout.count('draw_pity_names 不变') == 9
