"""P56 阶段十三-a：targeted 族（定轨 / 定轨 + 软保底）单元测试。

**P64 S7d 改造（旧类直构 → 新架构）**：原文件以 targeted 族两个旧行为类直构；
改造后一律经 `create_behavior(PityDef(...), state)` 取统一骨架 `Pity`。旧类内部
结构在新架构下的对应物：

| 旧形态 | 新承载点 |
|--------|----------|
| `fate_points` / `losses` | `Pity._trackers` 里的 `FateTracker`（`_ctls[...]`） |
| `guaranteed` / `lost_rotating` | 同上（`FateTracker` 的 flag 类键） |
| `counter`（`_soft` 变体） | `Pity._trackers` 里的 `CounterTracker`（`_counter`） |
| `_is_hit()` | `FateTracker` 的 `judge='selected'` 判据（内联），对外可观测面是 `Pity.did_fire` |
| `_active` | `Pity._lifecycle`（`is_active` / `_ns_active`） |

覆盖目标：
  1. 定轨命中 selected_card 后重置所有状态
  2. 歪非目标卡时 fate_points 递增 + guaranteed 翻转
  3. switch_resets_progress 的切换行为差异（策略层读 `PityDef`，本族不消费）
  4. cancel_epitomized_path 后 selected_card=None 且不累积
  5. fate_threshold=0 始终保证
  6. selected_card=None（不定轨）时不累积
"""

import pytest
from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pity import (
    PityState, DrawInfo, PityContext, create_behavior,
)


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def state():
    return PityState()


def _make_draw(reward_id, rarity='ssr', is_featured=False, selected=None):
    """构造 DrawInfo 快捷方法。

    **S8 起基础分布是卡级**（§3.9.1）：`base_probabilities` 与 `current` 的键即卡 id
    （旧稿写槽位名 `ssr_featured` / `ssr_standard`，卡级管道下 `transfer_linear` 取
    `dist[c]` 会直接 `KeyError`）。槽位三字段保留（ISSUE-901：旧保底类仍读它们），
    但**不是**本管道键空间。
    `rarity_rank` 方向为「rank 小 = 稀有度更高」（对齐 `config_store._parse_rarities`；
    旧稿写成 `{'ssr': 3, ...}` 会让 `_lower_rarities` 恒返空集、软保底静默恒等）。
    """
    featured_cards = {'ssr': ('f1', 'f2')}
    all_cards = ('f1', 'f2', 's1', 's2')
    return DrawInfo(
        pool_id='test_pool', pool_instance_id='test_pool_0',
        reward_id=reward_id, reward_rarity=rarity, is_featured=is_featured,
        scope_cards={'ssr': all_cards},
        featured_cards=featured_cards,
        scope_slots={'ssr': ('ssr_featured', 'ssr_standard')},
        featured_slots={'ssr': ('ssr_featured',)},
        card_to_slot={'f1': 'ssr_featured', 'f2': 'ssr_featured',
                       's1': 'ssr_standard', 's2': 'ssr_standard'},
        base_probabilities={'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25},
        rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
    )


def _make_ctx(state, reward_id, rarity='ssr', is_featured=False):
    """构造 PityContext 快捷方法。"""
    draw = _make_draw(reward_id, rarity, is_featured)
    return PityContext(
        draw=draw,
        current={'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25},
        state=state,
    )


def _make(state, btype, name, **pdef_kwargs):
    """经 `create_behavior` 构造骨架并补一次重绑（骨架不在构造期绑定零件）。"""
    pity = create_behavior(
        PityDef(name=name, btype=btype, scope='ssr', **pdef_kwargs), state)
    pity._rebind_state(state)
    return pity


# ══════════════════════════════════════════════════════════════════
# targeted：定向保底（定轨）
# ══════════════════════════════════════════════════════════════════

class TestTargetedPity:
    """定轨：selected_card 锁定目标 + fate_points 累积。"""

    def test_hit_selected_card_resets_all(self, state):
        """命中 selected_card → fate_points 清零 + guaranteed 清除 + losses 重置。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        # 先歪一次
        pity.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 1
        assert state.get('test_tgt', 'guaranteed', False) is True

        # 命中目标
        pity.after_draw(_make_ctx(state, 'f1', is_featured=True))
        assert state.get('test_tgt', 'fate_points', 0) == 0
        assert state.get('test_tgt', 'guaranteed', False) is False
        assert state.get('test_tgt', 'losses', 0) == 0

    def test_miss_accumulates_fate_points(self, state):
        """歪非目标 SSR → fate_points++ + guaranteed 翻转 + losses++。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        pity.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 1
        assert state.get('test_tgt', 'guaranteed', False) is True
        assert state.get('test_tgt', 'lost_rotating', False) is True
        assert state.get('test_tgt', 'losses', 0) == 1

    def test_no_selected_card_does_not_accumulate(self, state):
        """selected_card=None → 不累积、不翻转状态。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        # selected_card 默认为 None（不定轨状态）
        assert state.get('test_tgt', 'selected_card') is None

        pity.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_tgt', 'fate_points', 0) == 0
        assert state.get('test_tgt', 'guaranteed', False) is False

    def test_fate_threshold_zero_always_guaranteed(self, state):
        """fate_threshold=0 → 定轨后始终处于保证状态，**全部概率归入定轨卡**。

        **S8 起断言面是单卡**（§六 的「S8 单卡定向」条）：卡级管道下
        `SelectedModifier` 的 A = `(selected,)`，故定轨卡拿到整个 scope 的量，
        **另一张 featured 卡（f2）也归零**：这是 S8 相对旧实现（同槽位平摊 50/50）
        的语义提升，原断言只看槽位、看不见这一层。
        """
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=0)
        state.set('test_tgt', 'selected_card', 'f1')

        ctx = _make_ctx(state, '', rarity='')  # before_draw 不计 reward_id
        result = pity.before_draw(ctx)
        assert result['f1'] == pytest.approx(1.0), '定轨卡收下整个 scope'
        assert result['f2'] == pytest.approx(0.0), '同 scope 的另一张 featured 不在 A 内'
        assert result['s1'] == pytest.approx(0.0)
        assert result['s2'] == pytest.approx(0.0)

    def test_small_pity_uses_base_distribution(self, state):
        """小保底：不修改概率（原样返回基础分布）。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        ctx = _make_ctx(state, '', rarity='')
        result = pity.before_draw(ctx)
        assert result == {'f1': 0.25, 'f2': 0.25, 's1': 0.25, 's2': 0.25}

    def test_guaranteed_targets_selected_card_slot(self, state):
        """大保底状态：全部概率收窄到 `selected_card`（单卡定向）。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')
        state.set('test_tgt', 'guaranteed', True)

        ctx = _make_ctx(state, '', rarity='')
        result = pity.before_draw(ctx)
        assert result['f1'] == pytest.approx(1.0)
        assert result['f2'] == pytest.approx(0.0)
        assert result['s1'] == pytest.approx(0.0)
        assert result['s2'] == pytest.approx(0.0)

    def test_hit_judge_follows_selected_card(self, state):
        """命中判据 = `reward_id == selected_card`。

        旧类的 `_is_hit()` 在新架构下**没有同名对应物**：判据已内联进
        `FateTracker` 的 `judge='selected'`（`_judge_hit`），对外可观测面是
        `Pity.did_fire`（= 出 scope ∧ 命中定轨）。三条 draw 都出 scope，故
        `did_fire` 与本判据同答。
        """
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        # 命中目标
        assert pity.did_fire(_make_ctx(state, 'f1', is_featured=True)) is True
        # 命中其他 featured
        assert pity.did_fire(_make_ctx(state, 'f2', is_featured=True)) is False
        # 歪了
        assert pity.did_fire(_make_ctx(state, 's1', is_featured=False)) is False

    def test_did_fire_true_on_selected_hit(self, state):
        """did_fire() 只在命中定轨卡时为真。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')
        assert pity.did_fire(_make_ctx(state, 'f1', is_featured=True)) is True
        assert pity.did_fire(_make_ctx(state, 's1', is_featured=False)) is False

    def test_non_ssr_does_not_trigger(self, state):
        """非 scope 稀有度不触发状态转移。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')
        ctx = _make_ctx(state, 'r1', rarity='r', is_featured=False)
        pity.after_draw(ctx)
        assert state.get('test_tgt', 'fate_points', 0) == 0

    def test_miss_featured_but_not_selected_accumulates(self, state):
        """歪了 featured 但不是 selected_card → 仍然累积命定值。"""
        pity = _make(state, 'targeted', 'test_tgt', fate_threshold=1)
        state.set('test_tgt', 'selected_card', 'f1')

        # 出了 f2（featured 但不是 selected_card）
        pity.after_draw(_make_ctx(state, 'f2', is_featured=True))
        # 仍然歪：命中判据检查 reward_id == selected_card
        assert state.get('test_tgt', 'fate_points', 0) == 1


# ══════════════════════════════════════════════════════════════════
# targeted_soft：定轨 + 软保底
# ══════════════════════════════════════════════════════════════════

class TestTargetedSoftPity:
    """`_soft` 变体提供 soft counter + deltas 引擎委托。"""

    def test_counter_increments_on_before_draw(self, state):
        """before_draw 递增 counter。"""
        pity = _make(state, 'targeted_soft', 'test_ts',
                     fate_threshold=1, soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')
        ctx = _make_ctx(state, '', rarity='')
        pity.before_draw(ctx)
        assert state.get('test_ts', 'counter', 0) == 1

    def test_ssr_resets_counter(self, state):
        """SSR 出货 → counter 重置。"""
        pity = _make(state, 'targeted_soft', 'test_ts',
                     fate_threshold=1, soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')

        # 递增几次 counter
        ctx = _make_ctx(state, '', rarity='')
        for _ in range(10):
            pity.before_draw(ctx)
        assert state.get('test_ts', 'counter', 0) == 10

        # SSR 出货
        pity.after_draw(_make_ctx(state, 'f1', is_featured=True))
        assert state.get('test_ts', 'counter', 0) == 0

    def test_readonly_no_counter_increment(self, state):
        """readonly=True 不递增 counter。"""
        pity = _make(state, 'targeted_soft', 'test_ts',
                     fate_threshold=1, soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')
        ctx = _make_ctx(state, '', rarity='')
        pity.before_draw(ctx, readonly=True)
        assert state.get('test_ts', 'counter', 0) == 0

    def test_fate_points_work_with_soft(self, state):
        """软保底不破坏定轨的命定值累积。"""
        pity = _make(state, 'targeted_soft', 'test_ts',
                     fate_threshold=1, soft_start=63, soft_end=80)
        state.set('test_ts', 'selected_card', 'f1')

        # 歪一次
        pity.after_draw(_make_ctx(state, 's1', is_featured=False))
        assert state.get('test_ts', 'fate_points', 0) == 1
        assert state.get('test_ts', 'guaranteed', False) is True
