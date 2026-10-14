"""P60 块 1：GachaState.acquired 等价性 + 序列化。（P63: add_card 返回类型适配）"""
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
    result = state.add_card("diluc", path="draw", overflow_bands=bands)
    assert result == {"gem": 10}
    assert state.get_card_count("diluc") == 1

    # 第二次获得——无匹配段，返回 {}
    result2 = state.add_card("diluc", path="draw", overflow_bands=bands)
    assert result2 == {}


def test_add_card_acquired_by_path():
    """P63: acquired_by_path 正确记录路径切片。"""
    state = GachaState()
    state.add_card("diluc", path="draw")
    state.add_card("diluc", path="draw")
    state.add_card("diluc", path="milestone_gift")
    assert state.acquired_by_path["diluc"] == {"draw": 2, "milestone_gift": 1}


def test_add_card_bands_without_initial_counts_uses_state_field():
    """P64 S9-2：原「传了 bands 必须传 initial_counts，否则 ValueError」的守卫**已删除**。

    初始持有升为 `GachaState.initial_counts` 字段（单一真相源），`add_card` 内部
    直接读它，故「只传 bands」不再是错误输入，而是「本场初始持有为空」的正常形态：
    分段表按模拟内获得计数（`total_holding` = 0 + 1）定位，命中 `[1, ∞)`。
    该用例是**行为变更的正断言**（原用例断言 ValueError，其触发条件已不存在）。
    """
    state = GachaState()
    bands = [OverflowBand(1, None, {"gem": 40})]
    assert state.add_card("diluc", overflow_bands=bands) == {"gem": 40}
    assert state.total_holding("diluc") == 1


def test_get_card_count_unknown_is_zero():
    state = GachaState()
    assert state.get_card_count("nonexistent") == 0


def test_total_holding():
    """P64 S9-2：初始持有改读 `state.initial_counts` 字段（形参已移除）。"""
    state = GachaState(initial_counts={"diluc": 3, "jean": 1})
    state.add_card("diluc")
    state.add_card("diluc")
    assert state.total_holding("diluc") == 5  # 3 + 2
    assert state.total_holding("jean") == 1   # 1 + 0


def test_total_holding_with_initial_counts():
    """P63: initial_counts 正确参与 total_holding 定位——不误判为首次。"""
    state = GachaState(initial_counts={"X": 3})
    bands = [OverflowBand(1, 1, {"gem": 10}),
             OverflowBand(2, None, {"star": 5})]
    # 模拟：初始持有 3 张，第一次抽到 → total_holding=4
    result = state.add_card("X", path="draw", overflow_bands=bands)
    assert result == {"star": 5}  # 命中 [2,∞)，非 [1,1]
    assert state.total_holding("X") == 4


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


def test_clone_carries_initial_counts():
    """P64 S9-2（§六「`GachaState.clone()` 保真」）：`initial_counts` 加为字段后，
    `clone()` 必须逐字段带上它。

    `run_simulation` 首行即 `initial_state.clone()`，漏带则每场模拟的
    `state.initial_counts` 恒空、`total_holding` 少算初始持有、P63 溢出分档**静默**
    出错（本项是本次改动唯一的真实行为风险，且失败时不报错）。判据为 int 值浅比较。
    """
    s1 = GachaState(initial_counts={"X": 3})
    s2 = s1.clone()
    assert s2.initial_counts == s1.initial_counts == {"X": 3}
    # 深拷贝语义：改克隆不影响原对象
    s2.initial_counts["X"] = 99
    assert s1.initial_counts == {"X": 3}


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
