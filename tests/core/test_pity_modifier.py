"""P64 S8-1：`Modifier` 家族（§3.1.2 机制表 / §3.9.2 接口 / §3.9.4 助手）。

**本文件在 S8-1 整体改写**（原文件以 M1 的「槽位级 `apply` 返回分布」为断言面）：
S8 起各 Modifier 实现 `compute_delta(view, dist, ctx) -> Optional[增量向量]`，
`apply` 收敛为 `Modifier` 基类的唯一默认实现（`_apply_delta(dist, compute_delta(...) or {})`），
骨架逐项调用 `compute_delta`。故断言面随之换成三件：

1. **接口面**：`compute_delta` 的三参签名、`None` = 恒等、未覆写即
   `NotImplementedError`（防「漏写 `compute_delta` 的零件静默变成恒等」）；
2. **增量面**：A / Q / 转移量 / A 侧形状逐条对齐 §3.1.2 机制表，且转移族恒有
   `Σδ = 0`（§3.1.5.2.1），故 `_apply_delta` 的归一化退化为恒等；
3. **框架面**：`_apply_delta` 的三形态（`None` / `{}` / 非空增量）与退化保护。

**分布空间是卡级**（D20 / §3.9.1）：`dist` 的键即卡 id，A / Q 两列直接是卡集合。
旧稿写槽位名（`ssr_featured` / `ssr`）且断言「目标集绝对赋值 + 更高稀有度豁免」，
那两件事在 S8 都已消失（前者换成增量、后者换成「不写增量即精确保留」）。

**S7e golden 的 `modifier.*` 用例同批退役**：那 15 条固化的是 M1 的槽位级形态
（输入是槽位名、期望值是绝对赋值的产物），S8 起该形态在生产上不复存在，故
`tests/fixtures/p64_s7e_golden.json` 中这 15 条随本文件改写删除（其 `_format`
段已记该退役），本文件改用**显式期望值**钉住 S8 形态（逐条算得、可手核）。
"""

import ast
import inspect
import textwrap

import pytest

from gacha_simulator.core.pity import (
    AlwaysActive, Pity, _apply_delta,
)
from gacha_simulator.core.pity_modifier import (
    HardModifier, Modifier, NonFeaturedModifier, NotOwnedModifier, RotatingModifier,
    SelectedModifier, SoftModifier, _lower_rarities, transfer_linear,
)
from gacha_simulator.core.pity_primitives import DrawInfo, PityContext, PityState

# ══════════════════════════════════════════════════════════════════
# 夹具：一个 ssr（含 featured）/ sr / r 三稀有度池，**卡级**分布
# ══════════════════════════════════════════════════════════════════

SCOPE = 'ssr'
NAME = 'ssr_hard'

RARITY_RANK = {'ssr': 0, 'sr': 1, 'r': 2}
SCOPE_CARDS = {'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_std',), 'r': ('r_std',)}
FEATURED_CARDS = {'ssr': ('ssr_up',)}
SCOPE_SLOTS = {'ssr': ('ssr', 'ssr_featured'), 'sr': ('sr',), 'r': ('r',)}
FEATURED_SLOTS = {'ssr': ('ssr_featured',), 'sr': ('sr',), 'r': ('r',)}
CARD_TO_SLOT = {'ssr_up': 'ssr_featured', 'ssr_std': 'ssr', 'sr_std': 'sr', 'r_std': 'r'}
#: 卡级基础分布（Σ = 1.0）。它同时是 `ctx.base_probabilities`（`declared` 形状的 `w` 来源）。
BASE = {'ssr_up': 0.006, 'ssr_std': 0.004, 'sr_std': 0.05, 'r_std': 0.94}

#: 两张 featured 卡的池形（S8 的「单卡定向」判别面：A = 定轨卡 vs A = 全部 featured）。
TWO_UP_CARDS = {'ssr': ('f1', 'f2', 's1')}
TWO_UP_FEATURED = {'ssr': ('f1', 'f2')}
TWO_UP_BASE = {'f1': 0.2, 'f2': 0.2, 's1': 0.6}


def _draw(rarity_rank=None, scope_cards=None, featured_cards=None, base=None,
          scope_slots=None, featured_slots=None, card_to_slot=None):
    """构造一次抽卡的 `DrawInfo`（卡级分布所需的全部映射齐备）。

    槽位三字段仍填入（ISSUE-901：旧保底类与等价性装置读它们，删除点推迟到
    「发布前一次性移除旧保底类」的 commit），但**不是**本管道键空间。
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


def _ctx(dist=None, readonly=False, **kw):
    """构造一次抽卡的 `PityContext`（`current` 为**卡级**分布）。"""
    return PityContext(draw=_draw(**kw),
                       current=dict(dist if dist is not None else BASE),
                       state=PityState(), readonly=readonly)


class _View:
    """状态视图的最小替身：各机制只经 `view.get(key, default)` 读状态。"""

    def __init__(self, **kw):
        self._d = kw

    def get(self, key, default=None):
        return self._d.get(key, default)


def _view(**kw):
    return _View(**kw)


class _Sim:
    """`SimView` 的最小替身（`NotOwnedModifier` 只经 `ctx.sim.owns(card_id)` 读持有张数）。"""

    def __init__(self, owned=()):
        self._owned = set(owned)

    def owns(self, card_id):
        return 1 if card_id in self._owned else 0


def _ctx_with_sim(dist, owned=(), **kw):
    ctx = _ctx(dist, **kw)
    ctx.sim = _Sim(owned)
    return ctx


def _delta(mod, view=None, dist=None, ctx=None):
    """取一次 `compute_delta` 的结果（`view` 缺省为空视图）。

    `dist` 的取值次序：显式传入 → `ctx.current` → `BASE`。**`ctx` 与 `dist` 必须同源**
    （夹具换池形时两者要一起换，否则 A / Q 会落在另一个键空间上）。
    """
    if dist is None:
        dist = dict(ctx.current) if ctx is not None else dict(BASE)
    if ctx is None:
        ctx = _ctx(dist)
    return mod.compute_delta(view if view is not None else _View(), dist, ctx)


def _applied(mod, view=None, dist=None, ctx=None):
    """把 `compute_delta` 的结果经框架归一化作用到分布上（= 骨架的内循环同式）。"""
    if dist is None:
        dist = dict(ctx.current) if ctx is not None else dict(BASE)
    return _apply_delta(dist, _delta(mod, view, dist, ctx) or {})


# ══════════════════════════════════════════════════════════════════
# ① Modifier 基类与框架归一化（§3.9.2 / §3.14.3）
# ══════════════════════════════════════════════════════════════════

class TestModifierBase:
    """基类的两个默认实现 + 声明面 + 三形态（`None` / `{}` / 非空增量）。"""

    def test_base_compute_delta_raises_not_implemented(self):
        """未覆写 `compute_delta` 的子类**不得静默变成恒等零件**。

        §3.9.2 的基类代码块把 `compute_delta` 写成只有 docstring 的接口声明
        （等价于返回 `None`），但那样「漏写该方法的子类」会静默恒等（机制不生效、
        不报错），与本计划一律按阻塞级处理的失效模式同类。故基类实现体抛
        `NotImplementedError` 且带类名：六个机制全部覆写它，生产路径零影响。
        """
        with pytest.raises(NotImplementedError) as excinfo:
            Modifier().compute_delta(_View(), dict(BASE), _ctx())
        assert 'Modifier' in str(excinfo.value)

    def test_modifier_base_rebind_is_noop_and_declares_nothing(self):
        """`rebind` 空实现（P75 纪律：方法必须存在、不得省略）；`state_keys()` 默认
        `()`；`namespace` 默认 `None`。"""
        mod = Modifier()
        st = PityState()
        assert mod.rebind(st, NAME) is None
        assert st.to_dict() == {'data': {}}, '空实现不得写任何状态键'
        assert mod.state_keys() == ()
        assert mod.namespace is None

    def test_apply_default_impl_covers_three_delta_forms(self):
        """`apply` 的正式默认实现对三形态的处置：`None` / `{}` → 恒等；非空 → 归一化。

        `apply` 在 S8 的生产路径上无消费者（骨架改调 `compute_delta`），它是
        「`apply()` 保留为默认实现」这条契约的承载处（§3.14.3），故本用例直接驱动它。
        """
        dist = {'a': 0.5, 'b': 0.5}

        class _NoneMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                return None

        class _EmptyMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                return {}

        class _UnbalancedMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                return {'a': 0.25}      # Σ(out + δ) = 1.25 ≠ 1 → 归一化非恒等

        ctx = _ctx(dist)
        assert _NoneMod().apply(ctx, _View(), dict(dist), False) == dist
        assert _EmptyMod().apply(ctx, _View(), dict(dist), False) == dist
        assert _UnbalancedMod().apply(ctx, _View(), dict(dist), False) == \
            pytest.approx({'a': 0.6, 'b': 0.4})

    def test_state_keys_declared_by_reading_modifiers(self):
        """读 `counter` 的 Modifier 须覆写声明集（§3.9.2）——否则 §3.12.2 判据 2
        对全部 preset 退化为恒真。"""
        assert HardModifier(SCOPE).state_keys() == ('counter',)
        assert SoftModifier(SCOPE, ()).state_keys() == ('counter',)


class TestApplyDelta:
    """框架级归一化（§3.9.2）：`(p + δ) / Σ(p + δ)` 与其退化保护。"""

    def test_apply_delta_normalizes_unbalanced_delta(self):
        out = _apply_delta({'a': 0.5, 'b': 0.5}, {'a': 0.25})
        assert out == pytest.approx({'a': 0.6, 'b': 0.4})
        assert sum(out.values()) == pytest.approx(1.0)

    def test_apply_delta_ignores_keys_absent_from_dist(self):
        """只遍历 `dist` 的键：`δ` 里多出来的键**不参与输出**（增量按稀疏给出）。"""
        out = _apply_delta({'a': 1.0}, {'a': 0.0, 'zzz': 5.0})
        assert set(out) == {'a'} and out['a'] == pytest.approx(1.0)

    def test_apply_delta_degenerate_total_returns_original(self):
        """`Σ(out) <= 0` → 返回原分布（§3.9.5 的「归一化后总量 ≤ 0」行）。"""
        dist = {'a': 1.0}
        assert _apply_delta(dist, {'a': -1.0}) is dist
        assert _apply_delta(dist, {'a': -2.0}) is dist

    def test_apply_delta_balanced_delta_needs_no_normalization(self):
        """配平增量（转移族形态）在二进制精确取值下**逐位**等于 `p + δ`。

        归一化因子恰为 1.0（`Σδ = 0`），故除法不得扰动任何一位（§3.1.5.2.1 的
        「框架归一化退化为恒等」）。判据写成对 `p + δ` 的**严格相等**，而不是对输入
        分布相等：配平增量本身会移动质量，输入分布不是它的不动点。
        """
        dist = {'a': 0.25, 'b': 0.75}
        delta = {'a': 0.75, 'b': -0.75}
        assert _apply_delta(dist, delta) == {'a': 1.0, 'b': 0.0}
        assert _apply_delta(dist, delta) == {c: dist[c] + delta[c] for c in dist}

    def test_skeleton_normalizes_unbalanced_delta_from_custom_modifier(self):
        """**生产骨架的归一化兜底**（S8-4 审查 F1）：调用点不得退化为裸 `p + δ`。

        上面四条驱动的是 `_apply_delta` **本体**，而 `Pity.before_draw` 内循环的
        调用点此前无用例覆盖：把该处的 `_apply_delta(out, d)` 换成裸 `p + δ`，全量
        测试仍全绿（转移族恒配平，`Σ(p + δ)` 与 1 的偏差只有 1 ULP，落在各处
        1e-12 容差内），即「函数本体有面、生产调用点无面」。故本用例驱动**真实
        骨架**配一个**返回不配平 δ 的自定义 Modifier**（只给 `ssr_up` 加 0.1、
        不给任何卡减量，使 `Σ(p + δ) = 1.1`）：去掉调用点归一化即红。
        """
        class _UnbalancedMod(Modifier):
            def compute_delta(self, view, dist, ctx):
                return {'ssr_up': 0.1}

        pity = Pity(name='p', state=PityState(), scope=SCOPE, btype='hard',
                    trackers=[], modifiers=[_UnbalancedMod()],
                    lifecycle=AlwaysActive())
        out = pity.before_draw(_ctx())

        delta = {'ssr_up': 0.1}
        expected = {c: BASE[c] + delta.get(c, 0.0) for c in BASE}
        total = sum(expected.values())
        assert total == pytest.approx(1.1), '夹具须确实不配平（否则本用例无验收面）'
        for c in BASE:
            assert out[c] == pytest.approx(expected[c] / total, abs=1e-12), c
        assert sum(out.values()) == pytest.approx(1.0, abs=1e-12)


class TestNamespaceViewDispatch:
    """ISSUE-407 / ISSUE-505：遍历点经 `self._view_for(mod)` 取 view（S8-1 强制）。"""

    def test_namespaced_modifier_reads_its_own_namespace(self):
        """`namespace` 非 `None` 的 Modifier 必须读到**自己的命名空间**。

        判据两条：① 它收到的 view 是 `StateView(state, '<ns>')`；② 它读到的值来自
        该命名空间（同名键在两处放不同值即可分辨）。写死 `self._view` 时两条都红。
        """
        seen = {}

        class _NsMod(Modifier):
            namespace = 'x_soft'

            def compute_delta(self, view, dist, ctx):
                seen['name'] = view._name
                seen['value'] = view.get('probe')
                return None

        st = PityState()
        st.set('p', 'probe', 'default-ns')
        st.set('x_soft', 'probe', 'part-ns')
        pity = Pity(name='p', state=st, scope=SCOPE, btype='hard',
                    trackers=[], modifiers=[_NsMod()], lifecycle=AlwaysActive())
        pity.before_draw(_ctx())

        assert seen['name'] == 'x_soft', '零件须拿到自己命名空间的 view'
        assert seen['value'] == 'part-ns', '读到的值须来自该命名空间（不是默认 view）'

    def test_skeleton_never_passes_default_view_to_compute_delta(self):
        """S8 骨架内**无** `mod.compute_delta(ctx, self._view, …)` 直写形态（AST 判据）。

        该判据的对象是**骨架源码**（不扫行为），故「有人把遍历点改回 `self._view`」
        在测试期即失败（默认情形下无行为差异，只有声明命名空间的零件才显形，
        见上一条）。
        """
        # `getsource` 给的是**带类体缩进**的方法源码，先 dedent 再 parse
        src = textwrap.dedent(inspect.getsource(Pity.before_draw))
        tree = ast.parse(src)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == 'compute_delta']
        assert calls, '骨架内须有 compute_delta 调用点（否则本判据无对象）'
        for node in calls:
            args = node.args
            assert len(args) == 3, f'compute_delta 须收三参：{ast.dump(node)}'
            first = ast.dump(args[0])
            assert 'self' in first and '_view_for' in first, (
                f'首个实参须为 `self._view_for(mod)`，实测 {first}')
            assert 'self._view' not in first.replace('_view_for', ''), (
                f'不得写死 `self._view`：{first}')


# ══════════════════════════════════════════════════════════════════
# ② HardModifier（§3.1.2 机制表第 1 / 2 行）
# ══════════════════════════════════════════════════════════════════

class TestHardModifier:
    """`counter >= threshold` 时把源组概率整组搬给目标集（夺取型 `amount = p(Q)`）。"""

    def test_target_scope_moves_lower_rarity_into_scope(self):
        """`target='scope'`：A = `scope_cards[scope]`，Q = 更低稀有度，A 侧 `current`。

        A 内按当前比例收下 `p(Q)`（0.006 : 0.004 之比不变）→ 0.6 / 0.4。
        """
        delta = _delta(HardModifier(SCOPE, threshold=5, target='scope'), _view(counter=5))
        assert delta['ssr_up'] == pytest.approx(0.99 * 0.6)
        assert delta['ssr_std'] == pytest.approx(0.99 * 0.4)
        assert delta['sr_std'] == pytest.approx(-0.05)
        assert delta['r_std'] == pytest.approx(-0.94)
        assert sum(delta.values()) == pytest.approx(0.0), 'Σδ = 0（转移族配平）'
        assert _applied(HardModifier(SCOPE, threshold=5),
                        _view(counter=5)) == pytest.approx(
            {'ssr_up': 0.6, 'ssr_std': 0.4, 'sr_std': 0.0, 'r_std': 0.0})

    def test_target_featured_narrows_target_and_uses_declared_shape(self):
        """`target='featured'`：A = `featured_cards[scope]`，Q 还含 `scope\\A`，A 侧 `declared`。

        `declared` 在单卡 A 上退化为「收下整份 `p(Q)`」→ `ssr_up` 得 1.0
        （`p(Q)` = `ssr_std` + 更低稀有度 = 0.994）。
        """
        out = _applied(HardModifier(SCOPE, threshold=5, target='featured'),
                       _view(counter=5))
        assert out == pytest.approx({'ssr_up': 1.0, 'ssr_std': 0.0,
                                     'sr_std': 0.0, 'r_std': 0.0})

    def test_transfer_amount_is_pq_not_boost_fraction(self):
        """转移量口径 = 夺取型 `amount = p(Q)`（源组**整组**搬空），不是 soft 的
        `boost/100` 部分转移：构造 `p(Q)` 很小的分布，若误写成部分转移，源组会留残值。"""
        dist = {'ssr_up': 0.005, 'ssr_std': 0.005, 'sr_std': 0.01, 'r_std': 0.98}
        out = _applied(HardModifier(SCOPE, threshold=1, target='scope'),
                       _view(counter=1), dist=dist)
        assert out['sr_std'] == pytest.approx(0.0) and out['r_std'] == pytest.approx(0.0)
        assert out['ssr_up'] + out['ssr_std'] == pytest.approx(1.0), 'A 收下整组'

    def test_higher_rarity_is_exactly_untouched(self):
        """**S8 形态**：更高稀有度**不写增量即精确保留**（M1 的「豁免」形态已废）。

        `hard(scope='sr')`：A = sr 卡、Q = r 卡，ssr 两张卡既不在 A 也不在 Q，
        故其值**逐位**不变（不是「豁免后归一化缩水」），且 `Σδ = 0`、输出 `Σ = 1`
        （M1 输出 `Σ = 1.009`，见 §3.1.2 边界二与 §3.9.5 的 `Σ(p + δ) ≠ 1` 行）。
        """
        delta = _delta(HardModifier('sr', threshold=5, target='scope'), _view(counter=5))
        assert 'ssr_up' not in delta and 'ssr_std' not in delta, \
            '更高稀有度不得写增量（写 0 也不必要，未列出即 δ = 0）'
        out = _applied(HardModifier('sr', threshold=5, target='scope'), _view(counter=5))
        assert out['ssr_up'] == BASE['ssr_up'] and out['ssr_std'] == BASE['ssr_std']
        # A（sr 卡）收下 p(Q) = p(r 卡) = 0.94 → 0.99；更高稀有度那 0.01 不在 A 也不在 Q
        assert out['sr_std'] == pytest.approx(0.99) and out['r_std'] == pytest.approx(0.0)
        assert sum(out.values()) == pytest.approx(1.0), 'S8 起 Σp ≡ 1'

    def test_below_threshold_returns_none(self):
        """条件不成立 → `None`（恒等；§3.1.2「不生效即 return None」）。"""
        assert _delta(HardModifier(SCOPE, threshold=5), _view(counter=4)) is None

    def test_featured_empty_falls_back_to_scope(self):
        """`target='featured'` 且该 scope 无 featured 卡 → **空集回退 scope 全集**
        （对齐旧 `featured_slots.get(scope, scope_slots)`，ISSUE-403 的空集回退纪律）。

        回退后 A = scope 全集、Q = 更低稀有度；A 侧 `declared` 按声明权重
        （0.006 : 0.004）分配 `p(Q)` → 0.6 / 0.4（与 `current` 同值，因当前比例
        恰等于声明比例）。
        """
        ctx = _ctx(featured_cards={})
        out = _applied(HardModifier(SCOPE, threshold=5, target='featured'),
                       _view(counter=5), ctx=ctx)
        assert out == pytest.approx({'ssr_up': 0.6, 'ssr_std': 0.4,
                                     'sr_std': 0.0, 'r_std': 0.0})

    def test_lowest_rarity_scope_is_a_no_op(self):
        """**边界一**（§3.1.2）：scope 为最低稀有度时 Q 为空 → 不转移（恒等）。

        旧实现靠「绝对赋值 + 更高稀有度豁免」造出 `Σ > 1`（造质量），不属于
        「A 加 Q 减」族；手册无此配置，故登记为边界而非缺口。
        """
        assert _delta(HardModifier('r', threshold=5, target='scope'), _view(counter=5)) is None

    def test_declared_shape_transfers_when_pA_is_zero(self):
        """**来源二**（§3.1.5.6.1 / §3.9.5）：`p(A) = 0` 而 `w(A) > 0` 时 `declared` 仍转移。

        这正是「夺 UP 的算子先清空 featured、`hard(target='featured')` 仍要保 UP」
        的冲突配置路径，也是 `declared` 唯一的用武之地。
        """
        dist = {'ssr_up': 0.0, 'ssr_std': 0.01, 'sr_std': 0.05, 'r_std': 0.94}
        out = _applied(HardModifier(SCOPE, threshold=5, target='featured'),
                       _view(counter=5), dist=dist)
        assert out['ssr_up'] == pytest.approx(1.0), 'p(A) = 0 也要抬起目标集'
        assert out['ssr_std'] == pytest.approx(0.0) and out['r_std'] == pytest.approx(0.0)

    def test_declared_shape_returns_none_when_wA_is_zero(self):
        """**来源一**（池子声明该组不可获得）：`w(A) = 0` → 不转移（恒等）。"""
        ctx = _ctx(base={'ssr_up': 0.0, 'ssr_std': 0.01, 'sr_std': 0.05, 'r_std': 0.94})
        assert _delta(HardModifier(SCOPE, threshold=5, target='featured'),
                      _view(counter=5), ctx=ctx) is None


# ══════════════════════════════════════════════════════════════════
# ③ SoftModifier（§3.1.2 机制表第 3 行 / §3.4.1 修正 ①）
# ══════════════════════════════════════════════════════════════════

class TestSoftModifier:
    """`boost > 0` 时把源组的 `boost` 个百分点搬给 scope。"""

    DELTAS = ((4, 0.0), (6, 5.0))       # 前 4 抽不增，第 5 抽起每抽 +5%

    def test_boost_is_percentage_points_not_scaled_by_pq(self):
        """`amount = boost%(counter) / 100`：目标组概率**增加** boost 个百分点，
        **不得再乘 `p(Q)`**（§3.4.1 修正 ①）。

        反例口径 `amount = boost/100 · p(Q)` 在 `p(Q) = 0.99` 时给 0.0495，与 0.05
        差 5e-4；该差异前期极小、爬升后段才拉开，故必须直接钉住「增量恰为 boost/100」。
        """
        dist = dict(BASE)
        p_q = dist['sr_std'] + dist['r_std']
        delta = _delta(SoftModifier(SCOPE, self.DELTAS), _view(counter=5), dist)
        a_gain = delta['ssr_up'] + delta['ssr_std']
        assert a_gain == pytest.approx(0.05), 'counter=5 → boost=5 → amount=0.05'
        assert a_gain != pytest.approx(0.05 * p_q), '不得乘 p(Q)'
        assert sum(delta.values()) == pytest.approx(0.0), '转移族配平'

    def test_amount_is_capped_at_pq(self):
        """`amount` 封顶 `p(Q)`（§3.9.4 的前置条件表：`amount <= p(Q)`）。

        构造 `boost/100 > p(Q)` 的分布：不封顶则 Q 侧增量为负、产出负概率
        （§3.12.1 非负性判据会判违规）。本用例直接断言「Q 侧恰好归零、无负值」。
        """
        dist = {'ssr_up': 0.5, 'ssr_std': 0.4, 'sr_std': 0.05, 'r_std': 0.05}
        mod = SoftModifier(SCOPE, ((1, 0.0), (1, 100.0)))     # counter=2 → boost=100
        out = _applied(mod, _view(counter=2), dist=dist)
        assert min(out.values()) >= 0.0, f'不得产出负概率：{out}'
        assert out['sr_std'] == pytest.approx(0.0) and out['r_std'] == pytest.approx(0.0)
        assert out['ssr_up'] + out['ssr_std'] == pytest.approx(1.0)

    def test_counter_zero_returns_none(self):
        """条件不成立（boost 为 0）→ `None`（恒等）。"""
        assert _delta(SoftModifier(SCOPE, self.DELTAS), _view(counter=0)) is None

    def test_deltas_rle_accumulates_by_segment(self):
        """RLE 段表按 counter 定位当前段累计 boost%（旧 `_cumulative_boost` 同式）。"""
        mod = SoftModifier(SCOPE, ((4, 0.0), (6, 5.0)))
        assert _delta(mod, _view(counter=4)) is None
        delta = _delta(mod, _view(counter=10))
        assert delta['ssr_up'] + delta['ssr_std'] == pytest.approx(0.30)

    def test_scope_total_preserved_at_every_counter(self):
        """各档位下 `Σp = 1` 且非负（转移族配平的直接后果）。"""
        for counter in [0, 40, 80, 85, 90, 100]:
            out = _applied(SoftModifier(SCOPE, ((72, 0.0), (18, 5.555556))),
                           _view(counter=counter))
            assert sum(out.values()) == pytest.approx(1.0), f'counter={counter}'
            assert min(out.values()) >= 0.0

    def test_empty_scope_returns_none(self):
        """空目标集 → 恒等（§3.9.5；旧实现同为空集早退）。"""
        assert _delta(SoftModifier(SCOPE, self.DELTAS), _view(counter=5),
                      ctx=_ctx(scope_cards={'sr': ('sr_std',)})) is None


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


# ══════════════════════════════════════════════════════════════════
# ⑤ RotatingModifier（§3.1.2 机制表第 4 行 / §3.9.6 的只读标记）
# ══════════════════════════════════════════════════════════════════

class TestRotatingModifier:
    """`guaranteed`（∨ `extra_flag`）时把 scope 内非 featured 的概率整组搬给 featured。"""

    def test_target_set_is_featured_and_scope_is_conserved(self):
        """A = `featured_cards[scope]`、Q = `scope\\featured`、`amount = p(Q)`。

        scope 内重分配：scope 外（sr / r）**不写增量**、`Σ` 仍为 1。
        """
        delta = _delta(RotatingModifier(SCOPE), _view(guaranteed=True))
        assert delta['ssr_up'] == pytest.approx(0.004)
        assert delta['ssr_std'] == pytest.approx(-0.004)
        assert 'sr_std' not in delta and 'r_std' not in delta, 'scope 外不动'
        out = _applied(RotatingModifier(SCOPE), _view(guaranteed=True))
        assert out['ssr_up'] == pytest.approx(0.01) and out['ssr_std'] == pytest.approx(0.0)
        assert out['sr_std'] == BASE['sr_std'] and out['r_std'] == BASE['r_std']
        assert sum(out.values()) == pytest.approx(1.0)

    def test_empty_featured_returns_none(self):
        """空目标集（该 scope 无 featured 卡）→ 恒等（§3.9.5；旧实现同为空集早退）。"""
        assert _delta(RotatingModifier(SCOPE), _view(guaranteed=True),
                      ctx=_ctx(featured_cards={})) is None

    def test_not_guaranteed_returns_none(self):
        """条件不成立（`guaranteed` 未置位）→ `None`（§3.1.2「不生效即 return None」）。"""
        assert _delta(RotatingModifier(SCOPE), _View()) is None

    def test_extra_flag_triggers_but_readonly_query_suppresses_it(self):
        """`extra_flag` 只影响**条件**（§3.2 的 `rotating_cr` 行）；**只读查询**时被抑制
        （§3.9.6 的「处置（两期）②」的 M2 落点：抑制依据是 `ctx.readonly` 查询标记，
        不再是 Modifier 形参）。

        反向断言：去掉该抑制（或把标记读成永远 False）时第二条必红：「查询不体现
        CR 拦截」是旧 `RotatingCRBehavior` 的既定语义，策略层的概率查询依赖它。
        """
        mod = RotatingModifier(SCOPE, extra_flag='cr_intercepted')
        view = _View(cr_intercepted=True)
        assert _delta(mod, view, ctx=_ctx(readonly=False)) is not None, 'extra_flag 置位即触发'
        assert _delta(mod, view, ctx=_ctx(readonly=True)) is None, '只读查询须抑制 extra_flag'
        assert _delta(mod, _View(), ctx=_ctx(readonly=False)) is None, '两标志皆无则不触发'
        assert mod.state_keys() == ('guaranteed', 'cr_intercepted'), 'extra_flag 也须申报'
        assert RotatingModifier(SCOPE).state_keys() == ('guaranteed',)

    def test_guaranteed_is_not_suppressed_by_readonly(self):
        """`guaranteed` 不受只读标记影响（旧类同样无条件读它）。"""
        out = _applied(RotatingModifier(SCOPE), _view(guaranteed=True),
                       ctx=_ctx(readonly=True))
        assert out['ssr_up'] == pytest.approx(0.01)


# ══════════════════════════════════════════════════════════════════
# ⑥ NonFeaturedModifier（§3.1.2 机制表第 5 行 / §3.3 的 G1）
# ══════════════════════════════════════════════════════════════════

class TestNonFeaturedModifier:
    """G1（rotating_inverse）——`forced_loss` 时把 featured 的概率整组搬给非 featured。"""

    def test_target_set_is_scope_minus_featured(self):
        """A = `scope\\featured`、Q = `featured_cards[scope]`（与 rotating 互换），
        A 侧 `declared`；scope 总量不变、scope 外不动。"""
        out = _applied(NonFeaturedModifier(SCOPE), _view(forced_loss=True))
        assert out['ssr_std'] == pytest.approx(0.01) and out['ssr_up'] == pytest.approx(0.0)
        assert out['sr_std'] == BASE['sr_std'] and out['r_std'] == BASE['r_std']
        assert sum(out.values()) == pytest.approx(1.0)

    def test_declared_shape_works_when_pA_is_zero(self):
        """`p(A) = 0` 时 `declared` 仍可转移（§3.9.5 的 `p(A) == 0` 行末句）。

        A（非 featured 的 `ssr_std`）当前概率为 0，按声明权重分配仍把它抬起来：
        `δ_A = +p(Q) > 0`、`δ_Q = −p(Q)`。写成 `current` 形状时 `u_A` 无定义、
        整条机制退化为恒等（本用例必红）。
        """
        dist = {'ssr_up': 0.01, 'ssr_std': 0.0, 'sr_std': 0.05, 'r_std': 0.94}
        delta = _delta(NonFeaturedModifier(SCOPE), _view(forced_loss=True), dist=dist)
        assert delta['ssr_std'] == pytest.approx(0.01), 'p(A) = 0 也要抬起目标集'
        assert delta['ssr_up'] == pytest.approx(-0.01)

    def test_not_forced_loss_returns_none(self):
        """条件不成立 → `None`；`state_keys()` 声明该标志。"""
        assert _delta(NonFeaturedModifier(SCOPE), _View()) is None
        assert NonFeaturedModifier(SCOPE).state_keys() == ('forced_loss',)


# ══════════════════════════════════════════════════════════════════
# ⑦ SelectedModifier（§3.1.2 机制表第 6 行 / §六 的「S8 单卡定向」）
# ══════════════════════════════════════════════════════════════════

class TestSelectedModifier:
    """`guaranteed` 或定轨就绪时把 scope 的概率整组搬给**定轨选中卡**。"""

    @staticmethod
    def _two_up_ctx(dist=None):
        return _ctx(dist or TWO_UP_BASE, scope_cards=dict(TWO_UP_CARDS),
                    featured_cards=dict(TWO_UP_FEATURED), base=dict(TWO_UP_BASE))

    def test_targets_single_card_not_the_whole_featured_group(self):
        """**S8 单卡定向**（§六）：A = `(selected,)`，**同 scope 的另一张 featured 卡也归零**。

        判别性：A 若写成「全部 featured」，两张 UP 卡会按声明权重各得 0.5；本断言
        要求定轨卡独得 1.0、兄弟 UP 卡为 0：这正是 S8 相对旧实现（同槽位平摊
        50/50）的语义提升。
        """
        ctx = self._two_up_ctx()
        out = _applied(SelectedModifier(SCOPE, tau=1),
                       _view(selected_card='f1', guaranteed=True), ctx=ctx)
        assert out['f1'] == pytest.approx(1.0), '定轨卡独得整个 scope'
        assert out['f2'] == pytest.approx(0.0), '兄弟 UP 卡不在 A 内'
        assert out['s1'] == pytest.approx(0.0)

    def test_unset_selected_card_falls_back_to_all_featured(self):
        """未定轨（`selected_card` 缺失）→ 目标集退化为**全部 featured 卡**。

        依据：手册明写「不填卡 ID 时可改用 `guaranteed_init = true` 等效」，该组合正是
        「出金必是 UP、UP 内按声明权重分配」；旧 `_resolve_selected_slots(None, …)`
        首行即返回 `featured_slots`。反向断言：若此处返回 `None`，本用例必红。
        """
        ctx = self._two_up_ctx()
        out = _applied(SelectedModifier(SCOPE, tau=1), _view(guaranteed=True), ctx=ctx)
        assert out['f1'] == pytest.approx(0.5) and out['f2'] == pytest.approx(0.5)
        assert out['s1'] == pytest.approx(0.0)

    def test_selected_card_outside_featured_falls_back_to_all_featured(self):
        """定轨卡不在 featured 集内（如写了张标准卡）→ 回退全部 featured 卡。

        判据与旧 `_resolve_selected_slots` 对齐：它只在 featured 槽里认目标，
        故「选中一张 scope 内的非 featured 卡」得到的是全部 featured，而不是把那张
        标准卡当目标（**不得**写成 `sel in scope`）。
        """
        ctx = self._two_up_ctx()
        out = _applied(SelectedModifier(SCOPE, tau=1),
                       _view(selected_card='s1', guaranteed=True), ctx=ctx)
        assert out['f1'] == pytest.approx(0.5) and out['f2'] == pytest.approx(0.5)
        assert out['s1'] == pytest.approx(0.0)

    def test_fate_ready_triggers_without_guaranteed(self):
        """条件内联的第二析取项：已定轨 ∧ `fate_points >= tau`（`fate_ready`）。"""
        assert _delta(SelectedModifier(SCOPE, tau=1),
                      _view(selected_card='ssr_up', fate_points=1)) is not None

    def test_not_triggered_returns_none(self):
        """两个析取项都不成立 → `None`。

        含 `tau=0` 且**未定轨**的反例：旧实现把「已定轨」作为 fate 分支的合取项
        （`selected and fate_points >= threshold`），省掉它会让 `fate_points >= 0` 恒真。
        """
        assert _delta(SelectedModifier(SCOPE),
                      _view(selected_card='ssr_up', fate_points=0)) is None
        assert _delta(SelectedModifier(SCOPE, tau=0),
                      _view(selected_card='ssr_up')) is not None, 'tau=0 定轨即必出'
        assert _delta(SelectedModifier(SCOPE, tau=0), _View()) is None, '未定轨时 tau=0 不得触发'

    def test_state_keys_declare_selected_card(self):
        """`state_keys()` 须含读键 `selected_card`（§3.1.1 的 Modifier 行：读键就申报）。"""
        assert SelectedModifier(SCOPE).state_keys() == \
            ('guaranteed', 'fate_points', 'selected_card')


# ══════════════════════════════════════════════════════════════════
# ⑧ NotOwnedModifier（§3.1.2 机制表第 7 行 / §3.10.4 的 G3）
# ══════════════════════════════════════════════════════════════════

class TestNotOwnedModifier:
    """G3——`counter >= tau` 时把「未拥有」的 featured 卡之外的概率整组搬给它们。"""

    @staticmethod
    def _two_up_ctx(owned=()):
        return _ctx_with_sim(TWO_UP_BASE, owned=owned,
                             scope_cards=dict(TWO_UP_CARDS),
                             featured_cards=dict(TWO_UP_FEATURED),
                             base=dict(TWO_UP_BASE))

    def test_excludes_owned_featured_from_a(self):
        """A = featured 中**未拥有**者：已拥有的 UP 卡不进 A。

        判别性：去掉 `ctx.sim.owns(c) == 0` 过滤后 A = 两张 UP、按声明权重各得 0.5，
        本用例必红。
        """
        out = _applied(NotOwnedModifier(SCOPE, threshold=5), _view(counter=5),
                       ctx=self._two_up_ctx(owned=('f1',)))
        assert out['f2'] == pytest.approx(1.0), '未拥有的那张 UP 收下全部'
        assert out['f1'] == pytest.approx(0.0)

    def test_q_includes_owned_up_and_drains_it(self):
        """**Q 含已拥有的 UP、本抽被搬空**（§3.10.4 的 2026-10-07 裁决）。

        M1 的绝对赋值形态下该裁决不可观测（A 之外一律归零）；S8 的增量形态下 Q 的
        构成决定减量落点，故本用例是该裁决**唯一可断言的承载面**：已拥有的 UP 卡
        落在 Q 内 → 其增量为负、本抽抽不到它（「已获得的装备从 UP 组中排除」）。
        """
        ctx = self._two_up_ctx(owned=('f1',))
        delta = _delta(NotOwnedModifier(SCOPE, threshold=5), _view(counter=5), ctx=ctx)
        assert delta['f1'] < 0.0, '已拥有的 UP 必须在 Q 内被搬空'
        assert delta['f2'] > 0.0

    def test_all_owned_returns_none(self):
        """「全部已拥有」的退化分支取**形态 a**（§3.10.4）：A 为空 → 恒等。

        形态 b（仍给出一件）由 S9-3 的 `on_all_owned` 构造形参承载，本步不提前落。
        """
        assert _delta(NotOwnedModifier(SCOPE, threshold=5), _view(counter=5),
                      ctx=self._two_up_ctx(owned=('f1', 'f2'))) is None

    def test_below_threshold_returns_none(self):
        """条件极性：`counter >= tau`（**不是恒真**）——τ 未到即恒等。

        若误写成恒真，本用例必红；该形态正是 §3.10.4 开头否定的 pool 层近似。
        """
        assert _delta(NotOwnedModifier(SCOPE, threshold=50), _view(counter=49),
                      ctx=self._two_up_ctx()) is None
        assert _delta(NotOwnedModifier(SCOPE, threshold=50), _view(counter=50),
                      ctx=self._two_up_ctx()) is not None, '第 50 抽须触发'

    def test_higher_rarity_untouched(self):
        """scope 非最高稀有度时更高稀有度**逐位保留**（S8 的「不写增量」形态）。

        旧 M1 形态下此处输出 `Σ > 1`（豁免），S8 起 `Σ ≡ 1`（§3.9.5）。
        """
        scope_cards = {'ssr': ('ssr_up', 'ssr_std'), 'sr': ('sr_up', 'sr_std'),
                       'r': ('r_std',)}
        featured_cards = {'ssr': ('ssr_up',), 'sr': ('sr_up',)}
        dist = {'ssr_up': 0.006, 'ssr_std': 0.004, 'sr_up': 0.02, 'sr_std': 0.03,
                'r_std': 0.94}
        ctx = _ctx_with_sim(dist, owned=(), scope_cards=scope_cards,
                            featured_cards=featured_cards)
        out = _applied(NotOwnedModifier('sr', threshold=5), _view(counter=5), dist=dist,
                       ctx=ctx)
        assert out['ssr_up'] == dist['ssr_up'] and out['ssr_std'] == dist['ssr_std']
        # A（sr 的 UP 卡）收下 p(Q)（Q = scope\A ∪ 更低稀有度 = sr_std + r_std = 0.97）
        assert out['sr_up'] == pytest.approx(0.99) and out['sr_std'] == pytest.approx(0.0)
        assert out['r_std'] == pytest.approx(0.0)
        assert sum(out.values()) == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════
# ⑨ 转移族的两条族级不变式（§3.1.5.2.1）
# ══════════════════════════════════════════════════════════════════

class TestTransferFamilyInvariants:
    """六个机制在「触发」形态下的 `Σδ = 0` 与归一化后 `Σp = 1`、非负。"""

    @staticmethod
    def _cases():
        return [
            ('hard/scope', HardModifier(SCOPE, threshold=1, target='scope'),
             _view(counter=1), _ctx()),
            ('hard/featured', HardModifier(SCOPE, threshold=1, target='featured'),
             _view(counter=1), _ctx()),
            ('soft', SoftModifier(SCOPE, ((0, 0.0), (1, 30.0))), _view(counter=1), _ctx()),
            ('rotating', RotatingModifier(SCOPE), _view(guaranteed=True), _ctx()),
            ('non_featured', NonFeaturedModifier(SCOPE), _view(forced_loss=True), _ctx()),
            ('selected', SelectedModifier(SCOPE, tau=1),
             _view(selected_card='ssr_up', guaranteed=True), _ctx()),
            ('not_owned', NotOwnedModifier(SCOPE, threshold=1), _view(counter=1),
             _ctx_with_sim(BASE)),
        ]

    @pytest.mark.parametrize('label,mod,view,ctx', _cases(),
                             ids=[c[0] for c in _cases()])
    def test_delta_is_balanced_and_normalized(self, label, mod, view, ctx):
        dist = dict(ctx.current)
        delta = mod.compute_delta(view, dist, ctx)
        assert delta is not None, f'{label}：本用例要求触发形态'
        assert sum(delta.values()) == pytest.approx(0.0), f'{label}：Σδ = 0'
        out = _apply_delta(dist, delta)
        assert sum(out.values()) == pytest.approx(1.0), f'{label}：Σp = 1'
        assert min(out.values()) >= 0.0, f'{label}：不得产出负概率'

    @pytest.mark.parametrize('label,mod,view,ctx', _cases(),
                             ids=[c[0] for c in _cases()])
    def test_delta_keys_are_dist_keys(self, label, mod, view, ctx):
        """增量向量的键必须落在 `dist` 的键空间内（键空间错位的显形面）。

        `_apply_delta` 只遍历 `dist` 的键，故**错位的键会被静默丢弃**、机制退化为
        恒等；本判据把该形态变成响亮失败（这正是 §七 的原子单元警告所针对的失效）。
        """
        dist = dict(ctx.current)
        delta = mod.compute_delta(view, dist, ctx) or {}
        assert set(delta) <= set(dist), f'{label}：增量键越界 {set(delta) - set(dist)}'

    def test_delta_is_sparse(self):
        """增量按稀疏给出：未改动的卡**不出现**在向量里（`δ = 0` 的键不写）。"""
        delta = _delta(HardModifier('sr', threshold=5), _view(counter=5))
        assert set(delta) == {'sr_std', 'r_std'}, f'更高稀有度不得出现在增量里：{delta}'


def test_transfer_linear_is_the_shared_helper():
    """六个机制共用叶子层助手 `transfer_linear`（§3.9.4 的「定位是助手」）。

    判据：`RotatingModifier` 的增量与直接调用助手的结果逐位相同（证明机制没有
    另写一份搬运算术）。
    """
    dist = dict(BASE)
    direct = transfer_linear(dist, ('ssr_up',), ('ssr_std',), dist['ssr_std'])
    assert _delta(RotatingModifier(SCOPE), _view(guaranteed=True), dist) == direct


# ══════════════════════════════════════════════════════════════════
# ⑩ 空目标集：§六 的「S8 空目标集断言」要求**每个机制**都覆盖
# ══════════════════════════════════════════════════════════════════

def _empty_target_cases():
    """六个机制的「目标集为空」构造（§3.9.5 的空目标集行 / §六 的 S8 断言）。

    | 机制 | 目标集为空的构造 |
    |------|------------------|
    | `hard`（scope 分支） | 该 scope 无卡（`scope_cards` 缺键） |
    | `hard`（featured 分支） | 同上（空 featured 回退 scope，scope 亦空） |
    | `soft` | 同上 |
    | `rotating` | 该 scope 无 featured 卡 |
    | `non_featured` | scope 全是 featured 卡（补集为空） |
    | `selected` | 未定轨且无 featured 卡 |
    | `not_owned` | featured 全部已拥有 |
    """
    # `hard(target='featured')` 的 A 走「空 featured 回退 scope 全集」，故两条都要空；
    # `featured_cards` 非空而 `scope_cards` 缺该键是**畸形 spec**（featured ⊄ scope，
    # §3.1.5.6 的 `A ⊄ U` 边界，构造期校验未实现），不属本用例的形态。
    no_scope = _ctx(scope_cards={'sr': ('sr_std',)}, featured_cards={})
    no_featured = _ctx(featured_cards={})
    all_featured = _ctx(scope_cards={'ssr': ('ssr_up',)},
                        featured_cards={'ssr': ('ssr_up',)})
    return [
        ('hard/scope', HardModifier(SCOPE, threshold=1, target='scope'),
         _view(counter=1), no_scope),
        ('hard/featured', HardModifier(SCOPE, threshold=1, target='featured'),
         _view(counter=1), no_scope),
        ('soft', SoftModifier(SCOPE, ((0, 0.0), (1, 50.0))), _view(counter=1), no_scope),
        ('rotating', RotatingModifier(SCOPE), _view(guaranteed=True), no_featured),
        ('non_featured', NonFeaturedModifier(SCOPE), _view(forced_loss=True),
         all_featured),
        ('selected', SelectedModifier(SCOPE, tau=1), _view(guaranteed=True),
         no_featured),
        ('not_owned', NotOwnedModifier(SCOPE, threshold=1), _view(counter=1),
         _ctx_with_sim(BASE, owned=('ssr_up',), featured_cards={'ssr': ('ssr_up',)})),
    ]


@pytest.mark.parametrize('label,mod,view,ctx', _empty_target_cases(),
                         ids=[c[0] for c in _empty_target_cases()])
def test_empty_target_set_returns_none(label, mod, view, ctx):
    """**空目标集 → `compute_delta` 必须 `return None`**（恒等），每个机制一条。

    §六 的「S8 空目标集断言」原文：「`A` 为空或 `p(A) <= 0` 时 `compute_delta()` 必须
    `return None`（恒等），**不得把空集传给 `transfer_linear`**（虽然后者会对
    `p(A) <= 0` 返回 `None`，但「A 为空」这一语义判断留在调用方，才能区分『机制未触发』
    与『触发了但目标集为空』）」，并明写「断言须覆盖 §3.1.2 表里的**每个**机制」。

    **S8 的读法（与 §3.9.5 的边界表一致）**：`p(A) <= 0` 一支**只对
    `shape='current'` 的机制**成立（`u_A` 无定义 → 不转移）；取 `declared` 的三个
    机制（`hard(target='featured')` / `non_featured` / `selected`）按 `w` 分配，
    `p(A) = 0` 时仍能转移，只有 `w(A) = 0` 才返 `None`（该形态由
    `test_declared_shape_transfers_when_pA_is_zero` 与
    `test_declared_shape_returns_none_when_wA_is_zero` 单独钉住）。本用例只覆盖
    「A 为空」这一支。
    """
    dist = dict(ctx.current)
    assert mod.compute_delta(view, dist, ctx) is None, (
        f'{label}：目标集为空时须返回 None（恒等），不得把空集传给 transfer_linear')
