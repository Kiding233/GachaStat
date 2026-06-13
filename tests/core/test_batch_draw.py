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
from gacha_simulator.core.pool_config import PoolConfig
from gacha_simulator.core.state import GachaState


# ═══════════════════════════════════════════════════════════════════════
# Task 1: 数据模型——默认值
# ═══════════════════════════════════════════════════════════════════════

def test_pool_config_batch_size_default():
    """PoolConfig.batch_size 默认值为 1。"""
    pc = PoolConfig(
        pool_id='test', name='test', start_day=0, end_day=21,
        cost_str='draw_resource:160', distribution_file='pools/test.txt',
    )
    assert pc.batch_size == 1


def test_pool_batch_size_default():
    """运行时 Pool 对象 batch_size 默认为 1。"""
    from gacha_simulator.core.pool import Pool
    pool = Pool(id='test', name='test', cost=[], rewards=[])
    assert pool.batch_size == 1


# ═══════════════════════════════════════════════════════════════════════
# Task 2: 配置读写——schedule.txt 第 9 列
# ═══════════════════════════════════════════════════════════════════════

def test_parse_schedule_with_batch_size():
    """schedule.txt 第 9 列 batch_size 被正确解析。"""
    from gacha_simulator.core.pool_config import parse_schedule_file
    import tempfile, os
    content = (
        "pool_b10 | 十连池 | 0 | 21 | draw_resource:160 | pools/test.txt | ssr=c1 | | 10\n"
        "pool_s1  | 单抽池 | 0 | 21 | draw_resource:160 | pools/test.txt | ssr=c1 | | 1\n"
        "pool_def | 默认池 | 0 | 21 | draw_resource:160 | pools/test.txt | ssr=c1\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    try:
        tmp.write(content)
        tmp.close()
        configs, _ = parse_schedule_file(tmp.name)
        assert configs[0].batch_size == 10
        assert configs[1].batch_size == 1
        assert configs[2].batch_size == 1   # 缺省
    finally:
        os.unlink(tmp.name)


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
