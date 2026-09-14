"""gdr_binning 离散整数格点分箱测试（P58 善后——exchange 累抽币每池分箱外扩修复）。

背景：exchange_currency 剩余是离散整数（milestone every=1 / m_at=300），值域小。
修复前唯一值 >20 时被错误地走「对齐 160 抽卡成本」步长分箱，产生负边界与宽 bin；
唯一值 ≤20 时走有限格点中点分箱，0 与下一值中点外扩出负边界。修复后离散整数
数据优先走整数格点（size=1，起点=最小值）。
"""
import numpy as np

from gacha_simulator.core.gdr_binning import (
    compute_bins,
    _is_discrete_integer,
    _bins_integer_grid,
)


class TestIsDiscreteInteger:
    """离散整数判定边界。"""

    def test_all_integer_small_span(self):
        # 全整数 + 值域小 + 唯一值适中 → True
        vals = np.array([0, 5, 331, 335, 340], dtype=float)
        assert _is_discrete_integer(vals) is True

    def test_integer_large_span_rejected(self):
        # 值域 > 500 → False（draw_resource 0~55000 这类连续大值域）
        vals = np.array([0.0, 5000.0, 55000.0])
        assert _is_discrete_integer(vals) is False

    def test_float_rejected(self):
        # 含小数 → False（非整数格点数据）
        vals = np.array([0.5, 1.5, 331.5])
        assert _is_discrete_integer(vals) is False

    def test_many_uniq_rejected(self):
        # 唯一值 > 200 → False
        vals = np.arange(0, 300, 1.0)
        assert _is_discrete_integer(vals) is False


class TestIntegerGridBins:
    """整数格点分箱——size=1，起点=最小值。"""

    def test_edges_integer_step(self):
        edges = _bins_integer_grid(np.array([0.0, 5.0, 331.0])).bin_edges
        assert edges[0] == 0.0
        assert edges[1] - edges[0] == 1.0      # size=1
        assert edges[-1] == 332.0               # max+1

    def test_start_is_min_not_extended(self):
        # 起点=最小值本身，无中点外扩（这是修复的核心）
        edges = _bins_integer_grid(np.array([8.0, 15.0, 339.0])).bin_edges
        assert edges[0] == 8.0


class TestComputeBinsDiscreteInteger:
    """compute_bins 分流——离散整数走整数格点，连续大值域不受影响。"""

    def test_exchange_uniq5_no_negative_edge(self):
        # exchange 唯一值 ≤20（修复前有限格点中点外扩 → -2.5）
        vals = np.array([0.0, 5.0, 331.0, 335.0, 340.0])
        rb = compute_bins('resource_remaining:exchange_currency', vals, cost_per_draw=160)
        assert rb.bin_edges is not None
        assert rb.bin_edges[0] == 0.0                     # 无负边界
        assert rb.bin_edges[1] - rb.bin_edges[0] == 1.0   # 整数格点

    def test_exchange_uniq38_no_step_alignment(self):
        # exchange 唯一值 >20（修复前被步长对齐 160 → 负边界 -147）
        rng = np.random.RandomState(42)
        vals = []
        total = 0
        for _ in range(8):
            total += int(rng.uniform(8, 60))
            vals.append(total // 10 + (300 if total >= 300 else 0))
        vals = np.array(vals, dtype=float)
        rb = compute_bins('resource_remaining:exchange_currency', vals, cost_per_draw=160)
        assert rb.bin_edges is not None
        assert rb.bin_edges[0] == float(vals.min())       # 起点=最小值，非负
        assert rb.bin_edges[1] - rb.bin_edges[0] == 1.0   # 整数格点，非 160 步长

    def test_pity_draws_integer_grid(self):
        # 保底次数（整数小值域）走整数格点
        vals = np.array([9.0, 10.0, 11.0, 12.0, 13.0])
        rb = compute_bins('pity_draws', vals)
        assert rb.bin_edges[0] == 9.0
        assert rb.bin_edges[1] - rb.bin_edges[0] == 1.0

    def test_draw_large_span_not_integer_grid(self):
        # draw_resource 连续大值域 → 不走整数格点（值域 >500），保持原路径
        vals = np.array([55000.0, 49000.0, 43000.0, 37000.0, 31000.0, 25000.0,
                         19000.0, 13000.0, 7000.0, 1000.0, 800.0, 600.0,
                         400.0, 200.0, 100.0, 80.0])
        rb = compute_bins('resource_remaining:draw_resource', vals, cost_per_draw=160)
        assert rb.bin_edges is not None
        assert rb.bin_edges[1] - rb.bin_edges[0] != 1.0    # 不是整数格点

    def test_non_integer_finite_grid_unchanged(self):
        # 小数离散（唯一值 ≤20）仍走有限格点（bar_mode），不受整数格点分流影响
        vals = np.array([0.5, 1.5, 2.5, 3.5])
        rb = compute_bins('some_gdr', vals)
        assert rb.bar_mode is True
        assert rb.bin_edges is not None
