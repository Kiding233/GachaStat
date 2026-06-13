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
