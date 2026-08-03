"""P45 任务 2a2——GUI 分类判定逻辑冒烟测试 (不依赖 QApplication)."""
from gacha_simulator.core.comparison_analyzer import (
    classify_dominance,
    ClassificationResult,
)


class TestClassifyDominance:
    """分类判定逻辑冒烟测试——覆盖六条规则 + 降级 + 边界."""

    def test_smoke_fsd_row_dominates(self):
        """规则 2: FSD(j→i) 显著 + FSD(i→j) 不显著 → i ≻ j."""
        # j→i 显著 = 拒绝「j占优i」= i 占优 j → ≻
        result = classify_dominance(
            {1: 0.60, 2: 0.50, 3: 0.50},  # i→j 均不显著
            {1: 0.01, 2: 0.30, 3: 0.40},  # j→i FSD显著
        )
        assert result.label == '≻ (FSD)'
        assert result.effect_size_slot is None

    def test_smoke_fsd_col_dominates(self):
        """规则 1: FSD(i→j) 显著 + FSD(j→i) 不显著 → i ≺ j."""
        result = classify_dominance(
            {1: 0.01, 2: 0.02, 3: 0.03},  # i→j 全部显著
            {1: 0.60, 2: 0.50, 3: 0.50},  # j→i 均不显著
        )
        assert result.label == '≺ (FSD)'

    def test_smoke_cross_fsd(self):
        """规则 5: FSD 双向显著 → ×(FSD)."""
        result = classify_dominance(
            {1: 0.001, 2: 0.80, 3: 0.90},
            {1: 0.001, 2: 0.70, 3: 0.80},
        )
        assert result.label == '×(FSD)'  # no higher order to override

    def test_smoke_no_difference(self):
        """规则 6: 所有阶双向不显著 → =."""
        result = classify_dominance(
            {1: 0.50, 2: 0.60, 3: 0.70},
            {1: 0.30, 2: 0.40, 3: 0.50},
        )
        assert result.label == '='

    def test_smoke_ssd_single_sided(self):
        """规则 3: FSD 双向不显著，SSD 单向显著."""
        result = classify_dominance(
            {1: 0.12, 2: 0.15, 3: 0.90},
            {1: 0.08, 2: 0.01, 3: 0.80},  # j→i SSD显著
        )
        assert result.label == '≻ (SSD)'

    def test_smoke_tsd_single_sided(self):
        """规则 4: FSD+SSD 双向不显著，TSD 单向显著."""
        result = classify_dominance(
            {1: 0.12, 2: 0.15, 3: 0.20},
            {1: 0.08, 2: 0.10, 3: 0.01},  # j→i TSD显著
        )
        assert result.label == '≻ (TSD)'

    def test_all_none_is_err(self):
        """所有阶均无有效值 → err."""
        result = classify_dominance({}, {})
        assert result.label == 'err'

    def test_sparse_missing_order(self):
        """稀疏 dict——某阶缺失视为不显著."""
        result = classify_dominance(
            {1: 0.01, 2: 0.02},  # 缺 3
            {1: 0.60},            # 缺 2,3
        )
        # FSD(i→j) 显著 + FSD(j→i) 不显著 → ≺
        assert result.label == '≺ (FSD)'

    def test_none_values_filtered(self):
        """值为 None 的阶被正确过滤."""
        result = classify_dominance(
            {1: 0.01, 2: None, 3: None},
            {1: 0.60, 2: 0.50, 3: None},
        )
        assert result.label == '≺ (FSD)'


class TestClassificationResult:
    """ClassificationResult @dataclass 冒烟测试."""

    def test_smoke_defaults(self):
        """默认构造——effect_size_slot=None."""
        cr = ClassificationResult(label='=')
        assert cr.label == '='
        assert cr.effect_size_slot is None

    def test_smoke_effect_size_slot_mutable(self):
        """frozen=False 允许后赋值 effect_size_slot."""
        cr = ClassificationResult(label='≻ (FSD)')
        cr.effect_size_slot = 'CLES=0.62'
        assert cr.effect_size_slot == 'CLES=0.62'

    def test_smoke_all_labels(self):
        """所有已定义标签均可构造."""
        labels = [
            '≻ (FSD)', '≻ (SSD)', '≻ (TSD)',
            '≺ (FSD)', '≺ (SSD)', '≺ (TSD)',
            '×(FSD)', '×(SSD)', '×(TSD)',
            '×?(FSD)', '×?(SSD)', '×?(TSD)',
            '=', 'err',
        ]
        for label in labels:
            cr = ClassificationResult(label=label)
            assert cr.label == label
