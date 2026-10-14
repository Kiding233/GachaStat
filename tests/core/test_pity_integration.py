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
    AlwaysActive, Pity, PityState, PityEngine, DrawInfo, PityContext,
    StateView,
    compute_scope_mappings,
    PoolPitySpec,
    # P64 S6b（G5）：排序键的直测面
    _BTYPE_ORDER, _resolve_order, create_behavior,
)
from gacha_simulator.core.pity_modifier import Modifier
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pool import Pool, Reward
# P64 S9-2：`PityContext.sim` 非 Optional（3.10.2）------------------------------
# 直构 ctx 与 `PityEngine` 三个调度入口（before_draw / after_draw /
# get_probabilities）的 `sim` 都是**必填**（缺参在构造 ctx 时即 TypeError）。本文件
# 只验与「玩家持有」无关的机制，故用**空 state 的视图**作最小替身。
from gacha_simulator.core.state import GachaState as _GachaState, SimView as _SimView

_SIM = _SimView(_GachaState())


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
        # 两个**互不相同**的 featured 卡（P64 S7d 审查收口；S8-2 起断言面由槽位
        # 换成卡 id）：单卡夹具下「A = 定轨卡」与「A = 全部 featured」产出同值、
        # 判别力为零；两张 featured 卡时，定轨 f1 独得 scope 总量（0.015）、f2 归零，
        # 与「两张均分（各 0.0075）」可区分。
        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('f1', 'f2', 's1')},
            featured_cards={'ssr': ('f1', 'f2')},
            base_probabilities={'f1': 0.2, 'f2': 0.2, 's1': 0.6},
            rarity_rank={'ssr': 0},
        )
        return PityContext(
            draw=draw,
            current=dict(current or {'f1': 0.2, 'f2': 0.2, 's1': 0.6}),
            state=state,
        sim=_SIM,)

    def test_selected_card_located_via_card_to_slot(self):
        """selected 在 card_to_slot 中 → A 列落在其投影槽位（scope 总量全给该槽）。

        **本用例是「定轨卡定位」的判别面（P64 S7d 审查收口）**：把
        `SelectedModifier.compute_delta` 的 `A = (sel,) if sel in featured else featured`
        变异为 `A = featured`（完全忽略定轨卡）时，本用例必红。判别点：
        `f1` 应为 scope 总量 `1.0`（定轨卡独得），变异后 A 退化为
        `('f1', 'f2')`、两卡按声明权重各得 `0.5`。
        """
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=0)
        state.set('tgt', 'selected_card', 'f1')

        out = pity.before_draw(self._ctx(state))
        assert out['f1'] == pytest.approx(1.0)     # 定轨卡独得 scope 总量
        assert out['f2'] == pytest.approx(0.0)     # 兄弟 featured 卡被搬空
        assert out['s1'] == pytest.approx(0.0)

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
        assert out['f1'] == pytest.approx(0.5)   # 回退到全部 featured → 两卡按声明权重均分
        assert out['f2'] == pytest.approx(0.5)
        assert out['s1'] == pytest.approx(0.0)

    def test_selected_none_returns_all_featured(self):
        """selected=None → A 列 = 全部 featured 槽（经 `guaranteed` 分支触发）。

        **两个 featured 槽都分到概率**，即「复数语义」的判别面（旧夹具
        `featured_slots={'ssr': ('ssr_featured', 'ssr_featured2')}` 的等价恢复）。
        """
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'guaranteed', True)      # selected_card 保持未设置

        out = pity.before_draw(self._ctx(state))
        assert out['f1'] == pytest.approx(0.5)
        assert out['f2'] == pytest.approx(0.5)
        assert out['s1'] == pytest.approx(0.0)


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

        # S8-7：只取卡集合两项。`compute_scope_mappings` 的五元组形态保留至发布前
        # （ISSUE-901），本文件不再消费它的槽位产出。
        scope_cards, featured_cards = compute_scope_mappings(pool)[:2]

        source_def = PityDef(name='source', btype='rotating', scope='ssr')
        dep_def = PityDef(name='dependent', btype='hard', scope='ssr',
                           threshold=100, depends_on='source')

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            pity_names=('source', 'dependent'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
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
        engine.before_draw('test_pool', state, {'ssr_featured': 0.005, 'ssr_standard': 0.005}, sim=_SIM)
        engine.after_draw('test_pool', state, 'f1', sim=_SIM)

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
        """rotating 和 hard 概率叠加：hard 先夺走更低稀有度，rotating 再把非 featured 搬空。

        **S8-2 起断言面是卡级**（§3.9.1），且池子**必须含更低稀有度卡**：新
        `hard` 是夺取型（`amount = p(Q)`，Q = 更低稀有度，§3.1.2 表第 1 行），
        全 SSR 的池子上 `Q` 为空、hard 退化为恒等（旧稿的池只有两张 SSR 卡，
        在那个池上 hard 的「100%」是旧槽位级绝对赋值的产物）。故本用例补一张 R 卡
        作取源面，并把 `rarity_rank` 的方向修正为「rank 小 = 稀有度更高」
        （旧稿写 `{'ssr': 3, ...}`，会让 `_lower_rarities` 恒返空集、
        `transfer_linear` 因 `p(Q) = 0` 静默恒等：**本用例正是被这条掩盖的**）。
        """
        state = PityState()

        pool = Pool(
            id='test_pool', name='测试池',
            cost={'gem': 1},
            rewards=[
                (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.006),
                (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.004),
                (Reward(id='r1', name='R1', extra_info={'rarity': 'R'}), 0.99),
            ],
        )

        scope_cards, featured_cards = compute_scope_mappings(pool)[:2]

        rot_def = PityDef(name='rot', btype='rotating', scope='ssr')
        hard_def = PityDef(name='hard90', btype='hard', scope='ssr', threshold=90)

        pool_spec = PoolPitySpec(
            scope_cards=scope_cards, featured_cards=featured_cards,
            pity_names=('rot', 'hard90'),
            ssr_ids={'f1', 's1'}, featured_ids={'f1'},
        )

        engine = PityEngine(
            pool_specs={'test_pool': pool_spec},
            pity_defs=[rot_def, hard_def],
            state=state,
            rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
        )
        base = {'f1': 0.006, 's1': 0.004, 'r1': 0.99}

        # 初始：小保底（rotating 未置位）、未到硬保底阈值 → 恒等
        probs = engine.before_draw('test_pool', state, dict(base), sim=_SIM)
        assert probs == base

        # hard 单独触发（rotating 未置位）：Q = 更低稀有度（r1）整组搬空、
        # A = scope 卡集按当前比例收下（0.006 : 0.004 之比保持不变）
        state.set('hard90', 'counter', 89)
        probs_hard = engine.before_draw('test_pool', state, dict(base), sim=_SIM)
        assert probs_hard['r1'] == pytest.approx(0.0)
        assert probs_hard['f1'] / probs_hard['s1'] == pytest.approx(0.006 / 0.004)

        # 再叠 rotating 大保底：非 featured 的 s1 也被搬空、f1 收下全部
        state.set('rot', 'guaranteed', True)
        probs2 = engine.before_draw('test_pool', state, dict(base), sim=_SIM)
        assert probs2['s1'] == pytest.approx(0.0)
        assert probs2['r1'] == pytest.approx(0.0)
        assert probs2['f1'] == pytest.approx(1.0)

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
                                   current={}, state=state, sim=_SIM)
        assert pity.did_fire(out_of_scope) is False    # scope 门控挡住
        pity.after_draw(out_of_scope)
        assert state.get('rot', 'guaranteed', False) is False  # 状态未翻转

        in_scope = PityContext(draw=_mk_draw('f1', 'ssr', True),
                               current={}, state=state, sim=_SIM)
        assert pity.did_fire(in_scope) is True

    def test_rotating_matches_after_draw_reset(self):
        """did_fire 与 after_draw 的重置分支严格同条件。"""
        state = PityState()
        pity = _make_pity(state, 'rotating', 'rot')
        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state, sim=_SIM)
        pity.after_draw(ctx)
        assert state.get('rot', 'guaranteed', False) is False   # 状态未翻转
        assert pity.did_fire(ctx) is False                      # did_fire 亦为假

    def test_targeted_requires_scope(self):
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'selected_card', 'sf1')     # 定轨卡指向非 scope 稀有度

        ctx = PityContext(draw=_mk_draw('sf1', 'sr', True), current={}, state=state, sim=_SIM)
        assert pity.did_fire(ctx) is False           # scope 门控挡住
        pity.after_draw(ctx)
        assert state.get('tgt', 'fate_points', 0) == 0   # 命中判据为真但状态未累积

    def test_targeted_in_scope_fires(self):
        state = PityState()
        pity = _make_pity(state, 'targeted', 'tgt', fate_threshold=1)
        state.set('tgt', 'selected_card', 'f1')
        ctx = PityContext(draw=_mk_draw('f1', 'ssr', True), current={}, state=state, sim=_SIM)
        assert pity.did_fire(ctx) is True

    def test_counter_family_unchanged(self):
        """counter 驱动型仍为「出 scope 即真」，不看 featured。"""
        state = PityState()
        pity = _make_pity(state, 'hard', 'h', threshold=90)

        not_featured = PityContext(draw=_mk_draw('s1', 'ssr', False),
                                   current={}, state=state, sim=_SIM)
        assert pity.did_fire(not_featured) is True

        other_rarity = PityContext(draw=_mk_draw('sf1', 'sr', True),
                                   current={}, state=state, sim=_SIM)
        assert pity.did_fire(other_rarity) is False


# ════════════════════════════════════════════════════════
# 「卡 id → 稀有度」推断的守卫（缺陷 12 的同源重复实现已消除）
# ════════════════════════════════════════════════════════

class TestRarityInferenceGuards:
    '''`PityEngine._infer_rarity`（状态路径）的答案必须与池内真实稀有度一致。

    **S8-2 改写（ISSUE-504）**：原类名 `TestRarityInferenceConsistency`，断言面是
    「两份实现（A = `pool.infer_rarity_from_spec` 喂概率路径、B =
    `PityEngine._infer_rarity` 喂状态路径）逐卡同答」。**A 已随其最后一批消费者
    删除**（`banner.draw` 的 `scale_factors` 还原段与 `aggregate_probs_by_rarity`
    的内部调用；`banner.draw` 改走卡级直传后，概率路径不再需要「卡 id → 稀有度」
    的反查），故「两处实现漂移」这一缺陷形态**在结构上不再存在**（缺陷 12 的根因
    即 A 单方面漂移）。本类保留的是**剩下的那一份实现**的守卫：B 的答案必须等于
    池内每张卡声明的稀有度，且两条支撑它的不变量成立：不变量破了，B 就会答错
    （而不是「与另一份实现分歧」）。

    判据的两条不变量（真实配置全量扫描，实测 8 banner 各 1 池、每池 19 张卡，
    合计 152 张逐卡成立）：

    ① `ssr_ids ⊆ scope_cards['ssr']`（需要的是「查得到」而非「相等」：
       `batch_simulator` 建 `ssr_ids` 时排除 `_no_card`，等号会在合法配置上误红）；
    ② `featured_ids ⊆ scope_cards`。
    '''

    def test_infer_rarity_agrees_with_declared_rarity_on_multi_rarity_spec(self):
        '''不依赖真配置的最小构造：三种稀有度各给一张卡 + 一张表外卡。'''
        spec = PoolPitySpec(
            pity_names=['p'],
            scope_cards={'ssr': ('ssr_a',), 'sr': ('sr_a',), 'r': ('r_a',)},
            featured_cards={'ssr': ('ssr_a',)},
            ssr_ids={'ssr_a'},
            featured_ids={'ssr_a'},
        )
        engine = PityEngine({'k': spec}, [])
        for cid, expected in (('ssr_a', 'ssr'), ('sr_a', 'sr'), ('r_a', 'r')):
            assert engine._infer_rarity(cid, spec) == expected, cid
        # 表外卡 → 空串哨兵（「无稀有度」），不得回退猜测
        assert engine._infer_rarity('not_in_spec', spec) == ''

    def test_infer_rarity_on_real_config_and_invariants_hold(self):
        '''真实配置全量扫一遍：逐卡答对 + 两条不变量成立（不变量破了即答错）。'''
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
                    got = env.pity_engine._infer_rarity(rwd.id, spec) or None
                    real = (rwd.extra_info.get('rarity') or '').lower() or None
                    assert got == real, f'{rwd.id} @ {banner.id}.{pid}: 推断={got!r} 真实={real!r}'
                    checked += 1
        assert checked > 0, '未扫到任何卡——本测试无验收面'


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
    #: 卡级基础分布（S8-2 起管道为卡级）：SSR 的 UP 卡 0.6 + 更低稀有度卡 0.4，
    #: Σ = 1（归一化在 Σ = 1 时退化为恒等，故断言值即保底算出的值）。
    #: 夹具的卡集（`_mk_draw`）：`ssr` 一张 `f1`、`sr` 一张 `sf1`。
    CUR = {'f1': 0.6, 'sf1': 0.4}

    @classmethod
    def _make(cls, state, **pdef_kwargs):
        """经 `create_behavior` 构造 hard 骨架并补一次重绑。"""
        return _make_pity(state, 'hard', cls.NAME, threshold=cls.THRESHOLD,
                          **pdef_kwargs)

    @classmethod
    def _ctx(cls, state, rarity='r', featured=False):
        """一次抽卡的上下文：current 含两张卡（scope 一张 + 更低稀有度一张）。"""
        return PityContext(
            draw=_mk_draw('f1' if featured else 's1', rarity, featured),
            current=dict(cls.CUR),
            state=state,
        sim=_SIM,)

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

        # 第 80 抽：counter 未被出金清零 → 保底照常触发，scope 卡集收下全部
        #（Q = 更低稀有度 = sf1，夺取型 amount = p(Q)）
        assert self._draw(bh, state, rarity='ssr') == {
            'f1': 1.0, 'sf1': 0.0}
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
            'f1': 1.0, 'sf1': 0.0}

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
            'f1': 1.0, 'sf1': 0.0}


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


# ══════════════════════════════════════════════════════════════════
# P64 S9-1：`StateView` 限定 Modifier 状态视野（§3.10.3 / §七 S9-1）
# ══════════════════════════════════════════════════════════════════

class _NoCtxStateRead:
    """`ctx.state` 通道探针：**任何**属性访问即判失败。

    S9-1 的正例要证明「Modifier 读自己命名空间的值，**不经** `ctx.state` 也拿得到」。
    把 `ctx.state` 换成本对象后，路径上任何一处 `ctx.state.get(...)` / `ctx.state.data`
    都会抛 `AssertionError`，故「值确实来自 `view`」不再是一句声明，而是可判事实。
    """

    def __getattr__(self, item):
        raise AssertionError(
            f'本用例中 ctx.state 通道不可用，却被读到了 ctx.state.{item}：'
            f'状态键只许经 view 读（ISSUE-103 纪律）'
        )


class TestStateViewCrossPityReadClosed:
    """S9-1 验收：跨保底读在架构上关闭，且隔离**只由 `view` 形参承担**。

    `StateView.get` 只取 `data[self._name]`，故 Modifier 读他人命名空间的键恒返回
    `default`（不抛 `KeyError`、也不报错、更不泄露他人值）。`ctx.state` 是同一份账本
    的另一条通道，**仍能**读到他人键（ISSUE-103 登记的事实），本类用一条对照断言把它
    钉住：若哪天有人把隔离做到 `ctx.state` 上，该对照会红，说明「隔离只由 view 承担」
    这一分工已被改变，须同步改本节与 §3.10.3。

    两条用例的 Modifier 都走**真管道**（`Pity.before_draw` → `_view_for(mod)` →
    `compute_delta`），不是直构 `StateView` 的探针，故断言对象就是骨架实际交给
    Modifier 的那个对象。
    """

    PITY_NAME = 's9_self'
    FOREIGN_NAME = 's9_other'

    @classmethod
    def _make(cls, state, mod):
        return Pity(name=cls.PITY_NAME, state=state, scope='ssr', btype='hard',
                    trackers=[], modifiers=[mod], lifecycle=AlwaysActive())

    @staticmethod
    def _ctx(state):
        draw = DrawInfo(
            pool_id='p1', pool_instance_id='p1_0',
            reward_id='', reward_rarity='', is_featured=False,
            scope_cards={'ssr': ('c1',)},
            featured_cards={'ssr': ('c1',)},
            base_probabilities={'c1': 1.0},
            rarity_rank={'ssr': 0},
        )
        return PityContext(draw=draw, current={'c1': 1.0}, state=state, sim=_SIM)

    def test_stateview_reads_own_namespace_without_ctx_state(self):
        """正例：Modifier 经 `view` 读**自己**命名空间的键 → 拿到真值，且不经 `ctx.state`。

        判据三条：① 实参是 `StateView`（不是原始 `PityState`）；② 它的命名空间是本
        保底；③ 读到的值等于账本里的值，**且这一读不经 `ctx.state`**（`ctx.state` 被
        换成任何访问即抛的探针）。故「骨架把 `ctx.state` 当 view 传」或「`StateView`
        回退成全账本读」两种形态都会让本用例立即红。
        """
        seen = {}

        class _ProbeMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                seen['view'] = view
                seen['value'] = view.get('counter')
                return None

        state = PityState()
        state.set(self.PITY_NAME, 'counter', 7)
        pity = self._make(state, _ProbeMod())

        pity.before_draw(self._ctx(_NoCtxStateRead()))

        assert isinstance(seen['view'], StateView), \
            'Modifier 的 view 形参须是 StateView（不是原始 PityState）'
        assert seen['view']._name == self.PITY_NAME, '默认 view 须指向本保底命名空间'
        assert seen['value'] == 7, '经 view 须读到自己命名空间里的真值'

    def test_stateview_other_pity_key_returns_default_not_keyerror(self):
        """负例：Modifier 经 `view` 读**别的保底**命名空间的键 → 返回 `default`。

        判据三条：① 该键在账本里**确实存在**（夹具守卫，否则本用例无验收面）；
        ② 经 `view` 读到的是 `default`（既不抛 `KeyError`，也不泄露他人值）；
        ③ **对照**：同一个键经 `ctx.state` 仍能读到。第 ③ 条正是 ISSUE-103 登记的
        那条通道，用来把「隔离只由 `view` 形参承担、`ctx.state` 靠纪律关闭」这一事实
        钉住（隔离若被做到 `ctx.state` 上，本断言必红）。
        """
        DEFAULT = object()
        seen = {}

        class _ProbeMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                seen['view'] = view
                seen['own'] = view.get('counter', DEFAULT)
                seen['foreign'] = view.get('foreign_key', DEFAULT)
                return None

        state = PityState()
        state.set(self.PITY_NAME, 'counter', 3)
        state.set(self.FOREIGN_NAME, 'foreign_key', 'other-pity-value')
        # 夹具守卫：他人命名空间的键确实存在且值可辨（否则负例退化为空断言）
        assert state.get(self.FOREIGN_NAME, 'foreign_key') == 'other-pity-value'

        pity = self._make(state, _ProbeMod())
        ctx = self._ctx(state)
        pity.before_draw(ctx)

        assert seen['view']._name == self.PITY_NAME
        assert seen['own'] == 3, '自己命名空间的键仍须读到'
        assert seen['foreign'] is DEFAULT, \
            '读他人命名空间的键须返回 default（跨保底读在架构上关闭）'
        # 对照（ISSUE-103）：隔离只由 view 承担，ctx.state 通道仍在
        assert ctx.state.get(self.FOREIGN_NAME, 'foreign_key') == 'other-pity-value'


# ══════════════════════════════════════════════════════════════════
# P64 S9-2：`SimView` + `uses_sim` 注解校验 + 两条送达通道（§3.10.2）
# ══════════════════════════════════════════════════════════════════

def test_sim_view_owns_includes_initial_counts():
    """`SimView.owns()` 取 `total_holding` 口径，**含初始持有**（ISSUE-009）。

    判据四条：① 初始持有与模拟内获得**相加**（不是只看 `acquired`）；② 未持有的卡为 0；
    ③ 视图是 `GachaState` 的**活引用**（O(1) 包装、不复制账本：同一 state 再获得一张，
    视图随即反映）；④ `owns()` 与 `total_holding()` 逐值同源，且 `SimView` 的公开面
    **恰为 `owns` 一个源**（`balance()` 已于 2026-10-06 删除，§3.10.2）。
    """
    state = _GachaState(initial_counts={'c1': 2})
    state.add_card('c1')                     # 模拟内获得 1 张
    view = state.sim_view()

    assert view.owns('c1') == 3, '初始持有 2 + 模拟内 1 = 3（少算初始持有即本断言红）'
    assert view.owns('never_seen') == 0
    assert view.owns('c1') == state.total_holding('c1'), '两个入口须同口径'

    state.add_card('c1')                     # 活引用：视图不缓存旧值
    assert view.owns('c1') == 4

    public = {n for n in dir(view) if not n.startswith('_')}
    assert public == {'owns'},         f'SimView 只暴露 owns 一个源（§3.10.2 的「删除的符号」段），实测 {sorted(public)}'


def test_sim_view_annotation_unknown_source_raises_config_error():
    """`uses_sim` 注解名不在已知源集合内 → `ConfigError`（构造期，§3.10.2）。

    正负两态同测：负例（注解 `'balance'`，该源已于 2026-10-06 删除）必抛，正例
    （注解 `'owns'`，已知源）必须构造成功：只测负例无法区分「校验生效」与
    「校验把所有注解都拒了」。
    """
    from gacha_simulator.core.config_store import ConfigError
    from gacha_simulator.core.pity_modifier import KNOWN_SIM_SOURCES

    assert KNOWN_SIM_SOURCES == ('owns',), '已知源集合当前只有 owns'

    class _UnknownSourceMod(Modifier):
        uses_sim = ('balance',)              # 已删除的源，不在已知集合内

        def compute_delta(self, view, dist, ctx):
            return None

    class _KnownSourceMod(Modifier):
        uses_sim = ('owns',)

        def compute_delta(self, view, dist, ctx):
            return None

    def _make(mod):
        return Pity(name='s9_sim_annot', state=PityState(), scope='ssr',
                    btype='hard', trackers=[], modifiers=[mod],
                    lifecycle=AlwaysActive())

    with pytest.raises(ConfigError):
        _make(_UnknownSourceMod())

    _make(_KnownSourceMod())                 # 正例：已知源不拦


def test_pity_engine_requires_sim_argument():
    """`sim` 是**必填参**（§3.10.2）：缺参在构造 ctx 时即 `TypeError`。

    覆盖三处构造点：`PityEngine` 的三个调度入口（before_draw / after_draw /
    get_probabilities）与 `PityContext` 直构。若任一处被写回可选参（`sim=None`），
    「运行期读到 `None` → Modifier 静默退化为恒等」这一失效形态即复活，本用例是它
    的唯一捕获面（`None` 本身不会报错，只有「缺参」才会）。
    """
    state = PityState()
    engine = PityEngine(pool_specs={}, pity_defs=[], state=state)

    with pytest.raises(TypeError):
        engine.before_draw('p', state, {})
    with pytest.raises(TypeError):
        engine.get_probabilities('p', state, {})
    with pytest.raises(TypeError):
        engine.after_draw('p', state, 'c1')

    draw = DrawInfo(pool_id='p', pool_instance_id='p_0', reward_id='',
                    reward_rarity='', is_featured=False)
    with pytest.raises(TypeError):
        PityContext(draw=draw, current={}, state=state)


def test_channel_b_fills_sim_view():
    """通道 B（策略查询）：`StrategyContext.get_pity_probabilities` 确实把 `SimView`
    送进 `PityEngine.get_probabilities`，且该视图指向**当场的那个 `GachaState`**。

    通道 B **完全绕过 `Banner.draw`**（经 `_pity_cache` 直调引擎），故通道 A 全绿
    推不出 B 正确：两条通道各有一条填充点断言，缺一则「`sim` 只在一半路径生效」
    这一盲区不可见（§六「`sim` 双通道送达」，通道 A 的断言在
    `tests/service/test_gacha_service.py::test_channel_a_fills_sim_view`）。

    探针是只读包装（转发给原方法），故断言对象就是引擎实际收到的实参。
    """
    from gacha_simulator.core import AllPoolsEndCondition, TargetCardSet
    from gacha_simulator.core.state import GachaState, SimView
    from gacha_simulator.core.strategy import StrategyContext

    pool = Pool(
        id='b_channel', name='通道 B 池', cost={'gem': 1},
        rewards=[
            (Reward(id='f1', name='F1', extra_info={'rarity': 'SSR', 'featured': True}), 0.006),
            (Reward(id='s1', name='S1', extra_info={'rarity': 'SSR', 'featured': False}), 0.004),
            (Reward(id='r1', name='R1', extra_info={'rarity': 'R', 'featured': False}), 0.99),
        ],
    )
    scope_cards, featured_cards = compute_scope_mappings(pool)[:2]
    spec = PoolPitySpec(
        scope_cards=scope_cards, featured_cards=featured_cards,
        pity_names=('hard90',), ssr_ids={'f1', 's1'}, featured_ids={'f1'},
    )
    engine = PityEngine(
        pool_specs={pool.id: spec},
        pity_defs=[PityDef(name='hard90', btype='hard', scope='ssr', threshold=90)],
        state=PityState(), rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )
    # 夹具守卫：spec 必须在引擎内，否则 `get_probabilities` 在首行早退、探针恒空
    assert engine.get_spec(pool.id) is not None

    gacha_state = GachaState(initial_counts={'f1': 2})
    ctx = StrategyContext(
        state=gacha_state,
        current_pools=[pool], all_pools=[pool],
        future_schedules=[], target_cards=TargetCardSet([]),
        stop_condition=AllPoolsEndCondition(1000.0),
        _pity_engine=engine, _pity_state=PityState(),
    )

    seen = {}
    orig = engine.get_probabilities

    def spy(pool_id, st, base, sim):
        seen['sim'] = sim
        return orig(pool_id, st, base, sim)

    engine.get_probabilities = spy
    try:
        result = ctx.get_pity_probabilities(pool.id)
    finally:
        engine.get_probabilities = orig

    assert 'sim' in seen, '通道 B 未走到 PityEngine.get_probabilities（夹具失效）'
    sim = seen['sim']
    assert isinstance(sim, SimView),         f'通道 B 的 sim 实参须是 SimView，实测 {type(sim).__name__}'
    assert sim.owns('f1') == gacha_state.total_holding('f1') == 2,         'sim 须指向当场的那个 GachaState（含初始持有），不是另建的空 state'
    assert result, '分布查询须有产出（否则本用例无验收面）'


# ══════════════════════════════════════════════════════════════════
# P64 S9-4：G3 专项（精确建模判据，§六 G3 专项 / §3.10.4）
# ══════════════════════════════════════════════════════════════════

_G3_SKIP_TYPE = 'hard_exclude_owned_skip'
_G3_ANY_TYPE = 'hard_exclude_owned_any'

#: G3 夹具的池子形态：两张 UP（`up_a` / `up_b`）+ 一张同稀有度常驻（`std`）。
#: 三张同在 `scope_cards['ssr']` 内，故 `scope\A` 恒非空（Q 有减量可搬、`Σδ = 0`）。
_G3_SCOPE_CARDS = ('up_a', 'up_b', 'std')
_G3_FEATURED = ('up_a', 'up_b')
_G3_BASE = {'up_a': 0.3, 'up_b': 0.3, 'std': 0.4}


def _one_pity_pipeline(btype, *, name='g3', threshold=50, counter=0):
    """「一个 ssr 池 + 一条保底」的最小**真管道**夹具：返回 `(engine, pool, pity_state, base)`。

    池内 `rewards` 的权重与本夹具返回的 `base` **同值**，故通道 B 经 `pool.rewards`
    取到的 `base_probabilities` 与直调入口传的 `base` 一致（两条通道可比的前提，
    见 `test_channel_b_matches_before_draw`）。

    `counter` 经 `PityDef.counter_init` 落到 per-call state；`counter_init=0` 时该键
    不预建（L4 truthy 规则），读取回退 0。`threshold` 只有 counter 驱动型消费，
    其余类型收下不用（它是 `PityDef` 的字段，不是非法键）。
    """
    base = dict(_G3_BASE)
    pool = Pool(
        id='g3_pool', name='G3 池', cost={'gem': 1},
        rewards=[
            (Reward(id=c, name=c,
                    extra_info={'rarity': 'SSR', 'featured': c in _G3_FEATURED}),
             base[c])
            for c in _G3_SCOPE_CARDS
        ],
    )
    scope_cards, featured_cards = compute_scope_mappings(pool)[:2]
    spec = PoolPitySpec(
        pity_names=(name,),
        scope_cards=scope_cards, featured_cards=featured_cards,
        ssr_ids=set(_G3_SCOPE_CARDS), featured_ids=set(_G3_FEATURED),
    )
    pity_state = PityState()
    engine = PityEngine(
        pool_specs={pool.id: spec},
        pity_defs=[PityDef(name=name, btype=btype, scope='ssr',
                           threshold=threshold, counter_init=counter)],
        state=pity_state, rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )
    return engine, pool, pity_state, base


def _g3_engine(btype, *, owns=(), initial_counts=None, threshold=50, counter=0,
               name='g3'):
    """G3 夹具：在 `_one_pity_pipeline` 之上补一个 `GachaState` 与它的 `SimView`。

    返回 `(engine, pool, pity_state, gacha_state, sim, base)`。`owns` 是**本次模拟内
    获得**的卡（写 `acquired`），`initial_counts` 是**初始持有**（写 `initial_counts`
    字段）：两者都进 `SimView.owns()` 的 `total_holding` 口径（ISSUE-009），这正是
    ①（模拟内获得）与补充用例（初始持有）的对照面。
    """
    engine, pool, pity_state, base = _one_pity_pipeline(
        btype, name=name, threshold=threshold, counter=counter)
    gacha_state = _GachaState(initial_counts=dict(initial_counts or {}))
    for c in owns:
        gacha_state.add_card(c)
    return engine, pool, pity_state, gacha_state, gacha_state.sim_view(), base


class TestG3ExcludeOwned:
    """§六 G3 专项（精确建模判据）：崩坏3 精准补给「τ 抽必出**未获得的** UP」。

    本组的立组目的是把 G3 与「pool 层近似」的分界钉死（§3.10.4 开头「为什么不能
    沿用 pool 层近似」）：pool 层过滤（把已拥有的卡从 reward 列表移除）会让**每次
    抽卡**都不出它们，而真实机制只作用于保底触发点，故 ①② 必须分列、不可互替。

    ③a / ③b 是一对**并列的建模假设**（§3.10.4 的 2026-09-30 用户裁决：零直接信源，
    两形态各违背规则原文的一半，机制定稿前谁也不是「已确认等价」）。本组按 §六 的
    要求**两个 type 各断言一条**，两条断言的对象都是「该实现的实际行为」，不是
    「机制已定稿」的判定；日后查证定稿为一方时，删去被否的那条即可。
    """

    def test_g3_trigger_excludes_owned_up_from_target_set(self):
        """① 保底触发时**已拥有的 UP 不被选中**：目标集只含未拥有者，已拥有者被搬空。

        判据四条：① 未拥有的 UP 独得全部质量（`up_b` = 1.0）；② 已拥有的 UP 归零
        （`up_a` = 0），这一条同时证明**已拥有的 UP 落在 Q 内**（2026-10-07 用户
        裁决：Q = 更低稀有度 ∪ `scope\\A`），若按 `scope\\featured` 取 Q，`up_a` 会
        保留 0.3 的概率、本断言即红；③ 同稀有度常驻 `std` 也归零（它在 Q 内）；
        ④ 分布归一（`Σ = 1`）。
        """
        engine, _pool, pity_state, _gs, sim, base = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a',), counter=49)
        # 夹具守卫：`up_a` 确在 featured 内、确为「已拥有」，且它在基础分布里**有正
        # 概率**（否则 ② 的「归零」无判别力：池里本来就没有它）
        assert 'up_a' in _G3_FEATURED
        assert sim.owns('up_a') == 1 and sim.owns('up_b') == 0
        assert base['up_a'] > 0

        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)

        assert pity_state.get('g3', 'counter', 0) == 50, \
            '本抽须已到 τ（否则下面的断言另有原因）'
        assert out['up_b'] == pytest.approx(1.0)
        assert out['up_a'] == pytest.approx(0.0)
        assert out['std'] == pytest.approx(0.0)
        assert sum(out.values()) == pytest.approx(1.0)

    def test_g3_normal_draw_still_yields_owned_up(self):
        """② **普通抽卡仍能产出已拥有的装备**（与 pool 层近似的分界，必须单独断言）。

        `counter < τ`（本抽非保底抽）时该保底恒等：分布逐元素等于基础分布，已拥有的
        UP 保留原概率。若有人把 G3 实现成 pool 层过滤、或把触发条件写成恒真，本断言
        必红（那时 `up_a` 会是 0），而 ① 仍会通过，故 ①② 不可互替。
        """
        engine, _pool, pity_state, _gs, sim, base = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a',), counter=0)

        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)

        assert pity_state.get('g3', 'counter', 0) == 1, '本抽须未到 τ（counter 推进 0 → 1）'
        assert pity_state.get('g3', 'counter', 0) < 50
        for c in base:
            assert out[c] == pytest.approx(base[c]), f'{c}: 非触发抽须恒等'
        assert out['up_a'] > 0, '普通抽卡须仍能产出已拥有的 UP（pool 层近似会让它归零）'

    def test_g3_all_owned_skip_keeps_identity(self):
        """③a `hard_exclude_owned_skip`（形态 a）：全部 UP 已拥有 → 该次保底**不触发**（恒等）。

        判据两条：① 分布逐元素等于基础分布（该次 τ 抽的「必出 UP」不发生）；
        ② **对照**：同一夹具下只拥有一张 UP 时该保底**确实触发**（`up_b` = 1.0）。
        第 ② 条是夹具守卫：没有它，① 无法与「counter 没到 τ」区分开（两处的
        `counter_init=49` 经 advance 都到 50，断言的是同一个 τ）。
        """
        engine, _pool, pity_state, _gs, sim, base = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a', 'up_b'), counter=49)

        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)

        assert pity_state.get('g3', 'counter', 0) == 50, '本抽须已到 τ（否则恒等另有原因）'
        assert sim.owns('up_a') and sim.owns('up_b'), '夹具：两张 UP 都须已拥有'
        for c in base:
            assert out[c] == pytest.approx(base[c]), f'{c}: 全拥有时形态 a 须恒等'

        # 对照：同为 counter=49 / τ=50，只拥有一张 UP 时该保底触发
        engine2, _p2, ps2, _g2, sim2, base2 = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a',), counter=49)
        out2 = engine2.before_draw('g3_pool', ps2, dict(base2), sim2)
        assert out2['up_b'] == pytest.approx(1.0), '对照：未全拥有时须触发'

    def test_g3_all_owned_any_still_gives_one_up(self):
        """③b `hard_exclude_owned_any`（形态 b）：全部 UP 已拥有 → 目标集退化为全部 UP，仍给一件。

        判据四条：① 常驻卡 `std` 归零（质量全进 UP 组）；② 两张已拥有的 UP 分摊全部
        质量（各 > 0、和 = 1.0）：这是「仍给出一件 UP（不保证是未获得的）」的分布层
        表述；③ 该分布**不等于**基础分布（与恒等可区分）；④ **对照**：同夹具下形态 a
        恒等（`up_a` 保留 0.3），故两 type 在「全拥有」这一分支上真的分岔（形态 a / b
        是一对并列假设，实现不得退化为同一个）。
        """
        engine, _pool, pity_state, _gs, sim, base = _g3_engine(
            _G3_ANY_TYPE, owns=('up_a', 'up_b'), counter=49)

        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)

        assert pity_state.get('g3', 'counter', 0) == 50, '本抽须已到 τ'
        assert out['std'] == pytest.approx(0.0)
        assert out['up_a'] > 0 and out['up_b'] > 0, '退化的目标集须仍是两张 UP'
        assert out['up_a'] + out['up_b'] == pytest.approx(1.0)
        assert any(abs(out[c] - base[c]) > 1e-12 for c in base), \
            '形态 b 在全拥有时须真的改变分布（不得退化为恒等）'

        # 对照：形态 a 在同一夹具下恒等
        engine_a, _pa, ps_a, _ga, sim_a, base_a = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a', 'up_b'), counter=49)
        out_a = engine_a.before_draw('g3_pool', ps_a, dict(base_a), sim_a)
        assert out_a['up_a'] == pytest.approx(base_a['up_a']), '对照：形态 a 须恒等'

    def test_g3_initial_count_up_treated_as_owned(self):
        """G3 补充用例（ISSUE-009）：**初始持有**的 UP 同样被视为「已拥有」并被排除。

        `SimView.owns()` 是 `total_holding` 口径（= `initial_counts` + `acquired`），
        故「已拥有」的判定必须把初始持有算进去。本夹具的 `up_a` **只**在
        `initial_counts` 里（`acquired` 为空），A 列只剩 `up_b`。

        判据四条：① 引擎侧 `sim.owns()` 认初始持有（与 `total_holding` 同值）；② A 列
        排除它（`up_a` 归零、`up_b` 独得质量）；③ **反向守卫**：`gacha_state.acquired`
        本身**仍不预填**该卡（P60 语义「本次模拟新获得」，由
        `tests/service/test_gacha_service.py::test_initial_count_not_prepopulated` 钉住）
        ，迁移的是**消费侧口径**，不是 `acquired` 的定义；④ 与「模拟内获得」那一档
        （① 用例）结论一致：两条来源同口径。

        **跨层半条（2026-10-14 已由 S9-5 补齐）**：§六 本条还要求「跨层一致：策略侧
        同样为 True」。策略侧 9 处判据（4 个内置策略文件的 `ctx.acquired.get(...)`）
        已于 **S9-5** 迁到 `ctx.state.total_holding(...)`；跨层断言落在本类的
        `test_g3_engine_and_strategy_agree_on_owned_set`（同一 `GachaState` 上引擎侧
        `sim.owns()` 与策略侧判据结论一致），本用例只保留引擎侧半条。
        """
        engine, _pool, pity_state, gacha_state, sim, base = _g3_engine(
            _G3_SKIP_TYPE, initial_counts={'up_a': 1}, counter=49)

        assert gacha_state.acquired == {}, '初始持有不得预填 acquired（反向守卫）'
        assert sim.owns('up_a') == gacha_state.total_holding('up_a') == 1

        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)

        assert pity_state.get('g3', 'counter', 0) == 50
        assert out['up_a'] == pytest.approx(0.0), '初始持有的 UP 须被排除出目标集'
        assert out['up_b'] == pytest.approx(1.0)

    def test_g3_engine_and_strategy_agree_on_owned_set(self):
        """G3 **跨层半条**（S9-5 收口，2026-10-14，ISSUE-730 / ISSUE-944）。

        §六 G3 补充用例要求同一配置下两侧**同口径**：引擎侧 `SimView.owns()` 判
        「已拥有」的卡集，与策略侧 `ctx.state.total_holding()` 判「已拥有」的卡集
        一致，且**都含初始持有**。S9-4 落地时策略侧 9 处判据仍为 `ctx.acquired`
        （不含初始持有），该半条不可断言；S9-5 迁移后两侧同源。

        判据五条：① 夹具守卫：`up_a` **只**在 `initial_counts` 里（`acquired` 为空）；
        ② 引擎侧：`sim.owns()` 判 `up_a` 已拥有，且 G3 保底触发时把它排除出 A 列；
        ③ **口径同一性守卫**（S9-5 收口订正：**非**跨层判据）：两侧比的是
        `SimView.owns` 与 `GachaState.total_holding`，而 `sim` 即
        `gacha_state.sim_view()`，故两侧是**同一对象的同一函数**，无独立判别力
        （M1「`total_holding` 漏算 `initial_counts`」下两侧同时变空、③ 仍绿）；它拦的
        只是「把 `SimView.owns` 改成读 `acquired`」这类**口径分叉**（该变异下 ③ 红），
        故登记入「未被任何变异覆盖的新断言」清单；④ 策略侧：以**同一个
        `GachaState`** 构造 `StrategyContext`，`stop_on_target` 判 `up_a` 已达标
        （`WaitAction`，不为它抽卡）；⑤ 反向守卫：`gacha_state.acquired` 仍为空
        （P60 语义「本次模拟新获得」不变，迁移的是消费侧）。

        ④ 的遮蔽关系与判别力（2026-10-14 审查收口实测订正）：④ 的牙齿**不在 s3**
        （`stop_on_target` 主循环的 `>= quantity_needed`），而在 **s1**（第二段 banner
        循环的 `_pool_needs_target`）：`pool.is_exchange=False` 使兑换分支整体落空，
        s3 只决定第一段是否跳过该目标，不决定是否返回 `DrawAction`。探针实测（不改
        生产代码）：**本夹具的 `GachaState` 无 `resources`，`can_afford_batch` 恒
        False**，故第二段无论 s1 取何值都不返回 `DrawAction`，④ 在「仅回退 s1」「仅
        回退 s3」「策略侧 3 处全回退」下**都仍绿**（本夹具下 ④ 无判别力，已登记）；
        把 `gem` 补给 state 后复测，仅回退 s1 → `DrawAction`（④ 红）、仅回退 s3 →
        仍 `WaitAction`（④ 绿），遮蔽关系成立。
        """
        from gacha_simulator.core.action import WaitAction
        from gacha_simulator.core.banner import Banner
        from gacha_simulator.core.stop_condition import FixedActionCountCondition
        from gacha_simulator.core.strategy import StrategyContext, create_strategy
        from gacha_simulator.core.target_card import TargetCard, TargetCardSet

        engine, pool, pity_state, gacha_state, sim, base = _g3_engine(
            _G3_SKIP_TYPE, initial_counts={'up_a': 1}, counter=49)

        # ① 夹具守卫：初始持有只写 `initial_counts`，`acquired` 为空
        assert gacha_state.acquired == {}, '初始持有不得预填 acquired'
        assert gacha_state.initial_counts == {'up_a': 1}

        # ② 引擎侧：`owns` 认初始持有；G3 触发时排除该卡
        owned_engine = {c for c in _G3_FEATURED if sim.owns(c) > 0}
        assert owned_engine == {'up_a'}
        out = engine.before_draw('g3_pool', pity_state, dict(base), sim)
        assert pity_state.get('g3', 'counter', 0) == 50, '本抽须已到 τ'
        assert out['up_a'] == pytest.approx(0.0), '引擎侧须把初始持有的 UP 排除出 A 列'

        # ③ 口径同一性守卫：`SimView.owns` 与 `GachaState.total_holding` 同源
        owned_strategy = {c for c in _G3_FEATURED if gacha_state.total_holding(c) > 0}
        assert owned_strategy == owned_engine, \
            'SimView.owns 与 GachaState.total_holding 的口径不得分叉'

        # ④ 策略侧：同一 `GachaState` 上，`stop_on_target` 判 `up_a` 已达标
        banner = Banner(id='g3_pool', name='G3 池', pools={'main': pool})
        ctx = StrategyContext(
            state=gacha_state,
            current_pools=[pool], all_pools=[pool], future_schedules=[],
            target_cards=TargetCardSet([
                TargetCard(card_id='up_a', pool_ids=['g3_pool'], quantity_needed=1),
            ]),
            stop_condition=FixedActionCountCondition(100),
            banners=[banner], all_banners=[banner],
        )
        assert isinstance(create_strategy('stop_on_target', {}).select_action(ctx), WaitAction), \
            '策略侧须同样判 up_a 已达标（初始持有计入「已拥有」）'

        # ⑤ 反向守卫：`acquired` 本身仍不含该卡
        assert gacha_state.acquired == {}, '迁移的是消费侧，不是 acquired 的定义'


# ══════════════════════════════════════════════════════════════════
# P64 S9-4：S9 口径三条（sim / StateView / ctx.state 通道关闭，§六 / §3.10.2 / §3.10.3）
# ══════════════════════════════════════════════════════════════════

class TestS9SimAndStateViewScopes:
    """§六「S9 口径 · sim」与「S9 口径 · StateView」两条的落地面。"""

    def test_sim_reaches_every_registry_type(self):
        """**所有**保底都能读到 `ctx.sim`（非 Optional、永远填充）：三个入口逐条验。

        `sim` 的必填性与「缺参即 `TypeError`」由 S9-2 的
        `test_pity_engine_requires_sim_argument` 钉住（构造面）。本用例补**送达面**：
        对 `BEHAVIOR_REGISTRY` 的**全部**条目（动态取，新增 type 自动纳入）逐条跑真
        管道，断言每个 behavior 在自己的 `ctx` 上拿到的 `sim` **就是**调用方传进去的
        那个 `SimView` 实例（同一性），且三个入口各调度到它一次。

        **强度上限（如实声明）**：这是**结构保证**的机器化，不是「每条保底都真的读了
        sim」：只有 G3 的 `NotOwnedModifier` 会读它，其余条目的行为与 sim 无关。
        本用例的判别力在于「某个入口漏填 / 填了别的对象」：漏填由 `TypeError` 拦
        （构造期），填错对象由同一性断言拦。
        """
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        types = sorted(BEHAVIOR_REGISTRY)
        assert len(types) >= 13, f'registry 条目数异常（实测 {len(types)}）'
        probe = _SimView(_GachaState(initial_counts={'up_a': 1}))

        for t in types:
            name = 'p_' + t
            engine, pool, pity_state, base = _one_pity_pipeline(t, name=name)
            bh = engine.behaviors[name]
            seen = []
            orig_before, orig_after = bh.before_draw, bh.after_draw

            def spy_before(ctx, readonly=False, _o=orig_before):
                seen.append(ctx.sim)
                return _o(ctx, readonly=readonly)

            def spy_after(ctx, _o=orig_after):
                seen.append(ctx.sim)
                _o(ctx)

            bh.before_draw = spy_before
            bh.after_draw = spy_after
            try:
                engine.before_draw(pool.id, pity_state, dict(base), probe)
                engine.get_probabilities(pool.id, pity_state, dict(base), probe)
                engine.after_draw(pool.id, pity_state, 'up_a', probe)
            finally:
                del bh.before_draw
                del bh.after_draw

            assert len(seen) == 3, \
                f'{t}: 三个入口未各调度一次（实测 {len(seen)} 次，夹具或调度面变了）'
            assert all(s is probe for s in seen), \
                f'{t}: 有入口把别的对象（或 None）当 sim 传给了 behavior'

    def test_stateview_isolation_keeps_depends_on_activation(self):
        """§六「S9 口径 · StateView」第 2 条：`depends_on` 的激活传播不受 `StateView` 影响。

        传播由**引擎**在 `PityEngine.after_draw` 里做（`state.set(dep_name, "_active", True)`，
        写的是原始 `PityState`），不经过 Modifier，故与「Modifier 的 `view` 被限定在单个
        命名空间」这条隔离无关（§3.10.3 末段「不影响 `depends_on`」）。判据四条：
        ① 传播前依赖方 inactive；② 被依赖方命中后，**原始账本**上依赖方的 `_active`
        为 True（引擎侧写入、不经 Modifier）；③ 依赖方自己的 `before_draw` 经 **`view`**
        读到该 `_active` 为 True（隔离不挡本保底命名空间），且该 `view` 就是骨架交给
        Modifier 的那个对象（探针同一性）；④ 同一个 `view` 读**被依赖方**命名空间里
        确实存在的键返回 `default`（跨保底读仍关闭，与 S9-1 的负例同口径）。

        **与 S9-1 用例的分工（不可互替）**：S9-1 验「隔离在架构上关闭」与「`ctx.state`
        通道仍在」；本用例验「隔离**没有**把引擎侧的激活传播一起关掉」：若有人把
        `_active` 的读取塞进 Modifier、或改由 view 承担传播，S9-1 全绿而本用例必红。
        """
        base = dict(_G3_BASE)
        pool = Pool(
            id='sv_pool', name='SV 池', cost={'gem': 1},
            rewards=[
                (Reward(id=c, name=c,
                        extra_info={'rarity': 'SSR', 'featured': c in _G3_FEATURED}),
                 base[c])
                for c in _G3_SCOPE_CARDS
            ],
        )
        scope_cards, featured_cards = compute_scope_mappings(pool)[:2]
        spec = PoolPitySpec(
            pity_names=('src', 'dep'),
            scope_cards=scope_cards, featured_cards=featured_cards,
            ssr_ids=set(_G3_SCOPE_CARDS), featured_ids=set(_G3_FEATURED),
        )
        state = PityState()
        engine = PityEngine(
            pool_specs={pool.id: spec},
            pity_defs=[
                PityDef(name='src', btype='rotating', scope='ssr'),
                PityDef(name='dep', btype='hard', scope='ssr', threshold=90,
                        depends_on='src'),
            ],
            state=state, rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
        )

        dep = engine.behaviors['dep']
        assert state.get('dep', '_active', False) is False          # ①

        engine.before_draw(pool.id, state, dict(base), _SIM)
        engine.after_draw(pool.id, state, 'up_a', _SIM)             # src 命中 ssr
        assert state.get('dep', '_active', False) is True           # ② 引擎侧写入原始账本

        # 夹具守卫：被依赖方命名空间里确实有一个可辨的键（否则 ④ 是空断言）
        state.set('src', 'src_only_key', 'src-value')
        assert state.get('src', 'src_only_key') == 'src-value'

        seen = {}

        class _Probe(Modifier):
            def compute_delta(self, view, dist, ctx):
                seen['view'] = view
                seen['own_active'] = view.get('_active')
                seen['foreign'] = view.get('src_only_key', 'DEFAULT')
                return None

        dep._modifiers.append(_Probe())
        engine.before_draw(pool.id, state, dict(base), _SIM)

        assert 'view' in seen, '夹具失效：依赖方的 Modifier 未被调度'
        assert seen['view'] is dep._view, '骨架交给 Modifier 的须是本保底的默认 view'
        assert seen['view']._name == 'dep'
        assert seen['own_active'] is True                           # ③ 隔离不挡自己的键
        assert seen['foreign'] == 'DEFAULT'                         # ④ 跨保底读仍关闭


class TestSimChannelBEquivalence:
    """§六「`sim` 的两条送达通道」中**通道 B** 的独立验收（AUDIT-BREAK-9 追加，强制）。

    通道 B（`StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities`
    经 `_pity_cache`）**完全绕过 `Banner.draw`**，故通道 A 全绿推不出 B 正确。S9-2
    只落了「填充点」断言（`test_channel_b_fills_sim_view`），**1e-12 的逐元素对照
    归本步**（S8-6 收口的登记）。
    """

    def test_channel_b_matches_before_draw(self):
        """通道 B 的分布与 `before_draw` 在**可比条件**下逐元素一致（容差 1e-12）。

        **可比条件（本步自定口径，理由见下）**：两条通道对 counter 的推进不同：
        `before_draw` 走 `readonly=False`、`CounterTracker.advance` 把 counter +1；
        `get_probabilities` 走 `readonly=True`、advance 首行早退（no-op，§3.9.6「查询
        不写计数」）。故「同刻」= **两条通道看到同一个 counter 值**，本用例据此构造：
        A 侧 state 取 `counter_init = τ-1`（advance 后 = τ），B 侧 state 取
        `counter_init = τ`（不 advance），两侧都断言到同一值 τ。

        判据五条：① 两侧看到的 counter 相同（可比条件成立，否则下面的对照无意义）；
        ② 键集相同；③ 逐元素差 ≤ 1e-12；④ 非退化为恒等 `base`（G3 在该抽确实触发，
        否则「一致」可以由「两边都不生效」平凡满足）；⑤ 归一（和 = 1）。

        **未覆盖（登记）**：本用例不判「通道 B 是否落后真实下一抽一格」。实测
        `advance` 在 `readonly=True` 下是 no-op（`CounterTracker.advance` 首行早退，
        另有 `test_n1_readonly_query_does_not_advance_counter` 钉住），故策略在「已抽
        N 次」时查询得到的是 `counter = N` 的分布，而紧接着的那一抽看到 `N+1`：这是
        **本计划之前既有的语义**（§3.9.6「查询不写计数」），本步只按计划断言「可比
        条件下一致」，不改变该语义。
        """
        from gacha_simulator.core import AllPoolsEndCondition, TargetCardSet
        from gacha_simulator.core.strategy import StrategyContext

        # A 侧：counter_init = τ-1，before_draw 的 advance 把它推到 τ
        engine_a, pool, ps_a, _gsa, sim_a, base = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a',), counter=49)
        out_a = engine_a.before_draw(pool.id, ps_a, dict(base), sim_a)

        # B 侧：counter_init = τ，查询不推进（readonly），看到同一个 τ
        engine_b, _pool_b, ps_b, gs_b, _sim_b, _base_b = _g3_engine(
            _G3_SKIP_TYPE, owns=('up_a',), counter=50)
        ctx = StrategyContext(
            state=gs_b, current_pools=[pool], all_pools=[pool],
            future_schedules=[], target_cards=TargetCardSet([]),
            stop_condition=AllPoolsEndCondition(1000.0),
            _pity_engine=engine_b, _pity_state=ps_b,
        )
        out_b = ctx.get_pity_probabilities(pool.id)

        assert ps_a.get('g3', 'counter', 0) == ps_b.get('g3', 'counter', 0) == 50, \
            '可比条件：两条通道须看到同一个 counter（A 侧 advance 后 = τ，B 侧不推进 = τ）'
        assert set(out_a) == set(out_b), '两条通道的键集须相同'
        for c in out_a:
            assert abs(out_a[c] - out_b[c]) <= 1e-12, \
                f'{c}: 通道 B 与 before_draw 不一致（{out_a[c]} vs {out_b[c]}）'
        assert abs(out_b['up_b'] - 1.0) <= 1e-12 and out_b['up_a'] == 0.0, \
            '非退化：G3 在该抽须确实触发（否则「一致」可由两边都不生效平凡满足）'
        assert sum(out_b.values()) == pytest.approx(1.0)


class TestCtxStateChannelClosed:
    """§六「`ctx.state` 通道关闭（ISSUE-103）」的**机器守卫**（S9-4 落地）。

    §3.10.3 的纪律：Modifier 只经 `view` 读状态，**禁止经 `ctx.state` 读任何状态键**
    （含自身命名空间）。「架构上做不到」只对 `view` 形参成立，对 `ctx.state` 靠纪律，
    故纪律需要机器守卫（S9-1 收口明写「6 个真 Modifier 的 AST 扫描由 S9-4 落」）。
    """

    @staticmethod
    def _state_attr_reads(source, label):
        """AST 扫描：源码内所有 `X.state` 属性读取节点的行号。"""
        import ast as _ast
        import textwrap as _tw

        tree = _ast.parse(_tw.dedent(source), filename=label)
        return [n.lineno for n in _ast.walk(tree)
                if isinstance(n, _ast.Attribute) and n.attr == 'state']

    def test_modifier_classes_never_read_state_attribute(self):
        """6 个真 Modifier 的实现内**零** `X.state` 属性读取（含自身命名空间）。

        判据两条：① 被测集合**恰为 6 个**具体 Modifier（自 `pity_modifier` 模块动态
        发现：**发现机制本身**会把新增 Modifier 自动纳入，但下面的等式断言写死了名单，
        故新增 Modifier 时**本用例的集合断言须同步扩表**）；② 每个类的类源码 AST 内
        `X.state` 属性读取数为 0。类源码经 `inspect.getsource` 取，**docstring 不计**
        （AST 只认属性读取节点），故基类 docstring 里对 `ctx.state` 的说明不会误报。

        **强度上限（如实声明）**：拦的是**字面**属性读取（属性名 `state` 落在
        `Attribute` 节点上）；把键名写成**字符串常量**的形态拦不住，如
        `getattr(ctx, 'state')` / `vars(ctx)['state']` / `ctx.__dict__['state']`
        （AST 里没有 `attr == 'state'` 的节点，实测扫描结果为空）。反之把 `ctx` 先赋给
        别的名字再读 `state`（`c = ctx; c.state.get(...)`）**拦得住**：属性名仍是
        `state`，扫描照常命中。字符串键形态由
        `test_modifier_compute_delta_runs_with_ctx_state_probe` 的运行期探针补。
        """
        import inspect as _inspect

        from gacha_simulator.core import pity_modifier as pm

        mods = sorted(
            (c for c in vars(pm).values()
             if isinstance(c, type) and issubclass(c, pm.Modifier)
             and c is not pm.Modifier),
            key=lambda c: c.__name__)
        assert [c.__name__ for c in mods] == [
            'HardModifier', 'NonFeaturedModifier', 'NotOwnedModifier',
            'RotatingModifier', 'SelectedModifier', 'SoftModifier'], \
            f'「6 个真 Modifier」的集合变了：{[c.__name__ for c in mods]}'

        for c in mods:
            hits = self._state_attr_reads(_inspect.getsource(c), c.__name__)
            assert hits == [], (
                f'{c.__name__}: 实现内出现 {len(hits)} 处 `X.state` 属性读取'
                f'（行号 {hits}）：Modifier 只经 view 读状态（ISSUE-103）')

    def test_pity_module_has_no_ctx_state_key_read(self):
        """`pity.py` 内不再出现 `ctx.state.get(`（S9-1 收口给出的可机械复核判据）。

        **不得按字面 `grep 'ctx.state'` 归零**（该判据恒不可达）：全文件代码命中还剩
        `SoftPityMixin` 的 fork（`PityContext(draw=..., current=..., state=ctx.state)`）
        与 `TargetedBehavior._selected_card` 的 `StateView(ctx.state, self._name)`，
        两者都是**构造透传 / 视图构造**、不含键读取（§六 的口径限定）。故判据取三条：
        ① 字面判据（**代码口径**）：`ctx.state.get(` 的文本命中全部落在注释 / 字符串内
           （若日后文档里的同串被删，本判据退化为恒真，真值面只剩 ② ③）；
        ② 加强判据（AST，对**任何**对象而非只看 `ctx`）：不存在以 `.state` 为接收者的
           `.get(...)` 调用或下标读取；
        ③ 站点判据：`ctx.state` 的出现点**恰为两处**，其直接父节点类型分别是 `Call`
           （`StateView(ctx.state, ...)` 的实参）与 `keyword`（fork 的 `state=ctx.state`）
           ：任何新增的 `ctx.state` 用法（读取、传参、赋值）都会让本断言红，须人工
           复核后更新。
        """
        import ast as _ast
        import io as _io
        import tokenize as _tokenize

        path = ROOT / 'gacha_simulator' / 'core' / 'pity.py'
        src = path.read_text(encoding='utf-8')
        # ① 字面判据**只在代码口径下成立**：`ctx.state.get(` 的全部文本命中须落在
        #    注释 / 字符串（docstring）内。裸 `grep` 归零恒不可达（S9-1 收口的口径
        #    限定：pity.py 的迁移说明 docstring 里就写着这个串），代码级归零由下面
        #    的 AST 判据 ② 承担。
        hits = [i for i, line in enumerate(src.splitlines(), 1)
                if 'ctx.state.get(' in line]
        masked = set()
        for tok in _tokenize.generate_tokens(_io.StringIO(src).readline):
            if tok.type in (_tokenize.COMMENT, _tokenize.STRING):
                masked.update(range(tok.start[0], tok.end[0] + 1))
        code_hits = [ln for ln in hits if ln not in masked]
        assert code_hits == [], (
            f'`ctx.state.get(` 出现在**代码**里（行号 {code_hits}）；'
            f'文档 / 注释里的同串命中不算违规，代码里的算')

        tree = _ast.parse(src, 'pity.py')
        offenders = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute) \
                    and node.func.attr in ('get', '__getitem__') \
                    and isinstance(node.func.value, _ast.Attribute) \
                    and node.func.value.attr == 'state':
                offenders.append(node.lineno)
            if isinstance(node, _ast.Subscript) \
                    and isinstance(node.value, _ast.Attribute) \
                    and node.value.attr == 'state':
                offenders.append(node.lineno)
        assert offenders == [], \
            f'pity.py 出现以 .state 为接收者的键读取，行号 {offenders}'

        sites = []
        for parent in _ast.walk(tree):
            for child in _ast.iter_child_nodes(parent):
                if isinstance(child, _ast.Attribute) and child.attr == 'state' \
                        and isinstance(child.value, _ast.Name) \
                        and child.value.id == 'ctx':
                    sites.append((child.lineno, type(parent).__name__))
        assert sorted(t for _l, t in sites) == ['Call', 'keyword'], (
            '`ctx.state` 的出现点须恰为两处（StateView 构造实参 + SoftPityMixin fork '
            f'的构造透传），实测 {sites}')

    def test_modifier_compute_delta_runs_with_ctx_state_probe(self):
        """运行期补面：`ctx.state` 换成**任何访问即抛**的探针后，六个 Modifier 的
        `compute_delta` 仍正常返回。

        AST 扫描拦的是**字面**属性读取（属性名 `state` 落在 `Attribute` 节点上），拦不住
        把键名写成**字符串常量**的形态（`getattr(ctx, 'state')` / `vars(ctx)['state']` /
        `ctx.__dict__['state']`）；本用例把 `ctx.state` 换成抛异常的探针（`_NoCtxStateRead`
        的 `__getattr__` 对任何属性名即抛），故「该相位内触达 `ctx.state`」这一事实本身会
        让本用例失败，字符串键形态也拦得住（取到探针后读它的任何键都要过一次
        `__getattr__`）。

        **强度上限**：只覆盖本次调用走到的分支（六个 Modifier 都构造成「条件成立」
        形态，即各自触发分支），未走到的分支仍只有 AST 扫描这一层。
        """
        from gacha_simulator.core.pity_modifier import (
            HardModifier, NonFeaturedModifier, NotOwnedModifier, RotatingModifier,
            SelectedModifier, SoftModifier,
        )

        ctx = PityContext(
            draw=DrawInfo(
                pool_id='g3_pool', pool_instance_id='g3_pool_0',
                reward_id='', reward_rarity='', is_featured=False,
                scope_cards={'ssr': _G3_SCOPE_CARDS},
                featured_cards={'ssr': _G3_FEATURED},
                base_probabilities=dict(_G3_BASE),
                rarity_rank={'ssr': 0},
            ),
            current=dict(_G3_BASE),
            state=_NoCtxStateRead(),      # 触达即 AssertionError（ISSUE-103 的机器面）
            sim=_SimView(_GachaState(initial_counts={'up_a': 1})),
        )

        mods = [
            ('HardModifier', HardModifier('ssr', threshold=0)),
            ('SoftModifier', SoftModifier('ssr', deltas=((1, 5.0),))),
            ('RotatingModifier', RotatingModifier('ssr')),
            ('NonFeaturedModifier', NonFeaturedModifier('ssr')),
            ('SelectedModifier', SelectedModifier('ssr', tau=1)),
            ('NotOwnedModifier', NotOwnedModifier('ssr', threshold=0,
                                                  on_all_owned='skip')),
        ]
        assert len(mods) == 6

        results = {}
        for label, mod in mods:
            view = StateView(PityState(), 'x')
            results[label] = mod.compute_delta(view, dict(_G3_BASE), ctx)

        assert all(r is None or isinstance(r, dict) for r in results.values())
        assert results['NotOwnedModifier'] is not None, (
            '夹具失效：该相位须真的走到读 `ctx.sim` 的分支'
            '（否则本用例的探针面是空的）')
