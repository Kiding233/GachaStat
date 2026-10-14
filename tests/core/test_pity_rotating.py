"""P56 阶段十三-a：rotating 族（大小保底 / 捕获明光 / 两个 `_soft` 变体）单元测试。

**P64 S7d 改造（旧类直构 → 新架构）**：原文件以 rotating 族四个旧行为类直构；
改造后一律经 `create_behavior(PityDef(...), state)` 取统一骨架 `Pity`。旧类内部
结构在新架构下的对应物：

| 旧形态 | 新承载点 |
|--------|----------|
| `guaranteed` 标记 | `Pity._trackers` 里的 `FlagTracker`（`_flag_ctl`） |
| `cr_counter` | `Pity._trackers` 里的 `StreakTracker`（`_cr_counter`） |
| `counter`（`_soft` 变体） | `Pity._trackers` 里的 `CounterTracker`（`_counter`） |
| `_active` | `Pity._lifecycle`（`is_active` / `_ns_active`） |

覆盖目标：
  1. 纯净 rotating 大小保底翻转正确性：歪后 guaranteed=True、中 featured 后 guaranteed=False
  2. 小保底 featured 占比由基础分布决定（非硬编码 50%）
  3. CR 连歪计数器递增/重置/逻辑边界
  4. _soft 后缀 counter 递增 + SSR 重置
  5. readonly=True 时不修改状态
"""

import pytest
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pity import (
    PityState, DrawInfo, PityContext,
    _redistribute_scope, create_behavior,
)
# `transfer_linear` 的**家**是叶子层 `pity_primitives`（§3.9.4 的「模块归属」段：
# 它与 `Pity` 骨架之间无依赖，且实现层的 Modifier 也要用它），编排层 `pity.py` 只是
# re-export。本文件从**定义处**导入，使「归属是否漂移」在本行即显形。
from gacha_simulator.core.pity_primitives import transfer_linear
# P64 S9-2：`PityContext.sim` 非 Optional（3.10.2）------------------------------
# 直构 ctx 与 `PityEngine` 三个调度入口（before_draw / after_draw /
# get_probabilities）的 `sim` 都是**必填**（缺参在构造 ctx 时即 TypeError）。本文件
# 只验与「玩家持有」无关的机制，故用**空 state 的视图**作最小替身。
from gacha_simulator.core.state import GachaState as _GachaState, SimView as _SimView

_SIM = _SimView(_GachaState())



# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    return PityState()


@pytest.fixture
def base_ctx(state):
    """构造一个标准 SSR 小保底 PityContext（**卡级分布**，S8 起管道键空间）。

    基础分布：四张卡各 0.25（featured 两张 f1/f2 合计 50%，standard 两张 s1/s2
    合计 50%），Σ = 1。旧稿写槽位名（`ssr_featured` / `ssr_standard`）且 Σ = 0.01，
    卡级管道下 `transfer_linear` 取 `dist[c]`（c 为卡 id）会直接 `KeyError`；
    Σ = 1 也使 `_apply_delta` 的归一化退化为恒等（与生产路径同形）。
    `rarity_rank` 方向为「rank 小 = 稀有度更高」（旧稿写 `{'ssr': 3, ...}` 会让
    `_lower_rarities` 恒返空集、软保底静默恒等）。

    **S8-7 起本夹具不再构造槽位三字段**：它们只服务保留到发布前的旧保底类与等价性
    装置（ISSUE-901），本夹具喂的是卡级管道。同文件里仍构造槽位的是 `slot_ctx`
    （只服务 `TestRedistributeScope`，见其 docstring）与 `TestTransferLinear` 的
    单卡夹具（喂 `_redistribute_scope`）。
    """
    draw = DrawInfo(
        pool_id='test_pool',
        pool_instance_id='test_pool_0',
        reward_id='',
        reward_rarity='',
        is_featured=False,
        scope_cards={'ssr': ('f1', 'f2', 's1', 's2')},
        featured_cards={'ssr': ('f1', 'f2')},
        base_probabilities={'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25},
        rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )
    return PityContext(
        draw=draw,
        current={'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25},
        state=state,
    sim=_SIM,)


@pytest.fixture
def slot_ctx(state):
    """**槽位级**上下文的独立夹具：只服务 `TestRedistributeScope`。

    `_redistribute_scope` 是 M1 的槽位级函数，按 ISSUE-502 **保留至「发布前一次性
    移除旧保底类」的 commit**（其 4 处调用点全在旧类体内），故它的单测继续在槽位
    键空间上跑；与上面那个卡级夹具分开，避免「测旧函数」与「测新管道」共用一份
    夹具而互相带偏。
    """
    draw = DrawInfo(
        pool_id='test_pool',
        pool_instance_id='test_pool_0',
        reward_id='',
        reward_rarity='',
        is_featured=False,
        scope_cards={'ssr': ('f1', 'f2', 's1', 's2')},
        featured_cards={'ssr': ('f1', 'f2')},
        scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
        featured_slots={'ssr': ('ssr_featured',)},
        card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured',
                       's1': 'ssr_standard', 's2': 'ssr_standard'},
        base_probabilities={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )
    return PityContext(
        draw=draw,
        current={'ssr_featured': 0.005, 'ssr_standard': 0.005},
        state=state,
    sim=_SIM,)


def _make(state, btype, name, **pdef_kwargs):
    """经 `create_behavior` 构造骨架并补一次重绑。

    骨架**不在构造期绑定**零件 Counter/Flag（§3.1.4；绑定只发生在
    `Pity._rebind_state`），引擎的三条派发入口首行都会做这件事，本文件直驱骨架
    故须显式补一次。
    """
    pity = create_behavior(
        PityDef(name=name, btype=btype, scope='ssr', **pdef_kwargs), state)
    pity._rebind_state(state)
    return pity


# ══════════════════════════════════════════════════════════════════
# rotating：纯净轮换保底
# ══════════════════════════════════════════════════════════════════

class TestRotatingPity:
    """纯净大小保底：零参数事件驱动。"""

    def test_small_pity_uses_base_distribution(self, state, base_ctx):
        """小保底：featured 占比由基础分布决定，不修改概率。"""
        pity = _make(state, 'rotating', 'test_rot')
        result = pity.before_draw(base_ctx)
        # 小保底：分布原样返回（featured 卡合计 50%）
        assert result == {'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25}

    def test_guaranteed_pity_gives_100_percent_featured(self, state, base_ctx):
        """大保底：featured 100%。"""
        pity = _make(state, 'rotating', 'test_rot')
        # 先模拟歪一次 → guaranteed=True
        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        miss_ctx = PityContext(draw=draw_miss, current={'f1': 0.005, 's1': 0.005}, state=state, sim=_SIM)
        pity.after_draw(miss_ctx)
        assert state.get('test_rot', 'guaranteed', False) is True

        # 大保底：featured 卡集收下全部（卡级）
        result = pity.before_draw(base_ctx)
        assert sum(result[c] for c in ('f1', 'f2')) == pytest.approx(1.0)
        assert result['s1'] == pytest.approx(0.0) and result['s2'] == pytest.approx(0.0)

    def test_hit_featured_clears_guaranteed(self, state, base_ctx):
        """中 featured 后 guaranteed=False，回到小保底。"""
        pity = _make(state, 'rotating', 'test_rot')
        # 先歪一次
        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        miss_ctx = PityContext(draw=draw_miss, current={}, state=state, sim=_SIM)
        pity.after_draw(miss_ctx)
        assert state.get('test_rot', 'guaranteed', False) is True

        # 再中 featured
        draw_hit = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        hit_ctx = PityContext(draw=draw_hit, current={}, state=state, sim=_SIM)
        pity.after_draw(hit_ctx)
        assert state.get('test_rot', 'guaranteed', False) is False

    def test_non_ssr_does_not_trigger(self, state):
        """非 scope 稀有度不触发状态转移。"""
        pity = _make(state, 'rotating', 'test_rot')
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='r1', reward_rarity='sr', is_featured=False,
            scope_cards={}, featured_cards={},
            base_probabilities={}, rarity_rank={'ssr': 0, 'sr': 1},
        )
        ctx = PityContext(draw=draw, current={}, state=state, sim=_SIM)
        pity.after_draw(ctx)
        # guaranteed 未被设置（保持默认 False）
        assert state.get('test_rot', 'guaranteed', False) is False

    def test_did_fire_true_on_hit_false_on_miss(self, state):
        """`did_fire`：出 scope ∧ 命中（featured）为真，未命中为假。

        M4 统一语义（「本次抽卡是否让本保底回到初始状态」）由 `Pity.did_fire`
        （= `any(tr.did_reset(...))`）承载；旧类那个只看 `is_featured` 的命中判据
        已内联进 `FlagTracker`，并**叠加了 scope 门控**：两条 draw 都出 scope，
        故此处两者同答（scope 门控的判别力由
        `tests/core/test_pity_integration.py::TestDidFireUnified` 单独钉住）。
        """
        pity = _make(state, 'rotating', 'test_rot')
        draw_hit = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.01}, rarity_rank={'ssr': 0},
        )
        ctx_hit = PityContext(draw=draw_hit, current={}, state=state, sim=_SIM)
        assert pity.did_fire(ctx_hit) is True

        draw_miss = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('s1',)}, featured_cards={'ssr': ()},
            base_probabilities={'s1': 0.01}, rarity_rank={'ssr': 0},
        )
        ctx_miss = PityContext(draw=draw_miss, current={}, state=state, sim=_SIM)
        assert pity.did_fire(ctx_miss) is False


# ══════════════════════════════════════════════════════════════════
# rotating_cr：捕获明光
# ══════════════════════════════════════════════════════════════════

class TestRotatingCRPity:
    """轮换 + 捕获明光：CR 状态机。"""

    def test_cr_counter_increments_on_loss(self, state, base_ctx):
        """小保底歪了 → cr_counter++。"""
        pity = _make(state, 'rotating_cr', 'test_cr', cr_counter_threshold=3)
        draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        ctx = PityContext(draw=draw, current={}, state=state, sim=_SIM)
        pity.after_draw(ctx)
        assert state.get('test_cr', 'cr_counter', 0) == 1

    def test_cr_counter_resets_on_win(self, state):
        """小保底赢了 → cr_counter 归零。（需先经过 guaranteed→hit 回到小保底状态）"""
        pity = _make(state, 'rotating_cr', 'test_cr', cr_counter_threshold=3)

        # 第1抽：小保底歪 → cr_counter=1, guaranteed=True
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        pity.after_draw(PityContext(draw=miss_draw, current={}, state=state, sim=_SIM))
        assert state.get('test_cr', 'cr_counter', 0) == 1
        assert state.get('test_cr', 'guaranteed', False) is True

        # 第2抽：大保底命中 → guaranteed 清除，cr_counter 不变（CR 不介入大保底）
        hit_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        pity.after_draw(PityContext(draw=hit_draw, current={}, state=state, sim=_SIM))
        assert state.get('test_cr', 'guaranteed', False) is False  # 大保底清除
        assert state.get('test_cr', 'cr_counter', 0) == 1  # CR 不介入大保底

        # 第3抽：小保底赢 → cr_counter 归零
        pity.after_draw(PityContext(draw=hit_draw, current={}, state=state, sim=_SIM))
        assert state.get('test_cr', 'cr_counter', 0) == 0

    def test_cr_100_percent_intercept_at_threshold(self, state, base_ctx):
        """cr_counter >= threshold → 100% 拦截：featured_ratio=1.0。"""
        pity = _make(state, 'rotating_cr', 'test_cr', cr_counter_threshold=2)
        # 设 cr_counter = 2（达到阈值）
        state.set('test_cr', 'cr_counter', 2)
        # 设 guaranteed = False（小保底状态）
        state.set('test_cr', 'guaranteed', False)

        result = pity.before_draw(base_ctx)
        # 100% featured（卡级：featured 卡集收下全部）
        assert sum(result[c] for c in ('f1', 'f2')) == pytest.approx(1.0)
        assert result['s1'] == pytest.approx(0.0) and result['s2'] == pytest.approx(0.0)

    def test_cr_not_intercept_when_guaranteed(self, state, base_ctx):
        """大保底时 CR 不介入，由 `guaranteed` 分支接管。"""
        pity = _make(state, 'rotating_cr', 'test_cr', cr_counter_threshold=3)
        # 设 guaranteed = True（大保底状态）
        state.set('test_cr', 'guaranteed', True)

        result = pity.before_draw(base_ctx)
        # 大保底：100% featured（由 RotatingModifier 的 `guaranteed` 分支处理）
        assert sum(result[c] for c in ('f1', 'f2')) == pytest.approx(1.0)

    def test_readonly_mode_no_random_change(self, state, base_ctx):
        """readonly=True 时不执行随机判定，确定性返回。"""
        pity = _make(state, 'rotating_cr', 'test_cr', cr_counter_threshold=3)
        state.set('test_cr', 'guaranteed', False)
        state.set('test_cr', 'cr_counter', 0)
        result = pity.before_draw(base_ctx, readonly=True)
        # 小保底：分布原样返回
        assert result == {'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25}

    def test_cr_base_rate_deterministic(self, state, base_ctx):
        """cr_base_rate=1.0 forces 100% intercept; cr_base_rate=0 never intercepts."""
        pity_full = _make(state, 'rotating_cr', 'test_cr_full',
                          cr_counter_threshold=3, cr_base_rate=1.0)
        state.set('test_cr_full', 'guaranteed', False)
        state.set('test_cr_full', 'cr_counter', 0)
        result = pity_full.before_draw(base_ctx)
        assert sum(result[c] for c in ('f1', 'f2')) == pytest.approx(1.0)

        pity_none = _make(state, 'rotating_cr', 'test_cr_none',
                          cr_counter_threshold=3, cr_base_rate=0.0)
        state.set('test_cr_none', 'guaranteed', False)
        state.set('test_cr_none', 'cr_counter', 0)
        result2 = pity_none.before_draw(base_ctx)
        assert result2 == {'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25}

    def test_cr_state_probs_boundary(self, state, base_ctx):
        """cr_state_probs[idx]=1.0 triggers intercept at that state."""
        pity = _make(state, 'rotating_cr', 'test_cr_sp',
                     cr_counter_threshold=2, cr_state_probs=[1.0, 0.0, 0.0])
        state.set('test_cr_sp', 'guaranteed', False)
        state.set('test_cr_sp', 'cr_counter', 0)
        result = pity.before_draw(base_ctx)
        assert sum(result[c] for c in ('f1', 'f2')) == pytest.approx(1.0)

        pity2 = _make(state, 'rotating_cr', 'test_cr_sp2',
                      cr_counter_threshold=2, cr_state_probs=[0.0, 1.0, 0.0])
        state.set('test_cr_sp2', 'guaranteed', False)
        state.set('test_cr_sp2', 'cr_counter', 1)
        result2 = pity2.before_draw(base_ctx)
        assert sum(result2[c] for c in ('f1', 'f2')) == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════
# rotating_soft：轮换 + 软保底
# ══════════════════════════════════════════════════════════════════

class TestRotatingSoftPity:
    """`_soft` 变体提供 counter 管理 + deltas 引擎委托。"""

    def test_counter_increments_on_before_draw(self, state, base_ctx):
        """before_draw 递增 counter。"""
        pity = _make(state, 'rotating_soft', 'test_rs', soft_start=74, soft_end=90)
        pity.before_draw(base_ctx)
        assert state.get('test_rs', 'counter', 0) == 1

    def test_ssr_resets_counter(self, state, base_ctx):
        """SSR 出货 → counter 重置。"""
        pity = _make(state, 'rotating_soft', 'test_rs', soft_start=74, soft_end=90)
        # 递增几次 counter
        for _ in range(10):
            pity.before_draw(base_ctx)
        assert state.get('test_rs', 'counter', 0) == 10

        # SSR 出货
        hit_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='f1', reward_rarity='ssr', is_featured=True,
            scope_cards={'ssr': ('f1',)}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.01}, rarity_rank={'ssr': 0},
        )
        hit_ctx = PityContext(draw=hit_draw, current={}, state=state, sim=_SIM)
        pity.after_draw(hit_ctx)
        assert state.get('test_rs', 'counter', 0) == 0

    def test_readonly_no_counter_increment(self, state, base_ctx):
        """readonly=True 不递增 counter。"""
        pity = _make(state, 'rotating_soft', 'test_rs', soft_start=74, soft_end=90)
        pity.before_draw(base_ctx, readonly=True)
        assert state.get('test_rs', 'counter', 0) == 0

    def test_guaranteed_flag_works_with_soft(self, state, base_ctx):
        """软保底不破坏 rotating 的大小保底翻转。"""
        pity = _make(state, 'rotating_soft', 'test_rs', soft_start=74, soft_end=90)
        # 歪一次
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        pity.after_draw(PityContext(draw=miss_draw, current={}, state=state, sim=_SIM))
        assert state.get('test_rs', 'guaranteed', False) is True


# ══════════════════════════════════════════════════════════════════
# rotating_cr_soft：CR + 软保底
# ══════════════════════════════════════════════════════════════════

class TestRotatingCRSoftPity:
    """CR + 软保底组合：两个计数独立运作。"""

    def test_combined_cr_and_soft_counter(self, state, base_ctx):
        """CR counter 和 soft counter 独立运作。"""
        pity = _make(state, 'rotating_cr_soft', 'test_crs',
                     cr_counter_threshold=3, soft_start=74, soft_end=90)
        # 递增 soft counter
        pity.before_draw(base_ctx)
        assert state.get('test_crs', 'counter', 0) == 1

        # 歪一次 → cr_counter++
        miss_draw = DrawInfo(
            pool_id='test_pool', pool_instance_id='test_pool_0',
            reward_id='s1', reward_rarity='ssr', is_featured=False,
            scope_cards={'ssr': ('f1', 's1')}, featured_cards={'ssr': ('f1',)},
            base_probabilities={'f1': 0.005, 's1': 0.005},
            rarity_rank={'ssr': 0},
        )
        pity.after_draw(PityContext(draw=miss_draw, current={}, state=state, sim=_SIM))
        assert state.get('test_crs', 'cr_counter', 0) == 1
        # SSR 出货后 soft counter 重置
        assert state.get('test_crs', 'counter', 0) == 0


# ══════════════════════════════════════════════════════════════════
# _redistribute_scope：概率重分配工具函数
# ══════════════════════════════════════════════════════════════════

class TestRedistributeScope:
    """模块级概率重分配函数。"""

    def test_full_featured_ratio(self, slot_ctx):
        """featured_ratio=1.0 → 全部概率归入 featured 槽。"""
        result = _redistribute_scope(
            slot_ctx, featured_ratio=1.0, total=0.01,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        assert result['ssr_featured'] == pytest.approx(0.01)
        assert result['ssr_standard'] == pytest.approx(0.0)

    def test_half_featured_ratio_preserves_proportions(self, slot_ctx):
        """featured_ratio=0.5 → featured/standard 各占 50%，内部按权重比例分配。"""
        result = _redistribute_scope(
            slot_ctx, featured_ratio=0.5, total=0.01,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        assert result['ssr_featured'] == pytest.approx(0.005)
        assert result['ssr_standard'] == pytest.approx(0.005)

    def test_zero_total_ratio_math(self, slot_ctx):
        """total=0 时重分配算出全零，由调用方负责前置守卫（rotating Modifier 已有）。"""
        result = _redistribute_scope(
            slot_ctx, featured_ratio=0.5, total=0.0,
            featured_slots=('ssr_featured',), scope='ssr',
        )
        # total=0 → 所有槽位概率归零；调用方应在调用前检查 total<=0
        assert result['ssr_featured'] == pytest.approx(0.0)
        assert result['ssr_standard'] == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════
# S8-3：卡级助手 `transfer_linear`（§3.9.4）
# ══════════════════════════════════════════════════════════════════
#
# 本组是 S8-3 的块级验收面（§七 S8-3 的验收命令 `-k transfer_linear`）。它与上面的
# `TestRedistributeScope` 是**两个键空间的两代实现**，并存到「发布前一次性移除旧
# 保底类」的 commit（ISSUE-502）：`_redistribute_scope` 是槽位级、返回新分布；
# `transfer_linear` 是卡级、返回**增量向量**（§3.9.4）。

class TestTransferLinear:
    """`transfer_linear(dist, A, Q, amount, shape, weights)` 的双分支与全部守卫。

    **本类的单卡夹具（`test_transfer_linear_matches_scope_equivalent`）保留槽位三
    字段**：它把 `_redistribute_scope`（槽位级、保留至发布前，ISSUE-502）与新助手
    放在同一输入上对照，槽位映射正是旧函数的输入，故不在 S8-7 的槽位剥离面内。
    """

    def test_transfer_linear_matches_scope_equivalent(self):
        """单卡 A / 单卡 Q 且取值是二进制精确数时，与 `_redistribute_scope` 逐元素相等。

        「单槽位 / 组内等权」是两者**唯一**可以逐元素对照的场景：A 与 Q 各只含一张卡
        时，槽位级与卡级是 1:1 的同构（`card_to_slot` 是双射），两条算术路径也重合
        （`_redistribute_scope` 的 `total · w / w` 与 `transfer_linear` 的
        `p(A) + p(Q)` 在本组取值下都落回精确值 1.0 / 0.0）。
        **跨槽位或不等权场景不得照抄本断言**：两者的差别正在「A 内按当前比例还是按
        声明权重分配」（§3.9.4 的三点差别），那时只有增量向量可比（见下一条）。
        """
        dist = {'a': 0.25, 'q': 0.75}
        ctx = PityContext(
            draw=DrawInfo(
                pool_id='p', pool_instance_id='p_0', reward_id='',
                reward_rarity='', is_featured=False,
                scope_cards={'ssr': ('a', 'q')}, featured_cards={'ssr': ('a',)},
                scope_slots={'ssr': ('slot_a', 'slot_q')},
                featured_slots={'ssr': ('slot_a',)},
                card_to_slot={'a': 'slot_a', 'q': 'slot_q'},
                base_probabilities={'a': 0.25, 'q': 0.75},
                rarity_rank={'ssr': 0},
            ),
            current=dict(dist), state=PityState(),
        sim=_SIM,)
        old = _redistribute_scope(ctx, featured_ratio=1.0, total=0.25 + 0.75,
                                  featured_slots=('slot_a',), scope='ssr')
        delta = transfer_linear(dist, ('a',), ('q',), dist['q'])
        assert delta is not None
        new = {c: dist[c] + delta.get(c, 0.0) for c in dist}
        # 卡级 → 槽位级（本夹具的映射是双射，逐元素对照成立）
        assert new['a'] == old['slot_a']
        assert new['q'] == old['slot_q']
        assert new['a'] == 1.0 and new['q'] == 0.0

    def test_transfer_linear_ratio_preserving(self):
        """A 内两卡不等权：`current` 保当前比例、`declared` 按声明权重；Q 侧恒按当前比例。

        | 断言 | 判据 |
        |------|------|
        | `current` 的 δ_A 之比 == 当前 p 之比 | A 内「保持组内当前比例」 |
        | `declared` 的 δ_A 之比 == 声明权重之比 | A 内改按 `weights` 分配 |
        | 两者的 δ_Q 之比 == 当前 p 之比 | Q 侧形状不可指定，恒为当前形状 |
        | `Σδ == 0` | 转移族配平（§3.1.5.2.1），框架归一化退化为恒等 |

        **判别性**：把 `declared` 写成 `current`（或反之）会让第 1 / 2 条断言之一转红
        ：本夹具的当前比例（1:7）与声明权重（3:1）刻意不同。
        """
        dist = {'a1': 0.01, 'a2': 0.07, 'q1': 0.02, 'q2': 0.90}
        weights = {'a1': 0.75, 'a2': 0.25, 'q1': 0.5, 'q2': 0.5}
        amount = dist['q1'] + dist['q2']

        cur = transfer_linear(dist, ('a1', 'a2'), ('q1', 'q2'), amount)
        dec = transfer_linear(dist, ('a1', 'a2'), ('q1', 'q2'), amount,
                              shape='declared', weights=weights)

        assert abs(sum(cur.values())) < 1e-15, 'Σδ = 0（转移族配平）'
        assert abs(sum(dec.values())) < 1e-15
        # A 侧：current 保当前比例（1:7），declared 按声明权重（3:1）
        assert cur['a1'] / cur['a2'] == pytest.approx(dist['a1'] / dist['a2'])
        assert dec['a1'] / dec['a2'] == pytest.approx(weights['a1'] / weights['a2'])
        assert cur['a1'] / cur['a2'] != pytest.approx(weights['a1'] / weights['a2'])
        # Q 侧：两者都按当前比例（1:45），形状不可指定
        for d in (cur, dec):
            assert d['q1'] / d['q2'] == pytest.approx(dist['q1'] / dist['q2'])
        # 转移量：A 侧合计 == amount、Q 侧合计 == −amount
        for d in (cur, dec):
            assert d['a1'] + d['a2'] == pytest.approx(amount)
            assert d['q1'] + d['q2'] == pytest.approx(-amount)

    def test_transfer_linear_declared_survives_zero_pA(self):
        """`shape='declared'` 在 `p(A) = 0` 时仍可转移；`w(A) = 0` 时返回 `None`。

        这正是 §3.1.5.6.1「来源二」在冲突配置下生效的路径（`declared` 唯一的用武之地，
        §3.1.2 的「A 侧形状」段）：`p(A) = 0` 而 `w(A) > 0` → 转移照常；`w(A) = 0`
        （池子声明该组不可获得，来源一）→ 不转移。
        """
        dist = {'a': 0.0, 'q': 1.0}
        weights = {'a': 0.5, 'q': 0.5}
        d = transfer_linear(dist, ('a',), ('q',), dist['q'],
                            shape='declared', weights=weights)
        assert d is not None and d['a'] == pytest.approx(1.0) and d['q'] == pytest.approx(-1.0)
        assert transfer_linear(dist, ('a',), ('q',), dist['q'],
                               shape='declared', weights={'a': 0.0, 'q': 1.0}) is None
        # `current` 形状下 `p(A) = 0` 未定义（u_A 无定义）→ 不转移
        assert transfer_linear(dist, ('a',), ('q',), dist['q']) is None

    def test_transfer_linear_guards(self):
        """其余守卫：`p(Q) <= 0` / `amount <= 0` 返 `None`；未知 shape / 缺 weights 抛 `ValueError`。"""
        dist = {'a': 0.3, 'q': 0.7}
        assert transfer_linear(dist, ('a',), ('q',), 0.0) is None, 'amount <= 0'
        assert transfer_linear(dist, ('a',), ('q',), -0.1) is None
        assert transfer_linear(dist, ('a',), (), 0.5) is None, 'p(Q) = 0（无货可取）'
        with pytest.raises(ValueError):
            transfer_linear(dist, ('a',), ('q',), 0.5, shape='nope')
        with pytest.raises(ValueError):
            transfer_linear(dist, ('a',), ('q',), 0.5, shape='declared')
