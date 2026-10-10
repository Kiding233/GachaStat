"""P64 S2a：`Modifier` 家族（§3.1.2 机制表 / §3.9.2 接口）。

本文件承载两块：**S2a-1**（`Modifier` 基类 + `_lower_rarities` + `HardModifier` /
`SoftModifier`，转移量语义族）与 **S2a-2**（`RotatingModifier` /
`NonFeaturedModifier` / `SelectedModifier` / `NotOwnedModifier`，目标集语义族；分节标
「S2a-2」）。

覆盖 S2a-1 的四组被测面（§七 S2a-1 的验收四条）：

1. **`Modifier` 基类**——`apply` 的 M1 期占位实现（调用即 `NotImplementedError`）、
   `rebind` 空实现、`state_keys()` 默认 `()`、`namespace` 默认 `None`（AUDIT-BREAK-3）。
2. **`HardModifier`**——按 `target` 的两分支（`scope` / `featured`）与 §3.1.2 的
   **转移量口径**（夺取型 `amount = p(Q)`，源组整组搬空；**不是** soft 的 `boost/100`）。
3. **`SoftModifier`**——`t = boost%(counter) / 100`（§3.4.1 修正 ①），
   **不得再乘 `p(Q)`**。
4. **`_lower_rarities`**——scope 分层：返回 `rarity_rank` 中 `rank > rank(scope)` 的
   稀有度下的全部卡。

**分布空间**：M1 期 `dist` 是**槽位级**（§3.9 过渡期纪律），故夹具同时给出
`scope_cards`（卡集合，A/Q 的来源）与 `card_to_slot`（投影通道）；夹具的槽位名与
`compute_scope_mappings` 同规则（`{rarity}_featured` / `rarity`）。

**M1 形态的位级对照**：`HardModifier` / `SoftModifier` 的 M1 形态是「沿用旧实现」
（§3.9 过渡期纪律 / §3.9.5 的 `Σ(p + δ) ≠ 1` 行：目标集绝对赋值 + 更高稀有度豁免），
本文件末尾两条用例直接对旧 `HardPityBehavior` / `SoftStepBehavior` 做逐位比对
（断言用**严格 `==`**、非 `pytest.approx`：两侧算式逐字同源、求和顺序亦一致，
故 1e-6 以下的回归也必须钉住），
钉住该形态（§六 S1–S5 口径的单元级前置；旧类随发布前一次性移除时这两条同批删除）。
"""

import random

import pytest

from gacha_simulator.core.pity import (
    HardPityBehavior, RotatingBehavior, SoftStepBehavior, TargetedBehavior,
)
from gacha_simulator.core.pity_modifier import (
    HardModifier, Modifier, NonFeaturedModifier, NotOwnedModifier, RotatingModifier,
    SelectedModifier, SoftModifier, _lower_rarities,
)
from gacha_simulator.core.pity_primitives import DrawInfo, PityContext, PityState

SCOPE = 'ssr'
NAME = 'ssr_hard'

# ── 夹具：一个 ssr（含 featured）/ sr / r 三稀有度池 ──
RARITY_RANK = {'ssr': 0, 'sr': 1, 'r': 2}
SCOPE_CARDS = {'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_std',), 'r': ('r_std',)}
FEATURED_CARDS = {'ssr': ('ssr_up',)}
SCOPE_SLOTS = {'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)}
FEATURED_SLOTS = {'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)}
CARD_TO_SLOT = {'ssr_up': 'ssr_featured', 'ssr_std': 'ssr', 'sr_std': 'sr', 'r_std': 'r'}
BASE = {'ssr_featured': 0.006, 'ssr': 0.004, 'sr': 0.05, 'r': 0.94}   # Σ = 1.0


def _draw(rarity_rank=None, scope_cards=None, featured_cards=None, base=None,
          scope_slots=None, featured_slots=None, card_to_slot=None):
    """构造一次抽卡的 `DrawInfo`（槽位级分布所需的全部映射齐备）。

    `scope_slots` / `featured_slots` / `card_to_slot` 三个形参由 **S2a-2** 追加（带默认值，
    S2a-1 的全部既有调用不受影响）——「宽槽」夹具需要多槽映射，见 `WIDE_*`。
    """
    return DrawInfo(
        pool_id='p', pool_instance_id='p_0', reward_id='sr_std',
        reward_rarity='sr', is_featured=False,
        scope_cards=scope_cards if scope_cards is not None else SCOPE_CARDS,
        featured_cards=featured_cards if featured_cards is not None else FEATURED_CARDS,
        scope_slots=scope_slots if scope_slots is not None else SCOPE_SLOTS,
        featured_slots=featured_slots if featured_slots is not None else FEATURED_SLOTS,
        card_to_slot=card_to_slot if card_to_slot is not None else CARD_TO_SLOT,
        base_probabilities=base if base is not None else BASE,
        rarity_rank=rarity_rank if rarity_rank is not None else RARITY_RANK,
    )


def _ctx(dist=None, **kw):
    """构造一次抽卡的 `PityContext`（`current` 为槽位级分布）。"""
    st = PityState()
    return PityContext(draw=_draw(**kw), current=dict(dist or BASE), state=st)


class _View:
    """`StateView` 的最小替身——本族只经 `view.get(key, default)` 读 `counter`。"""

    def __init__(self, **kw):
        self._d = kw

    def get(self, key, default=None):
        return self._d.get(key, default)


def _view(counter):
    return _View(counter=counter)


# ══════════════════════════════════════════════════════════════════
# ① Modifier 基类（§3.9.2 / §3.14.3 / AUDIT-BREAK-3）
# ══════════════════════════════════════════════════════════════════

class TestModifierBase:
    """基类的两个默认实现 + 声明面。"""

    def test_modifier_base_apply_placeholder_raises_not_implemented(self):
        """M1 期占位实现：调用即 `NotImplementedError`。

        §3.9.2 / §3.14.3 给的默认实现体依赖 S8-1 的 `_apply_delta` 与 S8 起才存在的
        `compute_delta`，本步（M1 第 6 块）二者都不存在——照抄即 `NameError`，且 M1 期
        没有任何消费者（各具体 Modifier 均自实现 `apply`）。故本步只落占位。
        """
        with pytest.raises(NotImplementedError):
            Modifier().apply(_ctx(), _view(1), dict(BASE), False)

    def test_modifier_base_rebind_is_noop_and_declares_nothing(self):
        """`rebind` 空实现（P75 纪律：方法必须存在、不得省略）；`state_keys()` 默认
        `()`；`namespace` 默认 `None`。"""
        mod = Modifier()
        st = PityState()
        assert mod.rebind(st, NAME) is None
        assert st.to_dict() == {'data': {}}, '空实现不得写任何状态键'
        assert mod.state_keys() == ()
        assert mod.namespace is None

    def test_state_keys_declared_by_reading_modifiers(self):
        """读 `counter` 的 Modifier 须覆写声明集（§3.9.2）——否则 §3.12.2 判据 2
        对全部 preset 退化为恒真。"""
        assert HardModifier(SCOPE).state_keys() == ('counter',)
        assert SoftModifier(SCOPE, ()).state_keys() == ('counter',)


# ══════════════════════════════════════════════════════════════════
# ② HardModifier（§3.1.2 机制表第 1 / 2 行）
# ══════════════════════════════════════════════════════════════════

class TestHardModifier:
    """`counter >= threshold` 时把源组整组搬给目标集。"""

    def test_hard_modifier_target_scope_branch_drains_lower_rarities(self):
        """`target='scope'`：A = `scope_cards[scope]`（ssr 的两个槽），Q = 更低稀有度。"""
        dist = dict(BASE)
        out = HardModifier(SCOPE, threshold=5, target='scope').apply(
            _ctx(dist), _view(5), dist, False)

        assert out['ssr_featured'] == pytest.approx(0.6)    # 按声明权重 0.006 : 0.004
        assert out['ssr'] == pytest.approx(0.4)
        assert out['sr'] == 0.0 and out['r'] == 0.0, 'Q（更低稀有度）须整组搬空'

    def test_hard_modifier_target_featured_branch_narrows_target(self):
        """`target='featured'`：A = `featured_cards[scope]`，Q 还含 scope 去掉 A 的剩余。"""
        dist = dict(BASE)
        out = HardModifier(SCOPE, threshold=5, target='featured').apply(
            _ctx(dist), _view(5), dist, False)

        assert out['ssr_featured'] == pytest.approx(1.0)
        assert out['ssr'] == 0.0, 'tf=true 时 scope 内非 featured 槽进 Q、被搬空'
        assert out['sr'] == 0.0 and out['r'] == 0.0

    def test_hard_modifier_transfer_amount_is_pq_not_boost_fraction(self):
        """转移量口径 = 夺取型 `amount = p(Q)`（源组**整组**搬空），不是 soft 的
        `boost/100` 部分转移。

        构造 `p(Q)` 很小的分布：若误写成 soft 口径（部分转移），源组会留下残值。
        """
        dist = {'ssr_featured': 0.005, 'ssr': 0.005, 'sr': 0.01, 'r': 0.98}
        out = HardModifier(SCOPE, threshold=1, target='scope').apply(
            _ctx(dist), _view(1), dist, False)

        assert out['sr'] == 0.0 and out['r'] == 0.0, 'Q 整组搬空 = amount p(Q)'
        assert out['ssr_featured'] + out['ssr'] == pytest.approx(1.0), 'A 收下整组'

    def test_hard_modifier_higher_rarity_exempt_m1_form(self):
        """M1 形态：更高稀有度**豁免**（原值保留）→ 存在更高稀有度时输出 `Σ > 1`。

        这是 §3.9.5 的 `Σ(p + δ) ≠ 1` 行所记的 M1 口径（S8 的增量法改为「不写增量
        即精确保留」，`Σδ = 0`）；差 1e-4 ~ 3.5e-3，属 §3.1.2 边界二的已登记差异类。
        """
        dist = dict(BASE)
        out = HardModifier('sr', threshold=5, target='scope').apply(
            _ctx(dist), _view(5), dist, False)

        assert out['sr'] == pytest.approx(1.0), '目标集绝对赋值（M1 沿用旧实现）'
        assert out['r'] == 0.0, 'Q = 更低稀有度（rank 更大的 r）'
        assert out['ssr_featured'] == pytest.approx(BASE['ssr_featured']), '更高稀有度豁免'
        assert out['ssr'] == pytest.approx(BASE['ssr'])
        assert sum(out.values()) > 1.0, '豁免致 Σ > 1（M1 形态，非 S8 的配平形态）'

    def test_hard_modifier_below_threshold_returns_none(self):
        """条件不成立 → `None`（恒等；§3.1.2「不生效即 return None」）。"""
        dist = dict(BASE)
        assert HardModifier(SCOPE, threshold=5).apply(_ctx(dist), _view(4), dist, False) is None

    def test_hard_modifier_featured_empty_falls_back_to_scope(self):
        """`target='featured'` 且该 scope 无 featured 卡 → **空集回退 scope 全集**
        （对齐旧 `featured_slots.get(scope, scope_slots)`，ISSUE-403 的空集回退纪律）。"""
        dist = dict(BASE)
        ctx = _ctx(dist, featured_cards={})          # ssr 无 featured 卡
        out = HardModifier(SCOPE, threshold=5, target='featured').apply(ctx, _view(5), dist, False)

        assert out['ssr_featured'] == pytest.approx(0.6), '回退后 A = scope 全集（两槽）'
        assert out['ssr'] == pytest.approx(0.4)

    def test_hard_modifier_target_scope_matches_old_class(self):
        """M1 位级对照：`target='scope'` 与旧 `HardPityBehavior(target_featured=False)` 逐位相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        old = HardPityBehavior(NAME, ctx.state, scope=SCOPE, btype='hard',
                               threshold=5, target_featured=False)
        new = HardModifier(SCOPE, threshold=5, target='scope')

        expect = old._compute_probabilities(ctx, 5)
        got = new.apply(ctx, _view(5), dist, False)
        assert got == expect, '位级对照：严格相等（非 approx）'

    def test_hard_modifier_target_featured_matches_old_class(self):
        """M1 位级对照：`target='featured'` 与旧 `HardPityBehavior(target_featured=True)` 逐位相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        old = HardPityBehavior(NAME, ctx.state, scope=SCOPE, btype='hard',
                               threshold=5, target_featured=True)
        new = HardModifier(SCOPE, threshold=5, target='featured')

        expect = old._compute_probabilities(ctx, 5)
        got = new.apply(ctx, _view(5), dist, False)
        assert got == expect, '位级对照：严格相等（非 approx）'


# ══════════════════════════════════════════════════════════════════
# ③ SoftModifier（§3.1.2 机制表第 3 行 / §3.4.1 修正 ①）
# ══════════════════════════════════════════════════════════════════

class TestSoftModifier:
    """`boost > 0` 时把源组的 `boost` 个百分点搬给 scope。"""

    DELTAS = ((4, 0.0), (6, 5.0))       # 前 4 抽不增，第 5 抽起每抽 +5%

    def test_soft_modifier_boost_is_percentage_points_not_scaled_by_pq(self):
        """`t = boost%(counter) / 100`——目标组概率**增加** boost 个百分点，
        **不得再乘 `p(Q)`**（§3.4.1 修正 ①）。

        反例口径 `t = boost/100 * p(Q)` 在 `p(Q) = 0.99` 时给 0.0495，与 0.05 差
        5e-4；该差异前期极小、爬升后段才拉开，故必须直接钉住「增量恰为 boost/100」。
        """
        dist = dict(BASE)
        p_q = dist['sr'] + dist['r']
        ctx = _ctx(dist)
        out = SoftModifier(SCOPE, self.DELTAS).apply(ctx, _view(5), dist, False)

        before = dist['ssr_featured'] + dist['ssr']
        after = out['ssr_featured'] + out['ssr']
        assert after - before == pytest.approx(0.05), 'counter=5 → boost=5 → t=0.05 个百分点量'
        assert after - before != pytest.approx(0.05 * p_q), '不得乘 p(Q)'
        assert sum(out.values()) == pytest.approx(1.0), '转移族配平（更高稀有度未触碰）'

    def test_soft_modifier_counter_zero_returns_none(self):
        """条件不成立（boost 为 0）→ `None`（恒等）。"""
        dist = dict(BASE)
        assert SoftModifier(SCOPE, self.DELTAS).apply(_ctx(dist), _view(0), dist, False) is None

    def test_soft_modifier_deltas_rle_accumulates_by_segment(self):
        """RLE 段表按 counter 定位当前段累计 boost%（旧 `_cumulative_boost` 同式）。"""
        dist = dict(BASE)
        mod = SoftModifier(SCOPE, ((4, 0.0), (6, 5.0)))
        # counter=4 落在首段（增量 0）→ 无加成；counter=10 落在次段 → 6 抽 × 5 = 30
        assert mod.apply(_ctx(dist), _view(4), dist, False) is None
        out = mod.apply(_ctx(dist), _view(10), dist, False)
        before = dist['ssr_featured'] + dist['ssr']
        assert (out['ssr_featured'] + out['ssr']) - before == pytest.approx(0.30)

    def test_soft_modifier_matches_old_class(self):
        """M1 位级对照：与旧 `SoftStepBehavior` 逐位相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        old = SoftStepBehavior(NAME, ctx.state, scope=SCOPE, btype='soft_step',
                               deltas=self.DELTAS)
        new = SoftModifier(SCOPE, self.DELTAS)

        for counter in (0, 4, 5, 10, 40):
            expect = old._compute_probabilities(ctx, counter)
            got = new.apply(ctx, _view(counter), dist, False)
            assert (got is None and expect == dist) or \
                got == expect, f'counter={counter} 与旧类位级不等'


# ══════════════════════════════════════════════════════════════════
# ④ _lower_rarities（§3.1.2「更低稀有度」）
# ══════════════════════════════════════════════════════════════════

class TestLowerRarities:
    """返回 `rarity_rank` 中 `rank > rank(scope)` 的稀有度下的**全部卡**。"""

    def test_lower_rarities_scope_layering(self):
        """scope 分层：ssr → sr + r 的全部卡；sr → r 的全部卡；最低稀有度 → 空。"""
        ctx = _ctx()
        assert _lower_rarities(ctx, 'ssr') == ('sr_std', 'r_std')
        assert _lower_rarities(ctx, 'sr') == ('r_std',)
        assert _lower_rarities(ctx, 'r') == ()

    def test_lower_rarities_missing_scope_key_returns_empty(self):
        """`scope` 不在 `rarity_rank` 中 → 兜底 rank 99，无更大者，返回空元组
        （对齐旧 `rarity_rank.get(scope, 99)`；**不得下标**，§3.9.5 的 scope 键缺失行）。"""
        assert _lower_rarities(_ctx(), 'ur') == ()

    def test_lower_rarities_matches_card_set_source_of_truth(self):
        """来源是 `scope_cards`（卡集合的真相源）——rank 更大的稀有度无卡时不产出。"""
        ctx = _ctx(scope_cards={'ssr': ('ssr_up', 'ssr_std')}, rarity_rank=RARITY_RANK)
        assert _lower_rarities(ctx, 'ssr') == ()


def _random_dist(rng):
    raw = {k: rng.random() for k in BASE}
    tot = sum(raw.values())
    return {k: v / tot for k, v in raw.items()}


class TestRandomisedEquivalence:
    """随机分布下的 M1 位级对照（固定种子，防「只在基准分布上巧合相等」）。"""

    def test_hard_and_soft_match_old_classes_on_random_dists(self):
        rng = random.Random(20261010)
        for scope in (SCOPE, 'sr'):
            for tf in (False, True):
                dist = _random_dist(rng)
                ctx = _ctx(dist)
                old_h = HardPityBehavior(NAME, ctx.state, scope=scope, btype='hard',
                                         threshold=5, target_featured=tf)
                new_h = HardModifier(scope, threshold=5,
                                     target='featured' if tf else 'scope')
                assert new_h.apply(ctx, _view(5), dist, False) == \
                    old_h._compute_probabilities(ctx, 5), '位级对照：严格相等（非 approx）'

            for counter in (0, 4, 7):
                dist = _random_dist(rng)
                ctx = _ctx(dist)
                old_s = SoftStepBehavior(NAME, ctx.state, scope=scope, btype='soft_step',
                                         deltas=TestSoftModifier.DELTAS)
                new_s = SoftModifier(scope, TestSoftModifier.DELTAS)
                expect = old_s._compute_probabilities(ctx, counter)
                got = new_s.apply(ctx, _view(counter), dist, False)
                assert (got is None and expect == dist) or \
                    got == expect, f'counter={counter} 与旧类位级不等'

# ══════════════════════════════════════════════════════════════════
# S2a-2：目标集语义族（§3.1.2 机制表第 4/5/6/7 行）
# ══════════════════════════════════════════════════════════════════

#: 「宽槽」夹具——ssr 下 **2 个 featured 槽 + 2 个非 featured 槽**。
#:
#: `compute_scope_mappings` 只产出 `(rarity, f'{rarity}_featured')` 两个槽（同稀有度的
#: featured 卡合并进单槽），故在真实管道上四类的 A 恒为**单槽**，「A 内按声明权重分配」
#: 这一形状退化为不可观测（单槽时 `current` 与 `declared` 给出同一结果）。该夹具人为给出
#: 多槽，只为让 `declared` 形状可被断言到；槽位级分布是纯数据，不依赖
#: `compute_scope_mappings` 的产出。声明权重两侧都是 **3:1**。
WIDE_RANK = {'ssr': 0, 'sr': 1, 'r': 2}
WIDE_SCOPE_CARDS = {'ssr': ('ssr_up_a', 'ssr_up_b', 'ssr_std_a', 'ssr_std_b'),
                    'sr': ('sr_std',), 'r': ('r_std',)}
WIDE_FEATURED_CARDS = {'ssr': ('ssr_up_a', 'ssr_up_b')}
WIDE_SCOPE_SLOTS = {'ssr': ('ssr_a', 'ssr_b', 'ssr_fa', 'ssr_fb'),
                    'sr': ('sr',), 'r': ('r',)}
WIDE_FEATURED_SLOTS = {'ssr': ('ssr_fa', 'ssr_fb'), 'sr': ('sr',), 'r': ('r',)}
WIDE_CARD_TO_SLOT = {'ssr_up_a': 'ssr_fa', 'ssr_up_b': 'ssr_fb',
                     'ssr_std_a': 'ssr_a', 'ssr_std_b': 'ssr_b',
                     'sr_std': 'sr', 'r_std': 'r'}
WIDE_BASE = {'ssr_fa': 0.006, 'ssr_fb': 0.002, 'ssr_a': 0.003, 'ssr_b': 0.001,
             'sr': 0.05, 'r': 0.938}          # Σ = 1.0


def _wide_ctx(dist, **kw):
    """宽槽夹具的 `PityContext`。"""
    return _ctx(dist, rarity_rank=WIDE_RANK, scope_cards=WIDE_SCOPE_CARDS,
                featured_cards=WIDE_FEATURED_CARDS, scope_slots=WIDE_SCOPE_SLOTS,
                featured_slots=WIDE_FEATURED_SLOTS, card_to_slot=WIDE_CARD_TO_SLOT,
                base=WIDE_BASE, **kw)


class _Sim:
    """`SimView` 的最小替身——`NotOwnedModifier` 只经 `ctx.sim.owns(card_id)` 读持有张数。

    `SimView` 本体与 `PityContext.sim` 字段同归 **S9-2（M2）**（`core/state.py` +
    `core/pity_primitives.py`）；S2a-2（M1）先交付读取方，故单测以替身提供该字段（先例：
    S2a-1 对尚未存在的 `StateView` 用 `_View` 替身）。
    """

    def __init__(self, owned=()):
        self._owned = set(owned)

    def owns(self, card_id):
        return 1 if card_id in self._owned else 0


def _ctx_with_sim(dist, owned=(), **kw):
    """在 `PityContext` 上挂 `sim` 替身（该字段由 S9-2 落为正式字段）。"""
    ctx = _ctx(dist, **kw)
    ctx.sim = _Sim(owned)
    return ctx


# ══════════════════════════════════════════════════════════════════
# ① RotatingModifier（§3.1.2 机制表第 4 行）
# ══════════════════════════════════════════════════════════════════

class TestRotatingModifier:
    """`guaranteed`（∨ `extra_flag`）时把 scope 内非 featured 的概率整组搬给 featured。"""

    def test_rotating_modifier_target_set_is_featured_cards(self):
        """目标集构造：A = `featured_cards[scope]`（投影到槽位）、Q = `scope` 减去 featured。

        A 收下**整个 scope** 的量（scope 内非 featured 槽归零），scope 外的 sr / r 不动、
        `Σ` 仍为 1（scope 内重分配，不造质量）。
        """
        dist = dict(BASE)
        out = RotatingModifier(SCOPE).apply(
            _ctx(dist), _View(guaranteed=True), dist, False)

        assert out['ssr_featured'] == pytest.approx(dist['ssr'] + dist['ssr_featured'])
        assert out['ssr'] == 0.0, 'Q = scope 减去 featured，须整组搬空'
        assert out['sr'] == dist['sr'] and out['r'] == dist['r'], 'scope 外不动'
        assert sum(out.values()) == pytest.approx(1.0)

    def test_rotating_modifier_a_side_shape_is_declared(self):
        """A 侧形状 = `declared`——A 内按**声明权重**分配，与当前比例无关。

        宽槽夹具 + 人为扰动 `dist`（featured 两槽当前比例 1:7，声明权重 3:1）。
        按声明权重得 3:1；若误按当前比例（`current` 形状）则得 1:7。
        """
        dist = {'ssr_fa': 0.001, 'ssr_fb': 0.007, 'ssr_a': 0.002, 'ssr_b': 0.0,
                'sr': 0.05, 'r': 0.94}
        ctx = _wide_ctx(dist)
        out = RotatingModifier(SCOPE).apply(ctx, _View(guaranteed=True), dist, False)
        total = 0.001 + 0.007 + 0.002

        assert out['ssr_fa'] == pytest.approx(total * 3 / 4), 'A 内按声明权重 3:1'
        assert out['ssr_fb'] == pytest.approx(total * 1 / 4)
        assert out['ssr_a'] == 0.0 and out['ssr_b'] == 0.0, 'Q（非 featured）整组搬空'

    def test_rotating_modifier_empty_featured_returns_none(self):
        """空目标集（该 scope 无 featured 卡）→ 恒等（§3.9.5；旧实现同为空集早退）。"""
        dist = dict(BASE)
        ctx = _ctx(dist, featured_cards={})
        assert RotatingModifier(SCOPE).apply(
            ctx, _View(guaranteed=True), dist, False) is None

    def test_rotating_modifier_not_guaranteed_returns_none(self):
        """条件不成立（`guaranteed` 未置位）→ `None`（§3.1.2「不生效即 return None」）。"""
        dist = dict(BASE)
        assert RotatingModifier(SCOPE).apply(_ctx(dist), _View(), dist, False) is None

    def test_rotating_modifier_extra_flag_triggers_but_readonly_suppresses_it(self):
        """`extra_flag` 只影响**条件**（§3.2 的 `rotating_cr` 行）；`readonly=True` 时被抑制
        （§3.9.6 的 M1 期专项：只读查询不体现拦截，复刻旧查询语义）。

        反向断言：去掉 `readonly` 抑制后 `readonly=True` 仍返回分布，本用例必红。
        """
        dist = dict(BASE)
        mod = RotatingModifier(SCOPE, extra_flag='cr_intercepted')
        view = _View(cr_intercepted=True)

        assert mod.apply(_ctx(dist), view, dist, False) is not None, 'extra_flag 置位即触发'
        assert mod.apply(_ctx(dist), view, dist, True) is None, '只读查询须抑制 extra_flag'
        assert mod.apply(_ctx(dist), _View(), dist, False) is None, '两标志皆无则不触发'
        assert mod.state_keys() == ('guaranteed', 'cr_intercepted'), 'extra_flag 也须申报'
        assert RotatingModifier(SCOPE).state_keys() == ('guaranteed',)

    def test_rotating_modifier_matches_old_class(self):
        """M1 位级对照：与旧 `RotatingBehavior.before_draw`（guaranteed 分支）严格相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        ctx.state.set(NAME, 'guaranteed', True)
        old = RotatingBehavior(NAME, ctx.state, scope=SCOPE)
        new = RotatingModifier(SCOPE)

        expect = old.before_draw(ctx)
        got = new.apply(ctx, _View(guaranteed=True), dist, False)
        assert got == expect, '位级对照：严格相等（非 approx）'


# ══════════════════════════════════════════════════════════════════
# ② NonFeaturedModifier（§3.1.2 机制表第 5 行 / §3.3 的 G1）
# ══════════════════════════════════════════════════════════════════

class TestNonFeaturedModifier:
    """G1（rotating_inverse）——`forced_loss` 时把 featured 的概率整组搬给非 featured。"""

    def test_non_featured_modifier_target_set_is_scope_minus_featured(self):
        """目标集构造：A = `scope` 减去 featured（投影后）、Q = `featured_cards[scope]`。

        与 rotating 是同一算子的**反向调用**（§3.3）：A / Q 互换，scope 总量不变。
        """
        dist = dict(BASE)
        out = NonFeaturedModifier(SCOPE).apply(
            _ctx(dist), _View(forced_loss=True), dist, False)

        assert out['ssr'] == pytest.approx(dist['ssr'] + dist['ssr_featured'])
        assert out['ssr_featured'] == 0.0, 'Q = featured，须整组搬空'
        assert out['sr'] == dist['sr'] and out['r'] == dist['r']
        assert sum(out.values()) == pytest.approx(1.0)

    def test_non_featured_modifier_a_side_shape_is_declared(self):
        """A 侧形状 = `declared`——A（非 featured 两槽）内按声明权重 3:1 分配。

        扰动 `dist` 使两槽当前比例为 1:1；按声明权重得 3:1，按当前比例则得 1:1。
        """
        dist = {'ssr_fa': 0.0, 'ssr_fb': 0.008, 'ssr_a': 0.001, 'ssr_b': 0.001,
                'sr': 0.05, 'r': 0.94}
        ctx = _wide_ctx(dist)
        out = NonFeaturedModifier(SCOPE).apply(ctx, _View(forced_loss=True), dist, False)
        total = 0.008 + 0.001 + 0.001

        assert out['ssr_a'] == pytest.approx(total * 3 / 4), 'A 内按声明权重 3:1'
        assert out['ssr_b'] == pytest.approx(total * 1 / 4)
        assert out['ssr_fa'] == 0.0 and out['ssr_fb'] == 0.0, 'Q（featured）整组搬空'

    def test_non_featured_modifier_not_forced_loss_returns_none(self):
        """条件不成立（`forced_loss` 未置位）→ `None`；`state_keys()` 声明该标志。"""
        dist = dict(BASE)
        assert NonFeaturedModifier(SCOPE).apply(_ctx(dist), _View(), dist, False) is None
        assert NonFeaturedModifier(SCOPE).state_keys() == ('forced_loss',)


# ══════════════════════════════════════════════════════════════════
# ③ SelectedModifier（§3.1.2 机制表第 6 行）
# ══════════════════════════════════════════════════════════════════

class TestSelectedModifier:
    """`guaranteed` 或定轨就绪时把 scope 的概率整组搬给**定轨选中卡**。"""

    def test_selected_modifier_target_set_is_selected_card(self):
        """目标集构造：A = 定轨选中卡（投影到槽位）、Q = `scope` 减去 A。

        用**宽槽夹具**（两张 featured 卡各占一槽）：定轨 `ssr_up_a` → A 只含 `ssr_fa`，
        故 `ssr_fa` 收下整个 scope，另一 featured 槽 `ssr_fb` 与全部非 featured 槽归零。
        **判别性**：真实管道把 featured 卡合并进单槽，「A = 定轨卡」与「A = 全部 featured」
        在单槽下不可区分；若实现忽略 `selected_card` 按全部 featured 取 A，`ssr_fa` 只会
        拿到 3/4 个 scope 总量，本用例必红。
        """
        dist = dict(WIDE_BASE)
        view = _View(selected_card='ssr_up_a', guaranteed=True)
        out = SelectedModifier(SCOPE).apply(_wide_ctx(dist), view, dist, False)
        total = sum(dist[k] for k in WIDE_SCOPE_SLOTS['ssr'])

        assert out['ssr_fa'] == pytest.approx(total), 'A = 定轨选中卡所在槽，收下整个 scope'
        assert out['ssr_fb'] == 0.0, '另一 featured 槽不在 A 内，须归零'
        assert out['ssr_a'] == 0.0 and out['ssr_b'] == 0.0, 'Q = scope 减去 A，须整组搬空'
        assert out['sr'] == dist['sr'] and out['r'] == dist['r'], 'scope 外不动' 

    def test_selected_modifier_a_side_shape_is_declared(self):
        """A 侧形状 = `declared`（单槽退化为「A 收下整个 scope」）。

        `card_to_slot` 把同稀有度的 featured 卡合并进单槽，故 `SelectedModifier` 的 A 恒为
        单槽，`current` 与 `declared` 在此**不可区分**；可断言的是「A 收下 scope 总量，
        且与 A 的当前概率无关」——两种扰动下 A 的取值都等于 scope 总量。
        """
        mod = SelectedModifier(SCOPE)
        for a_cur in (0.0005, 0.019):
            dist = {'ssr_featured': a_cur, 'ssr': 0.02 - a_cur, 'sr': 0.11, 'r': 0.87}
            view = _View(selected_card='ssr_up', guaranteed=True)
            out = mod.apply(_ctx(dist), view, dist, False)
            assert out['ssr_featured'] == pytest.approx(0.02), 'A 收下 scope 总量'
            assert out['ssr'] == 0.0

    def test_selected_modifier_fate_ready_triggers_without_guaranteed(self):
        """条件内联的第二析取项：已定轨 ∧ `fate_points >= tau`（`fate_ready`）。"""
        dist = dict(BASE)
        view = _View(selected_card='ssr_up', fate_points=1)
        out = SelectedModifier(SCOPE, tau=1).apply(_ctx(dist), view, dist, False)
        assert out is not None and out['ssr_featured'] == pytest.approx(0.01)

    def test_selected_modifier_not_triggered_returns_none(self):
        """两个析取项都不成立 → `None`。

        含 `tau=0` 且**未定轨**的反例：旧实现把「已定轨」作为 fate 分支的合取项
        （`selected and fate_points >= threshold`），省掉它会让 `fate_points >= 0` 恒真。
        """
        dist = dict(BASE)
        assert SelectedModifier(SCOPE).apply(
            _ctx(dist), _View(selected_card='ssr_up', fate_points=0), dist, False) is None
        assert SelectedModifier(SCOPE, tau=0).apply(
            _ctx(dist), _View(selected_card='ssr_up'), dist, False) is not None, 'tau=0 定轨即必出'
        assert SelectedModifier(SCOPE, tau=0).apply(
            _ctx(dist), _View(), dist, False) is None, '未定轨时 tau=0 不得触发'

    def test_selected_modifier_unset_selected_card_falls_back_to_featured(self):
        """未定轨（`selected_card` 缺失）→ 目标集退化为**全部 featured 槽**（M1 沿用旧实现）。

        依据：手册明写「不填卡 ID 时可改用 `guaranteed_init = true` 等效」，该组合正是
        「出金必是 UP、UP 内按声明权重分配」；旧 `_resolve_selected_slots(None, …)` 首行即
        返回 `featured_slots`。反向断言：若此处返回 `None`，本用例必红。
        """
        dist = dict(BASE)
        out = SelectedModifier(SCOPE).apply(
            _ctx(dist), _View(guaranteed=True), dist, False)

        assert out is not None, 'guaranteed_init=True 且未定轨是既定配置形态'
        assert out['ssr_featured'] == pytest.approx(0.01), 'A 退化为全部 featured'
        assert out['ssr'] == 0.0

    def test_selected_modifier_state_keys_declare_selected_card(self):
        """`state_keys()` 须含读键 `selected_card`（§3.1.1 的 Modifier 行：读键就申报）。"""
        assert SelectedModifier(SCOPE).state_keys() == \
            ('guaranteed', 'fate_points', 'selected_card')

    def test_selected_modifier_matches_old_class(self):
        """M1 位级对照：与旧 `TargetedBehavior.before_draw`（guaranteed 分支）严格相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        ctx.state.set(NAME, 'selected_card', 'ssr_up')
        ctx.state.set(NAME, 'guaranteed', True)
        old = TargetedBehavior(NAME, ctx.state, scope=SCOPE, fate_threshold=1)
        new = SelectedModifier(SCOPE, tau=1)

        expect = old.before_draw(ctx)
        got = new.apply(ctx, _View(selected_card='ssr_up', guaranteed=True), dist, False)
        assert got == expect, '位级对照：严格相等（非 approx）'


# ══════════════════════════════════════════════════════════════════
# ④ NotOwnedModifier（§3.1.2 机制表第 7 行 / §3.10.4 的 G3）
# ══════════════════════════════════════════════════════════════════

class TestNotOwnedModifier:
    """G3——`counter >= tau` 时把「未拥有」的 featured 卡之外的概率整组搬给它们。"""

    def test_not_owned_modifier_target_set_is_unowned_featured(self):
        """目标集构造：A = `featured_cards[scope]` 中未拥有者、Q = 更低稀有度 ∪ scope 减去 A。

        全部未拥有时 A = 整个 featured；Q 含 scope 内非 featured **与更低稀有度**（sr / r
        归零），A 侧取绝对 1.0（hard 家族的 M1 形态）。
        """
        dist = dict(BASE)
        out = NotOwnedModifier(SCOPE, threshold=5).apply(
            _ctx_with_sim(dist), _view(5), dist, False)

        assert out['ssr_featured'] == pytest.approx(1.0), 'A 取绝对 1.0（hard 家族 M1 形态）'
        assert out['ssr'] == 0.0, 'scope 减去 A 进 Q、被搬空'
        assert out['sr'] == 0.0 and out['r'] == 0.0, '更低稀有度在 Q 内、被搬空'
        assert sum(out.values()) == pytest.approx(1.0)

    def test_not_owned_modifier_excludes_owned_featured_from_a(self):
        """A = featured 中**未拥有**者（拥有过滤）——宽槽夹具，已拥有一张 featured 卡。

        已拥有的 `ssr_up_a`（槽 `ssr_fa`）被排除出 A，故 A 只含 `ssr_fb`，它收下全部。
        **判别性**：若去掉 `ctx.sim.owns(c) == 0` 过滤，A = 两槽、按声明权重 3:1 分配
        （`ssr_fa` 得 3/4、`ssr_fb` 得 1/4），本用例必红。

        **M1 期不可断言的部分（如实登记）**：§3.10.4 的裁决「Q 含已拥有的 UP、本抽被搬空」
        在 M1 的**绝对赋值**形态下不可观测——A 之外一律归零，Q 的构成不影响结果；该裁决
        要到 S8 的增量形态（`Σδ = 0`，Q 的构成决定减量落点）才可断言。本用例只钉住
        **A 的拥有过滤**，即该裁决的「未获得」半。
        """
        dist = dict(WIDE_BASE)
        ctx = _wide_ctx(dist)
        ctx.sim = _Sim(owned=('ssr_up_a',))
        out = NotOwnedModifier(SCOPE, threshold=5).apply(ctx, _view(5), dist, False)

        assert out['ssr_fb'] == pytest.approx(1.0), '未拥有的那张 UP 收下全部'
        assert out['ssr_fa'] == 0.0, '已拥有的 UP 不进 A（§3.10.4 的排除语义）'
        assert out['ssr_a'] == 0.0 and out['ssr_b'] == 0.0
        assert out['sr'] == 0.0 and out['r'] == 0.0, '更低稀有度在 Q 内、被搬空' 

    def test_not_owned_modifier_a_side_shape_is_declared(self):
        """A 侧形状 = `declared`——A 内按**声明权重**分配（宽槽夹具，featured 两槽 3:1）。

        扰动 `dist` 使两 featured 槽当前比例为 7:1；按声明权重得 3:1。
        """
        dist = {'ssr_fa': 0.007, 'ssr_fb': 0.001, 'ssr_a': 0.001, 'ssr_b': 0.001,
                'sr': 0.05, 'r': 0.94}
        ctx = _wide_ctx(dist)
        ctx.sim = _Sim()                       # 两张 featured 均未拥有
        out = NotOwnedModifier(SCOPE, threshold=5).apply(ctx, _view(5), dist, False)

        assert out['ssr_fa'] == pytest.approx(0.75), 'A 内按声明权重 3:1（绝对 1.0 量）'
        assert out['ssr_fb'] == pytest.approx(0.25)
        assert out['ssr_a'] == 0.0 and out['ssr_b'] == 0.0
        assert out['sr'] == 0.0 and out['r'] == 0.0

    def test_not_owned_modifier_all_owned_returns_none(self):
        """「全部已拥有」的退化分支取**形态 a**（§3.10.4）：A 为空 → 恒等。

        形态 b（仍给出一件）由 S9-3 的 `on_all_owned` 构造形参承载，本步不提前落。
        """
        dist = dict(BASE)
        ctx = _ctx_with_sim(dist, owned=('ssr_up',))
        assert NotOwnedModifier(SCOPE, threshold=5).apply(ctx, _view(5), dist, False) is None

    def test_not_owned_modifier_below_threshold_returns_none(self):
        """条件极性：`counter >= tau`（**不是恒真**）——τ 未到即恒等。

        若误写成恒真，本用例必红；该形态正是 §3.10.4 开头否定的 pool 层近似。
        """
        dist = dict(BASE)
        assert NotOwnedModifier(SCOPE, threshold=50).apply(
            _ctx_with_sim(dist), _view(49), dist, False) is None
        assert NotOwnedModifier(SCOPE, threshold=50).apply(
            _ctx_with_sim(dist), _view(50), dist, False) is not None, '第 50 抽须触发'

    def test_not_owned_modifier_higher_rarity_exempt_m1_form(self):
        """M1 形态：更高稀有度**豁免**（原值保留）→ 存在更高稀有度时输出 `Σ > 1`
        （§3.9.5 的 `Σ(p + δ) ≠ 1` 行 / §3.1.2 边界二，属已登记差异类）。"""
        scope_cards = {'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_up', 'sr_std'),
                       'r': ('r_std',)}
        featured_cards = {'ssr': ('ssr_up',), 'sr': ('sr_up',)}
        scope_slots = {'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr', 'sr_up'),
                       'r': ('r',)}
        featured_slots = {'ssr': ('ssr_featured',), 'sr': ('sr_up',), 'r': ('r',)}
        card_to_slot = {'ssr_up': 'ssr_featured', 'ssr_std': 'ssr',
                        'sr_up': 'sr_up', 'sr_std': 'sr', 'r_std': 'r'}
        dist = {'ssr_featured': 0.006, 'ssr': 0.004, 'sr_up': 0.02, 'sr': 0.03, 'r': 0.94}
        ctx = _ctx_with_sim(dist, scope_cards=scope_cards,
                            featured_cards=featured_cards, scope_slots=scope_slots,
                            featured_slots=featured_slots, card_to_slot=card_to_slot)
        out = NotOwnedModifier('sr', threshold=5).apply(ctx, _view(5), dist, False)

        assert out['sr_up'] == pytest.approx(1.0), 'A = sr 的未拥有 featured'
        assert out['sr'] == 0.0 and out['r'] == 0.0
        assert out['ssr_featured'] == dist['ssr_featured'], '更高稀有度豁免'
        assert out['ssr'] == dist['ssr']
        assert sum(out.values()) > 1.0, '豁免致 Σ > 1（M1 形态，非 S8 的配平形态）'
