"""P60 块 2：PityState 序列化往返 + 旧格式自动升级。"""
import pytest
from gacha_simulator.core.pity import PityState


def test_new_format_roundtrip():
    state = PityState()
    state.incr("ssr_soft", "counter")
    state.incr("ssr_soft", "counter")
    state.set("rotating", "guaranteed", True)

    d = state.to_dict()
    restored = PityState.from_dict(d)

    assert restored.get("ssr_soft", "counter") == 2
    assert restored.get("rotating", "guaranteed") is True


def test_old_format_auto_upgrade():
    """旧序列化格式 {"counters": {"ssr_soft": 89}} 自动升级。"""
    old_data = {"counters": {"ssr_soft": 89, "ssr_hard": 10}}
    state = PityState.from_dict(old_data)

    assert state.get("ssr_soft", "counter") == 89
    assert state.get("ssr_hard", "counter") == 10
    # 升级后 to_dict 输出新格式
    new_d = state.to_dict()
    assert "data" in new_d
    assert "counters" not in new_d


def test_clone_is_deep():
    state = PityState()
    state.incr("bh1", "counter")
    clone = state.clone()
    clone.incr("bh1", "counter")
    assert state.get("bh1", "counter") == 1
    assert clone.get("bh1", "counter") == 2


def test_get_default():
    state = PityState()
    assert state.get("nonexistent", "counter") is None
    assert state.get("nonexistent", "counter", 0) == 0
