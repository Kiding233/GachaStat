"""P60 块 2：PityState 序列化往返（P81 B9 起不再支持旧格式自动升级）。"""
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


def test_old_format_no_longer_supported():
    """P81 B9：P60 之前的 {"counters": {...}} 旧格式不再自动升级，读取为空状态。

    本测试原为 test_old_format_auto_upgrade（断言旧格式被升级）。升级分支已删除，
    故改为**显式断言旧格式不再生效**：保留这条记录是为了让「旧格式不受支持」有据
    可查，而不是让它随分支一起静默消失（同 P81 §9.7 关于静默跳过测试的教训）。
    """
    old_data = {"counters": {"ssr_soft": 89, "ssr_hard": 10}}
    state = PityState.from_dict(old_data)

    assert state.get("ssr_soft", "counter") is None
    assert state.get("ssr_hard", "counter") is None
    new_d = state.to_dict()
    assert "data" in new_d
    assert new_d["data"] == {}


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
