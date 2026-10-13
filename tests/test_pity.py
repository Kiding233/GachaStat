"""保底引擎测试：软/硬保底概率行为 + PityState / PityEngine。

**P64 S7d 改造（旧类直构 → 新架构）**：本文件原以 counter 驱动两族的旧行为类直构
并调用其 `_compute_probabilities(ctx, counter)`。改造后一律经
`create_behavior(PityDef(...), state)` 取统一骨架 `Pity`，断言面随之改为
「骨架内部结构 + 公开调度入口」：

- **boost 爬升函数**由 `Pity._modifiers[0]`（软保底 Modifier）承载。旧
  `_compute_probabilities(ctx, counter)` 的「显式给计数」入口对应
  `Pity.before_draw(ctx, readonly=True)`（只读查询不推进 `advance` 相位，
  读到的正是预置的那个计数）；
- **阈值行为**由 `before_draw` 的产出分布承载（不再经旧类的槽位法内部路径）；
- **N1 相位**（计数在 `before_draw` 的 `advance` 段递增）由 `TestN1CounterPhase`
  两条顺序驱动用例钉住：`hard(threshold=90)` 首次 100% 落在第 90 抽、软保底满档
  同样落在第 90 抽。

**构造期纪律**：骨架 `Pity` **不在构造期绑定**零件 Counter/Flag（绑定只发生在
`Pity._rebind_state`，引擎三条派发入口首行都会做）。本文件直驱骨架处一律显式补
一次 `_rebind_state(state)`。
"""
import pytest

from gacha_simulator.core.config_store import PityDef
from gacha_simulator.core.pity import (
    DrawInfo, PityContext, PityEngine, PityState, PoolPitySpec, create_behavior,
)


# ═══════════════════════════════════════════════════════════════════
# 公共夹具：三稀有度 SSR 池的一次抽卡上下文
# ═══════════════════════════════════════════════════════════════════

#: 基础分布是**卡级**（S8 起管道为卡级，D20 / §3.9.1）：键即卡 id。旧稿写稀有度名
#: （`'ssr'` / `'sr'` / `'r'`）——本夹具的槽位名恰与稀有度名同形，故旧稿在 M1 的
#: 槽位级管道下可用；卡级管道下 A/Q 是卡集合、`transfer_linear` 取 `dist[c]`
#: （c 为卡 id）会直接 `KeyError`。
_SSR_PROBS = {'ssr_card': 0.006, 'sr_card': 0.051, 'r_card': 0.943}
_SSR_RANK = {'ssr': 0, 'sr': 1, 'r': 2}
_SSR_CARDS = {'ssr': ('ssr_card',), 'sr': ('sr_card',), 'r': ('r_card',)}
_SSR_SLOTS = {'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)}
_SSR_C2S = {'ssr_card': 'ssr', 'sr_card': 'sr', 'r_card': 'r'}


def _ssr_draw():
    """一次抽卡的静态事实：A 列（`scope_cards`）与分布键空间同键。

    S8 起 A 列是**卡集合**、`dist` 是**卡级**分布，两者同键空间（D20），
    故夹具的卡 id 必须与分布键一致；合成 spec 少一个键时保底会**静默恒等**
    （`d.get(c, 0.0)` 对未出现的键取 0），故夹具必须给全。槽位三字段保留
    （ISSUE-901：旧保底类仍读它们），但**不是**本管道键空间。
    """
    return DrawInfo(
        pool_id='t', pool_instance_id='t', reward_id='', reward_rarity='',
        is_featured=False,
        scope_cards=dict(_SSR_CARDS),
        featured_cards={},
        scope_slots=dict(_SSR_SLOTS),
        featured_slots=dict(_SSR_SLOTS),
        card_to_slot=dict(_SSR_C2S),
        base_probabilities=dict(_SSR_PROBS),
        rarity_rank=dict(_SSR_RANK),
    )


def _ssr_ctx(state):
    return PityContext(draw=_ssr_draw(), current=dict(_SSR_PROBS), state=state)


def _make_hard(state, threshold=90, name='test'):
    """构造 hard 骨架并补一次重绑（骨架不在构造期绑定零件）。"""
    pity = create_behavior(
        PityDef(name=name, btype='hard', scope='ssr', threshold=threshold,
                reset='ssr'), state)
    pity._rebind_state(state)
    return pity


def _make_soft(state, start=73, end=90, name='test'):
    """构造 soft_interval 骨架并补一次重绑。"""
    pity = create_behavior(
        PityDef(name=name, btype='soft_interval', scope='ssr',
                soft_start=start, soft_end=end, reset='ssr'), state)
    pity._rebind_state(state)
    return pity


# ═══════════════════════════════════════════════════════════════════
# Task 13(a1): 保底引擎核心：软/硬保底 + 3 种重置语义
# ═══════════════════════════════════════════════════════════════════

class TestSoftStepProgress:
    """软保底 boost 爬升：`SoftModifier._cumulative_boost` 与旧爬升曲线等价。

    §3.4.1 修正 ② 与 2026-10-06 端点裁决后 `soft_interval(73, 90)` 的
    deltas = ((72, 0.0), (18, 5.555556))：第 73 抽起加成、第 90 抽满。
    """

    @staticmethod
    def _boost(pity, counter):
        """取软保底 Modifier 的累计 boost%（旧 `_cumulative_boost` 的新承载点）。"""
        return pity._modifiers[0]._cumulative_boost(counter)

    def test_boost_zero_below_start(self):
        """counter < start → boost=0"""
        pity = _make_soft(PityState())
        assert self._boost(pity, 72) == 0.0
        assert self._boost(pity, 73) > 0.0

    def test_first_increment_lands_exactly_at_start(self):
        """§3.4.1 修正 ②：counter==start 恰为第一档增量，counter==start-1 为 0"""
        pity = _make_soft(PityState())
        assert self._boost(pity, 72) == 0.0
        assert self._boost(pity, 73) == pytest.approx(100.0 / 18)

    def test_boost_increases_after_start(self):
        """counter 进入增量段后 boost 递增"""
        pity = _make_soft(PityState())
        # deltas = ((72, 0.0), (18, 5.555556)) → counter=74: 2 档 = 11.1111%
        assert self._boost(pity, 74) == pytest.approx(2 * 100.0 / 18)
        assert self._boost(pity, 80) > self._boost(pity, 74)

    def test_boost_reaches_100_at_end(self):
        """counter=end 时 boost 恰为 100%（两端都含，100% 落在 end）"""
        pity = _make_soft(PityState())
        assert self._boost(pity, 90) == pytest.approx(100.0)
        assert self._boost(pity, 89) < 100.0

    def test_boost_clamped_at_100(self):
        """counter 超出范围后 boost 封顶 100%"""
        pity = _make_soft(PityState())
        assert self._boost(pity, 100) == pytest.approx(100.0)
        assert self._boost(pity, 200) == pytest.approx(100.0)

    def test_boost_lands_on_scope_probability_at_first_step(self):
        """boost 经只读查询落在**分布**上：第 73 抽 scope 恰增一个百分点档位。

        旧用例经 `_compute_probabilities(ctx, counter)` 只断言 boost 数值；本断言
        把它接到分布出口（`t = boost%/100` 的百分点绝对量口径，§3.4.1 修正 ①），
        使「boost 数值算对但没接到概率上」这一失效形态可见。
        """
        state = PityState()
        pity = _make_soft(state)
        state.set('test', 'counter', 73)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(0.006 + 100.0 / 18 / 100.0)
        assert out['sr_card'] < _SSR_PROBS['sr_card']
        assert out['r_card'] < _SSR_PROBS['r_card']
        assert sum(out.values()) == pytest.approx(1.0)

    def test_soft_preserves_total(self):
        """软保底各档位下概率和保持 1（`target_featured` 形态已按裁决 7B 移出配置面）。

        旧用例以 `target_featured=True` 收窄目标组后断言 Σ=1；该配置形态已由
        裁决 7B（2026-10-05）从 `soft_*` 的配置面移除（`create_behavior` 抛
        `ConfigError`，见 `tests/core/test_pity_validate_behaviors.py` 的 7B 用例），
        故本断言取**合法形态**（目标组 = scope 全集）覆盖同一不变式。
        """
        state = PityState()
        pity = _make_soft(state)
        for c in [0, 40, 80, 85, 90, 100]:
            state.set('test', 'counter', c)
            out = pity.before_draw(_ssr_ctx(state), readonly=True)
            assert sum(out.values()) == pytest.approx(1.0), f'counter={c}'


class TestHardPityThreshold:
    """硬保底阈值行为：`counter >= threshold` 时目标组 100%。"""

    def test_below_threshold_unchanged(self):
        state = PityState()
        pity = _make_hard(state)
        state.set('test', 'counter', 89)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out == pytest.approx(_SSR_PROBS)

    def test_at_threshold_ssr_100_pct(self):
        state = PityState()
        pity = _make_hard(state)
        state.set('test', 'counter', 90)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(1.0)
        assert out['sr_card'] == pytest.approx(0.0)

    def test_threshold_early_reached(self):
        state = PityState()
        pity = _make_hard(state, threshold=50)
        state.set('test', 'counter', 50)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(1.0)

    def test_hard_preserves_sum(self):
        state = PityState()
        pity = _make_hard(state)
        for c in [0, 50, 89, 90, 100]:
            state.set('test', 'counter', c)
            out = pity.before_draw(_ssr_ctx(state), readonly=True)
            assert sum(out.values()) == pytest.approx(1.0), f'counter={c}'


class TestN1CounterPhase:
    """N1 相位：计数型在 `before_draw` 的 `advance` 段递增。

    「第 N 抽读到的计数为 N」是 `hard(threshold=90)` 首次 100% 落在**第 90 抽**的
    唯一原因（旧 `CounterBasedBehavior.before_draw` 同为「先自增、再算概率」）。
    把 `advance` 整段删掉、或挪到 Modifier 链之后，两条用例必红。
    """

    def test_hard_first_100_percent_lands_on_threshold_draw(self):
        state = PityState()
        pity = _make_hard(state, threshold=90)
        first_full = None
        for n in range(1, 96):
            out = pity.before_draw(_ssr_ctx(state))
            if first_full is None and out['ssr_card'] == pytest.approx(1.0):
                first_full = n
        assert state.get('test', 'counter', 0) == 95, '每抽须推进一次计数'
        assert first_full == 90, f'首次 100% 应落在第 90 抽，实得 {first_full}'

    def test_soft_full_boost_lands_on_end_draw(self):
        state = PityState()
        pity = _make_soft(state, start=73, end=90)
        first_full = None
        for n in range(1, 96):
            out = pity.before_draw(_ssr_ctx(state))
            if first_full is None and out['ssr_card'] == pytest.approx(1.0):
                first_full = n
        assert state.get('test', 'counter', 0) == 95
        assert first_full == 90, f'软保底满档应落在第 90 抽，实得 {first_full}'


class TestPityState:
    """保底计数器状态"""

    def test_increment_new_counter(self):
        state = PityState()
        state.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 1

    def test_increment_existing(self):
        state = PityState()
        state.data.setdefault('soft_ssr', {})['counter'] = 5
        state.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 6

    def test_reset(self):
        state = PityState()
        state.data.setdefault('soft_ssr', {})['counter'] = 10
        state.set('soft_ssr', 'counter', 0)
        assert state.get('soft_ssr', 'counter', 0) == 0

    def test_get_nonexistent(self):
        state = PityState()
        assert state.get('nonexistent', 'counter', 0) == 0

    def test_clone_independent(self):
        state = PityState()
        state.incr('soft_ssr', 'counter')
        cloned = state.clone()
        cloned.incr('soft_ssr', 'counter')
        assert state.get('soft_ssr', 'counter', 0) == 1
        assert cloned.get('soft_ssr', 'counter', 0) == 2

    def test_to_from_dict_roundtrip(self):
        state = PityState()
        state.data = {'soft_ssr': {'counter': 5}, 'hard_ssr': {'counter': 2}}
        d = state.to_dict()
        restored = PityState.from_dict(d)
        assert restored.get('soft_ssr', 'counter', 0) == 5
        assert restored.get('hard_ssr', 'counter', 0) == 2


class TestPityEngineReset:
    """PityEngine after_draw 三种重置语义（新 API）"""

    @staticmethod
    def _make_engine(reset='any_ssr'):
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        pdef = _PityDef(
            name='test_pity', btype='soft_interval', scope='ssr',
            deltas=deltas, reset=reset, pools=('*',),
        )
        state = PityState()
        create_behavior(pdef, state)  # 验证行为可创建（不直接使用返回值）
        spec = PoolPitySpec(
            pity_names=['test_pity'],
            ssr_ids={'ssr_card', 'featured_card'},
            featured_ids={'featured_card'},
            scope_cards={'ssr': ('ssr_card', 'featured_card')},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
            card_to_slot={'ssr_card': 'ssr', 'featured_card': 'ssr'},
        )
        engine = PityEngine(
            pool_specs={'test_pool': spec},
            pity_defs=[pdef],
            state=state,
            rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
        )
        return engine, state

    def test_ssr_reset_on_ssr(self):
        """_reset='ssr' → 抽到任何 SSR 都重置"""
        engine, state = self._make_engine('ssr')
        state.incr('test_pity', 'counter')
        state.incr('test_pity', 'counter')
        assert state.get('test_pity', 'counter', 0) == 2
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 0

    def test_ssr_no_reset_on_sr(self):
        """_reset='ssr' → 非 SSR 不重置"""
        engine, state = self._make_engine('ssr')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'sr_card')
        assert state.get('test_pity', 'counter', 0) == 1

    def test_featured_reset_only_on_featured(self):
        """_reset='featured' → 标准 SSR 不重置"""
        engine, state = self._make_engine('featured')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'ssr_card')
        assert state.get('test_pity', 'counter', 0) == 1

    def test_featured_reset_on_featured(self):
        """_reset='featured' → featured SSR 触发重置"""
        engine, state = self._make_engine('featured')
        state.incr('test_pity', 'counter')
        engine.after_draw('test_pool', state, 'featured_card')
        assert state.get('test_pity', 'counter', 0) == 0

    def test_deactivate_on_early_hit(self):
        """deactivate_on_early_hit=True → 触发后停用，计数器保持（退役跳过重置）"""
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        pdef = _PityDef(
            name='test_once', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr',
            deactivate_on_early_hit=True,
            pools=('*',),
        )
        state2 = PityState()
        create_behavior(pdef, state2)
        spec2 = PoolPitySpec(
            pity_names=['test_once'],
            ssr_ids={'ssr_card'},
            featured_ids=set(),
            scope_cards={'ssr': ('ssr_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
            # S8 起 A 列（`scope_cards` 的卡）与分布键空间同键，`card_to_slot`
            # 仅为槽位字段的完整性保留（旧保底类读它，ISSUE-901）。
            card_to_slot={'ssr_card': 'ssr'},
        )
        eng2 = PityEngine(
            pool_specs={'test_pool': spec2},
            pity_defs=[pdef],
            state=state2,
            rarity_rank={'ssr': 0},
        )
        state2.incr('test_once', 'counter')
        assert state2.get('test_once', 'counter', 0) == 1
        eng2.after_draw('test_pool', state2, 'ssr_card')
        # deactivate_on_early_hit=True → 退役先于 commit，且跳过默认 counter reset
        assert state2.get('test_once', 'counter', 0) == 1  # counter 保持
        assert state2.get('test_once', '_active', True) is False  # 已停用


class TestPityEngineBeforeDraw:
    """PityEngine before_draw / get_probabilities（新 API）"""

    @staticmethod
    def _make_engine():
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 74, 90, None)
        pdef = _PityDef(
            name='test_pity', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr', pools=('*',),
        )
        state = PityState()
        create_behavior(pdef, state)
        spec = PoolPitySpec(
            pity_names=['test_pity'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',), 'r': ('r_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
            # S8 起 A 列（`scope_cards` 的卡）与分布键空间同键，`card_to_slot`
            # 仅为槽位字段的完整性保留（旧保底类读它，ISSUE-901）。
            card_to_slot={'ssr_card': 'ssr', 'r_card': 'r'},
        )
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs=[pdef],
            state=state,
            rarity_rank={'ssr': 0, 'r': 1},
        )
        return engine, state

    def test_before_draw_increments_counter(self):
        engine, state = self._make_engine()
        probs = engine.before_draw('pool', state, {'ssr_card': 0.006, 'r_card': 0.994})
        assert state.get('test_pity', 'counter', 0) == 1
        assert 'ssr_card' in probs

    def test_before_draw_unknown_pool(self):
        engine = PityEngine(pool_specs={}, pity_defs=[], state=PityState(), rarity_rank={})
        state = PityState()
        probs = engine.before_draw('nonexistent', state, {'a': 1.0})
        assert probs == {'a': 1.0}

    def test_get_probabilities_at_pity_cap(self):
        engine, state = self._make_engine()
        state.data.setdefault('test_pity', {})['counter'] = 90
        probs = engine.get_probabilities('pool', state, {'ssr_card': 0.006, 'r_card': 0.994})
        assert probs['ssr_card'] == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════
# Task 13(a2): 多保底叠加 + 计数器边界
# ═══════════════════════════════════════════════════════════════════

class TestMultiPityStacking:
    """多保底叠加顺序（新 API）"""

    @staticmethod
    def _make_two_pity_engine():
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        soft_pdef = _PityDef(
            name='soft', btype='soft_interval', scope='ssr',
            deltas=deltas, reset='ssr', pools=('*',),
        )
        hard_pdef = _PityDef(
            name='hard', btype='hard', scope='ssr',
            threshold=90, reset='ssr', pools=('*',),
        )
        state = PityState()
        create_behavior(soft_pdef, state)
        create_behavior(hard_pdef, state)
        spec = PoolPitySpec(
            pity_names=['soft', 'hard'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',), 'r': ('r_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
            # S8 起 A 列（`scope_cards` 的卡）与分布键空间同键，`card_to_slot`
            # 仅为槽位字段的完整性保留（旧保底类读它，ISSUE-901）。
            card_to_slot={'ssr_card': 'ssr', 'r_card': 'r'},
        )
        engine = PityEngine(
            pool_specs={'pool': spec},
            pity_defs=[soft_pdef, hard_pdef],
            state=state,
            rarity_rank={'ssr': 0, 'r': 1},
        )
        return engine, state

    def test_two_pities_stack(self):
        """软保底+硬保底叠加"""
        engine, state = self._make_two_pity_engine()
        # counter=82: 软保底生效但未达100%，硬保底未触发
        state.data = {'soft': {'counter': 82, '_active': True},
                      'hard': {'counter': 82, '_active': True}}
        probs = engine.get_probabilities('pool', state, {'ssr_card': 0.006, 'r_card': 0.994})
        assert 0.3 < probs['ssr_card'] < 0.99  # soft pity active, not 100%

        # counter=90: 硬保底覆盖 → SSR=100%
        state.data = {'soft': {'counter': 90, '_active': True},
                      'hard': {'counter': 90, '_active': True}}
        probs = engine.get_probabilities('pool', state, {'ssr_card': 0.006, 'r_card': 0.994})
        assert probs['ssr_card'] == pytest.approx(1.0)

    def test_pity_order_matters(self):
        """软保底(soft_interval)先于硬保底(hard)执行，概率叠加正确"""
        from gacha_simulator.core.config_store import PityDef as _PityDef
        from gacha_simulator.core.config_toml import _expand_soft_to_deltas
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        spdef = _PityDef(name='s', btype='soft_interval', scope='ssr',
                         deltas=deltas, reset='ssr', pools=('*',))
        hpdef = _PityDef(name='h', btype='hard', scope='ssr',
                         threshold=90, reset='ssr', pools=('*',))
        state3 = PityState()
        create_behavior(spdef, state3)
        create_behavior(hpdef, state3)
        spec3 = PoolPitySpec(
            pity_names=['s', 'h'],
            ssr_ids={'ssr_card'},
            scope_cards={'ssr': ('ssr_card',), 'r': ('r_card',)},
            scope_slots={'ssr': ('ssr',)},
            featured_slots={'ssr': ('ssr',)},
            # S8 起 A 列（`scope_cards` 的卡）与分布键空间同键，`card_to_slot`
            # 仅为槽位字段的完整性保留（旧保底类读它，ISSUE-901）。
            card_to_slot={'ssr_card': 'ssr', 'r_card': 'r'},
        )
        eng3 = PityEngine(
            pool_specs={'pool': spec3}, pity_defs=[spdef, hpdef],
            state=state3, rarity_rank={'ssr': 0, 'r': 1},
        )
        state3.data = {'s': {'counter': 82, '_active': True},
                       'h': {'counter': 82, '_active': True}}
        probs = eng3.get_probabilities('pool', state3, {'ssr_card': 0.006, 'r_card': 0.994})
        assert 0.3 < probs['ssr_card'] < 0.99


class TestCounterBoundaries:
    """保底计数器边界：经只读查询在**显式计数**下取分布。

    旧用例直调 `_compute_probabilities(ctx, counter)` 显式给计数；新架构的对应
    入口是 `before_draw(ctx, readonly=True)`。只读查询不推进 `advance` 相位，
    故读到的正是预置的那个计数（`hard(threshold=90)` 首次 100% 落在第 90 抽的
    顺序面由 `TestN1CounterPhase` 单独钉住）。
    """

    def test_counter_zero(self):
        state = PityState()
        pity = _make_hard(state)
        state.set('test', 'counter', 0)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out == pytest.approx(_SSR_PROBS)

    def test_counter_threshold_minus_one(self):
        state = PityState()
        pity = _make_hard(state)
        state.set('test', 'counter', 89)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out == pytest.approx(_SSR_PROBS)  # 尚未触发

    def test_counter_at_threshold(self):
        state = PityState()
        pity = _make_hard(state)
        state.set('test', 'counter', 90)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(1.0)  # 触发

    def test_soft_boundary_start(self):
        """counter=start-1 时 boost=0、概率不变；counter=start 起加成"""
        state = PityState()
        pity = _make_soft(state)
        state.set('test', 'counter', 72)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(0.006)
        state.set('test', 'counter', 73)
        out73 = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out73['ssr_card'] >= 0.006

    def test_soft_boundary_end(self):
        """counter=end 时 boost=100%，SSR=100%"""
        state = PityState()
        pity = _make_soft(state)
        state.set('test', 'counter', 90)
        out = pity.before_draw(_ssr_ctx(state), readonly=True)
        assert out['ssr_card'] == pytest.approx(1.0)
