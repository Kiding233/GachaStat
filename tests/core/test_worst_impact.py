import pytest

from gacha_simulator.core.config_store import PityDef as _PityDef
from gacha_simulator.core.worst_impact import (
    ConditionalResourceDistribution,
    WorstImpactAnalyzer,
    WorstImpactResult,
)
# P64 S9-2：`PityContext.sim` 非 Optional（3.10.2）------------------------------
# 直构 ctx 与 `PityEngine` 三个调度入口（before_draw / after_draw /
# get_probabilities）的 `sim` 都是**必填**（缺参在构造 ctx 时即 TypeError）。本文件
# 只验与「玩家持有」无关的机制，故用**空 state 的视图**作最小替身。
from gacha_simulator.core.state import GachaState as _GachaState, SimView as _SimView

_SIM = _SimView(_GachaState())



def _check_success_from_counts(obtained, target_specs):
    if not target_specs:
        return True
    for card_id, needed in target_specs.items():
        if obtained.get(card_id, 0) < needed:
            return False
    return True


def test_check_success_from_counts_all_obtained():
    assert _check_success_from_counts(
        {'char_a': 1, 'char_b': 2}, {'char_a': 1, 'char_b': 2}
    ) is True


def test_check_success_from_counts_partial():
    assert _check_success_from_counts(
        {'char_a': 1, 'char_b': 0}, {'char_a': 1, 'char_b': 1}
    ) is False


def test_check_success_from_counts_empty_targets():
    assert _check_success_from_counts({'char_a': 1}, {}) is True


def test_check_success_from_counts_missing_card():
    assert _check_success_from_counts(
        {'char_a': 1}, {'char_b': 1}
    ) is False


def test_conditional_resource_distribution():
    simulation_results = [
        {
            'card_counts': {'char_a': 1, 'char_b': 1},
            'final_resources': {'draw_resource': 1000},
        },
        {
            'card_counts': {'char_a': 0, 'char_b': 1},
            'final_resources': {'draw_resource': 200},
        },
        {
            'card_counts': {'char_a': 1, 'char_b': 1},
            'final_resources': {'draw_resource': 800},
        },
    ]
    target_specs = {'char_a': 1, 'char_b': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)

    assert len(dist.success_resources) == 2
    assert len(dist.failure_resources) == 1
    assert dist.success_resources == [1000, 800]
    assert dist.failure_resources == [200]


def test_conditional_distribution_all_condition():
    simulation_results = [
        {'card_counts': {'a': 1}, 'final_resources': {'draw_resource': 1000}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 200}},
    ]
    target_specs = {'a': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)

    all_dist = dist.get_conditional_distribution('all')
    assert all_dist.n == 2
    assert all_dist.mean() == 600.0


def test_worst_case_resource_failure():
    simulation_results = [
        {'card_counts': {'a': 1}, 'final_resources': {'draw_resource': 1000}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 200}},
        {'card_counts': {'a': 0}, 'final_resources': {'draw_resource': 100}},
    ]
    target_specs = {'a': 1}

    def checker(r):
        return _check_success_from_counts(r.get('card_counts', {}), target_specs)

    dist = ConditionalResourceDistribution(simulation_results, checker)
    worst = dist.get_worst_case_resource('failure', 0.5)
    assert worst == 150.0


def test_worst_impact_result_dataclass():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.3, 1: 0.5, 2: 0.2},
        expected_pools=0.9,
    )
    assert result.worst_resource == 500.0
    assert result.pity_coverage == 0.35
    assert result.expected_pools == 0.9


def test_worst_impact_result_get_p_ge():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.1, 1: 0.35, 2: 0.4, 3: 0.15},
        expected_pools=1.6,
    )
    assert abs(result.get_p_ge(0) - 1.0) < 1e-9
    assert abs(result.get_p_ge(1) - 0.9) < 1e-9
    assert abs(result.get_p_ge(2) - 0.55) < 1e-9
    assert abs(result.get_p_ge(3) - 0.15) < 1e-9
    assert abs(result.get_p_ge(4) - 0.0) < 1e-9


def test_worst_impact_result_max_consecutive_at_threshold():
    result = WorstImpactResult(
        worst_resource=500.0,
        pity_coverage=0.35,
        pool_distribution={0: 0.1, 1: 0.35, 2: 0.4, 3: 0.15},
        expected_pools=1.6,
    )
    assert result.get_max_consecutive_at_threshold(1.0) == 0
    assert result.get_max_consecutive_at_threshold(0.9) == 1
    assert result.get_max_consecutive_at_threshold(0.5) == 2
    assert result.get_max_consecutive_at_threshold(0.1) == 3


def test_worst_impact_result_empty_distribution():
    result = WorstImpactResult(
        worst_resource=0.0,
        pity_coverage=0.0,
    )
    assert result.get_p_ge(0) == 0.0
    assert result.get_p_ge(1) == 0.0
    assert result.get_max_consecutive_at_threshold(0.5) == 0


# ════════════════════════════════════════════════════════
# 虚拟池的卡集合对齐（原 ISSUE-006 / P17 补完）
# ════════════════════════════════════════════════════════

def _wi_config():
    """用真实 config.toml 构造最差影响分析的配置。"""
    from pathlib import Path
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
    cfg_path = (Path(__file__).resolve().parents[2]
                / 'gacha_simulator' / 'config' / 'config.toml')
    store = load_toml(str(cfg_path))
    return WorstImpactAnalyzer([], {}, store).prepare_simulation_config(50000.0)


def test_synthetic_pool_card_level_pipe_neither_drops_nor_invents_cards():
    """虚拟池的卡级管道不得静默丢卡、也不得引入槽位键。

    **S8-4 改写（ISSUE-504 / §3.9.3）**：原用例 `test_synthetic_pool_aggregate_
    conserves_probability` 断言的是**槽位级聚合**的守恒——`_build_pity_engine` 曾用
    **原始**卡 id 建 `scope_cards` / `featured_cards`（`limited_ssr_2`），而合成池里
    是重命名后的 `_wi_featured_{i}`，于是 `aggregate_probs_by_rarity` 认不出池内绝大
    多数卡属于哪个槽位、把它们丢弃（只剩 `{'ssr': 0.004}`，池内 99.6% 的概率凭空
    消失）。**S8-2 起「卡级 → 槽位级聚合」这一步在生产上不存在**（`banner.draw`
    卡级直传），故本用例改钉同一风险的**卡级形态**，断言内容不变（不得丢卡）：
    管道输出的键集必须与池内 reward id 逐一相同，且归一化后 Σ = 1。

    这同时是「对齐不变量」在管道侧的同源守卫：卡集合若与池内 id 对不上，
    `transfer_linear` 的 `sum(dist[c] for c in Q)` 会直接抛 `KeyError`（而不是像
    聚合那样静默丢卡），故本用例失败时的症状是异常而非断言——两者都由本行覆盖。

    **counter 预置 85（同 `test_synthetic_pool_pity_actually_fires`）**：不预置则
    `ssr_soft` 在爬升起点不触发、`before_draw` 恒等返回，本条的三项断言全部空转
    （恒等输入必然键集相同、Σ 恒为 1）。末条的「非空转守卫」正是为此。
    """
    from gacha_simulator.core.pity import PityState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    key = f'{banner.id}.main'
    spec = engine.get_spec(key)
    assert spec is not None, '本配置应把保底绑到虚拟池'

    probs = {r.id: p for r, p in pool.rewards}
    state = PityState.from_dict(cfg['pity_state_init'])
    state.set(spec.pity_names[0], 'counter', 85)   # 软保底爬升中段，必触发
    out = engine.before_draw(key, state, probs, sim=_SIM)

    assert set(out) == set(probs), (
        f'卡级管道改了键集：多出 {sorted(set(out) - set(probs))}、'
        f'丢掉 {sorted(set(probs) - set(out))}'
    )
    assert abs(sum(out.values()) - 1.0) < 1e-12, \
        f'Σ = {sum(out.values())}（卡级管道未归一）'
    assert out != probs, '保底未改动分布（本用例的键集 / 归一断言随之空转）'


def test_synthetic_pool_pity_actually_fires():
    """虚拟池的保底必须真的改动分布。

    P17（最差影响保底匹配修复，已完成）的记录称「修复后保底正确触发」，但实测
    200 抽里 `before_draw` 改动分布的次数为 0：保底绑上了池，却因为目标槽位的卡
    集合对不上（聚合把 UP 卡算进了普通槽），`target_total <= 0` 每次早退。
    """
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')
    assert spec.pity_names, '本配置应有绑到虚拟池的保底'

    fired = []
    orig = engine.before_draw

    def spy(key, st, dist, sim):
        # P64 S9-2：`before_draw` 的 `sim` 是必填参（§3.10.2），探针须同签名转发
        out = orig(key, st, dist, sim)
        if out != dist:
            fired.append(key)
        return out

    engine.before_draw = spy
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)   # 软保底爬升中段，必触发
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        engine.before_draw = orig

    assert fired, '保底未改动分布——虚拟池的保底没生效'


def test_synthetic_pool_card_level_sum_is_one_when_pity_fires():
    """保底生效时，喂给抽卡的卡级字典必须归一（Σ = 1）。

    虚拟池此前从不触发保底，故那段 `scale_factors` 还原路径在它身上从未跑过；
    表修对之后它第一次跑起来，这条断言即为其验收面。
    """
    from gacha_simulator.core import pool as pool_mod
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')

    captured = {}
    orig_apply = pool_mod.Pool._apply_probabilities

    def spy_apply(self, probs):
        captured['card'] = dict(probs)
        return orig_apply(self, probs)

    pool_mod.Pool._apply_probabilities = spy_apply
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        pool_mod.Pool._apply_probabilities = orig_apply

    card = captured['card']
    assert abs(sum(card.values()) - 1.0) < 1e-12, \
        f'Σ = {sum(card.values())}（保底调整未逐卡落实）'


def test_synthetic_pool_specs_satisfy_alignment_invariants():
    """每个虚拟池的 spec 都必须满足两条不变量（构造期保证的根因守卫）。

    不变量成立时，「卡 id → 稀有度」的推断（S8 起唯一实现是
    `PityEngine._infer_rarity`，喂状态路径）对池内每张卡必然答对；反过来说，
    这两条不变量被破坏就是本类缺陷的根因。

    **S8-2 改写（ISSUE-504）**：原第 ③ 条用 `pool.infer_rarity_from_spec`（A 实现）
    逐卡比对，该函数已随其最后一批消费者删除（`banner.draw` 的 `scale_factors`
    还原段与 `aggregate_probs_by_rarity` 的内部调用），故第 ③ 条改为**直接查
    `scope_cards` 的反查表**：这正是被删函数当年的唯一判据来源，断言内容
    （池内每张卡都查得到、且与它声明的稀有度一致）不变。
    """
    cfg = _wi_config()
    engine = cfg['pity_engine']
    checked = 0
    for banner in cfg['pools']:
        spec = engine.get_spec(f'{banner.id}.main')
        assert spec is not None
        # ① ssr_ids ⊆ scope_cards['ssr']（大小写归一后）
        #    用包含而非相等：`batch_simulator` 建 ssr_ids 时排除 `_no_card`
        #    （:1091 的 `cid != '_no_card'`），而 `compute_scope_mappings` 会把它计入
        #    scope_cards，故 SSR 稀有度的 `_no_card` 会让等号在**合法配置**上误红。
        #    这里需要的是「查得到」，即包含。
        sc_ssr = {c.lower() for c in spec.scope_cards.get('ssr', ())}
        assert {c.lower() for c in spec.ssr_ids} <= sc_ssr, \
            f'{banner.id}: ssr_ids 未被 scope_cards["ssr"] 覆盖'
        # ② featured_ids ⊆ scope_cards
        all_sc = {c.lower() for cs in spec.scope_cards.values() for c in cs}
        assert {c.lower() for c in spec.featured_ids} <= all_sc, \
            f'{banner.id}: featured_ids 不在 scope_cards 内'
        # ③ 池内每张卡都查得到，且与它的真实稀有度一致
        card_rarity = {c.lower(): r.lower()
                       for r, cs in spec.scope_cards.items() for c in cs}
        pool = banner.pools['main']
        for rwd, _ in pool.rewards:
            real = (rwd.extra_info.get('rarity') or '').lower() or None
            got = card_rarity.get(rwd.id.lower())
            assert got == real, \
                f'{rwd.id} @ {banner.id}: 查得 {got!r} vs 真实 {real!r}'
            checked += 1
    assert checked > 0, '未扫到任何卡——本测试无验收面'


def test_synthetic_pool_pity_moves_mass_into_featured_slot():
    """保底生效后，质量必须是从低稀有度槽搬进 scope 槽（证明方向，不只是「有变化」）。

    **目标集口径（2026-10-10，S4-2 随裁决 7B 改写；S8-2 迁到卡级）**：本用例原断言
    「搬进 `ssr_featured`（限定槽）、从 `ssr`（普通槽）取」，那是样例配置
    `config.toml` 的 `ssr_soft` 带 `target_featured = true` 时的形态。裁决 7B
    （2026-10-05）把 `soft_*` + `target_featured = true` 定为 `ConfigError`
    （soft 的目标集恒为 scope 全集，该形态可等价分解为「稀有度级 + 卡级」两步
    转移），样例配置随之删去该行，故本用例改断言**方向**：质量自低稀有度卡搬入
    **SSR 卡集**（`spec.scope_cards['ssr']`），低稀有度侧一律下降。
    **S8-2 起管道是卡级**（§3.9.1），故断言面由槽位名换成卡 id（原写 `scope_slots`
    的槽名，卡级管道下 `dist` 的键里根本没有它们）。断言目的（「方向而非仅
    『有变化』」）不变，变的只是目标集口径与键空间。
    """
    from gacha_simulator.core.pity import PityState
    from gacha_simulator.core.state import GachaState

    cfg = _wi_config()
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    pool = banner.pools['main']
    spec = engine.get_spec(f'{banner.id}.main')
    ssr_cards = tuple(spec.scope_cards['ssr'])

    seen = []
    orig = engine.before_draw

    def spy(key, st, dist, sim):
        # P64 S9-2：`before_draw` 的 `sim` 是必填参（§3.10.2），探针须同签名转发
        out = orig(key, st, dist, sim)
        if out != dist:
            seen.append((dict(dist), dict(out)))
        return out

    engine.before_draw = spy
    try:
        st = PityState.from_dict(cfg['pity_state_init'])
        st.set(spec.pity_names[0], 'counter', 85)
        banner._use_adjusted = False
        pool._use_adjusted = False
        banner.draw(GachaState(), engine, st, pool)
    finally:
        engine.before_draw = orig

    assert seen, '保底未生效——无验收面'
    before, after = seen[0]
    lower = [c for c in before if c not in ssr_cards]
    assert lower, '本用例需要 scope 之外的低稀有度卡作取源面'
    assert sum(after[c] for c in ssr_cards) > sum(before[c] for c in ssr_cards), \
        f'保底未把质量搬进 SSR 卡集：{before} → {after}'
    for c in lower:
        assert after[c] < before[c], \
            f'保底未从低稀有度卡 {c} 取质量：{before} → {after}'


# ════════════════════════════════════════════════════════════
# P64 S8-5：卡集合按池对齐（ISSUE-006 / ISSUE-201）+ 五类边界（§3.9.5）
# ════════════════════════════════════════════════════════════
#
# **旧词汇 → S8 实现面的映射**。S8-5 的任务行沿用旧词汇（`T` / `P` / `⟨m,p⟩`），
# 逐条对应的权威表述是《保底算子表示切换·因子向量转增量向量·改写方案》§3 的表
# （该表与 §3.9.5 同序，编号即下表编号）：
#
# | # | 旧词汇 | 旧含义 | S8 实现面 |
# |---|--------|--------|-----------|
# | 1 | `T == 0` | 目标组当前概率为 0 | `shape='current'` 时 `p(A) <= 0` → `transfer_linear` 返 `None`；`declared` 的机制按 `w` 分配、`p(A) = 0` 时仍能转移，只有 `w(A) = 0` 才返 `None` |
# | 2 | `P == 0` | U 内全零 | `p(Q) <= 0`（无货可取）→ 返 `None` |
# | 3 | `P − T == 0` | 目标占满 U | `p(Q) == amount`（源组被搬空），公式自然涵盖、无分支 |
# | 4 | 目标集为空 | `target_cards == ()` | 调用方在 `compute_delta()` 开头返 `None`（不得把空集传给助手） |
# | 5 | scope 键缺失 | 该稀有度无卡 | `scope_cards.get(scope, ())` / `featured_cards.get(scope, ())` 取空集 → `A` 为空 → 返 `None`，**禁止下标** |
# | 6 | `⟨m,p⟩ ≠ 1` | U 外更高稀有度被归一化缩放 | `Σδ = 0` ⟹ `Σ(p + δ) = 1`，归一化退化为恒等（旧因子实现该形状实测 Σ = 1.009） |
# | 7 | `T ⊄ U` | 目标解析器返回 U 之外的卡 | 构造期 `ConfigError`（**S8 未实现、只登记**，见 §3.9.5 的 S8 收口注） |
# | 8 | 归一化后总量 ≤ 0 | 退化保护 | `_apply_delta` 返原分布 |
#
# S8-5 的五个边界面是 #1 / #2 / #3 / #5 / #6（#4 与 #8 不在这五个之内）。
#
# **已由 S8-1 / S8-3 覆盖、本组不重复的项**（只登记落点）：
#   · 助手级四守卫 `pQ <= 0` / `amount <= 0` / `pA <= 0` / `wA <= 0`：
#     `tests/core/test_pity_rotating.py::TestTransferLinear::test_transfer_linear_guards`
#     （`pQ` / `amount` / 未知 shape / 缺 weights）
#   · `pA <= 0` 与 `declared` 例外（`wA <= 0` 才返 `None`，`p(A) = 0` 时仍可分配）：
#     `tests/core/test_pity_rotating.py::TestTransferLinear::test_transfer_linear_declared_survives_zero_pA`
#   · 「目标集为空 → 每个机制返 `None`」（#4）：
#     `tests/core/test_pity_modifier.py::test_empty_target_set_returns_none`（七机制各一条）
#   · `_apply_delta` 的三形态与退化保护（#8）：
#     `tests/core/test_pity_modifier.py` 的框架面用例
#
# **本组断言的对象与上述用例不同**：后者直驱 `Modifier.compute_delta` / 助手，
# 本组一律经 **worst_impact 第二处 `PoolPitySpec` 构造点**（`_build_pity_engine`，
# §3.9.3 处置表与 §3.9.3 B 段所指的构造点）与 `PityEngine.before_draw` 的卡级管道，
# 故覆盖的是「真实虚拟池 + 真实 spec」上的形态。

def _wi_config_custom(pity_defs=None, distribution=None, duration_days=21):
    """可控的最差影响配置：保底定义整表替换 + 池形状经 `custom_pool_config` 注入。

    `custom_pool_config` 走 `WorstImpactAnalyzer._apply_custom_pool_config`（**不读**
    `store.pools`），故 `_rewards` / `_featured_ids` 完全由 `distribution` 决定；99 个
    虚拟池仍由 `prepare_simulation_config` 逐个构造，`_build_pity_engine` 这一
    `PoolPitySpec` 构造点因此照常被本组用例覆盖。

    `distribution` 的条目形如 `{'card_id', 'rarity', 'featured', 'probability'}`
    （`probability` 为**百分数**，与 TOML 同口径）。
    """
    import copy
    from pathlib import Path
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.worst_impact import WorstImpactAnalyzer

    cfg_path = (Path(__file__).resolve().parents[2]
                / 'gacha_simulator' / 'config' / 'config.toml')
    store = copy.deepcopy(load_toml(str(cfg_path)))
    if pity_defs is not None:
        store.pity.pities = list(pity_defs)
    custom = ({'distribution': list(distribution), 'duration_days': duration_days}
              if distribution is not None else None)
    return WorstImpactAnalyzer(
        [], {}, store, custom_pool_config=custom,
    ).prepare_simulation_config(50000.0)


def _wi_pool0(cfg):
    """取虚拟池 0 的 `(engine, key, spec, 池内卡级分布)`。

    **`Pool.rewards` 的元素是 `(Reward, prob)` 二元组**（ISSUE-201），故按二元组解包
    （口径同 §3.9.1 的 `{r.id: p for r, p in pool.rewards}`）。
    """
    banner, engine = cfg['pools'][0], cfg['pity_engine']
    assert engine is not None, '本配置应构造出 pity_engine'
    key = f'{banner.id}.main'
    spec = engine.get_spec(key)
    assert spec is not None, f'{key} 未绑到 spec'
    probs = {r.id: p for r, p in banner.pools['main'].rewards}
    assert probs, f'{key} 池内无 reward'
    return engine, key, spec, probs


def _wi_state(cfg, pity_name=None, counter=None, **state_kw):
    """从快照派生一份 `PityState`（可预置计数与状态键）。"""
    from gacha_simulator.core.pity import PityState

    state = PityState.from_dict(cfg['pity_state_init'])
    if counter is not None:
        state.set(pity_name, 'counter', counter)
    for k, v in state_kw.items():
        state.set(pity_name, k, v)
    return state


def test_worst_impact_scope_cards_aligned_to_pool():
    """虚拟池的卡集合必须与池内 reward id 对齐（ISSUE-006 / ISSUE-201）。

    判据：对**每个**虚拟池的**每个** scope，
    `set(spec.scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`；`featured_cards`
    同式。`Pool.rewards` 的元素是 `(Reward, prob)` 二元组，故按二元组解包：写成
    `{r.id for r in pool.rewards}` 会立即 `AttributeError: 'tuple' object has no
    attribute 'id'`（ISSUE-201 记的正是这一处）。

    **本用例的作用是「保留不变量」**（S8-5 的 ISSUE-006 追加）：按池重建卡集合已由
    `e32577f` 落地、构造期覆盖不变量已就位（`_build_pity_engine` 的
    `_covered` / `_missing` / `ValueError`），S8 期间**无增量可做**，故本用例只钉住
    两件事：① 不变量在全部虚拟池上成立；② 它**非空转**：池内那张 UP 卡已被改名为
    `_wi_featured_{i}`，卡集合若退回 `e32577f` 之前的「原始卡 id」形态（`scope_cards`
    写 `limited_ssr_1` 而非池内的 `_wi_featured_0`），断言 ① 必红。
    """
    from gacha_simulator.core.worst_impact import MAX_POOLS

    cfg = _wi_config()
    engine = cfg['pity_engine']
    assert engine is not None, '本配置应构造出 pity_engine'

    checked_pools = 0
    checked_scopes = 0
    for banner in cfg['pools']:
        key = f'{banner.id}.main'
        spec = engine.get_spec(key)
        assert spec is not None, f'{key} 未绑到 spec'
        reward_ids = {r.id for r, _ in banner.pools['main'].rewards}
        assert reward_ids, f'{key} 池内无 reward'
        for scope, cards in spec.scope_cards.items():
            outside = set(cards) - reward_ids
            assert not outside, (
                f'{key} scope={scope!r}: scope_cards 含池外卡 {sorted(outside)}'
                f'（池内 {sorted(reward_ids)}）')
            checked_scopes += 1
        for scope, cards in spec.featured_cards.items():
            outside = set(cards) - reward_ids
            assert not outside, (
                f'{key} scope={scope!r}: featured_cards 含池外卡 {sorted(outside)}')

        checked_pools += 1

    assert checked_pools == MAX_POOLS == len(cfg['pools']), \
        f'未扫满虚拟池：{checked_pools} / {MAX_POOLS}'
    assert checked_scopes > 0, '未扫到任何 scope（本用例无验收面）'

    # 非空转守卫：池内 UP 卡已改名，原始名不在池内（卡集合若用原始名，上面的
    # 子集断言必红）
    ids0 = {r.id for r, _ in cfg['pools'][0].pools['main'].rewards}
    spec0 = engine.get_spec('_worst_impact_pool_0.main')
    assert '_wi_featured_0' in ids0, '虚拟池 0 的 UP 卡应已改名为 _wi_featured_0'
    assert '_wi_featured_0' in spec0.scope_cards['ssr'], \
        'scope_cards["ssr"] 未含池内那张 UP 卡'
    assert 'limited_ssr_1' not in ids0, (
        '池内 UP 卡仍是原始 id（本用例的对齐判据随之失去判别力）')


# ── 五类边界（§3.9.5 / 改写方案 §3 的 #1 / #2 / #3 / #5 / #6）──

def test_worst_impact_boundary_t_zero():
    """边界 #1 `T == 0`（目标组当前概率为 0）：恒等，**不得把零概率的 UP 抬起**。

    S8 实现面：`shape='current'` 时 `p(A) <= 0` → `transfer_linear` 返 `None`
    （`u_A = p_c/p(A)` 未定义）。旧实现 `share` 分支会把零概率的目标槽从 0 抬起来
    （§3.9.5 第 1 行的历史记录），本用例的判别点正是「抬不抬」。

    **覆盖登记**：助手级 `pA <= 0` 守卫与 `declared` 例外已覆盖于
    `tests/core/test_pity_rotating.py::TestTransferLinear::test_transfer_linear_declared_survives_zero_pA`，
    本用例不重复它，断言的是 worst_impact 构造点 + 卡级管道上的形态（目标组被前序
    算子清空后整条恒等）。
    """
    cfg = _wi_config_custom(pity_defs=[
        _PityDef(name='rot', btype='rotating', scope='ssr', guaranteed_init=True)])
    engine, key, spec, probs = _wi_pool0(cfg)

    A = tuple(spec.featured_cards['ssr'])
    Q = tuple(c for c in spec.scope_cards['ssr'] if c not in set(A))
    assert A and Q, '本用例需要 scope 内既有 featured 又有非 featured 卡'
    p_q = sum(probs[c] for c in Q)
    assert p_q > 0, '取源组须有货（否则命中的是 `p(Q) = 0` 守卫，不是本条）'

    # 构造「目标组已被前序算子清空」的当前分布：UP 的质量移给一张普通 SSR
    zeroed = dict(probs)
    zeroed[Q[0]] += zeroed[A[0]]
    zeroed[A[0]] = 0.0
    assert sum(zeroed.values()) == pytest.approx(1.0)
    assert sum(zeroed[c] for c in A) == 0.0, '本用例的前置：p(A) == 0'

    out = engine.before_draw(key, _wi_state(cfg), zeroed, sim=_SIM)
    assert out == zeroed, (
        f'p(A) = 0 时须整条恒等（不得把零概率目标抬起）：{zeroed} → {out}')
    assert abs(sum(out.values()) - 1.0) < 1e-12


def test_worst_impact_boundary_p_zero():
    """边界 #2 `P == 0`（U 内全零 / 无货可取）：恒等，且不得抛 `ZeroDivisionError`。

    S8 实现面：`p(Q) <= 0` → `transfer_linear` 返 `None`。本用例让 `Q` **非空**但
    `p(Q) = 0`、同时 `p(A) > 0`，故命中的是 `pQ <= 0` 这一支（不是 `pA <= 0`）。

    **断言强度声明**：本形态下机制侧的转移量 `amount = p(Q) = 0`，故「守卫返回
    `None`」与「返回全零增量」在管道输出上同值，本用例能拦的是**抛异常**（两条
    守卫同时移除时 `dist[c]/pQ` 会 `ZeroDivisionError`）与**分布被改动**，
    **拦不住**「把 `None` 改成全零字典」这类等价改写。守卫的判别性断言在助手级
    （`tests/core/test_pity_rotating.py::TestTransferLinear::test_transfer_linear_guards`
    的 `transfer_linear(dist, ('a',), (), 0.5) is None`：`Q` 为空而 `amount > 0`，
    守卫一旦移除即产出 `Σδ = 0.5` 的未配平增量、归一化会缩放全部分布）。
    """
    cfg = _wi_config_custom(pity_defs=[
        _PityDef(name='h', btype='hard', scope='sr', threshold=5)])
    engine, key, spec, probs = _wi_pool0(cfg)

    A = tuple(spec.scope_cards['sr'])
    Q = tuple(spec.scope_cards['r'])
    assert A and Q, '本用例需要 scope 与其更低稀有度都非空'

    # 当前分布：更低稀有度被前序算子搬空，质量全归 sr
    zeroed = dict(probs)
    zeroed[A[0]] += sum(probs[c] for c in Q)
    for c in Q:
        zeroed[c] = 0.0
    assert sum(zeroed.values()) == pytest.approx(1.0)
    assert sum(zeroed[c] for c in Q) == 0.0, '本用例的前置：p(Q) == 0'
    assert sum(zeroed[c] for c in A) > 0, 'A 侧须有概率（否则命中的是 `p(A) = 0` 支）'

    out = engine.before_draw(key, _wi_state(cfg, 'h', counter=5), zeroed, sim=_SIM)
    assert out == zeroed, f'p(Q) = 0 时须恒等：{zeroed} → {out}'
    assert abs(sum(out.values()) - 1.0) < 1e-12


def test_worst_impact_boundary_p_minus_t_zero():
    """边界 #3 `P − T == 0`（目标占满 U / 源组被搬空）：源组**精确**归零。

    S8 实现面：`p(Q) == amount` 时 `δ_Q = −amount · p_c/p(Q) = −p_c`，公式自然涵盖、
    无分支（§3.9.5 第 3 行）。**判别点是「精确」**：`transfer_linear` 的 Q 侧增量写
    `amount * (dist[c] / pQ)` 而非 `amount * dist[c] / pQ`（`pity_primitives.py` 的
    「先除后乘」注记）：夺取型机制的 `amount` 与 `pQ` 由同一表达式算出、位级相等，
    故先除后乘给出精确 `0.0`，先乘后除会留下 1 ULP 的**负**残值（实测
    `-5.55e-17`，会被 §3.12.1 的非负性判据判违规）。本用例断言 `out[c] == 0.0`
    （**位级**，非 `approx`），正是为拦该残值。
    """
    cfg = _wi_config_custom(
        pity_defs=[_PityDef(name='rot', btype='rotating', scope='ssr',
                            guaranteed_init=True)],
        distribution=_WI_SINGLE_SOURCE_DIST)
    engine, key, spec, probs = _wi_pool0(cfg)

    A = tuple(spec.featured_cards['ssr'])
    Q = tuple(c for c in spec.scope_cards['ssr'] if c not in set(A))
    assert A and Q, '本用例需要 scope 内既有 featured 又有非 featured 卡'
    p_q = sum(probs[c] for c in Q)
    assert p_q > 0, '取源组须有货（否则本用例的归零断言空转）'

    # 判别性自检（非空转守卫）：本形状下「先乘后除」必须留下非零残值，否则
    # 「精确 0.0」这条断言对两种写法同值、拦不住它（`_WI_SINGLE_SOURCE_DIST`
    # 把取源组收成单卡、取值 0.4，正是 `pity_primitives.py` 注记里显形的那个形状）
    mul_first = {c: probs[c] - p_q * probs[c] / p_q for c in Q}
    assert any(v != 0.0 for v in mul_first.values()), (
        f'本形状下两种写法同值（残值全 0），本用例的对零断言将失去判别力：{mul_first}')

    out = engine.before_draw(key, _wi_state(cfg), probs, sim=_SIM)
    assert out != probs, '保底未触发（本用例无验收面）'
    residue = {c: out[c] for c in Q if out[c] != 0.0}
    assert not residue, (
        '源组须被搬空到**精确** 0.0（`P − T == 0` 行；1 ULP 负残值即判红）：'
        f'{residue}')
    assert abs(sum(out[c] for c in A) - (sum(probs[c] for c in A) + p_q)) < 1e-12, \
        '目标组须恰好拿到源组的全部质量'
    assert abs(sum(out.values()) - 1.0) < 1e-12


#: scope 键缺失用例的三条机制（各自的 `.get(scope, ())` 调用点不同）：
#: `rotating` 走 `featured_cards.get`，`soft_step` / `hard` 走 `scope_cards.get`。
_SCOPE_KEY_MISSING_CASES = [
    ('rotating', lambda: _PityDef(name='p', btype='rotating', scope='ssr',
                                  guaranteed_init=True), None),
    ('soft_step', lambda: _PityDef(name='p', btype='soft_step', scope='ssr',
                                   deltas=((1, 100.0),)), 1),
    ('hard', lambda: _PityDef(name='p', btype='hard', scope='ssr',
                              threshold=5), 5),
]

#: `P − T == 0` 的判别性池形状：取源组收成**单卡且取值 0.4**：该形状下
#: 「先乘后除」会留下 1 ULP 负残值（实测 -5.55e-17），「先除后乘」给出精确 0.0。
#: 真实 config.toml 的虚拟池形状（6 张取源卡、每张 0.000333…）**两种写法同值**，
#: 故那条边界只在本形状上可判。
_WI_SINGLE_SOURCE_DIST = [
    {'card_id': 'up_ssr', 'rarity': 'SSR', 'featured': True, 'probability': 20.0},
    {'card_id': 'std_ssr', 'rarity': 'SSR', 'featured': False, 'probability': 40.0},
    {'card_id': 'sr_1', 'rarity': 'SR', 'featured': False, 'probability': 20.0},
    {'card_id': 'r_1', 'rarity': 'R', 'featured': False, 'probability': 20.0},
]

#: 池形状：`_WI_NO_SSR_DIST` 无 SSR 卡（`scope_cards` 与 `featured_cards` **都缺**
#: `'ssr'` 键）；`_WI_WITH_SSR_DIST` 是同组保底的对照组（键在、机制真的触发）。
_WI_NO_SSR_DIST = [
    {'card_id': 'sr_1', 'rarity': 'SR', 'featured': False, 'probability': 60.0},
    {'card_id': 'r_1', 'rarity': 'R', 'featured': False, 'probability': 40.0},
]
_WI_WITH_SSR_DIST = [
    {'card_id': 'up_ssr', 'rarity': 'SSR', 'featured': True, 'probability': 30.0},
    {'card_id': 'std_ssr', 'rarity': 'SSR', 'featured': False, 'probability': 10.0},
    {'card_id': 'sr_1', 'rarity': 'SR', 'featured': False, 'probability': 40.0},
    {'card_id': 'r_1', 'rarity': 'R', 'featured': False, 'probability': 20.0},
]


@pytest.mark.parametrize('label,pdef_factory,counter', _SCOPE_KEY_MISSING_CASES,
                         ids=[c[0] for c in _SCOPE_KEY_MISSING_CASES])
def test_worst_impact_boundary_scope_key_missing(label, pdef_factory, counter):
    """边界 #5 scope 键缺失：恒等而非抛 `KeyError`（§六 的「S8 边界断言」）。

    S8 实现面：`scope_cards` / `featured_cards` **一律经 `.get(scope, ())` 消费**，
    取到空集 → `A` 为空 → `compute_delta()` 返 `None`。`compute_scope_mappings` 只对
    池中实际出现的稀有度建键（`featured_cards` 更只对**有 featured 卡**的稀有度建键），
    而 `PityDef.pools` 默认 `('*',)`，故任何无 SSR 的池都会让绑定它的保底走到这里；
    实现若写成下标（`scope_cards[scope]`）即 `KeyError`，整场模拟崩溃。

    **三条机制各一条**（`.get` 的三个调用点）：`rotating` 走
    `RotatingModifier` 的 `featured_cards.get`，`soft_step` / `hard` 走
    `SoftModifier` / `HardModifier._target_cards` 的 `scope_cards.get`。

    **非空转对照**：同组保底在「键存在」的池上必须真的改动分布（否则本条的两处
    恒等断言只是「机制没生效」的假绿）。
    """
    # ① 键真的缺失：池内无 SSR 卡
    cfg = _wi_config_custom(pity_defs=[pdef_factory()], distribution=_WI_NO_SSR_DIST)
    engine, key, spec, probs = _wi_pool0(cfg)
    assert 'ssr' not in spec.scope_cards, \
        f'{label}: 本用例需要 scope_cards 缺 "ssr" 键'
    assert 'ssr' not in spec.featured_cards, \
        f'{label}: 本用例需要 featured_cards 缺 "ssr" 键'
    assert 'sr' in spec.scope_cards and 'r' in spec.scope_cards, \
        '本用例需要池内确有其他稀有度（否则缺键形态无判别力）'

    out = engine.before_draw(key, _wi_state(cfg, 'p', counter=counter), probs, sim=_SIM)
    assert out == probs, f'{label}: scope 键缺失时须恒等而非抛 KeyError：{probs} → {out}'
    assert abs(sum(out.values()) - 1.0) < 1e-12

    # ② 对照组：同组保底在「键存在」的池上真的触发
    cfg2 = _wi_config_custom(pity_defs=[pdef_factory()], distribution=_WI_WITH_SSR_DIST)
    engine2, key2, spec2, probs2 = _wi_pool0(cfg2)
    assert 'ssr' in spec2.scope_cards and 'ssr' in spec2.featured_cards, \
        '对照组需要 "ssr" 键存在'
    out2 = engine2.before_draw(key2, _wi_state(cfg2, 'p', counter=counter), probs2, sim=_SIM)
    assert out2 != probs2, f'{label}: 对照组未触发（① 的恒等断言随之空转）'
    assert abs(sum(out2.values()) - 1.0) < 1e-12


def test_worst_impact_boundary_non_unit_sum():
    """边界 #6 `⟨m,p⟩ ≠ 1`（U 外更高稀有度被归一化缩放）：`Σ(p + δ) = 1`。

    S8 实现面：转移族恒有 `Σδ = 0`，故 `Σ(p + δ) ≡ 1`、`_apply_delta` 的归一化退化
    为恒等。本形态（`hard` 的 scope 低于最高稀有度）在旧因子实现下输出 `Σ = 1.009`
    （「目标集绝对赋值 + 更高稀有度豁免」造出 Σ > 1，§六 差异清单 (a)），S8 输出
    `Σ = 1`。

    **本用例的判别点不是 `Σ == 1` 那条断言（它近乎空转）**：`_apply_delta` 对非退化
    输入**无条件归一化**（`{c: v/total}`），故 `Σout == 1` 是**结构保证**而非关于算子
    的事实：任何算子（含未配平的）经它之后 Σ 都是 1。真正的捕获面是紧随其后的
    **U 外逐卡不变**：算子一旦不配平（`Σδ ≠ 0`），`raw_total ≠ 1`，归一化就会把
    **每一张**卡（含 U 外的更高稀有度）等比缩放，旧因子形态下该缩放因子为 0.991。
    实测变异（A 侧增量乘 1.5 造出 `Σδ = 0.5·amount`）即由该条判红。

    **「U 之外的卡不被触碰」的口径（本步实测订正）**：§3.9.5 第 6 行写「U 之外的卡
    不被触碰」，实测**逐位不变不成立**：本形态的 `Σδ = 1.665e-16 ≠ 0`（浮点求和
    残差），`raw_total = 1.0000000000000002 ≠ 1.0`，于是 `_apply_delta` 的归一化
    **仍会执行**、把每张卡（含更高稀有度）乘以 `0.9999999999999998`。故本用例按
    **相对 1e-12** 断言不变（旧因子实现该组被乘 0.991，量级差 12 个数量级，判别力
    不受影响）；「逐位不变」只在 `Σδ` 恰为 `0.0` 的形状上成立（如
    `test_worst_impact_boundary_p_minus_t_zero` 的 `rotating` 形态，实测 `total`
    恰为 `1.0`、scope 外逐位相同）。
    """
    cfg = _wi_config_custom(pity_defs=[
        _PityDef(name='h', btype='hard', scope='sr', threshold=5)])
    engine, key, spec, probs = _wi_pool0(cfg)

    higher = tuple(spec.scope_cards['ssr'])     # 比 scope='sr' 更高：U 之外
    A = tuple(spec.scope_cards['sr'])
    Q = tuple(spec.scope_cards['r'])
    assert higher and A and Q, '本用例需要三档稀有度都非空'

    out = engine.before_draw(key, _wi_state(cfg, 'h', counter=5), probs, sim=_SIM)
    assert out != probs, '保底未触发（本用例无验收面）'
    assert abs(sum(out.values()) - 1.0) < 1e-12, (
        f'Σ = {sum(out.values())!r}（S8 口径为恒等 1.0；旧因子实现在该形状为 1.009）')
    # 目标占满 U：更低稀有度精确归零
    assert all(out[c] == 0.0 for c in Q), \
        f'源组未精确归零：{ {c: out[c] for c in Q if out[c] != 0.0} }'
    # U 外（更高稀有度）不被缩放（相对 1e-12；逐位不变不成立，见 docstring）
    for c in higher:
        assert abs(out[c] - probs[c]) <= 1e-12 * probs[c], (
            f'U 外的卡被缩放：{c} {probs[c]!r} → {out[c]!r}')


def test_worst_impact_boundary_readonly_query_suppresses_cr_intercept():
    """§3.9.6 的 `rotating_cr` 例外：只读查询**不体现拦截**，抽卡前**体现**。

    §3.9.6 的「处置②」在 M2 的落点：`readonly` 从 Modifier 签名废除，查询标记改由
    `PityContext.readonly` 承载（`Pity.before_draw` 首行按实参写入），
    `RotatingModifier` 据它抑制 `extra_flag`。**成因**（RULING-6B′）：6B′ 把 CR 掷骰
    移回 `before_draw` 的 `prepare` 相位，只读查询会走到 `prepare` 的 `readonly` 早退
    分支，于是 `cr_intercepted` 读到的是**上一次非只读调用**留下的 flag（差一抽）。

    **本用例补的是引擎级接线**：`tests/core/test_pity_modifier.py` 的 `extra_flag`
    用例直构 `ctx(readonly=True)`，**绕过了** `Pity.before_draw` 的
    `ctx.readonly = readonly` 那一行；该行一旦被删，Modifier 级用例仍绿而
    `get_probabilities` 会开始体现拦截。本用例经 `PityEngine.get_probabilities`
    走完整路径，故钉住该行。

    `cr_base_rate = 1.0` 使掷骰确定性命中（`random.random() < 1.0` 恒真），两态因此
    可判：查询（只读，`prepare` 早退、flag 保持预置的 `True`）必须恒等；抽卡前
    （非只读，`prepare` 掷中并置位）必须改动分布。
    """
    cfg = _wi_config_custom(pity_defs=[
        _PityDef(name='cr', btype='rotating_cr', scope='ssr',
                 cr_base_rate=1.0, cr_counter_threshold=3)])
    engine, key, spec, probs = _wi_pool0(cfg)
    A = tuple(spec.featured_cards['ssr'])
    Q = tuple(c for c in spec.scope_cards['ssr'] if c not in set(A))
    assert A and Q, '本用例需要 scope 内既有 featured 又有非 featured 卡'

    # ① 只读查询：`cr_intercepted` 已被上一次非只读调用置位，查询须**不体现**拦截
    st_query = _wi_state(cfg, 'cr', cr_intercepted=True)
    queried = engine.get_probabilities(key, st_query, probs, sim=_SIM)
    assert queried == probs, (
        f'只读查询体现了 CR 拦截（§3.9.6 的处置②失效）：{probs} → {queried}')
    assert st_query.get('cr', 'cr_intercepted') is True, \
        '只读查询改动了状态（`prepare` 的 readonly 早退失效）'

    # ② 抽卡前（同一初始状态）：拦截成立、分布必须被改动
    st_draw = _wi_state(cfg, 'cr', cr_intercepted=True)
    drawn = engine.before_draw(key, st_draw, probs, sim=_SIM)
    assert drawn != probs, '抽卡前未体现拦截（① 的恒等断言随之空转）'
    assert abs(sum(drawn.values()) - 1.0) < 1e-12


# ═══════════════════════════════════════════════════════════════════
# 2026-10-15：覆盖倍数（`pity_coverage`）的两条护栏
#
# 引入背景（P64 报告 §八「待复测」段的登记）：该指标**此前无任何 golden / 测试
# 钉住**（`grep -rn pity_coverage tests/ scripts/` 只命中一个 dataclass 构造用例），
# 故读数漂移不会被任何门控发现；同批登记的第二条是分母取错池。两条都在此收口。
# ═══════════════════════════════════════════════════════════════════

def _default_store():
    """随包默认配置的 `ConfigStore`（每个用例独立 deepcopy，互不污染）。"""
    import copy
    from pathlib import Path
    from gacha_simulator.core.config_toml import load_toml

    cfg_path = (Path(__file__).resolve().parents[2]
                / 'gacha_simulator' / 'config' / 'config.toml')
    return copy.deepcopy(load_toml(str(cfg_path)))


def test_pity_cost_unit_uses_reference_pool_not_first_pool():
    """`_get_pity_cost` 的分母单价取**参照池**，不是 `store.pools[0]`。

    参照池 = `_prepare_pool_info` 选定的 `pool_entries[-1]`（最后一个 enabled 池），
    它也是分析实际使用的池（`_parsed_cost` / `_resource_name` / `_rewards` 都由它
    派生）。原实现固定读 `store.pools[0].cost`（**第一个**池），池成本异构时分母
    取到一个与分析无关的单价。

    **默认配置 8 池同价，故该缺陷在随包配置上不可见**——按 2026-10-15 的原则，
    「随包配置跑不到」不构成不修的理由，严重度按「存在语义合理的配置能触发它」判。
    """
    store = _default_store()
    banners = store.banner.banners
    assert len(banners) >= 2, '本用例需要至少两个 Banner（池成本异构）'

    banners[0].pools[0].cost = 'draw_resource:999'      # 第一个池：旧实现的取值来源
    banners[-1].pools[0].cost = 'draw_resource:320'     # 参照池：_prepare_pool_info 选它

    analyzer = WorstImpactAnalyzer([], {}, store)
    analyzer._prepare_pool_info()

    assert analyzer._ref_pool_entry is not None, '本用例的前置：参照池须已选定'
    assert analyzer._ref_pool_entry.cost == 'draw_resource:320', \
        '本用例的前置：参照池应是最后一个 enabled 池'
    assert store.pools[0].cost == 'draw_resource:999', \
        '本用例的前置：第一个池的成本须与参照池不同（否则断言无判别力）'

    max_end = max(analyzer._get_pity_end(p) for p in store.pity.pities)
    assert analyzer._get_pity_cost() == max_end * 320, (
        f'分母单价取错池：期望参照池的 320 × {max_end}，'
        f'实际 {analyzer._get_pity_cost()}（第一个池为 999 × {max_end} = '
        f'{max_end * 999}）'
    )
    # 单价本身也单列一条：把「取错池」与「max_end 算错」两类失效分开
    assert analyzer._draw_unit_cost() == 320


def test_pity_coverage_golden_default_config():
    """默认配置 + GUI 默认口径的覆盖倍数 golden（α=0.05 / N=1000 / seed=42）。

    **口径**（与 GUI 面板默认完全同形，2026-10-15 实测复现）：
    - 主模拟：随包 `config.toml`、策略 `smart`（`[strategy].key`）、N=1000、seed=42
    - 最差影响：条件=成功、广义出率=面板默认 `target_achievement`、阈值 1.00、
      α=0.05、池形状取最后一个 enabled 池（面板 `_load_last_pool_config` 的口径）
    - 读数：`worst_resource`（成功组资源分布的 α 分位）/ `pity_cost`
      （`max_end × 单价` = 90 × 160）

    **只跑到分子与分母，不跑 `analyze()` 的第二段**（99 池判定模拟）：覆盖倍数在
    `analyze()` 里于第二段**之前**算定（`pity_coverage = self._compute_pity_coverage(
    worst_resource)`），故第二段不影响本读数，省下的时间用于把 golden 放进默认
    测试集。

    **为什么值得跑一次真模拟**：分子不是常量而是主模拟结果的 α 分位，只有真跑才
    能发现「主模拟结果漂移 → 读数漂移」；把 3060 写死成字面量只能验公式，验不出
    读数。分母另由配置现算（`_get_pity_cost()`），故两类漂移各有一条断言。
    """
    store = _default_store()
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, run_batch_parallel)

    env = SimulationEnvBuilder.from_config_store(store)
    env.return_compact = False                       # 与 GUI 主模拟同形
    target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    batch = run_batch_parallel(
        env=env, target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=1000, max_workers=4, seed=42,
        strategy_key=store.strategy_key,
        strategy_params=store.strategy_params,
    )
    aggregates = batch.extraction.get('aggregates', [])
    assert len(aggregates) == 1000, f'主模拟应产出 1000 条结果，实际 {len(aggregates)}'

    pe = [p for p in store.pools if p.enabled][-1]
    analyzer = WorstImpactAnalyzer(
        aggregates, target_specs, store,
        gdr_key='target_achievement', gdr_threshold=1.0,
        custom_pool_config={
            'duration_days': pe.end_day - pe.start_day,
            'cost': pe.cost,
            'distribution': [
                {'card_id': de.card_id, 'probability': de.probability,
                 'rarity': de.rarity, 'featured': de.featured,
                 'resources_gained': dict(de.resources_gained) if de.resources_gained else {}}
                for de in pe.distribution
            ],
        },
    )
    analyzer._prepare_pool_info()

    checker = analyzer._build_success_checker(
        target_specs=target_specs, ssr_ids=analyzer._main_ssr_ids)
    dist = ConditionalResourceDistribution(
        aggregates, checker.is_success, resource=analyzer._resource_name)
    worst_resource = dist.get_worst_case_resource('success', 0.05)

    assert worst_resource == 3060.0, (
        f'分子漂移：成功组 α=0.05 分位期望 3060，实际 {worst_resource}'
        f'（n_failure={len(dist.failure_resources)}）')
    assert analyzer._get_pity_cost() == 14400, (
        f'分母漂移：期望 90 × 160 = 14400，实际 {analyzer._get_pity_cost()}')
    assert analyzer._compute_pity_coverage(worst_resource) == pytest.approx(0.2125), (
        f'覆盖倍数漂移：期望 3060 / 14400 = 0.2125，'
        f'实际 {analyzer._compute_pity_coverage(worst_resource)}')
