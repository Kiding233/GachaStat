"""P45 任务 1b——comparison_analyzer 核心测试 (PySDTest v2 路径)。"""
import numpy as np
import pytest
from gacha_simulator.core.comparison_analyzer import (
    dd_bootstrap_test_v2,
    compute_dominance_matrix_v2,
    compute_integrated_cdf,
    benjamini_hochberg,
    _PYSDTEST_AVAILABLE,
)


@pytest.mark.skipif(not _PYSDTEST_AVAILABLE, reason="PySDTest 未安装")
class TestDDBootstrapV2:
    """dd_bootstrap_test_v2 基本功能测试。"""

    def test_basic_two_normal_samples(self):
        """两正态样本 n=200，返回值结构正确且 p_value ∈ [0,1]."""
        rng = np.random.default_rng(42)
        a = rng.normal(70, 10, size=200)
        b = rng.normal(75, 10, size=200)
        result = dd_bootstrap_test_v2(a, b, n_bootstrap=100, orders=[1])
        assert 1 in result
        r1 = result[1]
        assert 'p_value' in r1
        assert 'test_stat' in r1
        assert 'critical_val' in r1
        assert r1['p_value'] is not None
        assert 0.0 <= r1['p_value'] <= 1.0

    def test_orders_default_all_three(self):
        """未指定 orders 时默认返回全三阶."""
        rng = np.random.default_rng(42)
        a = rng.normal(70, 10, size=200)
        b = rng.normal(75, 10, size=200)
        result = dd_bootstrap_test_v2(a, b, n_bootstrap=100)
        for s in [1, 2, 3]:
            assert s in result, f"order={s} missing"
            assert result[s]['p_value'] is not None

    def test_seed_reproducibility(self):
        """相同 seed 产生相同结果."""
        rng = np.random.default_rng(42)
        a = rng.normal(0, 1, size=100)
        b = rng.normal(0.5, 1, size=100)
        r1 = dd_bootstrap_test_v2(a, b, n_bootstrap=80, orders=[1], seed=123)
        r2 = dd_bootstrap_test_v2(a, b, n_bootstrap=80, orders=[1], seed=123)
        assert r1[1]['p_value'] == r2[1]['p_value']

    def test_strict_dominance_detected(self):
        """S1 场景——B 严格占优 A 应检出（p 值很小）."""
        rng = np.random.default_rng(42)
        a = rng.normal(70, 10, size=300)
        b = rng.normal(80, 10, size=300)
        # A 占优 B 的 H₀ 应被拒绝 → p 小
        result_ab = dd_bootstrap_test_v2(a, b, orders=[1], n_bootstrap=200)
        # A 不占优 B (a_b_p 小), B 可能占优 A (b_a_p 大)
        assert result_ab[1]['p_value'] < 0.05, f"A→B p={result_ab[1]['p_value']}"


@pytest.mark.skipif(not _PYSDTEST_AVAILABLE, reason="PySDTest 未安装")
class TestDominanceMatrixV2:
    """compute_dominance_matrix_v2 矩阵形状与返回值测试。"""

    def test_shape_three_strategies(self):
        """3 策略输入 → 3×3 矩阵，对角为 None."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=200),
            rng.normal(75, 10, size=200),
            rng.normal(80, 10, size=200),
        ]
        names = ["A", "B", "C"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=100)
        assert len(result['matrix']) == 3
        for i in range(3):
            assert result['matrix'][i][i] is None
            assert result['classification'][i][i] == '—'

    def test_returns_required_keys(self):
        """返回值包含所有必要键."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=100),
            rng.normal(75, 10, size=100),
        ]
        names = ["A", "B"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80)
        for key in ['matrix', 'matrix_raw', 'dominates', 'classification',
                     'names', 'order', 'lower_is_better']:
            assert key in result, f"Missing key: {key}"
        assert result['dominates'] is None  # ISSUE-004

    def test_classification_sig_ns_err_labels(self):
        """classification 矩阵仅含 'sig'/'ns'/'err'/'—'."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=100),
            rng.normal(75, 10, size=100),
        ]
        names = ["A", "B"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80)
        for i in range(2):
            for j in range(2):
                label = result['classification'][i][j]
                assert label in ('sig', 'ns', 'err', '—'), f"Bad label at ({i},{j}): {label}"

    def test_seed_reproducibility_matrix(self):
        """固定 rng_seed 两次运行 matrix 完全一致."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=100),
            rng.normal(75, 10, size=100),
        ]
        names = ["A", "B"]
        r1 = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80, rng_seed=42)
        r2 = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80, rng_seed=42)
        for i in range(2):
            for j in range(2):
                if i == j:
                    continue
                assert r1['matrix'][i][j] is not None
                assert r2['matrix'][i][j] is not None
                assert r1['matrix'][i][j] == r2['matrix'][i][j], \
                    f"Mismatch at ({i},{j}): {r1['matrix'][i][j]} != {r2['matrix'][i][j]}"


class TestBenjaminiHochberg:
    """BH FDR 校正保序性测试。"""

    def test_preserves_order(self):
        """校正后 q 值排序与原始 p 值排序一致."""
        p_values = [0.001, 0.01, 0.05, 0.1, 0.5]
        corrected = benjamini_hochberg(p_values)
        # BH 保序性: p_i ≤ p_j ⇔ q_i ≤ q_j
        for i in range(len(p_values)):
            for j in range(i + 1, len(p_values)):
                if p_values[i] <= p_values[j]:
                    assert corrected[i] <= corrected[j], \
                        f"BH order violation: p[{i}]={p_values[i]} ≤ p[{j}]={p_values[j]} but q[{i}]={corrected[i]} > q[{j}]={corrected[j]}"

    def test_significant_items_remain_significant(self):
        """极显著 p 值校正后仍保持 <0.05."""
        p_values = [0.0001, 0.001, 0.01, 0.3, 0.5, 0.8]
        corrected = benjamini_hochberg(p_values)
        # 前三项极显著，校正后应 <0.05
        for i in range(3):
            assert corrected[i] < 0.05, f"p[{i}]={p_values[i]} → q={corrected[i]} should be <0.05"

    def test_empty_returns_empty(self):
        """空输入返回空列表."""
        assert benjamini_hochberg([]) == []

    def test_single_value_bounded(self):
        """单值输入返回 ≤1.0."""
        corrected = benjamini_hochberg([0.03])
        assert 0.0 <= corrected[0] <= 1.0


class TestComputeIntegratedCDF:
    """公共积分 CDF 函数测试。"""

    def test_order1_is_ecdf(self):
        """阶数 1 返回经验 CDF."""
        rng = np.random.default_rng(42)
        samples = rng.normal(0, 1, size=100)
        grid = np.linspace(-3, 3, 50)
        F = compute_integrated_cdf(samples, grid, order=1)
        assert F.shape == grid.shape
        assert F[0] >= 0.0
        assert F[-1] <= 1.0
        # ECDF 非递减
        assert np.all(np.diff(F) >= -1e-15)

    def test_higher_orders_smoother(self):
        """高阶积分 CDF 更平滑（值域更大）."""
        rng = np.random.default_rng(42)
        samples = rng.normal(0, 1, size=100)
        grid = np.linspace(-3, 3, 50)
        F1 = compute_integrated_cdf(samples, grid, order=1)
        F3 = compute_integrated_cdf(samples, grid, order=3)
        # 三阶积分累积使值域扩大
        assert np.max(F3) > np.max(F1)
