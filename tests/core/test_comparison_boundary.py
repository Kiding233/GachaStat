"""P45 任务 5——G6 边界覆盖用例。"""
import numpy as np
import pytest
from gacha_simulator.core.comparison_analyzer import (
    compute_dominance_matrix_v2,
    classify_dominance,
    benjamini_hochberg,
    _PYSDTEST_AVAILABLE,
)


@pytest.mark.skipif(not _PYSDTEST_AVAILABLE, reason="PySDTest 未安装")
class TestBoundaryCases:
    """G6 边界覆盖——确保极端/退化场景正确处理。"""

    def test_n2_minimal_scenario(self):
        """n=2 最简场景——分类矩阵应为 2×2，对角线为 '—'."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=200),
            rng.normal(75, 10, size=200),
        ]
        names = ["A", "B"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=100)
        assert len(result['matrix']) == 2
        assert len(result['classification']) == 2
        for i in range(2):
            assert result['matrix'][i][i] is None
            assert result['classification'][i][i] == '—'

    def test_identical_distributions(self):
        """全相等分布——同一数据复制为两个策略，预期分类为 '='."""
        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, size=500)
        values = [data, data.copy()]
        names = ["A", "B"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=200, rng_seed=42)
        # 相同数据 → 预期无差异，非交叉或占优
        label_01 = classify_dominance(
            {1: result['matrix'][0][1]}, {1: result['matrix'][1][0]}
        )
        label_10 = classify_dominance(
            {1: result['matrix'][1][0]}, {1: result['matrix'][0][1]}
        )
        # 允许少数样本导致 = 降级，但不应是交叉或占优（那表示系统性错误）
        assert label_01.label not in ('×(FSD)', '≻ (FSD)', '≺ (FSD)'), \
            f"Identical data should not classify as cross/dominance: {label_01.label}"
        assert label_10.label not in ('×(FSD)', '≻ (FSD)', '≺ (FSD)'), \
            f"Identical data should not classify as cross/dominance: {label_10.label}"

    def test_lower_is_better_negation(self):
        """(-)GDR 方向——lower_is_better=True 时数据取反在 v2 内部生效."""
        rng = np.random.default_rng(42)
        # A 的 miss_rate 均值低（更好），B 的 miss_rate 均值高（更差）
        a = rng.normal(0.1, 0.02, size=200)  # 更好
        b = rng.normal(0.3, 0.02, size=200)  # 更差
        values = [a, b]
        names = ["A", "B"]

        # lower_is_better=True → 内部对样本取负号后送入 PySDTest
        result = compute_dominance_matrix_v2(
            values, names, order=1, n_bootstrap=100,
            lower_is_better=True,
        )
        # A 更好（miss_rate 更低，取反后值更高）→ A 应 ≻ B
        label_ab = classify_dominance(
            {1: result['matrix'][0][1]}, {1: result['matrix'][1][0]}
        )
        # 验证 ≻ 指向真实更优方（A 优于 B）
        # 若静默跳过取反，会得出相反结论
        assert label_ab.label in ('≻ (FSD)', '='), \
            f"Expected A≻B or = for lower_is_better, got: {label_ab.label}"

    def test_bh_preserves_order(self):
        """BH FDR 校正不改变原始 p 值排序."""
        p_values = [0.001, 0.02, 0.03, 0.05, 0.15, 0.4, 0.8]
        corrected = benjamini_hochberg(p_values)
        for i in range(len(p_values)):
            for j in range(i + 1, len(p_values)):
                if p_values[i] <= p_values[j]:
                    assert corrected[i] <= corrected[j], \
                        f"BH order violation at ({i},{j})"

    def test_seed_reproducibility(self):
        """固定 rng_seed 两次运行 matrix 逐元素一致."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=200),
            rng.normal(75, 10, size=200),
            rng.normal(80, 10, size=200),
        ]
        names = ["A", "B", "C"]
        r1 = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80, rng_seed=42)
        r2 = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80, rng_seed=42)
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                assert r1['matrix'][i][j] == r2['matrix'][i][j], \
                    f"Seed repro violation at ({i},{j})"

    def test_diagonal_none(self):
        """对角线始终为 None."""
        rng = np.random.default_rng(42)
        values = [
            rng.normal(70, 10, size=100),
            rng.normal(75, 10, size=100),
        ]
        names = ["A", "B"]
        result = compute_dominance_matrix_v2(values, names, order=1, n_bootstrap=80)
        assert result['matrix'][0][0] is None
        assert result['matrix'][1][1] is None
        assert result['matrix_raw'][0][0] is None
        assert result['matrix_raw'][1][1] is None

    def test_classify_dominance_all_none_is_err(self):
        """所有阶均无有效 p 值 → 返回 'err'."""
        result = classify_dominance({}, {})
        assert result.label == 'err'

    def test_classify_dominance_sparse_fsd_only(self):
        """仅 FSD 有有效 p 值 → 正确判定."""
        # p_ij[1]=0.01 (显著), p_ji[1]=0.6 (不显著) → i 不占优 j → ≺
        result = classify_dominance({1: 0.01}, {1: 0.6})
        assert result.label == '≺ (FSD)'
