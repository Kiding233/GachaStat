"""P60 块 1：GachaState.acquired 等价性 + 序列化。（P63: add_card 返回类型适配）"""
import pytest
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.overflow import OverflowBand


def test_add_card_increments():
    """P63: add_card 不传 bands 时返回 {}（dict），但仍正确递增计数。"""
    state = GachaState()
    assert state.add_card("diluc") == {}
    assert state.get_card_count("diluc") == 1
    assert state.add_card("diluc") == {}
    assert state.get_card_count("diluc") == 2


def test_add_card_with_overflow_bands():
    """P63: 传入 overflow_bands 时返回溢出资源。"""
    state = GachaState()
    bands = [OverflowBand(1, 1, {"gem": 10})]
    result = state.add_card("diluc", path="draw",
                            overflow_bands=bands, initial_counts={})
    assert result == {"gem": 10}
    assert state.get_card_count("diluc") == 1

    # 第二次获得——无匹配段，返回 {}
    result2 = state.add_card("diluc", path="draw",
                             overflow_bands=bands, initial_counts={})
    assert result2 == {}


def test_add_card_acquired_by_path():
    """P63: acquired_by_path 正确记录路径切片。"""
    state = GachaState()
    state.add_card("diluc", path="draw")
    state.add_card("diluc", path="draw")
    state.add_card("diluc", path="milestone_gift")
    assert state.acquired_by_path["diluc"] == {"draw": 2, "milestone_gift": 1}


def test_add_card_no_initial_counts_raises():
    """P63: 传了 bands 但不传 initial_counts → ValueError。"""
    state = GachaState()
    bands = [OverflowBand(1, None, {"gem": 40})]
    with pytest.raises(ValueError, match="initial_counts"):
        state.add_card("diluc", overflow_bands=bands)


def test_get_card_count_unknown_is_zero():
    state = GachaState()
    assert state.get_card_count("nonexistent") == 0


def test_total_holding():
    state = GachaState()
    state.add_card("diluc")
    state.add_card("diluc")
    assert state.total_holding("diluc", {"diluc": 3}) == 5  # 3 + 2
    assert state.total_holding("jean", {"jean": 1}) == 1     # 1 + 0


def test_total_holding_with_initial_counts():
    """P63: initial_counts 正确参与 total_holding 定位——不误判为首次。"""
    state = GachaState()
    bands = [OverflowBand(1, 1, {"gem": 10}),
             OverflowBand(2, None, {"star": 5})]
    # 模拟：初始持有 3 张，第一次抽到 → total_holding=4
    result = state.add_card("X", path="draw",
                            overflow_bands=bands,
                            initial_counts={"X": 3})
    assert result == {"star": 5}  # 命中 [2,∞)，非 [1,1]
    assert state.total_holding("X", {"X": 3}) == 4


def test_clone_copies_acquired():
    state = GachaState()
    state.add_card("diluc")
    clone = state.clone()
    assert clone.get_card_count("diluc") == 1
    clone.add_card("diluc")
    # 修改克隆不影响原对象
    assert state.get_card_count("diluc") == 1
    assert clone.get_card_count("diluc") == 2


def test_clone_copies_acquired_by_path():
    """P63: clone() 深拷贝 acquired_by_path。"""
    state = GachaState()
    state.add_card("diluc", path="draw")
    state.add_card("diluc", path="milestone_gift")
    clone = state.clone()
    assert clone.acquired_by_path == {"diluc": {"draw": 1, "milestone_gift": 1}}
    # 修改克隆不影响原对象
    clone.add_card("diluc", path="draw")
    assert state.acquired_by_path["diluc"]["draw"] == 1
    assert clone.acquired_by_path["diluc"]["draw"] == 2


def test_acquired_default_empty():
    """GachaState 默认 acquired 为空 dict。"""
    state = GachaState()
    assert state.acquired == {}
    assert state.get_card_count("any") == 0


def test_acquired_by_path_default_empty():
    """P63: GachaState 默认 acquired_by_path 为空 dict。"""
    state = GachaState()
    assert state.acquired_by_path == {}


def test_pity_counters_deleted():
    """pity_counters 字段已删除。"""
    state = GachaState()
    assert not hasattr(state, 'pity_counters')
