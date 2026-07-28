"""P63：溢出分段表测试——match_overflow_bands + expand_sugar_to_bands。

替代旧 test_pool_bonus.py（compute_bonus_resources 已废弃）。
"""

import pytest
from gacha_simulator.core.overflow import (
    OverflowBand,
    match_overflow_bands,
    expand_sugar_to_bands,
)


# ══════════════════════════════════════════════════════════════════
# match_overflow_bands 边界用例（MATCH-1 ~ MATCH-10）
# ══════════════════════════════════════════════════════════════════

def test_match_empty_bands():
    """MATCH-1: 空 bands——无规则即无产出"""
    assert match_overflow_bands([], 1) == {}


def test_match_single_infinite_band_n1():
    """MATCH-2: 单段恒真表 [1,∞)——n=1 命中"""
    bands = [OverflowBand(1, None, {"gem": 40})]
    assert match_overflow_bands(bands, 1) == {"gem": 40}


def test_match_single_infinite_band_n5():
    """MATCH-3: 恒真表 n=5 仍命中"""
    bands = [OverflowBand(1, None, {"gem": 40})]
    assert match_overflow_bands(bands, 5) == {"gem": 40}


def test_match_single_infinite_band_n100():
    """MATCH-4: 恒真表 n=100 仍命中"""
    bands = [OverflowBand(1, None, {"gem": 40})]
    assert match_overflow_bands(bands, 100) == {"gem": 40}


def test_match_three_segment_middle():
    """MATCH-5: 三段表中段命中"""
    bands = [
        OverflowBand(1, 1, {"A": 10}),
        OverflowBand(2, 7, {"B": 10}),
        OverflowBand(8, None, {"C": 25}),
    ]
    assert match_overflow_bands(bands, 3) == {"B": 10}


def test_match_gap_no_hit():
    """MATCH-6: 区间不完备——[2,7] 无段，落在间隙"""
    bands = [
        OverflowBand(1, 1, {"A": 10}),
        OverflowBand(8, None, {"C": 25}),
    ]
    assert match_overflow_bands(bands, 3) == {}


def test_match_unordered_input():
    """MATCH-7: bands 乱序——验证匹配不依赖输入顺序"""
    bands = [
        OverflowBand(8, None, {"C": 25}),
        OverflowBand(1, 1, {"A": 10}),
    ]
    assert match_overflow_bands(bands, 1) == {"A": 10}


def test_match_at_upper_bound():
    """MATCH-8: n=2 命中 [1,2] 上界"""
    bands = [
        OverflowBand(1, 2, {"A": 10}),
        OverflowBand(3, 3, {"B": 20}),
    ]
    assert match_overflow_bands(bands, 2) == {"A": 10}


def test_match_exact_single_point():
    """MATCH-9: n=3 命中 [3,3] 精确单点"""
    bands = [
        OverflowBand(1, 2, {"A": 10}),
        OverflowBand(3, 3, {"B": 20}),
    ]
    assert match_overflow_bands(bands, 3) == {"B": 20}


def test_match_beyond_last_finite():
    """MATCH-10: n=6 超出最后一个段且该段非无穷"""
    bands = [OverflowBand(1, 5, {"A": 10})]
    assert match_overflow_bands(bands, 6) == {}


# ══════════════════════════════════════════════════════════════════
# expand_sugar_to_bands 语法糖展开（SUGAR-1 ~ SUGAR-5）
# ══════════════════════════════════════════════════════════════════

def test_sugar_first_time_only():
    """SUGAR-1: 仅首次获得"""
    bands = expand_sugar_to_bands(first_time_bonus={"gem": 10})
    assert len(bands) == 1
    assert bands[0].min == 1
    assert bands[0].max == 1
    assert bands[0].resources == {"gem": 10}


def test_sugar_excess_only():
    """SUGAR-2: 仅满突后"""
    bands = expand_sugar_to_bands(
        excess_bonus={"threshold": 7, "resources": {"star": 25}}
    )
    assert len(bands) == 1
    assert bands[0].min == 7
    assert bands[0].max is None
    assert bands[0].resources == {"star": 25}


def test_sugar_nth_only():
    """SUGAR-3: 仅第 N 次"""
    bands = expand_sugar_to_bands(nth_time_bonus={3: {"token": 20}})
    assert len(bands) == 1
    assert bands[0].min == 3
    assert bands[0].max == 3
    assert bands[0].resources == {"token": 20}


def test_sugar_first_plus_excess():
    """SUGAR-4: 首次+满突——中间 [2,6] 不存空段"""
    bands = expand_sugar_to_bands(
        first_time_bonus={"A": 10},
        excess_bonus={"threshold": 7, "resources": {"A": 25}},
    )
    assert len(bands) == 2
    # 验证 match 行为等价
    assert match_overflow_bands(bands, 1) == {"A": 10}
    assert match_overflow_bands(bands, 3) == {}     # 间隙
    assert match_overflow_bands(bands, 7) == {"A": 25}
    assert match_overflow_bands(bands, 10) == {"A": 25}


def test_sugar_vs_manual_equivalence():
    """SUGAR-5: 语法糖展开 vs 手写 bands 等价性"""
    sugar = expand_sugar_to_bands(
        first_time_bonus={"gem": 10},
        excess_bonus={"threshold": 7, "resources": {"star": 25}},
    )
    manual = [
        OverflowBand(1, 1, {"gem": 10}),
        OverflowBand(7, None, {"star": 25}),
    ]
    assert len(sugar) == len(manual)
    for sb, mb in zip(sugar, manual):
        assert sb.min == mb.min
        assert sb.max == mb.max
        assert sb.resources == mb.resources


def test_sugar_all_empty_returns_empty():
    """全部语法糖为空 → 返回空列表"""
    bands = expand_sugar_to_bands()
    assert bands == []


def test_sugar_excess_no_resources_skipped():
    """excess_bonus 有 threshold 但无 resources → 跳过"""
    bands = expand_sugar_to_bands(
        excess_bonus={"threshold": 5, "resources": {}}
    )
    assert bands == []


def test_sugar_nth_multiple():
    """多个 nth_time_bonus → 多条 bands"""
    bands = expand_sugar_to_bands(nth_time_bonus={
        2: {"gem": 50},
        5: {"gem": 200},
    })
    assert len(bands) == 2
    assert match_overflow_bands(bands, 2) == {"gem": 50}
    assert match_overflow_bands(bands, 5) == {"gem": 200}
    assert match_overflow_bands(bands, 3) == {}


# ══════════════════════════════════════════════════════════════════
# 语法糖 match 等价性——替代旧 compute_bonus_resources 11 例
# ══════════════════════════════════════════════════════════════════

def test_bonus_first_time_equiv():
    """旧 first_time_bonus 等价——首次获得触发"""
    bands = expand_sugar_to_bands(first_time_bonus={"gem": 50})
    assert match_overflow_bands(bands, 1) == {"gem": 50}


def test_bonus_first_time_not_second_equiv():
    """旧 first_time_bonus 等价——第二次不触发"""
    bands = expand_sugar_to_bands(first_time_bonus={"gem": 50})
    assert match_overflow_bands(bands, 2) == {}


def test_bonus_nth_exact_equiv():
    """旧 nth_time_bonus 等价——第N次触发"""
    bands = expand_sugar_to_bands(nth_time_bonus={3: {"gem": 100}})
    assert match_overflow_bands(bands, 3) == {"gem": 100}


def test_bonus_nth_not_other_equiv():
    """旧 nth_time_bonus 等价——非指定次数不触发"""
    bands = expand_sugar_to_bands(nth_time_bonus={3: {"gem": 100}})
    assert match_overflow_bands(bands, 4) == {}


def test_bonus_nth_multiple_equiv():
    """旧 nth_time_bonus 多 N 等价"""
    bands = expand_sugar_to_bands(nth_time_bonus={
        2: {"gem": 50},
        5: {"gem": 200},
    })
    assert match_overflow_bands(bands, 5) == {"gem": 200}


def test_bonus_excess_above_equiv():
    """旧 excess_bonus 等价——超出阈值触发"""
    bands = expand_sugar_to_bands(
        excess_bonus={"threshold": 5, "resources": {"starlight": 25}}
    )
    assert match_overflow_bands(bands, 8) == {"starlight": 25}


def test_bonus_excess_below_equiv():
    """旧 excess_bonus 等价——未超阈值不触发"""
    bands = expand_sugar_to_bands(
        excess_bonus={"threshold": 5, "resources": {"starlight": 25}}
    )
    assert match_overflow_bands(bands, 4) == {}


def test_bonus_excess_no_threshold_equiv():
    """旧 excess_bonus 等价——默认极高阈值"""
    bands = expand_sugar_to_bands(
        excess_bonus={"threshold": 999999, "resources": {"starlight": 25}}
    )
    # n=6 远低于 999999 ——不命中
    assert match_overflow_bands(bands, 6) == {}


def test_bonus_combined_equiv():
    """旧 combined_bonus 等价——首次和 N 次分别命中"""
    bands = expand_sugar_to_bands(
        first_time_bonus={"gem": 50},
        nth_time_bonus={3: {"gem": 100}},
    )
    assert match_overflow_bands(bands, 1) == {"gem": 50}
    assert match_overflow_bands(bands, 3) == {"gem": 100}


def test_bonus_no_bonus_equiv():
    """旧 no_bonus 等价——无规则卡无论获得几次都无产出"""
    bands = expand_sugar_to_bands()
    assert match_overflow_bands(bands, 1) == {}
    assert match_overflow_bands(bands, 6) == {}


def test_bonus_initial_count_equiv():
    """旧 first_time 含初始持有等价——n>1 不触发 first_time"""
    bands = expand_sugar_to_bands(first_time_bonus={"gem": 50})
    # 初始持有 1 张 → total_holding=2——不应触发 first_time
    assert match_overflow_bands(bands, 2) == {}
