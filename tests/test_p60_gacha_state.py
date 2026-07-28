"""P60 块 1：GachaState.acquired 等价性 + 序列化。"""
import pytest
from gacha_simulator.core.state import GachaState


def test_add_card_increments():
    state = GachaState()
    assert state.add_card("diluc") == 1
    assert state.add_card("diluc") == 2
    assert state.get_card_count("diluc") == 2


def test_get_card_count_unknown_is_zero():
    state = GachaState()
    assert state.get_card_count("nonexistent") == 0


def test_total_holding():
    state = GachaState()
    state.add_card("diluc")
    state.add_card("diluc")
    assert state.total_holding("diluc", {"diluc": 3}) == 5  # 3 + 2
    assert state.total_holding("jean", {"jean": 1}) == 1     # 1 + 0


def test_clone_copies_acquired():
    state = GachaState()
    state.add_card("diluc")
    clone = state.clone()
    assert clone.get_card_count("diluc") == 1
    clone.add_card("diluc")
    # 修改克隆不影响原对象
    assert state.get_card_count("diluc") == 1
    assert clone.get_card_count("diluc") == 2


def test_acquired_default_empty():
    """GachaState 默认 acquired 为空 dict。"""
    state = GachaState()
    assert state.acquired == {}
    assert state.get_card_count("any") == 0


def test_pity_counters_deleted():
    """pity_counters 字段已删除。"""
    state = GachaState()
    assert not hasattr(state, 'pity_counters')
