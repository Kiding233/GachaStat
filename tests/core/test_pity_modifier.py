"""P64 S2a-1：`Modifier` 基类 + `_lower_rarities` + `HardModifier` / `SoftModifier`（§3.1.2 / §3.9.2）。

覆盖四组被测面（§七 S2a-1 的验收四条）：

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
本文件末尾两条用例直接对旧 `HardPityBehavior` / `SoftStepBehavior` 做逐位比对，
钉住该形态（§六 S1–S5 口径的单元级前置；旧类随发布前一次性移除时这两条同批删除）。
"""

import random

import pytest

from gacha_simulator.core.pity import HardPityBehavior, SoftStepBehavior
from gacha_simulator.core.pity_modifier import (
    HardModifier, Modifier, SoftModifier, _lower_rarities,
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


def _draw(rarity_rank=None, scope_cards=None, featured_cards=None, base=None):
    """构造一次抽卡的 `DrawInfo`（槽位级分布所需的全部映射齐备）。"""
    return DrawInfo(
        pool_id='p', pool_instance_id='p_0', reward_id='sr_std',
        reward_rarity='sr', is_featured=False,
        scope_cards=scope_cards if scope_cards is not None else SCOPE_CARDS,
        featured_cards=featured_cards if featured_cards is not None else FEATURED_CARDS,
        scope_slots=SCOPE_SLOTS, featured_slots=FEATURED_SLOTS,
        card_to_slot=CARD_TO_SLOT,
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
        assert got == pytest.approx(expect)

    def test_hard_modifier_target_featured_matches_old_class(self):
        """M1 位级对照：`target='featured'` 与旧 `HardPityBehavior(target_featured=True)` 逐位相等。"""
        dist = {'ssr_featured': 0.013, 'ssr': 0.007, 'sr': 0.11, 'r': 0.87}
        ctx = _ctx(dist)
        old = HardPityBehavior(NAME, ctx.state, scope=SCOPE, btype='hard',
                               threshold=5, target_featured=True)
        new = HardModifier(SCOPE, threshold=5, target='featured')

        expect = old._compute_probabilities(ctx, 5)
        got = new.apply(ctx, _view(5), dist, False)
        assert got == pytest.approx(expect)


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
            assert (got is None and expect == pytest.approx(dist)) or \
                got == pytest.approx(expect), f'counter={counter} 与旧类不等'


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
                    pytest.approx(old_h._compute_probabilities(ctx, 5))

            for counter in (0, 4, 7):
                dist = _random_dist(rng)
                ctx = _ctx(dist)
                old_s = SoftStepBehavior(NAME, ctx.state, scope=scope, btype='soft_step',
                                         deltas=TestSoftModifier.DELTAS)
                new_s = SoftModifier(scope, TestSoftModifier.DELTAS)
                expect = old_s._compute_probabilities(ctx, counter)
                got = new_s.apply(ctx, _view(counter), dist, False)
                assert (got is None and expect == pytest.approx(dist)) or \
                    got == pytest.approx(expect)
