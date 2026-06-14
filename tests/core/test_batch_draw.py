"""P44: 池子批次抽卡（十连强制）——测试。

测试覆盖范围:
- Task 1: PoolConfig/PoolEntry/Pool 默认 batch_size=1
- Task 2: schedule.txt 第 9 列解析
- Task 3: can_afford_batch + _choose_option_from
- Task 4: 策略 batch_size 感知
- Task 5a: 服务层批次循环骨架
- Task 5b: 保底逐发调用
- Task 5c: _pending_wait_gains 批次归因
"""

import pytest
from gacha_simulator.core.config_store import PoolEntry
from gacha_simulator.core.state import GachaState


# ═══════════════════════════════════════════════════════════════════════
# Task 1: 数据模型——默认值
# ═══════════════════════════════════════════════════════════════════════

def test_pool_entry_batch_size_default():
    """PoolEntry.batch_size 默认值为 1。"""
    pe = PoolEntry(
        pool_id='test', name='test', pool_type='角色',
        start_day=0, end_day=21, cost='draw_resource:160',
        distribution=[], distribution_template='',
    )
    assert pe.batch_size == 1


def test_pool_batch_size_default():
    """运行时 Pool 对象 batch_size 默认为 1。"""
    from gacha_simulator.core.pool import Pool
    pool = Pool(id='test', name='test', cost=[], rewards=[])
    assert pool.batch_size == 1


# ═══════════════════════════════════════════════════════════════════════
# Task 3: 资源检查——can_afford_batch + _choose_option_from
# ═══════════════════════════════════════════════════════════════════════

class TestCanAffordBatch:
    def test_single_resource_sufficient(self):
        """单一资源足够 batch_size 发。"""
        state = GachaState(resources={'draw_resource': 2000})
        cost = {'draw_resource': 160}
        assert state.can_afford_batch(cost, 10) is True

    def test_single_resource_insufficient(self):
        """单一资源不够 batch_size 发。"""
        state = GachaState(resources={'draw_resource': 1500})
        cost = {'draw_resource': 160}
        assert state.can_afford_batch(cost, 10) is False

    def test_batch_size_1_delegates_to_can_afford(self):
        """batch_size=1 退化为 can_afford。"""
        state = GachaState(resources={'draw_resource': 200})
        cost = {'draw_resource': 160}
        assert state.can_afford_batch(cost, 1) == state.can_afford(cost)

    def test_multi_resource_priority_switching(self):
        """免费抽耗尽后自动切换到付费资源。"""
        state = GachaState(resources={
            'free_draw': 5,
            'draw_resource': 2000,
        })
        cost = [{'free_draw': 1}, {'draw_resource': 160}]
        assert state.can_afford_batch(cost, 10) is True

    def test_multi_resource_insufficient_after_priority_exhaustion(self):
        """免费抽耗尽后付费资源不足 → False。"""
        state = GachaState(resources={
            'free_draw': 5,
            'draw_resource': 400,
        })
        cost = [{'free_draw': 1}, {'draw_resource': 160}]
        assert state.can_afford_batch(cost, 10) is False

    def test_batch_size_1_multi_resource(self):
        """batch_size=1 多资源退化测试。"""
        state = GachaState(resources={'free_draw': 1})
        cost = [{'free_draw': 1}, {'draw_resource': 160}]
        assert state.can_afford_batch(cost, 1) is True
        state2 = GachaState(resources={'draw_resource': 200})
        assert state2.can_afford_batch(cost, 1) is True
        state3 = GachaState(resources={})
        assert state3.can_afford_batch(cost, 1) is False


# ═══════════════════════════════════════════════════════════════════════
# Task 4: 策略适配——batch_size 感知
# ═══════════════════════════════════════════════════════════════════════

def test_strategy_can_afford_batch_uses_pool_batch_size():
    """策略调用 can_afford_batch 时第二个参数为 pool.batch_size（非硬编码 1）。"""
    from gacha_simulator.core.pool import Pool, Reward
    from gacha_simulator.core.schedule import PoolSchedule
    from gacha_simulator.core.strategy import SmartStrategy, StrategyContext
    from gacha_simulator.core.stop_condition import StopCondition
    from gacha_simulator.core.target_card import TargetCardSet, TargetCard

    class NoopStop(StopCondition):
        def check(self, state, history, stats=None):
            return False
        def description(self):
            return "noop"

    pool = Pool(
        id='test_b10', name='十连池', cost=[{'coin': 10}],
        rewards=[(Reward(id='card_a', name='A'), 1.0)],
        batch_size=10
    )
    state = GachaState(resources={'coin': 100})
    original_can_afford_batch = state.can_afford_batch
    call_args = []
    def spy(cost, batch_size):
        call_args.append((cost, batch_size))
        return original_can_afford_batch(cost, batch_size)
    state.can_afford_batch = spy

    # SmartStrategy 需要 target card 才会触发 pool 遍历中的 can_afford 检查
    tc = TargetCard(card_id='card_a', quantity_needed=1, pool_ids=['test_b10'])
    ctx = StrategyContext(
        state=state, current_pools=[pool], all_pools=[pool],
        future_schedules=[], stop_condition=NoopStop(),
        target_cards=TargetCardSet([tc]), acquired={},
        pool_draw_counts={'test_b10': 0}, total_draws=0,
        ssr_ids=set(),
    )
    strategy = SmartStrategy()
    strategy.select_action(ctx)
    assert len(call_args) >= 1
    assert call_args[0][1] == pool.batch_size
    assert call_args[0][1] == 10


# ═══════════════════════════════════════════════════════════════════════
# Task 5a: 服务层批次循环骨架
# ═══════════════════════════════════════════════════════════════════════

class TestGachaServiceBatchDrawSkeleton:
    """Task 5a: 批次循环骨架——预检查 + 循环 + 逐发 spend + break。"""

    def test_batch_draw_executes_n_draws(self):
        """batch_size=3 的池子一次 DrawAction 执行 3 发。"""
        from gacha_simulator.core.pool import Pool, Reward
        from gacha_simulator.core.action import DrawAction
        from gacha_simulator.core.strategy import Strategy
        from gacha_simulator.core.stop_condition import StopCondition
        from gacha_simulator.core.target_card import TargetCardSet
        from gacha_simulator.service.gacha_service import GachaService

        pool = Pool(
            id='test_batch', name='batch池', cost=[{'coin': 10}],
            rewards=[(Reward(id='card_a', name='A'), 1.0)],
            batch_size=3,
        )
        state = GachaState(resources={'coin': 100})

        class FixedDraw(Strategy):
            def select_action(self, ctx):
                return DrawAction(pool_id='test_batch')
            def description(self):
                return "fixed batch"

        class NeverStop(StopCondition):
            def check(self, state, pools, stats):
                return False
            def description(self):
                return "never stop"

        service = GachaService(
            pools=[pool], strategy=FixedDraw(),
            stop_condition=NeverStop(),
            target_cards=TargetCardSet([]),
            pity_engine=None, resource_gain=None,
            schedule_manager=None, card_defs=[], ssr_ids=set(),
        )
        # max_iterations=1：限制 1 次迭代，验证批次循环在一次动作中执行 N 发
        result = service.run_simulation_compact(state, max_iterations=1)
        # 关键断言：1 次 DrawAction + batch_size=3 → 3 发，非旧代码的 1 发
        assert result.total_draws == 3
        assert result.total_consumed.get('coin', 0) == 30

    def test_batch_draw_insufficient_skips(self):
        """资源不足 batch_size 发时静默跳过。"""
        from gacha_simulator.core.pool import Pool, Reward
        from gacha_simulator.core.action import DrawAction
        from gacha_simulator.core.strategy import Strategy
        from gacha_simulator.core.stop_condition import StopCondition
        from gacha_simulator.core.target_card import TargetCardSet
        from gacha_simulator.service.gacha_service import GachaService

        pool = Pool(
            id='test_batch', name='batch池', cost=[{'coin': 10}],
            rewards=[(Reward(id='card_a', name='A'), 1.0)],
            batch_size=10,
        )
        state = GachaState(resources={'coin': 50})

        class FixedDraw(Strategy):
            def select_action(self, ctx):
                return DrawAction(pool_id='test_batch')
            def description(self):
                return "fixed batch"

        class NeverStop(StopCondition):
            def check(self, state, pools, stats):
                return stats.total_draws > 0
            def description(self):
                return "never stop"

        service = GachaService(
            pools=[pool], strategy=FixedDraw(),
            stop_condition=NeverStop(),
            target_cards=TargetCardSet([]),
            pity_engine=None, resource_gain=None,
            schedule_manager=None, card_defs=[], ssr_ids=set(),
        )
        result = service.run_simulation_compact(state, max_iterations=100)
        assert result.total_draws == 0


# ═══════════════════════════════════════════════════════════════════════
# Task 5b: 保底逐发调用
# ═══════════════════════════════════════════════════════════════════════

def test_batch_draw_pity_called_per_draw():
    """保底引擎逐发调用 before_draw / after_draw——不使用过期缓存。"""
    from unittest.mock import MagicMock
    from gacha_simulator.core.pool import Pool, Reward
    from gacha_simulator.core.action import DrawAction
    from gacha_simulator.core.strategy import Strategy
    from gacha_simulator.core.stop_condition import StopCondition
    from gacha_simulator.core.target_card import TargetCardSet
    from gacha_simulator.service.gacha_service import GachaService

    pool = Pool(
        id='test_batch', name='batch池', cost=[{'coin': 10}],
        rewards=[(Reward(id='card_a', name='A'), 1.0)],
        batch_size=3,
    )
    state = GachaState(resources={'coin': 100})

    class FixedDraw(Strategy):
        def select_action(self, ctx):
            return DrawAction(pool_id='test_batch')
        def description(self):
            return "fixed batch"

    class ThreeDrawStop(StopCondition):
        def check(self, state, pools, stats):
            return stats.total_draws >= 3
        def description(self):
            return "three draw stop"

    mock_pity = MagicMock()
    mock_pity.get_spec.return_value = None
    mock_pity.before_draw.return_value = {'card_a': 1.0}

    service = GachaService(
        pools=[pool], strategy=FixedDraw(),
        stop_condition=ThreeDrawStop(),
        target_cards=TargetCardSet([]),
        pity_engine=mock_pity, resource_gain=None,
        schedule_manager=None, card_defs=[], ssr_ids=set(),
    )
    result = service.run_simulation_compact(state, max_iterations=100)
    assert result.total_draws == 3
    # 关键断言：batch_size=3 → before_draw 调用 3 次（非 1 次缓存复用）
    assert mock_pity.before_draw.call_count == 3
    assert mock_pity.after_draw.call_count == 3


# ═══════════════════════════════════════════════════════════════════════
# Task 5c: _pending_wait_gains 批次归因
# ═══════════════════════════════════════════════════════════════════════

def test_batch_on_draw_called_per_draw_not_per_action():
    """批次中 collector.on_draw 逐发调用 batch_size 次（非 1 次），确保归因粒度正确。"""
    from gacha_simulator.core.pool import Pool, Reward
    from gacha_simulator.core.action import DrawAction
    from gacha_simulator.core.strategy import Strategy
    from gacha_simulator.core.stop_condition import StopCondition
    from gacha_simulator.core.target_card import TargetCardSet
    from gacha_simulator.service.gacha_service import GachaService

    pool = Pool(
        id='test_batch', name='batch池', cost=[{'coin': 10}],
        rewards=[(Reward(id='card_a', name='A'), 1.0)],
        batch_size=3,
    )
    state = GachaState(resources={'coin': 100})

    class FixedDraw(Strategy):
        def select_action(self, ctx):
            return DrawAction(pool_id='test_batch')
        def description(self):
            return "fixed batch"

    class ThreeDrawStop(StopCondition):
        def check(self, state, pools, stats):
            return stats.total_draws >= 3
        def description(self):
            return "three draw stop"

    on_draw_calls = []
    from gacha_simulator.core import CompactCollector

    class SpyCollector(CompactCollector):
        def on_draw(self, **kwargs):
            on_draw_calls.append(kwargs)
            super().on_draw(**kwargs)

    service = GachaService(
        pools=[pool], strategy=FixedDraw(),
        stop_condition=ThreeDrawStop(),
        target_cards=TargetCardSet([]),
        pity_engine=None, resource_gain=None,
        schedule_manager=None, card_defs=[], ssr_ids=set(),
    )
    result = service.run_simulation(state, max_iterations=100, collector=SpyCollector())
    assert result.total_draws == 3
    assert len(on_draw_calls) == 3  # ← 核心断言：每发一次 on_draw，非每动作一次
